"""Download and unpack the FAA NASR 28-day airport subscription (APT_CSV archive)."""

import io
import logging
import zipfile
from datetime import date, timedelta
from pathlib import PurePosixPath

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

NASR_CYCLE_DAYS = 28
# NASR subscriptions follow the 28-day AIRAC schedule; any past effective date anchors the sequence.
NASR_CYCLE_ANCHOR = date(2025, 1, 23)
NASR_ARCHIVE_BASE_URL = "https://nfdc.faa.gov/webContent/28DaySub/extra/"
DOWNLOAD_TIMEOUT_SECONDS = 120.0

AIRPORT_TABLES = ("APT_BASE", "APT_RWY", "APT_RWY_END")

# Spelled out rather than using strftime("%b"), which depends on the process locale.
_MONTH_ABBREVIATIONS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def cycle_effective_date(on: date) -> date:
    """Return the effective date of the NASR cycle in force on the given day."""
    elapsed_cycles = (on - NASR_CYCLE_ANCHOR).days // NASR_CYCLE_DAYS
    return NASR_CYCLE_ANCHOR + timedelta(days=elapsed_cycles * NASR_CYCLE_DAYS)


def previous_cycles(cycle: date, count: int) -> list[date]:
    return [cycle - timedelta(days=NASR_CYCLE_DAYS * i) for i in range(1, count + 1)]


def archive_url(cycle: date) -> str:
    stamp = f"{cycle.day:02d}_{_MONTH_ABBREVIATIONS[cycle.month - 1]}_{cycle.year}"
    return f"{NASR_ARCHIVE_BASE_URL}{stamp}_APT_CSV.zip"


async def download_archive(cycle: date) -> bytes:
    url = archive_url(cycle)
    logger.info("Downloading FAA NASR airport archive %s", url)
    async with httpx.AsyncClient(follow_redirects=False, timeout=DOWNLOAD_TIMEOUT_SECONDS) as client:
        response = await client.get(url)
        response.raise_for_status()
    return response.content


def extract_tables(archive: bytes, tables: tuple[str, ...] = AIRPORT_TABLES) -> dict[str, pd.DataFrame]:
    """Read the named CSV tables (all columns as strings) from a NASR APT_CSV archive."""
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        # Match on exact file name: a substring test would let "APT_RWY" match "APT_RWY_END.csv".
        members = {PurePosixPath(name).stem: name for name in zf.namelist() if name.endswith(".csv")}
        missing = [t for t in tables if t not in members]
        if missing:
            raise ValueError(f"NASR archive is missing tables: {', '.join(missing)}")
        return {t: pd.read_csv(io.BytesIO(zf.read(members[t])), dtype=str) for t in tables}
