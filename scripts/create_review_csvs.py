"""Script to create scenario review CSV files and organize scenarios by reviewer."""

import csv
import random
import shutil
from pathlib import Path

# Define paths
BASE_DIR = Path(__file__).parent.parent
SCENARIOS_DIR = BASE_DIR / "pas" / "scenarios"
GENERATED_SCENARIOS_DIR = SCENARIOS_DIR / "generated_scenarios_w_claude_agent"
STAGING_DIR = SCENARIOS_DIR / "staging"
REVIEWS_DIR = SCENARIOS_DIR / "reviews"

# Reviewers
REVIEWERS = ["Deepak", "Cheng", "Chang"]

# Set seed for reproducibility
random.seed(42)


def get_scenarios_from_folder(folder: Path, source_name: str) -> list[dict[str, str | Path]]:
    """Get all scenario names and file paths from a folder."""
    scenarios = []
    if folder.exists():
        for file in sorted(folder.glob("*.py")):
            if file.name.startswith("__"):
                continue
            scenarios.append({
                "name": file.stem,
                "source": source_name,
                "file_path": file,
            })
    return scenarios


def distribute_scenarios(
    scenarios: list[dict[str, str | Path]], reviewers: list[str]
) -> dict[str, list[dict[str, str | Path]]]:
    """Randomly distribute scenarios among reviewers."""
    shuffled = scenarios.copy()
    random.shuffle(shuffled)

    assignments: dict[str, list[dict[str, str | Path]]] = {reviewer: [] for reviewer in reviewers}

    for i, scenario in enumerate(shuffled):
        reviewer = reviewers[i % len(reviewers)]
        assignments[reviewer].append(scenario)

    return assignments


def setup_reviewer_folder(reviewer: str, scenarios: list[dict[str, str | Path]], reviews_dir: Path) -> None:
    """Move scenario files and create CSV in reviewer's folder."""
    reviewer_dir = reviews_dir / reviewer.lower()
    reviewer_dir.mkdir(parents=True, exist_ok=True)

    # Move scenario files
    for scenario in scenarios:
        src_path = scenario["file_path"]
        if isinstance(src_path, Path) and src_path.exists():
            dst_path = reviewer_dir / src_path.name
            shutil.move(str(src_path), str(dst_path))

    # Create CSV in the same folder
    csv_file = reviewer_dir / "scenario_review.csv"
    folder_path = f"pas/scenarios/reviews/{reviewer.lower()}"

    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Scenario Name", "Folder", "Review Status", "Comments"])

        sorted_scenarios = sorted(scenarios, key=lambda x: str(x["name"]))
        for scenario in sorted_scenarios:
            writer.writerow([scenario["name"], folder_path, "", ""])

    print(f"{reviewer}: {len(scenarios)} scenarios -> {reviewer_dir}/")


def main() -> None:
    """Main function to organize scenarios and create review CSV files."""
    # Collect all scenarios
    all_scenarios: list[dict[str, str | Path]] = []

    # Get scenarios from generated_scenarios_w_claude_agent
    generated_scenarios = get_scenarios_from_folder(GENERATED_SCENARIOS_DIR, "generated_scenarios_w_claude_agent")
    all_scenarios.extend(generated_scenarios)
    print(f"Found {len(generated_scenarios)} scenarios in generated_scenarios_w_claude_agent")

    # Get scenarios from staging
    staging_scenarios = get_scenarios_from_folder(STAGING_DIR, "staging")
    all_scenarios.extend(staging_scenarios)
    print(f"Found {len(staging_scenarios)} scenarios in staging")

    print(f"Total scenarios: {len(all_scenarios)}")
    print()

    # Distribute among reviewers
    assignments = distribute_scenarios(all_scenarios, REVIEWERS)

    # Create reviews directory and setup each reviewer's folder
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)

    print("Setting up reviewer folders...")
    for reviewer, scenarios in assignments.items():
        setup_reviewer_folder(reviewer, scenarios, REVIEWS_DIR)

    print()
    print("Done! Each reviewer folder contains scenarios and a scenario_review.csv file.")


if __name__ == "__main__":
    main()
