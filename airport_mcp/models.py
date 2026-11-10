"""Structured tool outputs. Field descriptions are published to agents as the tools' output schema."""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

FacilityType = Literal["airport", "heliport", "seaplane_base", "ultralight", "gliderport", "balloonport"]
FacilityStatus = Literal["operational", "closed_indefinitely", "closed_permanently"]


class AirportSummary(BaseModel):
    faa_id: str = Field(description="FAA location identifier, e.g. 'JFK' or '1N7'.")
    icao_id: Optional[str] = Field(None, description="ICAO code, e.g. 'KJFK' or 'PANC'. Null for many small fields.")
    name: Optional[str] = Field(None, description="Official FAA facility name (FAA abbreviations such as INTL, RGNL, MUNI).")
    city: Optional[str] = None
    state: Optional[str] = Field(None, description="Two-letter state or territory code.")
    country: Optional[str] = Field(None, description="Two-letter country code (almost always 'US').")
    facility_type: Optional[FacilityType] = None
    status: Optional[FacilityStatus] = None
    public_use: Optional[bool] = Field(None, description="True if open to the public; False for private-use facilities.")
    elevation_ft: Optional[float] = Field(None, description="Airport reference elevation, feet above mean sea level.")
    latitude: Optional[float] = Field(None, description="Airport reference point latitude, decimal degrees.")
    longitude: Optional[float] = Field(None, description="Airport reference point longitude, decimal degrees (negative = west).")


class AirportMatch(AirportSummary):
    runway_count: int = Field(description="Number of landing surfaces (runways, helipads, water lanes).")
    longest_runway_ft: Optional[int] = Field(None, description="Length of the longest landing surface, feet.")


class AirportSearchResult(BaseModel):
    data_cycle: date = Field(description="Effective date of the FAA NASR data cycle used.")
    total_matches: int = Field(description="Matches before applying `limit`.")
    airports: list[AirportMatch] = Field(description="Best matches first: exact codes, then larger operational airports.")


class RunwayEnd(BaseModel):
    end_id: str = Field(description="Runway end designator, e.g. '04L'. Approaches land toward this heading.")
    latitude: Optional[float] = Field(None, description="Threshold latitude, decimal degrees.")
    longitude: Optional[float] = Field(None, description="Threshold longitude, decimal degrees.")
    elevation_ft: Optional[float] = Field(None, description="Threshold elevation, feet MSL.")
    touchdown_zone_elevation_ft: Optional[float] = Field(None, description="Highest elevation in the first 3,000 ft of landing surface, feet MSL.")
    true_alignment_deg: Optional[int] = Field(None, description="True (not magnetic) heading of the runway centerline from this end, degrees.")
    ils_type: Optional[str] = Field(None, description="Instrument landing system, e.g. ILS, ILS/DME, LOC/GS, LOC/DME, LOCALIZER, LDA, SDF. Null if none.")
    approach_lighting: Optional[str] = Field(None, description="Approach light system code, e.g. MALSR, ALSF2, ODALS, SSALR. Null if none.")
    visual_glide_slope_indicator: Optional[str] = Field(None, description="VGSI code, e.g. P4L = 4-box PAPI on left side, V2L = 2-box VASI on left.")
    glide_path_angle_deg: Optional[float] = Field(None, description="Visual glide path angle, degrees.")
    displaced_threshold_ft: Optional[int] = Field(None, description="Length of displaced threshold, feet.")
    takeoff_run_available_ft: Optional[int] = Field(None, description="Declared TORA, feet.")
    landing_distance_available_ft: Optional[int] = Field(None, description="Declared LDA, feet.")


class Runway(BaseModel):
    runway_id: str = Field(description="Runway designator, e.g. '04L/22R'; helipads are 'H1', 'H2', ...")
    length_ft: Optional[int] = None
    width_ft: Optional[int] = None
    surface: Optional[str] = Field(None, description="FAA surface code(s): CONC, ASPH, PEM (part paved), TURF, DIRT, GRVL, WATER, MATS, ... Compound values like 'ASPH-CONC'.")
    is_paved: bool = Field(description="True if any surface component is CONC, ASPH, PEM, or treated.")
    is_helipad: bool
    condition: Optional[str] = Field(None, description="Pavement condition: EXCELLENT, GOOD, FAIR, POOR, or FAILED.")
    edge_lighting: Optional[str] = Field(None, description="Runway edge light intensity: HIGH, MED, LOW, NSTD (non-standard), PERI (perimeter), FLD (flood), STRB.")
    has_ils: bool = Field(description="True if either end has an ILS or LOC/GS approach.")
    ends: list[RunwayEnd] = Field(description="Both runway ends (one for helipads).")


class AirportRunways(BaseModel):
    data_cycle: date = Field(description="Effective date of the FAA NASR data cycle used.")
    airport: AirportSummary
    total_runways: int = Field(description="Landing surfaces at the airport before filters were applied.")
    runways: list[Runway] = Field(description="Runways that satisfy the requested filters, in FAA order.")


class NearbyAirport(AirportSummary):
    distance_nm: float = Field(description="Great-circle distance from the origin, nautical miles.")
    bearing_deg: int = Field(description="Initial true bearing from the origin to this airport, degrees.")
    qualifying_runways: list[str] = Field(description="Runway IDs at this airport that meet all runway criteria.")
    longest_qualifying_runway_ft: Optional[int] = None


class NearbyAirportsResult(BaseModel):
    data_cycle: date = Field(description="Effective date of the FAA NASR data cycle used.")
    origin_airport: Optional[AirportSummary] = Field(None, description="Origin airport, when the search was centered on one.")
    origin_latitude: float
    origin_longitude: float
    radius_nm: float
    total_found: int = Field(description="Qualifying airports within the radius before applying `limit`.")
    airports: list[NearbyAirport] = Field(description="Qualifying airports, nearest first.")
