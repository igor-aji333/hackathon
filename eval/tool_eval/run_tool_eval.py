"""Deterministic tool-level evaluation for the Airport MCP server.

Runs every case in cases.yaml through a real MCP client (in-memory
transport), then measures cold start, per-call latency, determinism across
repeats, and behaviour under concurrent load. Writes TOOL_EVAL_RESULTS.md.

    uv run python eval/tool_eval/run_tool_eval.py [--repeats 5]
"""

import argparse
import asyncio
import json
import logging
import platform
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import median, quantiles
from typing import Any

import yaml
from fastmcp import Client

from airport_mcp.server import create_server

HERE = Path(__file__).resolve().parent
_MISSING = object()


@dataclass
class CaseResult:
    case_id: str
    category: str
    tool: str
    passed: bool
    deterministic: bool
    latencies_ms: list[float]
    failures: list[str] = field(default_factory=list)


def resolve(data: Any, path: str) -> Any:
    """Follow a dotted path; '*' maps over a list and flattens the result."""
    values, fanned = [data], False
    for part in path.split("."):
        next_values = []
        for value in values:
            if part == "*":
                fanned = True
                next_values.extend(value if isinstance(value, list) else [])
            elif isinstance(value, list) and part.isdigit():
                next_values.append(value[int(part)] if int(part) < len(value) else _MISSING)
            elif isinstance(value, dict):
                next_values.append(value.get(part, _MISSING))
            else:
                next_values.append(_MISSING)
        values = next_values
    return values if fanned else values[0]


def check(case: dict, is_error: bool, text: str, data: Any) -> list[str]:
    failures = []
    if case.get("expect_error"):
        if not is_error:
            return ["expected isError=True, got a successful result"]
        if case.get("error_contains") and case["error_contains"] not in text:
            failures.append(f"error text missing {case['error_contains']!r}: {text[:120]!r}")
        return failures
    if is_error:
        return [f"unexpected error: {text[:160]}"]

    for path, want in (case.get("equals") or {}).items():
        got = resolve(data, path)
        if got != want:
            failures.append(f"{path}: expected {want!r}, got {got!r}")
    for path, want in (case.get("contains") or {}).items():
        got = resolve(data, path)
        if not isinstance(got, list) or want not in got:
            failures.append(f"{path}: {want!r} not in {got!r}")
    for path, unwanted in (case.get("excludes") or {}).items():
        got = resolve(data, path)
        if isinstance(got, list) and unwanted in got:
            failures.append(f"{path}: {unwanted!r} should be absent")
    for path, want in (case.get("count") or {}).items():
        got = resolve(data, path)
        if not isinstance(got, list) or len(got) != want:
            failures.append(f"len({path}): expected {want}, got {len(got) if isinstance(got, list) else got!r}")
    for path in case.get("type_number") or []:
        got = resolve(data, path)
        if not isinstance(got, (int, float)) or isinstance(got, bool):
            failures.append(f"{path}: expected a number, got {type(got).__name__}")
    return failures


async def call(client: Client, tool: str, args: dict) -> tuple[bool, str, Any, float]:
    start = time.perf_counter()
    result = await client.call_tool(tool, args, raise_on_error=False)
    elapsed_ms = (time.perf_counter() - start) * 1000
    text = result.content[0].text if result.content else ""
    return result.is_error, text, result.structured_content, elapsed_ms


async def run_cases(client: Client, cases: list[dict], repeats: int) -> list[CaseResult]:
    results = []
    for case in cases:
        outcomes = [await call(client, case["tool"], case.get("args", {})) for _ in range(repeats)]
        is_error, text, data, _ = outcomes[0]
        fingerprints = {json.dumps([o[0], o[1] if o[0] else o[2]], sort_keys=True, default=str) for o in outcomes}
        results.append(CaseResult(
            case_id=case["id"],
            category=case.get("category", ""),
            tool=case["tool"],
            passed=not check(case, is_error, text, data),
            deterministic=len(fingerprints) == 1,
            latencies_ms=[o[3] for o in outcomes],
            failures=check(case, is_error, text, data),
        ))
    return results


async def measure_cold_start() -> float:
    """Fresh server, data read from the local Parquet cache, first tool call."""
    start = time.perf_counter()
    async with Client(create_server()) as client:
        await client.call_tool("airport_get_runways", {"airport_id": "KJFK"})
    return (time.perf_counter() - start) * 1000


async def measure_concurrency(client: Client, n: int) -> tuple[int, int, float]:
    airports = ["KJFK", "KLAX", "KORD", "KDEN", "KSEA", "PANC", "KMIA", "KBOS", "KEWR", "KDTW"]
    calls = [
        client.call_tool("airport_get_runways", {"airport_id": airports[i % len(airports)]}, raise_on_error=False)
        if i % 2 == 0 else
        client.call_tool("airport_find_nearby", {"airport_id": airports[i % len(airports)], "radius_nm": 60}, raise_on_error=False)
        for i in range(n)
    ]
    start = time.perf_counter()
    results = await asyncio.gather(*calls, return_exceptions=True)
    elapsed_ms = (time.perf_counter() - start) * 1000
    ok = sum(1 for r in results if not isinstance(r, BaseException) and not r.is_error)
    return ok, n, elapsed_ms


def pct(values: list[float], q: int) -> float:
    if len(values) < 2:
        return values[0]
    return quantiles(values, n=100, method="inclusive")[q - 1]


def render(results: list[CaseResult], cold_ms: float, concurrency: tuple[int, int, float],
           repeats: int, data_cycle: str) -> str:
    passed = sum(r.passed for r in results)
    deterministic = sum(r.deterministic for r in results)
    lines = [
        "# Airport MCP – Tool Evaluation Results",
        "",
        f"*Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} by `eval/tool_eval/run_tool_eval.py`"
        f" · FAA NASR cycle {data_cycle} · Python {platform.python_version()} on {platform.system()}.*",
        "",
        "Every case is executed through a real MCP client (FastMCP in-memory transport), so argument",
        "validation, structured output and `isError` semantics are exercised exactly as an agent sees them.",
        f"Each case runs {repeats}× to measure latency and confirm identical output across calls.",
        "",
        "## Summary",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Cases passed | **{passed}/{len(results)}** |",
        f"| Deterministic across {repeats} repeats | {deterministic}/{len(results)} |",
    ]
    all_ms = [ms for r in results for ms in r.latencies_ms]
    lines += [
        f"| Warm latency p50 / p95 / max (all calls) | {median(all_ms):.1f} / {pct(all_ms, 95):.1f} / {max(all_ms):.1f} ms |",
        f"| Cold start (new server, Parquet cache → first answer) | {cold_ms:.0f} ms |",
        f"| Concurrent load ({concurrency[1]} mixed calls via `asyncio.gather`) | {concurrency[0]}/{concurrency[1]} succeeded in {concurrency[2]:.0f} ms |",
        "",
        "## By category",
        "",
        "| Category | Passed |",
        "|---|:---:|",
    ]
    categories: dict[str, list[CaseResult]] = {}
    for r in results:
        categories.setdefault(r.category, []).append(r)
    for name, rs in categories.items():
        lines.append(f"| {name} | {sum(r.passed for r in rs)}/{len(rs)} |")

    lines += ["", "## Cases", "", "| Case | Tool | Result | p50 ms | Notes |", "|---|---|:---:|---:|---|"]
    for r in results:
        notes = "; ".join(r.failures) or ("" if r.deterministic else "non-deterministic output")
        lines.append(f"| `{r.case_id}` | `{r.tool}` | {'✅' if r.passed else '❌'} | {median(r.latencies_ms):.1f} | {notes} |")
    lines.append("")
    lines.append("Case definitions and expected values: [`cases.yaml`](cases.yaml).")
    return "\n".join(lines) + "\n"


async def main_async(repeats: int, output: Path) -> int:
    cases = yaml.safe_load((HERE / "cases.yaml").read_text())["cases"]

    # Make sure the dataset is cached locally before timing the cold start.
    async with Client(create_server()) as client:
        warm = await client.call_tool("airport_search", {"query": "JFK"})
        data_cycle = warm.structured_content["data_cycle"]

    cold_ms = await measure_cold_start()

    async with Client(create_server()) as client:
        await client.call_tool("airport_search", {"query": "warmup"})
        results = await run_cases(client, cases, repeats)
        concurrency = await measure_concurrency(client, 50)

    output.write_text(render(results, cold_ms, concurrency, repeats, data_cycle), encoding="utf-8")
    for r in results:
        print(f"{'PASS' if r.passed else 'FAIL'}  {r.case_id:32} {median(r.latencies_ms):7.1f} ms  {'; '.join(r.failures)}")
    print(f"\n{sum(r.passed for r in results)}/{len(results)} passed · cold start {cold_ms:.0f} ms · "
          f"concurrency {concurrency[0]}/{concurrency[1]} · report: {output}")
    return 0 if all(r.passed for r in results) and concurrency[0] == concurrency[1] else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repeats", type=int, default=5, help="Calls per case (latency + determinism).")
    parser.add_argument("--output", type=Path, default=HERE.parent / "TOOL_EVAL_RESULTS.md")
    args = parser.parse_args()
    # Expected error cases are logged by FastMCP at ERROR level; keep the console readable.
    logging.getLogger("fastmcp").setLevel(logging.CRITICAL)
    raise SystemExit(asyncio.run(main_async(args.repeats, args.output)))


if __name__ == "__main__":
    main()
