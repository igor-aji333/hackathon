# Usage Instructions

## Available Tools

### 1. `airport_get_runways(icao_or_faa_id)`
Query an airport by ICAO or FAA identifier to get runway structural information[cite: 1].

**Parameters:**
- `icao_or_faa_id` (string): The 3-letter FAA identifier (e.g., 'JFK') or 4-letter ICAO identifier (e.g., 'KJFK') of the US airport[cite: 1].
- `limit` (int, optional): Maximum number of runways to return (default: 20)[cite: 1].
- `offset` (int, optional): Pagination offset (default: 0)[cite: 1].
- `response_format` (string, optional): Format of the response, 'json' or 'markdown' (default: 'json')[cite: 1].

**Returns:** 
JSON object (or markdown string) containing:
- `total_count`: Total number of runways[cite: 1]
- `count`: Number of runways in current page[cite: 1]
- `offset`: Current pagination offset[cite: 1]
- `has_more`: Boolean indicating if more items exist[cite: 1]
- `next_offset`: Offset for the next page if `has_more` is true[cite: 1]
- `icao_id`: Airport identifier[cite: 1]
- `name`: Airport name[cite: 1]
- `city`: City location[cite: 1]
- `state`: State code[cite: 1]
- `country`: Country code[cite: 1]
- `items`: Array of runway objects with:
  - `rwy_id`: Runway identifier[cite: 1]
  - `length_ft`: Runway length in feet[cite: 1]
  - `width_ft`: Runway width in feet[cite: 1]
  - `surface`: Surface type code[cite: 1]
  - `condition`: Condition code[cite: 1]
  - `latitude_1`: Coordinate pair latitude[cite: 1]
  - `longitude_1`: Coordinate pair longitude[cite: 1]
  - `lights`: Lighting code[cite: 1]

### 2. `airport_get_runway_ends(icao_or_faa_id)`
Query an airport to get comprehensive runway end information (thresholds, elevations, alignments, glideslopes, etc.)[cite: 1].

**Parameters:**
- `icao_or_faa_id` (string): The 3-letter FAA identifier (e.g., 'JFK') or 4-letter ICAO identifier (e.g., 'KJFK') of the target US airport[cite: 1].
- `limit` (int, optional): Maximum number of runway ends to return (default: 20)[cite: 1].
- `offset` (int, optional): Pagination offset (default: 0)[cite: 1].
- `response_format` (string, optional): Format of the response, 'json' or 'markdown' (default: 'json')[cite: 1].

**Returns:** 
JSON object (or markdown string) containing:
- `total_count`: Total number of runway ends[cite: 1]
- `count`: Number of runway ends in current page[cite: 1]
- `offset`: Current pagination offset[cite: 1]
- `has_more`: Boolean indicating if more items exist[cite: 1]
- `next_offset`: Offset for the next page if `has_more` is true[cite: 1]
- `icao_id`: Airport identifier[cite: 1]
- `city`: City location[cite: 1]
- `state`: State code[cite: 1]
- `country`: Country code[cite: 1]
- `items`: Array of runway end objects with:
  - `rwy_id`: Parent Runway identifier[cite: 1]
  - `rwy_end_id`: Runway End identifier[cite: 1]
  - `latitude`: Runway end latitude[cite: 1]
  - `longitude`: Runway end longitude[cite: 1]
  - `elevation_ft`: Elevation in feet[cite: 1]
  - `true_alignment`: True alignment[cite: 1]
  - `ils_type`: ILS Type[cite: 1]
  - `approach_light_system`: Approach light system code[cite: 1]
  - `visual_glide_path_angle`: Glide path angle[cite: 1]

## Examples

### Query JFK Airport Runways
```json
{
  "tool": "airport_get_runways",
  "parameters": {
    "icao_or_faa_id": "JFK",
    "response_format": "json"
  }
}

```

### Query Los Angeles International Airport Runway Ends

```json
{
  "tool": "airport_get_runway_ends",
  "parameters": {
    "icao_or_faa_id": "KLAX",
    "response_format": "json"
  }
}

```

## Sample Response (airport_get_runways)

```json
{
  "total_count": 4,
  "count": 4,
  "offset": 0,
  "has_more": false,
  "icao_id": "JFK",
  "name": "JOHN F KENNEDY INTL",
  "city": "NEW YORK",
  "state": "NY",
  "country": "US",
  "items": [
    {
      "rwy_id": "04L/22R",
      "length_ft": 12079.0,
      "width_ft": 200.0,
      "surface": "ASPH-CONC-G",
      "condition": "GOOD",
      "latitude_1": "40-38-09.9575N",
      "longitude_1": "073-47-21.7225W",
      "lights": "HIGH"
    }
  ]
}

```

## Error Handling

If airport is not found:

```json
{
  "isError": true,
  "error": "Airport identifier 'XXX' not found."
}

```

## CLI Testing

Test the server directly from command line:

```bash
# Run server in stdio mode
python -m airport_mcp.server

# Or use with stdio transport
python -c "import asyncio; from airport_mcp.airport_get_runways import airport_get_runways; print(asyncio.run(airport_get_runways('JFK')))"

```

### Using with MCP Inspector

```bash
# Install MCP inspector
npm install -g @modelcontextprotocol/inspector

# Run inspector pointing to your server
mcp-inspector python -m airport_mcp.server

```

## MCP Client Configuration

### Opencode Configuration

Add to `mcp.json`:

```json
{
  "mcpServers": {
    "airport": {
      "command": "python",
      "args": ["-m", "airport_mcp.server"],
      "cwd": "/path/to/hackathon"
    }
  }
}

```

### HTTP Transport Configuration

For HTTP-based MCP clients, you can run the server with SSE:

```bash
# Run with HTTP transport (requires fastmcp[ssestream])
MCP_TRANSPORT=streamable-http python -m airport_mcp.server

```

Configure in opencode `.opencode/mcp.json`:

```json
{
  "mcpServers": {
    "airport": {
      "url": "http://localhost:8000/sse"
    }
  }
}

```

### Claude Desktop Configuration

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "airport": {
      "command": "python",
      "args": ["-m", "airport_mcp.server"],
      "cwd": "/path/to/hackathon"
    }
  }
}

```
