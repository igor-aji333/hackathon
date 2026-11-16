"""`airport_search` — resolve an airport name, city or code to FAA and ICAO identifiers."""

from typing import Annotated, Optional

from fastmcp import FastMCP
from pydantic import Field

from .. import queries
from ..models import AirportSearchResult
from .common import READ_ONLY, ToolContext


def register(mcp: FastMCP, context: ToolContext) -> None:
    @mcp.tool(name="airport_search", title="Search US airports", annotations=READ_ONLY)
    async def airport_search(
        query: Annotated[str, Field(
            description="Airport name, city, or code, e.g. 'Boston Logan', 'Seattle-Tacoma', 'Anchorage', 'KDEN'.",
            min_length=2, max_length=100,
        )],
        state: Annotated[Optional[str], Field(
            description="Optional two-letter US state or territory code to restrict results, e.g. 'TX'.",
            pattern=r"^[A-Za-z]{2}$",
        )] = None,
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
        return await context.run(
            queries.search_airports, query, state, include_all_facility_types, limit
        )
