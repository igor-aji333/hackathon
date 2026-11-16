"""Cross-cutting plumbing shared by the tool scripts.

A tool script declares its own parameters and calls into `queries`; everything that is
identical for every tool lives here. `ToolContext` is what each script receives instead
of the repository, so no tool has to know how a NASR cycle is loaded or how domain
errors map onto the MCP error vocabulary.
"""

import asyncio
from typing import Any, Callable, TypeVar

from fastmcp.exceptions import ToolError

from .. import queries
from ..repository import AirportRepository, DataUnavailableError

T = TypeVar("T")

#: Annotations every tool carries: reads published data, no side effects, closed world.
READ_ONLY = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False}

#: FAA location identifiers are 3-4 alphanumerics ('JFK', '1N7'); ICAO codes add a prefix
#: ('KJFK', 'PANC'). Surrounding whitespace is tolerated and trimmed downstream.
AIRPORT_ID_PATTERN = r"^\s*[A-Za-z0-9]{3,4}\s*$"


class ToolContext:
    """Dataset access and error translation for the tool scripts."""

    def __init__(self, repository: AirportRepository) -> None:
        self._repository = repository

    async def run(self, query: Callable[..., T], *args: Any) -> T:
        """Run a `queries` function against the current cycle in a worker thread.

        Data outages and domain errors become `ToolError`, which MCP clients see as
        `isError: true` results carrying a message that says what to do next.
        """
        try:
            dataset = await self._repository.get()
        except DataUnavailableError as exc:
            raise ToolError(
                f"FAA airport data is temporarily unavailable ({exc}). Retry in a few minutes."
            ) from exc

        try:
            return await asyncio.to_thread(query, dataset, *args)
        except queries.AirportNotFoundError as exc:
            raise ToolError(
                f"{exc}. Check the code, or call airport_search with the airport's name or city to find it."
            ) from exc
        except queries.InvalidQueryError as exc:
            raise ToolError(str(exc)) from exc
