"""Exercise the tools end-to-end through an in-memory MCP client, as an agent would call them."""

import pytest
from fastmcp import Client

from airport_mcp.repository import AirportRepository
from airport_mcp.server import create_server
from conftest import FakeDownloader


@pytest.fixture
async def client(repository):
    async with Client(create_server(repository)) as mcp_client:
        yield mcp_client


async def call(client, tool, **arguments):
    return await client.call_tool(tool, arguments, raise_on_error=False)


async def test_tools_publish_output_schemas(client):
    tools = {tool.name: tool for tool in await client.list_tools()}

    assert set(tools) == {"airport_search", "airport_get_runways", "airport_find_nearby"}
    assert all(tool.output_schema for tool in tools.values())
    assert all(tool.annotations.read_only_hint for tool in tools.values())


@pytest.mark.parametrize(
    ("query", "expected_faa_id"),
    [
        ("Kennedy International Airport", "JFK"),  # synonym + stopword handling
        ("ted stevens anchorage", "ANC"),
        ("PANC", "ANC"),  # exact ICAO code
        ("lga", "LGA"),  # exact FAA code, lower case
    ],
)
async def test_search_finds_airport(client, query, expected_faa_id):
    result = await call(client, "airport_search", query=query)

    assert result.structured_content["airports"][0]["faa_id"] == expected_faa_id


async def test_search_excludes_heliports_unless_requested(client):
    default = await call(client, "airport_search", query="New York")
    everything = await call(client, "airport_search", query="New York", include_all_facility_types=True)

    assert "JRA" not in [a["faa_id"] for a in default.structured_content["airports"]]
    assert "JRA" in [a["faa_id"] for a in everything.structured_content["airports"]]


async def test_search_state_filter(client):
    result = await call(client, "airport_search", query="intl", state="AK")

    assert [a["faa_id"] for a in result.structured_content["airports"]] == ["ANC"]


async def test_get_runways_by_non_k_icao_code_returns_typed_nested_data(client):
    result = await call(client, "airport_get_runways", airport_id="PANC")
    data = result.structured_content

    assert data["airport"]["faa_id"] == "ANC"
    assert data["airport"]["icao_id"] == "PANC"
    assert data["airport"]["name"] == "TED STEVENS ANCHORAGE INTL"
    runway = data["runways"][0]
    assert runway["length_ft"] == 10600
    assert runway["has_ils"] is True
    assert runway["ends"][0]["true_alignment_deg"] == 90
    assert runway["ends"][0]["approach_lighting"] == "MALSR"


async def test_get_runways_filters_keep_unfiltered_total(client):
    result = await call(client, "airport_get_runways", airport_id="KJFK", min_length_ft=13000)
    data = result.structured_content

    assert data["total_runways"] == 3
    assert [r["runway_id"] for r in data["runways"]] == ["13R/31L"]


async def test_get_runways_can_exclude_helipads(client):
    result = await call(client, "airport_get_runways", airport_id="JFK", include_helipads=False)

    assert [r["runway_id"] for r in result.structured_content["runways"]] == ["04L/22R", "13R/31L"]


async def test_unknown_airport_is_a_protocol_error_pointing_to_search(client):
    result = await call(client, "airport_get_runways", airport_id="ZZZZ")

    assert result.is_error
    assert "airport_search" in result.content[0].text


async def test_malformed_identifier_is_rejected(client):
    result = await call(client, "airport_get_runways", airport_id="J!K")

    assert result.is_error


async def test_find_nearby_applies_status_use_and_runway_criteria(client):
    result = await call(client, "airport_find_nearby", airport_id="JFK", radius_nm=30)
    data = result.structured_content

    # JFK is the origin; NY01 is private; CLX is closed; JRA has only a helipad.
    assert [a["faa_id"] for a in data["airports"]] == ["LGA"]
    assert 8 < data["airports"][0]["distance_nm"] < 10
    assert data["airports"][0]["bearing_deg"] in range(300, 340)


async def test_find_nearby_by_coordinates_with_ils_requirement(client):
    result = await call(
        client, "airport_find_nearby", latitude=40.7, longitude=-73.8, require_ils=True, public_use_only=False
    )

    assert {a["faa_id"] for a in result.structured_content["airports"]} == {"JFK", "LGA"}


async def test_find_nearby_requires_an_origin(client):
    result = await call(client, "airport_find_nearby", radius_nm=20)

    assert result.is_error
    assert "latitude" in result.content[0].text


async def test_data_outage_is_reported_as_retryable_error(store):
    offline = AirportRepository(store, downloader=FakeDownloader(fail=True))
    async with Client(create_server(offline)) as client:
        result = await call(client, "airport_search", query="JFK")

    assert result.is_error
    assert "temporarily unavailable" in result.content[0].text
