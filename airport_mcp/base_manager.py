from abc import ABC, abstractmethod
from datetime import datetime
import logging
from typing import Any, Optional
import pandas as pd

from .faa_data_client import (
    CACHE_EXPIRATION_DAYS,
    FAADataService,
    StorageConfig,
    StorageManager,
)

logger = logging.getLogger(__name__)


class BaseAirportManager(ABC):
    """Abstract base manager handling shared FAA cycle lifecycle, pruning, and indexing."""

    def __init__(self, dataset_name: str, key_columns: list[str]):
        storage = StorageManager(StorageConfig.from_env())
        self.client = FAADataService(storage, dataset_name)
        self.key_columns = key_columns

    @staticmethod
    def normalize_identifier(ident: str) -> str:
        """Normalize 4-letter ICAO codes (e.g., 'KJFK') to 3-letter FAA codes ('JFK') when applicable."""
        ident_upper = ident.upper()
        if ident_upper.startswith("K") and len(ident_upper) == 4:
            return ident_upper[1:]
        return ident_upper

    async def _prepare_data(self) -> None:
        """Ensure NASR data is loaded, pruned of sparse values, and indexed by ARPT_ID."""
        if (
            self.client.df is None
            or self.client.last_download is None
            or (datetime.now() - self.client.last_download).days > CACHE_EXPIRATION_DAYS
        ):
            await self.client.initialize()
            df = self.client.df

            # Drop rows where all columns outside the primary keys are missing
            cols_to_check = [c for c in df.columns if c not in self.key_columns]
            if cols_to_check:
                df = df.dropna(axis=0, how="all", subset=cols_to_check)

            if "ARPT_ID" in df.columns:
                df["ARPT_ID"] = df["ARPT_ID"].str.upper()
                df = df.set_index("ARPT_ID")
            self.client.df = df
            
    def _resolve_airport_records(self, ident: str) -> tuple[Optional[str], Optional[pd.DataFrame]]:
        """Resolve either 3-letter FAA or 4-letter ICAO index rows from cached DataFrame."""
        df = self.client.df
        ident_upper = ident.upper()
        norm_ident = self.normalize_identifier(ident)
        lookup_id = norm_ident if norm_ident in df.index else ident_upper

        if lookup_id not in df.index:
            return None, None

        return lookup_id, df.loc[[lookup_id]].copy()

    @abstractmethod
    async def query(self, ident: str) -> Optional[dict[str, Any]]:
        """Query airport specifications by FAA or ICAO identifier."""
        raise NotImplementedError
    
