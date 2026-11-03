# eval/phoenix/judges/correctness_judge.py
from typing import Any, Dict


def match_expected_response(output: Dict[str, Any], expected: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """Evaluates correctness using string comparison against ground truth."""
    agent_response = str(output.get("responses", "")).strip().lower()
    ground_truth = str(expected.get("expected") or expected.get("answer", "")).strip().lower()

    is_correct = bool(ground_truth and (ground_truth == agent_response or ground_truth in agent_response))

    return {
        "score": 1 if is_correct else 0,
        "label": "correct" if is_correct else "incorrect",
    }
