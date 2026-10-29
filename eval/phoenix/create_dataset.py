import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
import pandas as pd
import yaml
from phoenix.client import Client

REGISTRY_PATH = Path(__file__).parent / "datasets.yaml"

def main():
    parser = argparse.ArgumentParser(description="Upload XML evaluation datasets to Phoenix")
    parser.add_argument("--dataset-name", required=True, help="Key defined in datasets.yaml")
    parser.add_argument("--phoenix-name", default=None, help="Name inside Phoenix (defaults to key)")
    parser.add_argument("--dry-run", action="store_true", help="Validate XML schema without uploading")
    args = parser.parse_args()

    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        registry = yaml.safe_load(f)["datasets"]

    if args.dataset_name not in registry:
        raise KeyError(f"Dataset '{args.dataset_name}' not registered in datasets.yaml")

    info = registry[args.dataset_name]
    xml_path = Path(__file__).parent / info["xml_path"]

    # Parse XML
    tree = ET.parse(xml_path)
    root = tree.getroot()

    data = []
    for qa_pair in root.findall('qa_pair'):
        question = qa_pair.find('question').text.strip()
        answer = qa_pair.find('answer').text.strip()
        data.append({"query": question, "expected": answer})

    df = pd.DataFrame(data)

    print(f"Validated {len(df)} records in {xml_path}")

    if args.dry_run:
        print("Dry run complete. No data uploaded.")
        print(df.head())
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
