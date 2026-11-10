"""Lifecycle of the airport dataset: cache lookup, FAA download, cycle refresh, and stale fallback."""

import asyncio
import io
import logging
import time
from datetime import date
from typing import Awaitable, Callable, Optional

import pandas as pd

from .dataset import AirportDataset
from .nasr import AIRPORT_TABLES, cycle_effective_date, download_archive, extract_tables, previous_cycles
from .storage import ArtifactStore

logger = logging.getLogger(__name__)

# After a failed refresh, keep serving the loaded cycle and wait this long before retrying.
REFRESH_RETRY_SECONDS = 15 * 60
# How many older cycles to look for in the cache when nothing newer can be obtained.
STALE_CYCLES_TO_TRY = 6


class DataUnavailableError(RuntimeError):
    """Raised when no airport data can be downloaded and nothing usable is cached."""


def cache_name(cycle: date, table: str) -> str:
    # The cycle is part of every file name, so tables from different cycles can never be mixed.
    return f"nasr_{cycle.isoformat()}_{table}.parquet"


class AirportRepository:
    """Provides the airport dataset for the NASR cycle currently in effect.

    All three FAA tables are loaded together from the same cycle archive and swapped in as a single
    immutable snapshot, so concurrent tool calls always see a consistent view.
    """

    def __init__(
        self,
        store: ArtifactStore,
        downloader: Callable[[date], Awaitable[bytes]] = download_archive,
        today: Callable[[], date] = date.today,
    ):
        self._store = store
        self._download = downloader
        self._today = today
        self._dataset: Optional[AirportDataset] = None
        self._lock = asyncio.Lock()
        self._last_failure: Optional[float] = None

    @property
    def dataset(self) -> Optional[AirportDataset]:
        """The currently loaded snapshot, without triggering a load (used by health checks)."""
        return self._dataset

    async def get(self) -> AirportDataset:
        target_cycle = cycle_effective_date(self._today())
        if self._is_usable(target_cycle):
            return self._dataset

        async with self._lock:
            # Another request may have completed the load while this one waited for the lock.
            if self._is_usable(target_cycle):
                return self._dataset
            try:
                self._dataset = await self._load_cycle(target_cycle)
                self._last_failure = None
            except Exception:
                self._last_failure = time.monotonic()
                logger.exception("Could not load NASR cycle %s", target_cycle)
                if self._dataset is None:
                    self._dataset = await self._load_latest_cached(target_cycle)
                else:
                    logger.warning("Continuing to serve NASR cycle %s", self._dataset.cycle)
            return self._dataset

    def _is_usable(self, target_cycle: date) -> bool:
        if self._dataset is None:
            return False
        if self._dataset.cycle >= target_cycle:
            return True
        return self._last_failure is not None and time.monotonic() - self._last_failure < REFRESH_RETRY_SECONDS

    async def _load_cycle(self, cycle: date) -> AirportDataset:
        tables = await asyncio.to_thread(self._read_cached_tables, cycle)
        if tables is None:
            archive = await self._download(cycle)
            tables = await asyncio.to_thread(extract_tables, archive)
            await asyncio.to_thread(self._write_cached_tables, cycle, tables)
        dataset = await asyncio.to_thread(AirportDataset.from_tables, cycle, tables)
        logger.info("Loaded NASR cycle %s (%d airports)", cycle, len(dataset.airports))
        return dataset

    async def _load_latest_cached(self, target_cycle: date) -> AirportDataset:
        for cycle in previous_cycles(target_cycle, STALE_CYCLES_TO_TRY):
            tables = await asyncio.to_thread(self._read_cached_tables, cycle)
            if tables is not None:
                logger.warning("Serving stale NASR cycle %s (current cycle is %s)", cycle, target_cycle)
                return await asyncio.to_thread(AirportDataset.from_tables, cycle, tables)
        raise DataUnavailableError(
            f"FAA NASR cycle {target_cycle} could not be downloaded and no cached cycle is available"
        )

    def _read_cached_tables(self, cycle: date) -> Optional[dict[str, pd.DataFrame]]:
        tables = {}
        for table in AIRPORT_TABLES:
            data = self._store.read(cache_name(cycle, table))
            if data is None:
                return None
            tables[table] = pd.read_parquet(io.BytesIO(data))
        return tables

    def _write_cached_tables(self, cycle: date, tables: dict[str, pd.DataFrame]) -> None:
        for table in AIRPORT_TABLES:
            self._store.write(cache_name(cycle, table), tables[table].to_parquet(index=False))
