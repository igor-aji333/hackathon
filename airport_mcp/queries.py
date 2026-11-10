"""Agent-facing queries over an AirportDataset: pure functions with no I/O or MCP concerns."""

from typing import Any, Optional

import numpy as np
import pandas as pd

from .dataset import AirportDataset, search_tokens
from .models import (
    AirportMatch,
    AirportRunways,
    AirportSearchResult,
    AirportSummary,
    NearbyAirport,
    NearbyAirportsResult,
    Runway,
    RunwayEnd,
)

FACILITY_TYPES = {
    "A": "airport", "H": "heliport", "C": "seaplane_base",
    "U": "ultralight", "G": "gliderport", "B": "balloonport",
}
FACILITY_STATUSES = {"O": "operational", "CI": "closed_indefinitely", "CP": "closed_permanently"}
EARTH_RADIUS_NM = 3440.065


class AirportNotFoundError(LookupError):
    def __init__(self, identifier: str):
        self.identifier = identifier
        super().__init__(f"No US airport found with identifier '{identifier}'")


class InvalidQueryError(ValueError):
    """The request is well-typed but cannot be answered as asked."""


def _float(value: Any) -> Optional[float]:
    return None if pd.isna(value) else float(value)


def _int(value: Any) -> Optional[int]:
    return None if pd.isna(value) else int(round(float(value)))


def _text(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    return value.strip() or None


def resolve_airport(dataset: AirportDataset, identifier: str) -> str:
    faa_id = dataset.resolve_identifier(identifier)
    if faa_id is None:
        raise AirportNotFoundError(identifier)
    return faa_id


def _summary_fields(faa_id: str, row: pd.Series) -> dict[str, Any]:
    use_code = _text(row["FACILITY_USE_CODE"])
    return {
        "faa_id": faa_id,
        "icao_id": _text(row["ICAO_ID"]),
        "name": _text(row["ARPT_NAME"]),
        "city": _text(row["CITY"]),
        "state": _text(row["STATE_CODE"]),
        "country": _text(row["COUNTRY_CODE"]),
        "facility_type": FACILITY_TYPES.get(row["SITE_TYPE_CODE"]),
        "status": FACILITY_STATUSES.get(row["ARPT_STATUS"]),
        "public_use": None if use_code is None else use_code == "PU",
        "elevation_ft": _float(row["ELEV"]),
        "latitude": _float(row["LAT_DECIMAL"]),
        "longitude": _float(row["LONG_DECIMAL"]),
    }


def airport_summary(dataset: AirportDataset, faa_id: str) -> AirportSummary:
    return AirportSummary(**_summary_fields(faa_id, dataset.airports.loc[faa_id]))


def search_airports(
    dataset: AirportDataset,
    query: str,
    state: Optional[str] = None,
    include_all_facility_types: bool = False,
    limit: int = 10,
) -> AirportSearchResult:
    airports = dataset.airports
    code = query.strip().upper()
    exact_code = pd.Series(airports.index == code, index=airports.index) | (airports["ICAO_ID"] == code)

    tokens = search_tokens(query)
    if tokens:
        # Prefix match per token, so "Detroit Metro" finds "DETROIT METRO WAYNE COUNTY".
        mask = pd.Series(True, index=airports.index)
        for token in tokens:
            mask &= airports["SEARCH_TEXT"].str.contains(" " + token, regex=False)
        mask |= exact_code
    else:
        mask = exact_code.copy()
    if state:
        mask &= airports["STATE_CODE"] == state.strip().upper()
    if not include_all_facility_types:
        mask &= (airports["SITE_TYPE_CODE"] == "A") | exact_code

    matches = airports[mask]
    ranking = pd.DataFrame({
        "exact": exact_code[mask],
        "operational": matches["ARPT_STATUS"] == "O",
        "has_icao": matches["ICAO_ID"].notna(),
        "longest": matches["LONGEST_RUNWAY_FT"].fillna(0),
    })
    ordered = ranking.sort_values(
        ["exact", "operational", "has_icao", "longest"], ascending=False, kind="stable"
    ).index[:limit]

    results = [
        AirportMatch(
            **_summary_fields(faa_id, airports.loc[faa_id]),
            runway_count=int(airports.at[faa_id, "RUNWAY_COUNT"]),
            longest_runway_ft=_int(airports.at[faa_id, "LONGEST_RUNWAY_FT"]),
        )
        for faa_id in ordered
    ]
    return AirportSearchResult(data_cycle=dataset.cycle, total_matches=int(mask.sum()), airports=results)


def _runway_end(row: pd.Series) -> RunwayEnd:
    return RunwayEnd(
        end_id=str(row["RWY_END_ID"]).strip(),
        latitude=_float(row["LAT_DECIMAL"]),
        longitude=_float(row["LONG_DECIMAL"]),
        elevation_ft=_float(row["RWY_END_ELEV"]),
        touchdown_zone_elevation_ft=_float(row["TDZ_ELEV"]),
        true_alignment_deg=_int(row["TRUE_ALIGNMENT"]),
        ils_type=_text(row["ILS_TYPE"]),
        approach_lighting=_text(row["APCH_LGT_SYSTEM_CODE"]),
        visual_glide_slope_indicator=_text(row["VGSI_CODE"]),
        glide_path_angle_deg=_float(row["VISUAL_GLIDE_PATH_ANGLE"]),
        displaced_threshold_ft=_int(row["DISPLACED_THR_LEN"]),
        takeoff_run_available_ft=_int(row["TKOF_RUN_AVBL"]),
        landing_distance_available_ft=_int(row["LNDG_DIST_AVBL"]),
    )


def get_airport_runways(
    dataset: AirportDataset,
    identifier: str,
    min_length_ft: Optional[int] = None,
    paved_only: bool = False,
    include_helipads: bool = True,
) -> AirportRunways:
    faa_id = resolve_airport(dataset, identifier)
    runways = dataset.rows_for(dataset.runways, faa_id)
    total = len(runways)

    keep = np.ones(total, dtype=bool)
    if min_length_ft is not None:
        keep &= (runways["RWY_LEN"] >= min_length_ft).to_numpy()
    if paved_only:
        keep &= runways["IS_PAVED"].to_numpy()
    if not include_helipads:
        keep &= ~runways["IS_HELIPAD"].to_numpy()
    runways = runways[keep]

    ends_by_runway: dict[str, list[RunwayEnd]] = {}
    for _, end_row in dataset.rows_for(dataset.runway_ends, faa_id).iterrows():
        ends_by_runway.setdefault(end_row["RWY_ID"], []).append(_runway_end(end_row))

    return AirportRunways(
        data_cycle=dataset.cycle,
        airport=airport_summary(dataset, faa_id),
        total_runways=total,
        runways=[
            Runway(
                runway_id=row["RWY_ID"],
                length_ft=_int(row["RWY_LEN"]),
                width_ft=_int(row["RWY_WIDTH"]),
                surface=_text(row["SURFACE_TYPE_CODE"]),
                is_paved=bool(row["IS_PAVED"]),
                is_helipad=bool(row["IS_HELIPAD"]),
                condition=_text(row["COND"]),
                edge_lighting=_text(row["RWY_LGT_CODE"]),
                has_ils=bool(row["HAS_ILS"]),
                ends=ends_by_runway.get(row["RWY_ID"], []),
            )
            for _, row in runways.iterrows()
        ],
    )


def _distance_and_bearing(
    lat: float, lon: float, lats: np.ndarray, lons: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Great-circle distance (nm) and initial true bearing (deg) from one point to many."""
    phi1, lambda1 = np.radians(lat), np.radians(lon)
    phi2, lambda2 = np.radians(lats), np.radians(lons)
    d_phi, d_lambda = phi2 - phi1, lambda2 - lambda1
    a = np.sin(d_phi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(d_lambda / 2) ** 2
    distance = 2 * EARTH_RADIUS_NM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    bearing = np.degrees(np.arctan2(
        np.sin(d_lambda) * np.cos(phi2),
        np.cos(phi1) * np.sin(phi2) - np.sin(phi1) * np.cos(phi2) * np.cos(d_lambda),
    ))
    return distance, (bearing + 360.0) % 360.0


def find_nearby_airports(
    dataset: AirportDataset,
    origin_identifier: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    radius_nm: float = 50.0,
    min_runway_length_ft: Optional[int] = None,
    paved_only: bool = False,
    require_ils: bool = False,
    public_use_only: bool = True,
    limit: int = 10,
) -> NearbyAirportsResult:
    origin_summary: Optional[AirportSummary] = None
    origin_faa_id: Optional[str] = None
    if origin_identifier:
        if latitude is not None or longitude is not None:
            raise InvalidQueryError("Provide either an origin airport or latitude/longitude, not both.")
        origin_faa_id = resolve_airport(dataset, origin_identifier)
        origin_summary = airport_summary(dataset, origin_faa_id)
        latitude, longitude = origin_summary.latitude, origin_summary.longitude
        if latitude is None or longitude is None:
            raise InvalidQueryError(f"Airport '{origin_identifier}' has no published coordinates.")
    elif latitude is None or longitude is None:
        raise InvalidQueryError("Provide an origin airport identifier, or both latitude and longitude.")

    runways = dataset.runways
    qualifies = ~runways["IS_HELIPAD"]
    if min_runway_length_ft is not None:
        qualifies &= runways["RWY_LEN"] >= min_runway_length_ft
    if paved_only:
        qualifies &= runways["IS_PAVED"]
    if require_ils:
        qualifies &= runways["HAS_ILS"]
    qualifying = runways[qualifies]

    candidates = dataset.airports[
        dataset.airports.index.isin(qualifying.index.unique())
        & (dataset.airports["ARPT_STATUS"] == "O")
        & dataset.airports["LAT_DECIMAL"].notna()
        & dataset.airports["LONG_DECIMAL"].notna()
    ]
    if public_use_only:
        candidates = candidates[candidates["FACILITY_USE_CODE"] == "PU"]
    if origin_faa_id is not None:
        candidates = candidates[candidates.index != origin_faa_id]

    distance, bearing = _distance_and_bearing(
        latitude, longitude, candidates["LAT_DECIMAL"].to_numpy(), candidates["LONG_DECIMAL"].to_numpy()
    )
    within = distance <= radius_nm
    order = np.argsort(distance[within], kind="stable")
    nearby_ids = candidates.index[within][order]
    nearby_distance = distance[within][order]
    nearby_bearing = bearing[within][order]

    # Aggregate runway details only for the airports actually returned.
    returned = qualifying[qualifying.index.isin(nearby_ids[:limit])]
    by_airport = returned.groupby(level=0).agg(runway_ids=("RWY_ID", list), longest=("RWY_LEN", "max"))

    airports = [
        NearbyAirport(
            **_summary_fields(faa_id, candidates.loc[faa_id]),
            distance_nm=round(float(dist), 1),
            bearing_deg=int(round(float(brg))) % 360,
            qualifying_runways=by_airport.at[faa_id, "runway_ids"],
            longest_qualifying_runway_ft=_int(by_airport.at[faa_id, "longest"]),
        )
        for faa_id, dist, brg in zip(nearby_ids[:limit], nearby_distance[:limit], nearby_bearing[:limit])
    ]
    return NearbyAirportsResult(
        data_cycle=dataset.cycle,
        origin_airport=origin_summary,
        origin_latitude=latitude,
        origin_longitude=longitude,
        radius_nm=radius_nm,
        total_found=len(nearby_ids),
        airports=airports,
    )
