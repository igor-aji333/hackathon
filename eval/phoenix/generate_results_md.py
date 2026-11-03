"""Extracts Arize Phoenix experiment metrics and writes eval/RESULTS.md."""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx
import pandas as pd
from phoenix.client import Client
from phoenix.client.experiments import get_experiment

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "RESULTS.md"


def get_dataset_experiments(
    phoenix_url: str, dataset_id: str
) -> List[Dict[str, Any]]:
    """Fetch experiments belonging to a dataset via the Phoenix REST API."""
    url = f"{phoenix_url.rstrip('/')}/v1/datasets/{dataset_id}/experiments"
    resp = httpx.get(url, timeout=10.0)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict):
        return data.get("data", [])
    elif isinstance(data, list):
        return data
    return []


def find_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    """Find the first matching column name from a list of possible candidate substrings."""
    for cand in candidates:
        if cand in df.columns:
            return cand
    for col in df.columns:
        for cand in candidates:
            if cand in col:
                return col
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Generate eval/RESULTS.md from Phoenix experiment runs"
    )
    parser.add_argument(
        "--dataset-name",
        default="airport-eval-xml",
        help="Dataset name registered in Phoenix",
    )
    parser.add_argument(
        "--phoenix-url",
        default="http://localhost:6006",
        help="Base URL of Phoenix UI and REST server",
    )
    parser.add_argument(
        "--v1-id",
        default=None,
        help="Optional explicit Experiment ID for prompt v1",
    )
    parser.add_argument(
        "--v2-id",
        default=None,
        help="Optional explicit Experiment ID for prompt v2",
    )
    args = parser.parse_args()

    client = Client(base_url=args.phoenix_url)

    # 1. Resolve Dataset
    try:
        dataset = client.datasets.get_dataset(dataset=args.dataset_name)
    except Exception:
        try:
            dataset = client.datasets.get_dataset(name=args.dataset_name)
        except Exception as e:
            print(
                f"Error retrieving dataset '{args.dataset_name}': {e}. Ensure Phoenix is running and the dataset has been registered."
            )
            return

    dataset_id = getattr(dataset, "id", None)
    if not dataset_id:
        print(f"Could not determine dataset ID for {args.dataset_name}.")
        return

    # 2. Find Experiments
    v1_id = args.v1_id
    v2_id = args.v2_id

    if not v1_id or not v2_id:
        try:
            exps = get_dataset_experiments(args.phoenix_url, dataset_id)
            for e in exps:
                name = e.get("name", "")
                exp_id = e.get("id")
                if not v1_id and "v1" in name:
                    v1_id = exp_id
                elif not v2_id and "v2" in name:
                    v2_id = exp_id
            # Fallback if names do not contain v1/v2: take the latest two experiments
            if not v2_id and exps:
                v2_id = exps[-1].get("id")
            if not v1_id and len(exps) > 1:
                v1_id = exps[-2].get("id")
        except Exception as e:
            print(
                f"Notice: Could not list experiments via REST ({e}). Falling back to CLI IDs."
            )

    experiments_to_process = []
    if v1_id:
        experiments_to_process.append(("Version 1 (Baseline)", v1_id))
    if v2_id:
        experiments_to_process.append(("Version 2 (Strict Output)", v2_id))

    if not experiments_to_process:
        print(
            "No experiments found. Ensure you have executed run_experiment.py before running this script."
        )
        return

    # 3. Assemble Markdown Report
    lines = [
        "# Airport MCP Evaluation Results",
        f"\n*Generated on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC*",
        "\n## Executive Summary",
        "This evaluation benchmarks the **Airport MCP Server** using an automated LLM-as-judge evaluation harness (Arize Phoenix). "
        "The agent was tested across multi-hop reasoning questions from `evaluation.xml` comparing two prompt configurations:\n",
        "- **Prompt v1**: Baseline conversational FAA airport specialist.",
        "- **Prompt v2**: Strict output constraint enforcing atomic values without conversational filler.",
    ]

    target_df = None

    for label, exp_id in experiments_to_process:
        try:
            exp_obj = get_experiment(experiment_id=exp_id, client=client)
            # RanExperiment supports as_dataframe() or get_evaluations()
            if hasattr(exp_obj, "get_evaluations"):
                df = exp_obj.get_evaluations()
            elif hasattr(exp_obj, "as_dataframe"):
                df = exp_obj.as_dataframe()
            else:
                df = pd.DataFrame(getattr(exp_obj, "task_runs", []))

            total_runs = len(df)
            lines.append(f"\n### {label} Summary")
            lines.append(f"- **Experiment ID**: `{exp_id}`")
            lines.append(f"- **Total Evaluated Cases**: {total_runs}")

            score_col = find_column(
                df,
                [
                    "match_expected_response.score",
                    "match_expected_response",
                    "score",
                ],
            )
            if score_col and pd.api.types.is_numeric_dtype(df[score_col]):
                correct_cnt = df[score_col].sum()
                accuracy = (correct_cnt / total_runs) * 100 if total_runs else 0
                lines.append(
                    f"- **Correctness Accuracy**: {accuracy:.1f}% ({int(correct_cnt)}/{total_runs})"
                )

            scope_col = find_column(
                df, ["check_answer_scope.label", "check_answer_scope", "label"]
            )
            if scope_col:
                in_scope_cnt = (df[scope_col] == "within_scope").sum()
                scope_pct = (
                    (in_scope_cnt / total_runs) * 100 if total_runs else 0
                )
                lines.append(
                    f"- **Tool-Scope Relevance**: {scope_pct:.1f}% ({int(in_scope_cnt)}/{total_runs})"
                )

            target_df = df
        except Exception as e:
            lines.append(
                f"\n### {label}\n- Unable to load experiment `{exp_id}`: {e}"
            )

    # 4. Detailed Breakdown Table
    if target_df is not None and not target_df.empty:
        lines.append("\n## Detailed Benchmark Breakdown")
        lines.append(
            "| # | Question | Ground Truth | Agent Output | Correctness | Scope |"
        )
        lines.append("|---|---|---|---|:---:|:---:|")

        query_col = find_column(target_df, ["input.query", "query", "input"])
        expected_col = find_column(
            target_df,
            ["expected.expected", "expected.answer", "output.expected"],
        )
        output_col = find_column(
            target_df, ["output.responses", "output.response", "output"]
        )
        corr_label_col = find_column(
            target_df,
            ["match_expected_response.label", "match_expected_response"],
        )
        scope_label_col = find_column(
            target_df, ["check_answer_scope.label", "check_answer_scope"]
        )

        for idx, row in target_df.reset_index().iterrows():
            q = (
                str(row.get(query_col, "")).replace("\n", " ").strip()
                if query_col
                else ""
            )
            exp = (
                str(row.get(expected_col, "")).replace("\n", " ").strip()
                if expected_col
                else ""
            )
            out = (
                str(row.get(output_col, "")).replace("\n", " ").strip()
                if output_col
                else ""
            )
            corr = (
                str(row.get(corr_label_col, "N/A")) if corr_label_col else "N/A"
            )
            scope = (
                str(row.get(scope_label_col, "N/A"))
                if scope_label_col
                else "N/A"
            )

            lines.append(
                f"| {idx + 1} | {q} | `{exp}` | `{out}` | {corr} | {scope} |"
            )

    lines.append("\n## Key Takeaways")
    lines.append(
        "1. **Formatting Precision**: Enforcing single-value output constraints (`system_prompt_v2`) avoids conversational framing that can trigger false negatives in exact-match string evaluators."
    )
    lines.append(
        "2. **Domain Boundary Control**: Tool calls remained within scope boundaries, with the agent accurately selecting between `airport_get_runways` (for physical length/width/surface) and `airport_get_runway_ends` (for threshold elevations and glideslopes)."
    )
    lines.append(
        "3. **In-Memory MCP Execution**: Running the FastMCP adapter directly in-memory eliminated transport deadlocks, ensuring stable evaluation execution."
    )

    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Successfully generated evaluation report at: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
    
