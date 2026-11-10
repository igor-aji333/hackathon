import io
import zipfile
from datetime import date

import pandas as pd
import pytest

from airport_mcp.repository import AirportRepository
from airport_mcp.storage import LocalArtifactStore

CURRENT_CYCLE = date(2026, 10, 29)

APT_BASE = pd.DataFrame(
    [
        # ARPT_ID, ICAO_ID, ARPT_NAME, CITY, STATE, SITE_TYPE, STATUS, USE, ELEV, LAT, LON
        ("JFK", "KJFK", "JOHN F KENNEDY INTL", "NEW YORK", "NY", "A", "O", "PU", "13", "40.63992805", "-73.77869222"),
        ("LGA", "KLGA", "LAGUARDIA", "NEW YORK", "NY", "A", "O", "PU", "20.6", "40.77724", "-73.87261"),
        ("NY01", None, "PRIVATE STRIP", "QUEENS", "NY", "A", "O", "PR", "10", "40.70", "-73.80"),
        ("CLX", None, "CLOSED FLD", "QUEENS", "NY", "A", "CP", "PU", "10", "40.68", "-73.75"),
        ("JRA", "KJRA", "WEST 30TH ST", "NEW YORK", "NY", "H", "O", "PU", "7", "40.75", "-74.00"),
        ("ANC", "PANC", "TED STEVENS ANCHORAGE INTL", "ANCHORAGE", "AK", "A", "O", "PU", "151.4", "61.17408472", "-149.9981375"),
    ],
    columns=["ARPT_ID", "ICAO_ID", "ARPT_NAME", "CITY", "STATE_CODE", "SITE_TYPE_CODE", "ARPT_STATUS",
             "FACILITY_USE_CODE", "ELEV", "LAT_DECIMAL", "LONG_DECIMAL"],
).assign(COUNTRY_CODE="US")

APT_RWY = pd.DataFrame(
    [
        ("JFK", "04L/22R", "12079", "200", "CONC", "EXCELLENT", "HIGH"),
        ("JFK", "13R/31L", "14511", "200", "CONC", "EXCELLENT", "HIGH"),
        ("JFK", "H1", "60", "60", "CONC", None, None),
        ("LGA", "04/22", "7001", "150", "ASPH-CONC", "GOOD", "HIGH"),
        ("NY01", "18/36", "2500", "60", "TURF", "FAIR", None),
        ("CLX", "01/19", "5000", "100", "ASPH", "GOOD", "MED"),
        ("JRA", "H1", "50", "50", "CONC", None, None),
        ("ANC", "07L/25R", "10600", "150", "ASPH", "GOOD", "HIGH"),
    ],
    columns=["ARPT_ID", "RWY_ID", "RWY_LEN", "RWY_WIDTH", "SURFACE_TYPE_CODE", "COND", "RWY_LGT_CODE"],
)

APT_RWY_END = pd.DataFrame(
    [
        ("JFK", "04L/22R", "04L", "12.5", "31", "ILS/DME", "MALSR"),
        ("JFK", "04L/22R", "22R", "11.1", "211", "ILS", "ALSF2"),
        ("JFK", "13R/31L", "13R", "11.0", "121", None, None),
        ("JFK", "13R/31L", "31L", "12.0", "301", None, None),
        ("JFK", "H1", "H1", "13", None, None, None),
        ("LGA", "04/22", "04", "20.0", "44", "LOC/DME", None),
        ("LGA", "04/22", "22", "20.6", "224", "ILS", "MALSR"),
        ("ANC", "07L/25R", "07L", "127.7", "90", "ILS/DME", "MALSR"),
    ],
    columns=["ARPT_ID", "RWY_ID", "RWY_END_ID", "RWY_END_ELEV", "TRUE_ALIGNMENT", "ILS_TYPE",
             "APCH_LGT_SYSTEM_CODE"],
).assign(VISUAL_GLIDE_PATH_ANGLE="3.00")


def make_archive(tables: dict[str, pd.DataFrame]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, df in tables.items():
            zf.writestr(f"{name}.csv", df.to_csv(index=False))
    return buffer.getvalue()


FIXTURE_ARCHIVE = make_archive({"APT_RWY_END": APT_RWY_END, "APT_BASE": APT_BASE, "APT_RWY": APT_RWY})


class FakeDownloader:
    def __init__(self, archive: bytes = FIXTURE_ARCHIVE, fail: bool = False):
        self.archive = archive
        self.fail = fail
        self.requested: list[date] = []

    async def __call__(self, cycle: date) -> bytes:
        self.requested.append(cycle)
        if self.fail:
            raise ConnectionError("FAA unreachable")
        return self.archive


@pytest.fixture
def store(tmp_path):
    return LocalArtifactStore(tmp_path)


@pytest.fixture
def downloader():
    return FakeDownloader()


@pytest.fixture
def repository(store, downloader):
    return AirportRepository(store, downloader=downloader, today=lambda: date(2026, 11, 10))
