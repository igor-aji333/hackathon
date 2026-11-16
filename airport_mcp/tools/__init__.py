"""MCP tool registry: one script per agent-facing tool.

Every module in `TOOL_MODULES` owns exactly one tool — its name, title, description,
validated parameters and output model — and exposes `register(mcp, context)`. Adding a
tool means adding a script here and one entry to the tuple; nothing else changes.

Registration order is the order tools are listed to clients, so it follows the workflow
the server's instructions describe: resolve an identifier, then ask about one airport,
then compare airports in an area.
"""

from fastmcp import FastMCP

from ..repository import AirportRepository
from . import airport_find_nearby, airport_get_runways, airport_search
from .common import ToolContext

TOOL_MODULES = (airport_search, airport_get_runways, airport_find_nearby)

__all__ = ["TOOL_MODULES", "ToolContext", "register_tools"]


def register_tools(mcp: FastMCP, repository: AirportRepository) -> None:
    """Register every tool script against one shared data-access context."""
    context = ToolContext(repository)
    for module in TOOL_MODULES:
        module.register(mcp, context)
