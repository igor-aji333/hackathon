# Airport MCP Server

An MCP server that gives AI agents reliable, structured access to **official FAA airport and runway data**
for every US airport, heliport and seaplane base. It downloads the FAA NASR (National Airspace System
Resource) dataset, keeps it current on the FAA's 28-day publication cycle, and exposes three
goal-oriented tools:

| Tool | Agent goal it serves |
|---|---|
| `airport_search` | "Which airport is *Ted Stevens Anchorage*?" – resolve names, cities or partial codes to identifiers. |
| `airport_get_runways` | "Can a 9,000 ft paved runway at KDEN take us? Which end has an ILS?" – full runway and runway-end picture for one airport, with optional filters. |
| `airport_find_nearby` | "Nearest public airport to KDEN with an 8,000 ft paved ILS runway?" – diversion / alternate planning by distance and runway capability. |

All tools return **typed, schema-validated structured output** (Pydantic models published as MCP
`outputSchema`), are annotated read-only/idempotent, and report problems as MCP tool errors
(`isError: true`) with a message that tells the agent what to do next.

See [USAGE.md](USAGE.md) for the full tool reference and examples.

## Design

### Why these tools

The FAA publishes airports, runways and runway ends as three separate CSV tables. Exposing one tool
per table would force the agent to make several calls and join the results itself. Instead, each tool
maps to a question an agent is actually asked:

- **Search** exists because users name airports ("O'Hare", "Anchorage") far more often than they
  quote codes. FAA abbreviations (INTL, RGNL, MUNI, …) and punctuation are normalized, so
  "Ted Stevens Anchorage International" finds `TED STEVENS ANCHORAGE INTL`.
- **Get runways** returns each runway *with both of its ends nested*, so a single call answers
  questions about lengths, surfaces, ILS, approach lights and elevations. Server-side filters
  (`min_length_ft`, `paved_only`, `include_helipads`) keep the payload focused.
- **Find nearby** performs a vectorized great-circle search over all ~19k facilities, joined with
  runway capability. This is impossible to do efficiently through a per-airport API.

Identifiers are forgiving: FAA codes (`JFK`, `1N7`), US ICAO codes (`KJFK`), and non-`K` ICAO codes
(`PANC`, `PHNL`, `TJSJ`) all resolve, case-insensitively and with whitespace trimmed.

### Module layout

```
airport_mcp/
├── server.py      # FastMCP app: instructions, pre-warm lifespan, /health, transport selection
├── tools.py       # Agent-facing tool definitions: names, descriptions, validated parameters, error mapping
├── models.py      # Pydantic output models (become each tool's outputSchema)
├── queries.py     # Pure query logic over an in-memory dataset (search ranking, filters, haversine)
├── dataset.py     # Immutable, indexed snapshot of one NASR cycle + identifier resolution
├── repository.py  # Data lifecycle: cycle detection, download, Parquet cache, refresh, stale fallback
├── nasr.py        # FAA NASR cycle calendar, download URL, CSV extraction
├── storage.py     # Artifact store protocol with local-disk and S3 implementations
└── config.py      # Typed settings from environment variables / .env
```

Each layer depends only on the ones below it. `queries.py` has no I/O, so it can be unit-tested
against small fixture tables, and the repository takes its storage and downloader as injected
dependencies.

### Reliability

- **Cycle-consistent caching.** Cache files are keyed by cycle (`nasr_2026-10-29_APT_RWY.parquet`),
  so the airport, runway and runway-end tables always come from the same cycle.
- **Non-blocking.** Download parsing, Parquet I/O and queries run in worker threads (`asyncio.to_thread`),
  so the event loop keeps serving other requests.
- **Single-flight loading.** An `asyncio.Lock` with a double-check ensures concurrent first calls trigger
  one download, not fifty.
- **Graceful degradation.** If a new cycle cannot be downloaded, the server keeps serving the
  previous cycle and retries after 15 minutes. On a cold start without network access, it falls back
  to any of the last six cached cycles. Every response carries `data_cycle`, so agents can see which
  data cycle answered.
- **Pre-warm.** Data loads when the server starts, so the first tool call is fast. If pre-warming
  fails, the tools retry lazily.

## Installation

Requires Python 3.11+.

```bash
uv sync                       # or: pip install -e .
uv sync --extra s3            # optional: S3 cache backend (boto3)
```

## Running

```bash
uv run airport-mcp                                    # stdio (default; for desktop MCP clients)
MCP_TRANSPORT=streamable-http uv run airport-mcp      # http://127.0.0.1:8000/mcp  (+ /health)
```

The first start downloads the ~9 MB FAA archive and takes a few seconds. Later starts load the
Parquet cache in about 0.5 s.

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `AIRPORT_MCP_STORAGE_BACKEND` | `local` | `local` or `s3` |
| `AIRPORT_MCP_DATA_DIR` | `~/.airport_mcp_data` | Local cache directory |
| `AIRPORT_MCP_S3_BUCKET` | – | Required when backend is `s3` |
| `AIRPORT_MCP_S3_KEY` | `airport_mcp/` | S3 key prefix |
| `MCP_TRANSPORT` | `stdio` | `stdio`, `streamable-http` or `sse` |
| `MCP_HOST` / `MCP_PORT` | `127.0.0.1` / `8000` | Bind address for HTTP transports |
| `DATABRICKS_APP_PORT` or `PORT` | – | If set (by a hosting platform), serve streamable HTTP on `0.0.0.0:<port>` |

### Client configuration

```json
{
  "mcpServers": {
    "airport": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/hackathon", "airport-mcp"]
    }
  }
}
```

To inspect the server interactively: `npx @modelcontextprotocol/inspector uv run airport-mcp`.

## Testing and evaluation

The server is checked at three levels. Each level has its own command and committed results.

| Level | Result |
|---|---|
| Unit and integration tests | 31/31 pass, offline |
| Deterministic tool eval (real FAA data) | 29/29 cases pass; 29/29 deterministic; warm p50 5 ms, p95 15 ms; cold start 0.5 s; 50/50 concurrent calls succeed |
| Agent eval (17 questions, local `muse-glimmer` agent, `gemma4:31b` judge) | Prompt v1: 94% exact match / 100% contains answer. Prompt v2: 100% exact match. Both 100% in scope. |

### 1. Unit and integration tests – `tests/`

```bash
uv sync --group dev
uv run pytest
```

These tests run against small fixture tables and a fake downloader, so they need no network access.
They cover:

- NASR cycle math and URL building.
- Repository behaviour: cache hit and miss, one download under 10 concurrent callers, refresh
  failure keeping the stale cycle, cold-start fallback, and cycle-consistent cache keys.
- Every tool through a real MCP client: output schemas, annotations, `isError` on bad input,
  ICAO/FAA resolution, filters, and search ranking.

### 2. Deterministic tool evaluation – `eval/tool_eval/` → [eval/TOOL_EVAL_RESULTS.md](eval/TOOL_EVAL_RESULTS.md)

```bash
uv run python eval/tool_eval/run_tool_eval.py
```

This evaluation calls the live tools on real FAA data with 29 declarative cases ([`cases.yaml`](eval/tool_eval/cases.yaml))
in seven categories:

- identifier resolution
- data accuracy
- filters
- search
- proximity
- error handling
- input validation

Each case runs five times to check that the output is identical every time and to measure latency.
The harness also measures cold-start time and fires 50 mixed concurrent calls. It needs no LLM, so
the results are reproducible.

### 3. Agent evaluation (LLM-as-judge) – `eval/phoenix/` → [eval/RESULTS.md](eval/RESULTS.md)

A LangChain agent connected to the server in-memory answers the 17 questions in
[`eval/evaluation.xml`](eval/evaluation.xml). The questions cover:

- multi-step runway and runway-end reasoning
- name-to-code resolution
- non-K ICAO codes
- diversion search
- a non-existent airport
- an out-of-scope weather request

Every answer was verified against the data. Two prompt versions are compared, and each answer gets
three scores, all recorded in [Arize Phoenix](https://docs.arize.com/phoenix):

- **exact match** (headline; normalized, unit- and format-tolerant)
- **contains answer** (separates formatting failures from reasoning failures)
- **scope** (an LLM judge, using a different model from the agent)

```bash
uv sync --group eval
# .env: USAI_BASE_URL, USAI_API_KEY, AGENT_MODEL, JUDGE_MODEL (any OpenAI-compatible endpoint, e.g. Ollama)
uv run phoenix serve &                                    # UI at http://localhost:6006
cd eval/phoenix
uv run python create_dataset.py --dataset-name airport-eval
uv run python run_experiment.py --system-prompt-version v1   # prints the experiment ID
uv run python run_experiment.py --system-prompt-version v2
uv run python generate_results_md.py --experiment v1=<ID> --experiment v2=<ID>
uv run python run_eval_only.py --experiment-id <ID>          # re-score a stored experiment
```

## Scope and limitations

- Static US airport infrastructure only. There is no weather, NOTAMs, frequencies, schedules or
  non-US airports. The server instructions tell agents this.
- Data is only as current as the latest FAA cycle. Every response includes the `data_cycle`
  effective date.
