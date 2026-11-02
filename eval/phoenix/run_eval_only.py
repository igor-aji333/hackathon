import os
import sys
from pathlib import Path

# Add current directory and repo root to sys.path so judges can be imported cleanly
current_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(current_dir))
sys.path.insert(0, str(current_dir.parent.parent))

from phoenix.client import Client
from phoenix.client.experiments import evaluate_experiment
from judges.relevance_judge import check_answer_scope


# Code-based Exact Match Evaluator (matches the logic in run_experiment.py)
def match_expected_response(output: dict, expected: dict) -> dict:
    """Evaluates whether the agent output matches the ground truth answer."""
    actual = str(output.get("responses", "")).strip()
    target = str(expected.get("answer", "")).strip()
    is_correct = actual.lower() == target.lower()
    return {
        "score": 1 if is_correct else 0,
        "label": "correct" if is_correct else "incorrect",
    }


def main():
    client = Client()

    # Replace with your experiment ID from the previous run
    experiment_id = "RXhwZXJpbWVudDox"

    print(f"Fetching experiment {experiment_id}...")
    experiment = client.experiments.get_experiment(experiment_id=experiment_id)

    print("Running evaluators on stored experiment task runs...")
    evaluate_experiment(
        experiment=experiment,
        evaluators=[match_expected_response, check_answer_scope],
        client=client,
    )

    print(f"Done!")


if __name__ == "__main__":
    main()
    