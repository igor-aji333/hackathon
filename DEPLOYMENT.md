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

## Storage Backends

The server supports multiple storage backends for caching the CSV data:

### Local Filesystem (default)
Data is stored in `~/.airport_mcp_data/`:
- `apt_rwy.csv` - Runway data
- `download_time.txt` - Last download timestamp

### AWS S3
Set the following environment variables:
```bash
export AIRPORT_MCP_STORAGE_BACKEND=s3
export AIRPORT_MCP_S3_BUCKET=your-bucket-name
export AIRPORT_MCP_S3_KEY="airport_mcp/"  # Optional prefix
```

Install boto3:
```bash
pip install -e ".[s3]"
```

### Databricks
Data is automatically stored to `/dbfs/mnt/airport_mcp_data/` when running inside Databricks (detected via `DATABRICKS_RUNTIME_VERSION` environment variable).

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

- Runway data is cached for 28 days before automatic re-download
- The cache timestamp is derived from the FAA zip filename date (not current time)
- Data is read from all configured storage backends on load

## Troubleshooting

- **Network issues**: Ensure internet connectivity to download FAA data
- **Permission errors**: Check write permissions for `~/.airport_mcp_data/`
- **Data not found**: Verify the airport identifier exists in FAA records
- **S3 access denied**: Ensure AWS credentials are configured (via env vars or IAM role)