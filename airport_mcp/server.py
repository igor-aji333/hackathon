import os
import asyncio
from dotenv import load_dotenv

# MUST be called before any other imports read environment variables
load_dotenv()

import logging
from fastmcp import FastMCP
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

from .runway_tool import airport_manager, get_airport_runways
from .runway_end_tool import airport_runway_end_manager, get_airport_runway_ends

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

SERVER_INSTRUCTIONS = """
TOOL SELECTION GUIDE:
- get_airport_runways: Use for physical structural runway data (length, width, surface, lighting).
- get_airport_runway_ends: Use for thresholds, elevations, glide slopes, and alignments.

DOMAIN CONVENTIONS:
- Inputs accept either 3-letter FAA codes (e.g., JFK) or 4-letter ICAO codes (e.g., KJFK).
- Required environment variable for custom storage: AIRPORT_MCP_STORAGE_BACKEND (local, s3, databricks).
"""

mcp = FastMCP("Airport MCP Server", instructions=SERVER_INSTRUCTIONS)

# Register tools with explicit names and capability annotations
mcp.tool(
    name="get_airport_runways",
    annotations={"readOnlyHint": True, "idempotentHint": True}
)(get_airport_runways)

mcp.tool(
    name="get_airport_runway_ends",
    annotations={"readOnlyHint": True, "idempotentHint": True}
)(get_airport_runway_ends)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    mcp_transport: str = "stdio"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8000

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    is_ready = (airport_manager.client.df is not None) and (airport_runway_end_manager.client.df is not None)
    return JSONResponse({
        "status": "healthy" if is_ready else "initializing",
        "service": "airport_mcp",
        "runways_cache_timestamp": airport_manager.client.last_download.isoformat() if airport_manager.client.last_download else None,
        "runway_ends_cache_timestamp": airport_runway_end_manager.client.last_download.isoformat() if airport_runway_end_manager.client.last_download else None
    })

@mcp.custom_route("/", methods=["GET"])
async def root(request: Request) -> RedirectResponse:
    return RedirectResponse(url="/health")

async def pre_warm_caches():
    """Asynchronously pre-warm the data caches on startup."""
    try:
        logger.info("Pre-warming data caches...")
        await airport_manager._prepare_data()
        await airport_runway_end_manager._prepare_data()
        logger.info("Caches successfully pre-warmed.")
    except Exception as e:
        logger.critical(f"Fatal initialization failure: {e}")

if __name__ == "__main__":
    settings = Settings()
    platform_port = os.getenv("DATABRICKS_APP_PORT") or os.getenv("PORT")
    
    # Load the data before starting the server
    asyncio.run(pre_warm_caches())
    
    # Start the server
    if platform_port:
        mcp.run(transport="streamable-http", host="0.0.0.0", port=int(platform_port))
    elif settings.mcp_transport == "streamable-http":
        mcp.run(transport="streamable-http", host=settings.mcp_host, port=settings.mcp_port)
    elif settings.mcp_transport == "sse":
        mcp.run(transport="sse", host=settings.mcp_host, port=settings.mcp_port)
    else:
        mcp.run(transport="stdio")
        
