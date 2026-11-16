"""`airport_find_nearby` — airports near a point whose runways meet given requirements."""

from typing import Annotated, Optional

from fastmcp import FastMCP
from pydantic import Field

from .. import queries
from ..models import NearbyAirportsResult
from .common import AIRPORT_ID_PATTERN, READ_ONLY, ToolContext


def register(mcp: FastMCP, context: ToolContext) -> None:
    @mcp.tool(name="airport_find_nearby", title="Find nearby airports with suitable runways",
              annotations=READ_ONLY)
    async def airport_find_nearby(
        airport_id: Annotated[Optional[str], Field(
            description="Center the search on this airport (FAA or ICAO code). Omit when giving coordinates.",
            pattern=AIRPORT_ID_PATTERN,
        )] = None,
        latitude: Annotated[Optional[float], Field(
            description="Center latitude in decimal degrees. Use with longitude instead of airport_id.",
            ge=-90, le=90,
        )] = None,
        longitude: Annotated[Optional[float], Field(
            description="Center longitude in decimal degrees (negative = west).", ge=-180, le=180,
        )] = None,
        radius_nm: Annotated[float, Field(description="Search radius in nautical miles.", gt=0, le=500)] = 50,
        min_runway_length_ft: Annotated[Optional[int], Field(
            description="Require at least one runway this long, in feet.", ge=0,
        )] = None,
        paved_only: Annotated[bool, Field(description="Require the qualifying runway to be paved.")] = False,
        require_ils: Annotated[bool, Field(
            description="Require the qualifying runway to have an ILS or LOC/GS approach on either end.",
        )] = False,
        public_use_only: Annotated[bool, Field(description="Exclude private-use airports.")] = True,
        limit: Annotated[int, Field(description="Maximum airports to return.", ge=1, le=50)] = 10,
    ) -> NearbyAirportsResult:
        """Find operational airports near an airport or coordinates whose runways meet given requirements.

        Use for diversion and alternate planning or regional comparisons, e.g. "nearest public airport to
        KDEN with a paved runway of at least 8,000 ft and an ILS". A single runway must satisfy all runway
        criteria together. Results are nearest first, with great-circle distance (nm), initial true bearing
        from the origin, and the runways that qualify. Helipads never qualify; the origin airport is excluded.
        """
        return await context.run(
            queries.find_nearby_airports, airport_id, latitude, longitude, radius_nm,
            min_runway_length_ft, paved_only, require_ils, public_use_only, limit,
        )
