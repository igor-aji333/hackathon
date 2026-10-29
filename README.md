# Airport MCP Server

A FastMCP server that provides comprehensive query access to FAA airport runway and runway end data. This server downloads, caches, and parses the 28-day FAA NASR (National Airspace System Resource) cycle data, exposing it to MCP clients for AI agents to query.

## Features
- **Runway Information:** Retrieve length, width, surface, condition, and coordinates for runways (`get_airport_runways`).
- **Runway Ends Information:** Retrieve elevations, thresholds, alignments, and glide slopes for runway ends (`get_airport_runway_ends`).
- **Smart Caching:** Data is automatically downloaded, converted to Parquet for speed, and cached for 28 days based on FAA cycle schedules.
- **Multiple Storage Backends:** Supports Local Disk, AWS S3, and Databricks Volumes.
- **MCP Transports:** Supports Stdio, Server-Sent Events (SSE), and Streamable HTTP.

## Prerequisites
- Python 3.13 or higher
- Git

## Installation

1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd airport-mcp

```

2. **Set up virtual environment:**
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

```


3. **Install dependencies:**
```bash
pip install -r requirements.txt
# Or using uv: uv pip install -r requirements.txt

```



## Running the Server

Run the server in Stdio mode (default for most MCP clients):

```bash
python -m airport_mcp.server

```

Run with HTTP/SSE transport (requires `fastmcp[ssestream]`):

```bash
MCP_TRANSPORT=streamable-http python -m airport_mcp.server

```

## Storage Backends

The server supports multiple storage backends for caching the CSV/Parquet data:

### Local Filesystem (default)

Data is stored in `~/.airport_mcp_data/`:

* `<dataset>.parquet` - Cached dataset
* `nasr_cycle_timestamp.txt` - Last cycle timestamp

### AWS S3

Set the following environment variables:

```bash
export AIRPORT_MCP_STORAGE_BACKEND=s3
export AIRPORT_MCP_S3_BUCKET=your-bucket-name
export AIRPORT_MCP_S3_KEY="airport_mcp/"  # Optional prefix

```

### Databricks

Data is automatically stored to `/Volumes/users/<user>/airport_mcp_data` when running inside Databricks (detected via the `DATABRICKS_RUNTIME_VERSION` environment variable).

## Available Tools

### 1. `get_airport_runways(icao_or_faa_id)`

Query an airport by ICAO or FAA identifier to get runway structural information.

**Parameters:**

* `icao_or_faa_id` (string): The airport identifier (e.g., 'JFK', 'KLAX')

**Returns (JSON):**
Provides array of runways with `rwy_id`, `length_ft`, `width_ft`, `surface`, `condition`, coordinates, and `lights`.

### 2. `get_airport_runway_ends(icao_or_faa_id)`

Query an airport to get comprehensive runway end data (thresholds, elevations, alignments, glideslopes).

**Parameters:**

* `icao_or_faa_id` (string): The airport identifier (e.g., 'JFK', 'KLAX')

**Returns (JSON):**
Provides array of runway ends with `rwy_end_id`, `latitude`, `longitude`, `elevation_ft`, `true_alignment`, `ils_type`, and `visual_glide_path_angle`.

## MCP Client Configuration

### Claude Desktop Configuration

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "airport": {
      "command": "python",
      "args": ["-m", "airport_mcp.server"],
      "cwd": "/path/to/airport-mcp"
    }
  }
}

```

### Opencode Configuration

Add to `.opencode/mcp.json` using SSE:

```json
{
  "mcpServers": {
    "airport": {
      "url": "http://localhost:8000/sse"
    }
  }
}

```

## Testing

**CLI Testing:**

```bash
python -c "from airport_mcp.runway_tool import get_airport_runways; print(get_airport_runways('JFK'))"

```

**MCP Inspector:**

```bash
npm install -g @modelcontextprotocol/inspector
mcp-inspector python -m airport_mcp.server

```

**Run Unit Tests:**

```bash
pip install -e ".[dev]"
pytest tests/

```



