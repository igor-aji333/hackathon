"""MCP tool definitions: agent-facing names, descriptions, and validated parameters.

Each tool answers a complete user goal in one call and returns a typed Pydantic model, so clients
receive both structured content and a published output schema. Domain errors are raised as
`ToolError`, which MCP clients see as `isError: true` results with an actionable message.
"""

import asyncio
from typing import Annotated, Optional

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from . import queries
from .dataset import AirportDataset
from .models import AirportRunways, AirportSearchResult, NearbyAirportsResult
from .repository import AirportRepository, DataUnavailableError

READ_ONLY = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False}

AirportId = Annotated[
    str,
    Field(
        description=(
            "FAA location identifier (e.g. 'JFK', 'ANC', '1N7') or ICAO code (e.g. 'KJFK', 'PANC'). "
            "If you only know the airport's name or city, call airport_search first."
        ),
        pattern=r"^\s*[A-Za-z0-9]{3,4}\s*$",
    ),
]
StateCode = Annotated[
    Optional[str],
    Field(description="Optional two-letter US state or territory code to restrict results, e.g. 'TX'.",
          pattern=r"^[A-Za-z]{2}$"),
]


def register_tools(mcp: FastMCP, repository: AirportRepository) -> None:
    async def load_dataset() -> AirportDataset:
        try:
            return await repository.get()
        except DataUnavailableError as exc:
            raise ToolError(f"FAA airport data is temporarily unavailable ({exc}). Retry in a few minutes.") from exc

    async def run_query(fn, *args, **kwargs):
        dataset = await load_dataset()
        try:
            return await asyncio.to_thread(fn, dataset, *args, **kwargs)
        except queries.AirportNotFoundError as exc:
            raise ToolError(
                f"{exc}. Check the code, or call airport_search with the airport's name or city to find it."
            ) from exc
        except queries.InvalidQueryError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(name="airport_search", title="Search US airports", annotations=READ_ONLY)
    async def airport_search(
        query: Annotated[str, Field(
            description="Airport name, city, or code, e.g. 'Boston Logan', 'Seattle-Tacoma', 'Anchorage', 'KDEN'.",
            min_length=2, max_length=100,
        )],
        state: StateCode = None,
        include_all_facility_types: Annotated[bool, Field(
            description="Also return heliports, seaplane bases, gliderports, etc. Default: airports only.",
        )] = False,
        limit: Annotated[int, Field(description="Maximum airports to return.", ge=1, le=50)] = 10,
    ) -> AirportSearchResult:
        """Find US airports by name, city, or code and get their FAA and ICAO identifiers.

        Use this first whenever the user refers to an airport by name ("Chicago O'Hare", "Detroit Metro")
        or you are unsure of its code; the other tools require an identifier. Matching is case-insensitive
        and word-prefix based, and understands FAA abbreviations (International=INTL, Regional=RGNL,
        Municipal=MUNI). Results are ranked: exact code matches first, then operational airports with ICAO
        codes and longer runways. Each match includes location, elevation, runway count, and longest runway.
        """
        return await run_query(queries.search_airports, query, state, include_all_facility_types, limit)

    @mcp.tool(name="airport_get_runways", title="Get an airport's runways and runway ends", annotations=READ_ONLY)
    async def airport_get_runways(
        airport_id: AirportId,
        min_length_ft: Annotated[Optional[int], Field(
            description="Only return runways at least this long, in feet.", ge=0,
        )] = None,
        paved_only: Annotated[bool, Field(
            description="Only return paved runways (concrete, asphalt, partially paved, or treated).",
        )] = False,
        include_helipads: Annotated[bool, Field(description="Include helipads (IDs H1, H2, ...).")] = True,
    ) -> AirportRunways:
        """Get every runway at one US airport, with full detail for both runway ends, in a single call.

        Per runway: length, width, surface, paved/helipad flags, pavement condition, edge lighting, ILS
        availability. Per runway end: threshold coordinates and elevation, touchdown-zone elevation, true
        alignment, ILS type, approach lighting (e.g. MALSR), PAPI/VASI, glide path angle, displaced threshold,
        and declared distances (TORA, LDA). Use for any question about a specific airport's runways or runway
        ends: longest runway, which end is highest, which runways have an ILS, approach lights on 22R.
        Filters narrow the list; `total_runways` always gives the unfiltered count.
        Not for finding an airport by name (use airport_search) or comparing airports in an area
        (use airport_find_nearby).
        """
        return await run_query(
            queries.get_airport_runways, airport_id, min_length_ft, paved_only, include_helipads
        )

    @mcp.tool(name="airport_find_nearby", title="Find nearby airports with suitable runways", annotations=READ_ONLY)
    async def airport_find_nearby(
        airport_id: Annotated[Optional[str], Field(
            description="Center the search on this airport (FAA or ICAO code). Omit when giving coordinates.",
            pattern=r"^\s*[A-Za-z0-9]{3,4}\s*$",
        )] = None,
        latitude: Annotated[Optional[float], Field(
            description="Center latitude in decimal degrees. Use with longitude instead of airport_id.", ge=-90, le=90,
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
        return await run_query(
            queries.find_nearby_airports, airport_id, latitude, longitude, radius_nm,
            min_runway_length_ft, paved_only, require_ils, public_use_only, limit,
        )
