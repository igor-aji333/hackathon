# Airport MCP – Tool Evaluation Results

*Generated 2026-11-10 20:47 UTC by `eval/tool_eval/run_tool_eval.py` · FAA NASR cycle 2026-10-29 · Python 3.13.15 on Linux.*

Every case is executed through a real MCP client (FastMCP in-memory transport), so argument
validation, structured output and `isError` semantics are exercised exactly as an agent sees them.
Each case runs 5× to measure latency and confirm identical output across calls.

## Summary

| Metric | Result |
|---|---|
| Cases passed | **29/29** |
| Deterministic across 5 repeats | 29/29 |
| Warm latency p50 / p95 / max (all calls) | 5.4 / 15.4 / 40.7 ms |
| Cold start (new server, Parquet cache → first answer) | 545 ms |
| Concurrent load (50 mixed calls via `asyncio.gather`) | 50/50 succeeded in 876 ms |

## By category

| Category | Passed |
|---|:---:|
| identifier resolution | 5/5 |
| data accuracy | 5/5 |
| filters | 2/2 |
| search | 5/5 |
| proximity | 4/4 |
| error handling | 3/3 |
| input validation | 5/5 |

## Cases

| Case | Tool | Result | p50 ms | Notes |
|---|---|:---:|---:|---|
| `runways-faa-code` | `airport_get_runways` | ✅ | 5.9 |  |
| `runways-icao-code` | `airport_get_runways` | ✅ | 5.7 |  |
| `runways-non-k-icao` | `airport_get_runways` | ✅ | 5.1 |  |
| `runways-case-and-whitespace` | `airport_get_runways` | ✅ | 6.0 |  |
| `runways-alphanumeric-faa-id` | `airport_get_runways` | ✅ | 4.3 |  |
| `jfk-longest-runway` | `airport_get_runways` | ✅ | 4.9 |  |
| `den-16000-surface` | `airport_get_runways` | ✅ | 4.6 |  |
| `sea-runway-ends` | `airport_get_runways` | ✅ | 5.1 |  |
| `dtw-22r-approach-lights` | `airport_get_runways` | ✅ | 7.9 |  |
| `numeric-types` | `airport_get_runways` | ✅ | 6.0 |  |
| `ord-min-length-filter` | `airport_get_runways` | ✅ | 6.6 |  |
| `ewr-exclude-helipads` | `airport_get_runways` | ✅ | 5.0 |  |
| `search-by-name-non-k` | `airport_search` | ✅ | 16.6 |  |
| `search-apostrophe` | `airport_search` | ✅ | 8.7 |  |
| `search-exact-code-first` | `airport_search` | ✅ | 8.9 |  |
| `search-city-state` | `airport_search` | ✅ | 9.7 |  |
| `search-no-match` | `airport_search` | ✅ | 11.0 |  |
| `nearby-diversion-den` | `airport_find_nearby` | ✅ | 10.9 |  |
| `nearby-sfo-long-runway` | `airport_find_nearby` | ✅ | 9.9 |  |
| `nearby-coordinates` | `airport_find_nearby` | ✅ | 8.7 |  |
| `nearby-open-ocean` | `airport_find_nearby` | ✅ | 14.1 |  |
| `unknown-airport` | `airport_get_runways` | ✅ | 1.2 |  |
| `nearby-unknown-origin` | `airport_find_nearby` | ✅ | 1.2 |  |
| `nearby-missing-origin` | `airport_find_nearby` | ✅ | 1.1 |  |
| `empty-airport-id` | `airport_get_runways` | ✅ | 1.0 |  |
| `negative-min-length` | `airport_get_runways` | ✅ | 0.9 |  |
| `latitude-out-of-range` | `airport_find_nearby` | ✅ | 1.0 |  |
| `limit-too-large` | `airport_search` | ✅ | 1.0 |  |
| `empty-search-query` | `airport_search` | ✅ | 0.9 |  |

Case definitions and expected values: [`cases.yaml`](cases.yaml).
