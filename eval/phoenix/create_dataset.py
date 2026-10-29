import argparse
from pathlib import Path
import pandas as pd
import yaml
from phoenix.client import Client

REGISTRY_PATH = Path(__file__).parent / "datasets.yaml"


def main():
    parser = argparse.ArgumentParser(description="Upload evaluation datasets to Phoenix")
    parser.add_argument("--dataset-name", required=True, help="Key defined in datasets.yaml")
    parser.add_argument("--phoenix-name", default=None, help="Name inside Phoenix (defaults to key)")
    parser.add_argument("--dry-run", action="store_true", help="Validate CSV schema without uploading")
    args = parser.parse_args()

    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        registry = yaml.safe_load(f)["datasets"]

    if args.dataset_name not in registry:
        raise KeyError(f"Dataset '{args.dataset_name}' not registered in datasets.yaml")

    info = registry[args.dataset_name]
    csv_path = Path(__file__).parent / info["csv_path"]

    df = pd.read_csv(csv_path)
    for col in info["input_keys"] + info["output_keys"]:
        if col not in df.columns:
            raise ValueError(f"Missing required column '{col}' in {csv_path}")

    print(f"Validated {len(df)} records in {csv_path}")
    if args.dry_run:
        print("Dry run complete. No data uploaded.")
        return

    client = Client()
    target_name = args.phoenix_name or args.dataset_name
    dataset = client.datasets.create_dataset(
        dataframe=df,
        name=target_name,
        input_keys=info["input_keys"],
        output_keys=info["output_keys"],
        description=info.get("description", ""),
    )
    print(f"Dataset created successfully: {dataset.id}")


if __name__ == "__main__":
    main()

