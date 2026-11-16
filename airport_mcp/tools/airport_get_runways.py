"""`airport_get_runways` — every runway and runway end at one airport, in a single call."""

from typing import Annotated, Optional

from fastmcp import FastMCP
from pydantic import Field

from .. import queries
from ..models import AirportRunways
from .common import AIRPORT_ID_PATTERN, READ_ONLY, ToolContext

AirportId = Annotated[
    str,
    Field(
        description=(
            "FAA location identifier (e.g. 'JFK', 'ANC', '1N7') or ICAO code (e.g. 'KJFK', 'PANC'). "
            "If you only know the airport's name or city, call airport_search first."
        ),
        pattern=AIRPORT_ID_PATTERN,
    ),
]


def register(mcp: FastMCP, context: ToolContext) -> None:
    @mcp.tool(name="airport_get_runways", title="Get an airport's runways and runway ends",
              annotations=READ_ONLY)
    async def airport_get_runways(
        airport_id: AirportId,
        min_length_ft: Annotated[Optional[int], Field(
            description="Only return runways at least this long, in feet.", ge=0,
        )] = None,
        paved_only: Annotated[bool, Field(
            description="Only return paved runways (concrete, asphalt, or partially bitumen-bound).",
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
        return await context.run(
            queries.get_airport_runways, airport_id, min_length_ft, paved_only, include_helipads
        )
