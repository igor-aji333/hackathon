"""Server entry point: wires the FAA data repository to MCP tools and selects a transport.

Run with `python -m airport_mcp.server` or `fastmcp run airport_mcp/server.py:mcp`.
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

from .config import Settings
from .repository import AirportRepository
from .storage import create_store
from .tools import register_tools

logger = logging.getLogger(__name__)

SERVER_INSTRUCTIONS = """\
Official FAA NASR data for US airports (all 50 states and territories), refreshed every 28-day cycle.

Typical workflow:
1. If the user names an airport rather than giving a code, call airport_search to get its identifier.
2. Call airport_get_runways for anything about one airport's runways or runway ends.
3. Call airport_find_nearby to find or compare airports around a location by runway capability.

Identifiers: FAA codes ('JFK', 'ANC') and ICAO codes ('KJFK', 'PANC') are both accepted.
Units: lengths and elevations in feet; distances in nautical miles; alignments and bearings are true degrees.
Scope: static airport infrastructure only. No weather, NOTAMs, flight schedules, or non-US airports.
"""


def create_server(repository: Optional[AirportRepository] = None) -> FastMCP:
    if repository is None:
        repository = AirportRepository(create_store(Settings()))

    @asynccontextmanager
    async def prewarm(server: FastMCP):
        # Load data before serving so the first tool call is fast; on failure, tools retry lazily.
        try:
            await repository.get()
        except Exception:
            logger.exception("Airport data pre-warm failed; will retry on first tool call")
        yield {}

    mcp = FastMCP(
        "Airport MCP Server",
        instructions=SERVER_INSTRUCTIONS,
        lifespan=prewarm,
        mask_error_details=True,
    )
    register_tools(mcp, repository)

    @mcp.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> JSONResponse:
        dataset = repository.dataset
        return JSONResponse({
            "status": "ready" if dataset else "initializing",
            "service": "airport_mcp",
            "data_cycle": dataset.cycle.isoformat() if dataset else None,
            "airports_loaded": len(dataset.airports) if dataset else 0,
        })

    @mcp.custom_route("/", methods=["GET"])
    async def root(request: Request) -> RedirectResponse:
        return RedirectResponse(url="/health")

    return mcp


mcp = create_server()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    settings = Settings()
    if settings.platform_port:
        mcp.run(transport="streamable-http", host="0.0.0.0", port=settings.platform_port)
    elif settings.mcp_transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport=settings.mcp_transport, host=settings.mcp_host, port=settings.mcp_port)


if __name__ == "__main__":
    main()
