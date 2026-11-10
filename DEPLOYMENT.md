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
- `<dataset>.parquet` - Parquet runway datasets
- `nasr_cycle_timestamp.txt` - NASR cycle timestamp

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

## Test DataBricks deployment
### Login
```bash
databricks auth login --host https://dbc-aae0ba16-8727.cloud.databricks.com
```

### Verify login:
```bash
databricks current-user me
```


### Update to  the latest commit:
```bash
databricks apps deploy airport --git-branch master
```

### Check logs:
```bash
databricks apps logs airport --tail-lines 100
```

### Get the token:
```bash
DATABRICKS_TOKEN="$(databricks auth token --output json | jq -r .access_token)"
```


### Get session id:
```bash
SESSION_ID=$(curl -s -i -X POST "https://airport-7474654188777746.aws.databricksapps.com/mcp" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DATABRICKS_TOKEN" \
  -H "Mcp-Protocol-Version: 2025-03-26" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2025-03-26",
      "capabilities": {},
      "clientInfo": {"name": "curl-test", "version": "1.0.0"}
    }
  }' | grep -i '^mcp-session-id:' | awk '{print $2}' | tr -d '\r')

```

### Make a request:
```bash
curl -s -X POST "https://airport-7474654188777746.aws.databricksapps.com/mcp" \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer $DATABRICKS_TOKEN" \
     -H "Mcp-Protocol-Version: 2025-03-26" \
     -H "Mcp-Session-Id: $SESSION_ID" \
     -d '{
       "jsonrpc": "2.0",
       "id": 2,
       "method": "tools/call",
       "params": {
         "name": "airport_get_runways",
         "arguments": {
           "icao_or_faa_id": "DCA",
           "response_format": "json"
         }
       }
     }' | sed -n 's/^data: //p' | jq -r '
    .result.content[0].text | fromjson as $d |
    "### Runways for \($d.icao_id) (\($d.city), \($d.state), \($d.country))\n",
    "| Runway | Length (ft) | Width (ft) | Surface | Condition | Lights |",
    "|---|---|---|---|---|---|",
    ($d.items[] | "| \(.rwy_id) | \(.length_ft | floor) | \(.width_ft | floor) | \(.surface) | \(.condition) | \(.lights) |")
  '
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

