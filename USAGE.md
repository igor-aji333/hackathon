# Usage Instructions

## Available Tool

### `get_airport_runways(icao_or_faa_id)`

Query an airport by ICAO or FAA identifier to get runway information.

**Parameters:**
- `icao_or_faa_id` (string): The airport identifier (e.g., 'JFK', 'KLAX', 'KJFK', 'LAX')

**Returns:**
JSON object containing:
- `icao_id`: Airport identifier
- `name`: Airport name
- `city`: City location
- `state`: State code
- `country`: Country code
- `runways`: Array of runway objects with:
  - `rwy_id`: Runway identifier
  - `length_ft`: Runway length in feet
  - `width_ft`: Runway width in feet
  - `surface`: Surface type code
  - `condition`: Condition code
  - `latitude_1`, `longitude_1`: First coordinate pair
  - `latitude_2`, `longitude_2`: Second coordinate pair
  - `lights`: Lighting code

## Examples

### Query JFK Airport Runways
```json
{
  "tool": "get_airport_runways",
  "parameters": {
    "icao_or_faa_id": "JFK"
  }
}
```

### Query Los Angeles International Airport
```json
{
  "tool": "get_airport_runways",
  "parameters": {
    "icao_or_faa_id": "KLAX"
  }
}
```

## Sample Response
```json
{
  "icao_id": "JFK",
  "name": "JOHN F. KENNEDY INTERNATIONAL AP",
  "city": "JAMAICA",
  "state": "NY",
  "country": "US",
  "runways": [
    {
      "rwy_id": "04L/22R",
      "length_ft": 14000,
      "width_ft": 150,
      "surface": "CONC",
      "condition": "STD",
      "latitude_1": 40.641389,
      "longitude_1": -73.778056,
      "latitude_2": 40.631389,
      "longitude_2": -73.768056,
      "lights": "RWY"
    }
  ]
}
```

## Error Handling

If airport is not found:
```json
{
  "error": "Airport 'XXX' not found"
}
```

## CLI Testing

Test the server directly from command line:

```bash
# Run server in stdio mode
python -m airport_mcp.server

# Or use with stdio transport
python -c "
from airport_mcp.server import get_airport_runways
import json
print(get_airport_runways('JFK'))
"
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