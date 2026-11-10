"""Write eval/RESULTS.md from recorded Phoenix experiments.

Scores are taken verbatim from the evaluators stored in Phoenix (no
re-scoring here), and every question is matched to its dataset example by ID.

Usage:
    python generate_results_md.py --experiment v1=<ID> --experiment v2=<ID>
"""

import argparse
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Optional

from dotenv import load_dotenv
from phoenix.client import Client

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "RESULTS.md"


@dataclass
class RunRecord:
    query: str
    expected: str
    output: str
    latency_s: Optional[float]
    error: Optional[str]
    labels: dict[str, str] = field(default_factory=dict)
    scores: dict[str, Optional[float]] = field(default_factory=dict)


def _seconds(start: Any, end: Any) -> Optional[float]:
    try:
        return (datetime.fromisoformat(str(end)) - datetime.fromisoformat(str(start))).total_seconds()
    except (TypeError, ValueError):
        return None


def _response_text(output: Any) -> str:
    if isinstance(output, dict):
        output = output.get("responses", output)
    return " ".join(str(output or "").split())


def load_runs(client: Client, experiment_id: str) -> list[RunRecord]:
    experiment = client.experiments.get_experiment(experiment_id=experiment_id)
    dataset = client.datasets.get_dataset(
        dataset=experiment["dataset_id"], version_id=experiment["dataset_version_id"]
    )
    examples = {ex["id"]: ex for ex in dataset.examples}

    position_of = {ex["id"]: pos for pos, ex in enumerate(dataset.examples)}
    records: dict[str, RunRecord] = {}

    for run in experiment["task_runs"]:
        example = examples.get(run["dataset_example_id"], {})
        records[run["id"]] = RunRecord(
            query=str(example.get("input", {}).get("query", "")),
            expected=str(example.get("output", {}).get("expected", "")),
            output=_response_text(run.get("output")),
            latency_s=_seconds(run.get("start_time"), run.get("end_time")),
            error=run.get("error"),
        )

    for evaluation in experiment["evaluation_runs"]:
        record = records.get(evaluation.experiment_run_id)
        if record is None:
            continue
        result = evaluation.result
        if isinstance(result, (list, tuple)):
            result = result[0] if result else None
        result = result or {}
        record.labels[evaluation.name] = str(result.get("label") or "error")
        record.scores[evaluation.name] = result.get("score")

    runs_by_example = sorted(
        ((position_of.get(run["dataset_example_id"], 10**6), records[run["id"]]) for run in experiment["task_runs"]),
        key=lambda item: item[0],
    )
    return [record for _, record in runs_by_example]


def _rate(runs: list[RunRecord], metric: str) -> str:
    scored = [r.scores.get(metric) for r in runs if r.scores.get(metric) is not None]
    if not scored:
        return "n/a"
    hits = sum(1 for s in scored if s >= 1)
    return f"{100 * hits / len(runs):.0f}% ({hits}/{len(runs)})"


def _cell(text: str, limit: int = 80) -> str:
    text = text.replace("|", "\\|")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def render(experiments: dict[str, tuple[str, list[RunRecord]]]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Airport MCP – Agent Evaluation Results",
        "",
        f"*Generated {now} by `eval/phoenix/generate_results_md.py`.*",
        "",
        f"Agent model: `{os.getenv('AGENT_MODEL', 'unknown')}` · Judge model: `{os.getenv('JUDGE_MODEL', 'unknown')}`"
        " (different models to avoid self-preference bias).",
        "",
        "An LLM agent (LangChain + in-memory MCP adapter) answers every question in",
        "`eval/evaluation.xml` using only the server's tools. Each answer is scored by:",
        "",
        "- **Exact match** (headline): normalized response equals the ground truth.",
        "- **Contains answer**: ground truth appears as a whole token (separates formatting from reasoning failures).",
        "- **Scope** (LLM judge): agent stayed within FAA airport-infrastructure data and did not invent out-of-scope facts.",
        "",
        "## Summary",
        "",
        "| Prompt | Experiment ID | Exact match | Contains answer | Scope | Task errors | Median latency |",
        "|---|---|:---:|:---:|:---:|:---:|:---:|",
    ]
    for version, (exp_id, runs) in experiments.items():
        latencies = [r.latency_s for r in runs if r.latency_s is not None]
        lines.append(
            f"| {version} | `{exp_id}` | {_rate(runs, 'exact_match')} | {_rate(runs, 'contains_answer')} "
            f"| {_rate(runs, 'check_answer_scope')} | {sum(1 for r in runs if r.error)} "
            f"| {f'{median(latencies):.1f}s' if latencies else 'n/a'} |"
        )

    versions = list(experiments)
    reference = experiments[versions[0]][1]
    header = "| # | Question | Expected | " + " | ".join(f"{v} output | {v} exact" for v in versions) + " |"
    lines += ["", "## Per-question results", "", header, "|" + "---|" * (3 + 2 * len(versions))]
    for i, ref in enumerate(reference):
        cells = [str(i + 1), _cell(ref.query, 120), f"`{ref.expected}`"]
        for v in versions:
            runs = experiments[v][1]
            run = runs[i] if i < len(runs) else None
            if run is None:
                cells += ["–", "–"]
                continue
            output = f"ERROR: {run.error}" if run.error else run.output
            cells += [f"`{_cell(output)}`", "✅" if (run.scores.get("exact_match") or 0) >= 1 else "❌"]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--experiment", action="append", required=True, metavar="LABEL=ID",
                        help="Experiment to include, e.g. v1=RXhwZXJpbWVudDox. Repeat for each prompt version.")
    parser.add_argument("--phoenix-url", default="http://localhost:6006")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    load_dotenv()

    client = Client(base_url=args.phoenix_url)
    experiments: dict[str, tuple[str, list[RunRecord]]] = {}
    for spec in args.experiment:
        label, _, exp_id = spec.partition("=")
        if not exp_id:
            parser.error(f"--experiment must be LABEL=ID, got {spec!r}")
        experiments[label] = (exp_id, load_runs(client, exp_id))

    args.output.write_text(render(experiments), encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
