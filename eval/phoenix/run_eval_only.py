# eval/phoenix/run_eval_only.py
import os
import sys
from pathlib import Path

current_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(current_dir))
sys.path.insert(0, str(current_dir.parent.parent))

from phoenix.client import Client
from phoenix.client.experiments import evaluate_experiment
from judges import check_answer_scope, match_expected_response


def main():
    client = Client()
    experiment_id = "RXhwZXJpbWVudDox"
    print(f"Fetching experiment {experiment_id}...")
    experiment = client.experiments.get_experiment(experiment_id=experiment_id)
    print("Running evaluators on stored experiment task runs...")
    evaluate_experiment(
        experiment=experiment,
        evaluators=[match_expected_response, check_answer_scope],
        client=client,
    )
    print("Done!")


if __name__ == "__main__":
    main()
