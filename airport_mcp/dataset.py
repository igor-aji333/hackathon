"""Typed, query-ready snapshot of one FAA NASR cycle's airport tables."""

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

import pandas as pd

PAVED_SURFACES = frozenset({"CONC", "ASPH", "PEM", "TRTD", "TREATED"})
# Precision approaches with vertical guidance (localizer-only, LDA, and SDF are excluded).
ILS_TYPES = frozenset({"ILS", "ILS/DME", "LOC/GS"})
_HELIPAD_ID = re.compile(r"^H\d")

# FAA airport names abbreviate common words; map the spelled-out forms users type onto them.
_SEARCH_SYNONYMS = {
    "INTERNATIONAL": "INTL",
    "REGIONAL": "RGNL",
    "MUNICIPAL": "MUNI",
    "MEMORIAL": "MEML",
    "COUNTY": "CO",
    "FIELD": "FLD",
    "METROPOLITAN": "METRO",
    "SAINT": "ST",
}
_SEARCH_STOPWORDS = frozenset({"AIRPORT", "AIRFIELD", "THE", "OF"})

AIRPORT_COLUMNS = [
    "ARPT_ID", "ICAO_ID", "ARPT_NAME", "CITY", "STATE_CODE", "COUNTRY_CODE", "SITE_TYPE_CODE",
    "ARPT_STATUS", "FACILITY_USE_CODE", "ELEV", "LAT_DECIMAL", "LONG_DECIMAL",
]
RUNWAY_COLUMNS = ["ARPT_ID", "RWY_ID", "RWY_LEN", "RWY_WIDTH", "SURFACE_TYPE_CODE", "COND", "RWY_LGT_CODE"]
RUNWAY_END_COLUMNS = [
    "ARPT_ID", "RWY_ID", "RWY_END_ID", "LAT_DECIMAL", "LONG_DECIMAL", "RWY_END_ELEV", "TRUE_ALIGNMENT",
    "ILS_TYPE", "APCH_LGT_SYSTEM_CODE", "VISUAL_GLIDE_PATH_ANGLE", "VGSI_CODE", "TDZ_ELEV",
    "DISPLACED_THR_LEN", "TKOF_RUN_AVBL", "LNDG_DIST_AVBL",
]


def search_tokens(text: Optional[str]) -> list[str]:
    """Normalize free text into upper-case tokens comparable with FAA naming conventions."""
    if not text:
        return []
    cleaned = re.sub(r"[^A-Z0-9 ]", " ", str(text).upper().replace("'", ""))
    tokens = (_SEARCH_SYNONYMS.get(token, token) for token in cleaned.split())
    return [token for token in tokens if token not in _SEARCH_STOPWORDS]


def is_paved(surface_code: Optional[str]) -> bool:
    """Surface codes may be compound (e.g. 'ASPH-CONC'); any paved component counts."""
    if not isinstance(surface_code, str):
        return False
    return any(part in PAVED_SURFACES for part in re.split(r"[-/]", surface_code.upper()))


def _select(table: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    # reindex tolerates columns the FAA drops in a future schema revision (they become NaN).
    return table.reindex(columns=columns).copy()


def _to_numeric(df: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")


def _normalize_ids(series: pd.Series) -> pd.Series:
    return series.str.strip().str.upper()


@dataclass(frozen=True)
class AirportDataset:
    cycle: date
    airports: pd.DataFrame  # one row per facility, indexed by FAA location identifier
    runways: pd.DataFrame  # indexed by FAA identifier; several rows per airport
    runway_ends: pd.DataFrame  # indexed by FAA identifier; two rows per runway
    icao_to_faa: dict[str, str]

    @classmethod
    def from_tables(cls, cycle: date, tables: dict[str, pd.DataFrame]) -> "AirportDataset":
        airports = _select(tables["APT_BASE"], AIRPORT_COLUMNS)
        airports["ARPT_ID"] = _normalize_ids(airports["ARPT_ID"])
        airports["ICAO_ID"] = _normalize_ids(airports["ICAO_ID"])
        airports = airports.dropna(subset=["ARPT_ID"]).drop_duplicates("ARPT_ID")
        _to_numeric(airports, ["ELEV", "LAT_DECIMAL", "LONG_DECIMAL"])

        runways = _select(tables["APT_RWY"], RUNWAY_COLUMNS)
        runways["ARPT_ID"] = _normalize_ids(runways["ARPT_ID"])
        runways = runways.dropna(subset=["ARPT_ID", "RWY_ID"])
        _to_numeric(runways, ["RWY_LEN", "RWY_WIDTH"])
        runways["IS_HELIPAD"] = runways["RWY_ID"].str.match(_HELIPAD_ID).fillna(False).astype(bool)
        runways["IS_PAVED"] = runways["SURFACE_TYPE_CODE"].map(is_paved).astype(bool)

        ends = _select(tables["APT_RWY_END"], RUNWAY_END_COLUMNS)
        ends["ARPT_ID"] = _normalize_ids(ends["ARPT_ID"])
        ends = ends.dropna(subset=["ARPT_ID", "RWY_ID"])
        _to_numeric(ends, [
            "LAT_DECIMAL", "LONG_DECIMAL", "RWY_END_ELEV", "TRUE_ALIGNMENT", "VISUAL_GLIDE_PATH_ANGLE",
            "TDZ_ELEV", "DISPLACED_THR_LEN", "TKOF_RUN_AVBL", "LNDG_DIST_AVBL",
        ])

        ils_runways = set(
            ends.loc[ends["ILS_TYPE"].isin(ILS_TYPES), ["ARPT_ID", "RWY_ID"]].itertuples(index=False, name=None)
        )
        runways["HAS_ILS"] = [
            (airport, runway) in ils_runways for airport, runway in zip(runways["ARPT_ID"], runways["RWY_ID"])
        ]

        runway_stats = runways.groupby("ARPT_ID")["RWY_LEN"].agg(RUNWAY_COUNT="size", LONGEST_RUNWAY_FT="max")
        airports = airports.join(runway_stats, on="ARPT_ID")
        airports["RUNWAY_COUNT"] = airports["RUNWAY_COUNT"].fillna(0).astype(int)
        airports["SEARCH_TEXT"] = [
            " " + " ".join(search_tokens(name) + search_tokens(city) + [faa, icao if isinstance(icao, str) else ""]) + " "
            for name, city, faa, icao in zip(
                airports["ARPT_NAME"], airports["CITY"], airports["ARPT_ID"], airports["ICAO_ID"]
            )
        ]

        icao_to_faa = dict(
            airports.dropna(subset=["ICAO_ID"])[["ICAO_ID", "ARPT_ID"]].itertuples(index=False, name=None)
        )

        def indexed(df: pd.DataFrame) -> pd.DataFrame:
            # Stable sort keeps FAA row order within an airport while enabling fast .loc lookups.
            return df.set_index("ARPT_ID").sort_index(kind="stable")

        return cls(
            cycle=cycle,
            airports=indexed(airports),
            runways=indexed(runways),
            runway_ends=indexed(ends),
            icao_to_faa=icao_to_faa,
        )

    def resolve_identifier(self, identifier: str) -> Optional[str]:
        """Map an FAA location identifier or ICAO code to the FAA identifier, or None if unknown."""
        ident = identifier.strip().upper()
        if ident in self.airports.index:
            return ident
        if ident in self.icao_to_faa:
            return self.icao_to_faa[ident]
        # Users often prefix 'K' to small airports that have no published ICAO code.
        if len(ident) == 4 and ident.startswith("K") and ident[1:] in self.airports.index:
            return ident[1:]
        return None

    def rows_for(self, table: pd.DataFrame, faa_id: str) -> pd.DataFrame:
        if faa_id not in table.index:
            return table.iloc[0:0]
        return table.loc[[faa_id]]
