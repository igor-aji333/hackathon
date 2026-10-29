import argparse
from pathlib import Path
from phoenix.client import Client
import yaml

from agent import AirportAgent
from judges import check_answer_scope, match_expected_response

REGISTRY_PATH = Path(__file__).parent / "datasets.yaml"


def main():
    parser = argparse.ArgumentParser(description="Run evaluation experiment against Airport MCP server")
    parser.add_argument("--dataset-name", default="airport-eval-0", help="Dataset name in datasets.yaml")
    parser.add_argument("--system-prompt-version", choices=["v1", "v2"], default="v1")
    parser.add_argument("--project-name", default="airport-mcp-eval")
    parser.add_argument("--phoenix-endpoint", default="http://localhost:4317")
    args = parser.parse_args()

    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        registry = yaml.safe_load(f)["datasets"]

    if args.dataset_name not in registry:
        raise KeyError(f"Dataset '{args.dataset_name}' not found in datasets.yaml")

    client = Client()
    dataset = client.datasets.get_dataset(name=args.dataset_name)

    agent = AirportAgent(
        system_prompt_version=args.system_prompt_version,
        project_name=args.project_name,
        endpoint=args.phoenix_endpoint,
    )
    task = agent.create_experiment_task()

    print(f"Executing experiment on dataset: {args.dataset_name} with prompt: {args.system_prompt_version}")
    experiment = client.experiments.run_experiment(
        dataset=dataset,
        task=task,
        evaluators=[match_expected_response, check_answer_scope],
        experiment_name=f"airport-{args.system_prompt_version}",
        experiment_description=f"Airport MCP evaluation using prompt {args.system_prompt_version}",
    )
    print(f"Experiment completed. Details available in Phoenix UI: {experiment}")


if __name__ == "__main__":
    main()

