"""Re-run the evaluators on an already-recorded Phoenix experiment.

Usage: python run_eval_only.py --experiment-id <ID> [--phoenix-url URL]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from phoenix.client import Client
from phoenix.client.experiments import evaluate_experiment

from judges import EVALUATORS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-id", required=True, help="Phoenix experiment ID to re-score")
    parser.add_argument("--phoenix-url", default="http://localhost:6006")
    args = parser.parse_args()

    client = Client(base_url=args.phoenix_url)
    experiment = client.experiments.get_experiment(experiment_id=args.experiment_id)
    print(f"Re-scoring experiment {args.experiment_id}...")
    evaluate_experiment(experiment=experiment, evaluators=EVALUATORS, client=client)
    print("Done.")


if __name__ == "__main__":
    main()
