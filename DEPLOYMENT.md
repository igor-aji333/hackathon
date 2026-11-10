# Deployment

## Local

```bash
uv sync
uv run airport-mcp                                     # stdio
MCP_TRANSPORT=streamable-http MCP_PORT=8000 uv run airport-mcp
curl http://127.0.0.1:8000/health
```

When `PORT` or `DATABRICKS_APP_PORT` is set (as hosting platforms do), the server ignores
`MCP_TRANSPORT`. It serves streamable HTTP on `0.0.0.0:<port>`, with the MCP endpoint at `/mcp` and a
readiness probe at `/health`.

## Data cache

The FAA publishes a new NASR cycle every 28 days. The server works out the current cycle from the
calendar and downloads `https://nfdc.faa.gov/webContent/28DaySub/extra/<DD>_<Mon>_<YYYY>_APT_CSV.zip`.
It stores the three tables it needs as Parquet, one file per table per cycle:

```
nasr_2026-10-29_APT_BASE.parquet
nasr_2026-10-29_APT_RWY.parquet
nasr_2026-10-29_APT_RWY_END.parquet
```

- **Local** (default): `~/.airport_mcp_data/`, or set `AIRPORT_MCP_DATA_DIR`. Use a persistent volume in containers.
- **S3**: `AIRPORT_MCP_STORAGE_BACKEND=s3`, `AIRPORT_MCP_S3_BUCKET=<bucket>`, and optionally
  `AIRPORT_MCP_S3_KEY=<prefix>`. Install with `uv sync --extra s3`. Credentials come from the standard
  AWS chain (environment variables, profile, or IAM role).

If a new cycle cannot be downloaded, the server keeps serving the previous cycle and retries after
15 minutes. Old cycle files can be deleted at any time.

> Upgrading from 0.2.x: the old cache files (`APT_RWY.parquet`, `APT_RWY_END.parquet`,
> `FAA_NASR_*.zip`, `nasr_cycle_timestamp.txt`) are no longer used and can be removed.

## Databricks Apps

[`app.yaml`](app.yaml) runs `python -m airport_mcp.server`. Databricks sets `DATABRICKS_APP_PORT`, so
the app serves streamable HTTP.

```bash
databricks auth login --host https://<workspace>.cloud.databricks.com
databricks apps deploy airport --git-branch master
databricks apps logs airport --tail-lines 100
```

Smoke test against the deployed app:

```bash
APP_URL=https://<app-name>.aws.databricksapps.com
TOKEN="$(databricks auth token --output json | jq -r .access_token)"
HDRS=(-H "Content-Type: application/json" -H "Accept: application/json, text/event-stream"
      -H "Authorization: Bearer $TOKEN" -H "Mcp-Protocol-Version: 2025-06-18")

SESSION_ID=$(curl -s -i -X POST "$APP_URL/mcp" "${HDRS[@]}" -d '{
  "jsonrpc": "2.0", "id": 1, "method": "initialize",
  "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "curl", "version": "1"}}
}' | grep -i '^mcp-session-id:' | awk '{print $2}' | tr -d '\r')

curl -s -X POST "$APP_URL/mcp" "${HDRS[@]}" -H "Mcp-Session-Id: $SESSION_ID" \
  -d '{"jsonrpc": "2.0", "method": "notifications/initialized"}'

curl -s -X POST "$APP_URL/mcp" "${HDRS[@]}" -H "Mcp-Session-Id: $SESSION_ID" -d '{
  "jsonrpc": "2.0", "id": 2, "method": "tools/call",
  "params": {"name": "airport_get_runways", "arguments": {"airport_id": "DCA"}}
}' | sed -n 's/^data: //p' | jq -r '
  .result.structuredContent as $d |
  "### Runways at \($d.airport.name) (\($d.airport.faa_id)/\($d.airport.icao_id)) – cycle \($d.data_cycle)",
  "| Runway | Length | Width | Surface | ILS |", "|---|---|---|---|---|",
  ($d.runways[] | "| \(.runway_id) | \(.length_ft) | \(.width_ft) | \(.surface) | \(.has_ils) |")'
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `/health` reports `initializing` | The first download is still running, or it failed. Check the logs for `pre-warm failed`. Tool calls retry automatically. |
| Tool error "temporarily unavailable" | The FAA site is unreachable and no cached cycle exists. Check outbound HTTPS to `nfdc.faa.gov`. |
| `AIRPORT_MCP_S3_BUCKET must be set` | You set the S3 backend without a bucket. |
| S3 `AccessDenied` | The IAM role needs `s3:GetObject` and `s3:PutObject` on the prefix. |
