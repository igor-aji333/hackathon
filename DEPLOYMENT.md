# Deployment Instructions

## Prerequisites
- Python 3.13 or higher
- Git

## Installation

1. Clone the repository:
```bash
git clone <repo-url>
cd hackathon
```

2. Set up virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
# Or using uv:
uv pip install -r requirements.txt
```

## Running the MCP Server

```bash
python -m airport_mcp.server
```

## MCP Client Configuration

Add to your MCP client configuration:

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

## Data Caching

- Runway data is cached in `~/.airport_mcp_data/`
- CSV file: `apt_rwy.csv`
- Download timestamp: `download_time.txt`
- Automatic re-download every 28 days or when data is missing

## Troubleshooting

- **Network issues**: Ensure internet connectivity to download FAA data
- **Permission errors**: Check write permissions for `~/.airport_mcp_data/`
- **Data not found**: Verify the airport identifier exists in FAA records