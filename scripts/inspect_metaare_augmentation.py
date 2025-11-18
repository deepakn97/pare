"""Script to inspect Meta-ARE augmentation data from HuggingFace datasets."""

from __future__ import annotations

import json

from datasets import load_dataset  # type: ignore[import-untyped]

# Load Meta-ARE dataset (using validation split which has augmentation data)
# Dataset name from Meta-ARE benchmark
dataset_name = "meta-agents-research-environments/gaia2"
dataset_config = "adaptability"
dataset_split = "validation"

print(f"Loading dataset: {dataset_name}/{dataset_config}/{dataset_split}")
print("This may take a moment to download...")

try:
    dataset = load_dataset(
        dataset_name,
        dataset_config,
        split=dataset_split,
        streaming=True,
    )

    print("\n" + "=" * 80)
    print("COLLECTING APP TYPES ACROSS SCENARIOS")
    print("=" * 80 + "\n")

    # Collect all app types and store one example per app type
    app_examples = {}
    num_scenarios_to_check = 20

    for i, row in enumerate(dataset):
        if i >= num_scenarios_to_check:
            break

        data_str = row.get("data", "{}")
        data = json.loads(data_str)
        augmentation = data.get("augmentation", {})

        if not augmentation or "apps" not in augmentation:
            continue

        for app_data in augmentation["apps"]:
            app_name = app_data.get("name", "unknown")

            # Store first example of each app type
            if app_name not in app_examples:
                app_examples[app_name] = app_data

        print(f"Processed {i + 1} scenarios, found {len(app_examples)} unique app types")

    # Display results
    print(f"\n{'=' * 80}")
    print(f"UNIQUE APP TYPES FOUND: {list(app_examples.keys())}")
    print(f"{'=' * 80}\n")

    # Show one example per app type
    for app_name, app_data in app_examples.items():
        app_state = app_data.get("app_state", {})

        print(f"\n{'=' * 80}")
        print(f"APP: {app_name}")
        print(f"{'=' * 80}")
        print(f"App state structure keys: {list(app_state.keys())}")

        # Show email example
        if "folders" in app_state and "INBOX" in app_state["folders"]:
            emails = app_state["folders"]["INBOX"].get("emails", [])
            if emails:
                print("\nExample email:")
                print(json.dumps(emails[0], indent=2))

        # Show messaging example
        if "conversations" in app_state:
            conversations = app_state["conversations"]
            if conversations:
                conv_id = next(iter(conversations.keys()))
                print("\nExample conversation:")
                print(json.dumps(conversations[conv_id], indent=2))

        # Show shopping example
        if "products" in app_state:
            products = app_state["products"]
            if products:
                product_id = next(iter(products.keys()))
                print("\nExample product:")
                print(json.dumps(products[product_id], indent=2))

        print()


except Exception as e:
    print(f"\nError loading dataset: {e}")
    print("\nNote: You may need to:")
    print("1. Install datasets: pip install datasets")
    print("2. Authenticate with HuggingFace: huggingface-cli login")
    print("3. Have access to the Meta-ARE benchmark dataset")
