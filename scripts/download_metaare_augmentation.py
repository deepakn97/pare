"""Download augmentation data from Meta-ARE adaptability dataset for PARE noise generation."""

from __future__ import annotations

import json
from pathlib import Path

from datasets import load_dataset  # type: ignore[import-untyped]

# Configuration
DATASET_NAME = "meta-agents-research-environments/gaia2"
DATASET_CONFIG = "adaptability"
DATASET_SPLIT = "validation"
OUTPUT_FILE = Path(__file__).parent.parent / "data" / "metaare_augmentation_data.json"
NUM_SCENARIOS = 10  # Number of scenarios to aggregate data from

print(f"Downloading augmentation data from {DATASET_NAME}/{DATASET_CONFIG}/{DATASET_SPLIT}")
print(f"Will aggregate data from {NUM_SCENARIOS} scenarios")
print("This may take a moment...")

try:
    dataset = load_dataset(
        DATASET_NAME,
        DATASET_CONFIG,
        split=DATASET_SPLIT,
        streaming=True,
    )

    # Aggregate augmentation data from multiple scenarios
    aggregated_apps = {}

    for i, row in enumerate(dataset):
        if i >= NUM_SCENARIOS:
            break

        scenario_id = row.get("scenario_id", f"unknown_{i}")
        print(f"Processing scenario {i + 1}/{NUM_SCENARIOS}: {scenario_id}")

        data_str = row.get("data", "{}")
        data = json.loads(data_str)
        augmentation = data.get("augmentation", {})

        if not augmentation or "apps" not in augmentation:
            print("  No augmentation data found, skipping")
            continue

        # Aggregate data by app type
        for app_data in augmentation["apps"]:
            app_name = app_data.get("name", "unknown")
            app_state = app_data.get("app_state", {})

            if app_name not in aggregated_apps:
                aggregated_apps[app_name] = {
                    "name": app_name,
                    "app_state": {},
                }

            # Merge email data (deduplicate by subject+sender+content)
            if "folders" in app_state:
                if "folders" not in aggregated_apps[app_name]["app_state"]:
                    aggregated_apps[app_name]["app_state"]["folders"] = {"INBOX": {"emails": []}}
                    aggregated_apps[app_name]["email_seen"] = set()

                inbox_emails = app_state.get("folders", {}).get("INBOX", {}).get("emails", [])
                added = 0
                for email in inbox_emails:
                    # Create content signature for deduplication
                    email_sig = (email.get("subject"), email.get("sender"), email.get("content", ""))
                    if email_sig not in aggregated_apps[app_name]["email_seen"]:
                        aggregated_apps[app_name]["app_state"]["folders"]["INBOX"]["emails"].append(email)
                        aggregated_apps[app_name]["email_seen"].add(email_sig)
                        added += 1
                if added > 0:
                    print(f"  Added {added} unique emails from {app_name}")

            # Merge messaging data (deduplicate by conversation content)
            if "conversations" in app_state:
                if "conversations" not in aggregated_apps[app_name]["app_state"]:
                    aggregated_apps[app_name]["app_state"]["conversations"] = {}
                    aggregated_apps[app_name]["conv_seen"] = set()

                conversations = app_state["conversations"]
                added = 0
                for conv_id, conv_data in conversations.items():
                    # Create content signature for deduplication
                    messages = conv_data.get("messages", [])
                    conv_sig = tuple((m.get("sender"), m.get("content", "")) for m in messages)

                    if conv_sig not in aggregated_apps[app_name]["conv_seen"]:
                        unique_conv_id = f"{scenario_id}_{conv_id}"
                        aggregated_apps[app_name]["app_state"]["conversations"][unique_conv_id] = conv_data
                        aggregated_apps[app_name]["conv_seen"].add(conv_sig)
                        added += 1

                if added > 0:
                    print(f"  Added {added} unique conversations from {app_name}")

            # Merge shopping data (deduplicate by product name)
            if "products" in app_state:
                if "products" not in aggregated_apps[app_name]["app_state"]:
                    aggregated_apps[app_name]["app_state"]["products"] = {}
                    aggregated_apps[app_name]["product_seen"] = set()

                products = app_state["products"]
                added = 0
                for product_id, product_data in products.items():
                    # Create content signature for deduplication
                    product_name = product_data.get("name", "")

                    if product_name not in aggregated_apps[app_name]["product_seen"]:
                        unique_product_id = f"{scenario_id}_{product_id}"
                        aggregated_apps[app_name]["app_state"]["products"][unique_product_id] = product_data
                        aggregated_apps[app_name]["product_seen"].add(product_name)
                        added += 1

                if added > 0:
                    print(f"  Added {added} unique products from {app_name}")

    # Prepare final structure (clean up deduplication tracking sets)
    for app_data in aggregated_apps.values():
        app_data.pop("email_seen", None)
        app_data.pop("conv_seen", None)
        app_data.pop("product_seen", None)

    final_augmentation_data = {"apps": list(aggregated_apps.values())}

    # Statistics
    print(f"\n{'=' * 80}")
    print("AGGREGATION SUMMARY")
    print(f"{'=' * 80}")
    for app_data in final_augmentation_data["apps"]:
        app_name = app_data["name"]
        app_state = app_data["app_state"]

        if "folders" in app_state:
            email_count = len(app_state["folders"]["INBOX"]["emails"])
            print(f"{app_name}: {email_count} emails")

        if "conversations" in app_state:
            conv_count = len(app_state["conversations"])
            total_messages = sum(len(conv.get("messages", [])) for conv in app_state["conversations"].values())
            print(f"{app_name}: {conv_count} conversations, {total_messages} messages")

        if "products" in app_state:
            product_count = len(app_state["products"])
            total_variants = sum(len(p.get("variants", {})) for p in app_state["products"].values())
            print(f"{app_name}: {product_count} products, {total_variants} variants")

    # Save to file
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(final_augmentation_data, f, indent=2)

    print(f"\n{'=' * 80}")
    print(f"Saved augmentation data to: {OUTPUT_FILE}")
    print(f"File size: {OUTPUT_FILE.stat().st_size / 1024:.2f} KB")
    print(f"{'=' * 80}")

except Exception as e:
    print(f"\nError: {e}")
    print("\nMake sure you have:")
    print("1. Installed datasets: uv pip install datasets")
    print("2. Authenticated with HuggingFace: huggingface-cli login")
    print("3. Access to the Meta-ARE dataset")
