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


## Evaluation (LLM-as-Judge)

This project includes an automated LLM-as-judge evaluation harness using [Arize Phoenix](https://docs.arize.com/phoenix) to measure how effectively an AI agent can answer realistic questions using the server's tools. The evaluation framework is located in `eval/phoenix/`.

### Prerequisites

Ensure you have installed the development dependencies and configured your evaluation models:

1. **Install Dev Dependencies:**
   ```bash
   uv sync --group dev

```

2. **Configure Environment:**
Create a `.env` file at the repository root with your model gateway credentials and model selections (it is recommended to use different models for the agent and the judge to avoid self-preference bias):
```env
USAI_API_KEY=your_api_key
USAI_BASE_URL=https://your-gateway-url/api/v1
AGENT_MODEL=gpt-4o
JUDGE_MODEL=claude-3-5-sonnet-20241022

```



### Execution Workflow

Run all evaluation commands from within the `eval/phoenix/` directory.

**1. Start the Phoenix Server**
Launch the local Phoenix server to collect telemetry and host the UI (runs on port 6006):

```bash
uv run arize-phoenix serve

```

**2. Register the Dataset**
Upload the benchmark dataset (`airport-eval-0`) to your Phoenix instance. You can validate it first with a dry run:

```bash
cd eval/phoenix
uv run create_dataset.py --dataset-name airport-eval-0 --dry-run
uv run create_dataset.py --dataset-name airport-eval-0

```

**3. Run the Experiment**
Execute the evaluation. This spins up a LangChain agent connected to the MCP server over stdio, feeds it the dataset, and scores the responses for correctness and tool-scope relevance using the LLM-as-judge:

```bash
uv run run_experiment.py --dataset-name airport-eval-0 --system-prompt-version v2

```

**4. Review Results**
Navigate to [http://localhost:6006](http://localhost:6006) in your browser. Under the **Experiments** tab, you can inspect individual traces, view the exact tool-call arguments generated by the agent, and review the logic behind the judges' verdicts.



