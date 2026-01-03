#!/usr/bin/env python3
"""Analyze app usage distribution across registered PAS scenarios.

Creates a pie chart showing which apps are used how many times (as percentage).
"""

from __future__ import annotations

import argparse
import logging
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import seaborn as sns
from dotenv import load_dotenv

# Load environment variables before importing registry
load_dotenv()

from pas.scenarios.utils.registry import registry  # noqa: E402

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def get_app_usage_from_scenarios() -> Counter[str]:
    """Analyze all registered scenarios and count app usage.

    Returns:
        Counter mapping app class names to usage counts.
    """
    app_counter: Counter[str] = Counter()

    # Get all registered scenarios
    all_scenarios = registry.get_all_scenarios()
    logger.info(f"Found {len(all_scenarios)} registered scenarios")

    for scenario_id, scenario_class in all_scenarios.items():
        try:
            # Instantiate the scenario
            scenario = scenario_class()

            # Initialize apps (some scenarios need sandbox_dir)
            scenario.init_and_populate_apps(sandbox_dir=Path("sandbox"))

            # Count apps by class name
            if scenario.apps:
                for app in scenario.apps:
                    app_name = app.__class__.__name__
                    # Clean up app names for display
                    if app_name.startswith("Stateful"):
                        app_name = app_name[8:]  # Remove "Stateful" prefix
                    if app_name.endswith("App"):
                        app_name = app_name[:-3]  # Remove "App" suffix
                    app_counter[app_name] += 1

            logger.info(f"Processed scenario: {scenario_id}")

        except Exception as e:
            logger.warning(f"Failed to process scenario {scenario_id}: {e}")

    return app_counter


def create_pie_chart(
    app_counter: Counter[str],
    output_path: str | None = None,
    title: str = "App Usage Distribution in PAS",
) -> None:
    """Create a pie chart of app usage distribution.

    Args:
        app_counter: Counter mapping app names to usage counts.
        output_path: Path to save the chart. If None, displays interactively.
        title: Title for the chart.
    """
    if not app_counter:
        print("No app data to visualize.")
        return

    # Set seaborn style
    sns.set_theme(style="whitegrid")

    # Sort by count (descending) for better visualization
    sorted_items = app_counter.most_common()
    labels = [item[0] for item in sorted_items]
    sizes = [item[1] for item in sorted_items]
    total = sum(sizes)

    # Get seaborn deep color palette
    colors = sns.color_palette("deep", n_colors=len(labels))

    # Create figure
    fig, ax = plt.subplots(figsize=(10, 8))

    # Create pie chart with percentage labels
    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=labels,
        autopct=lambda pct: f"{pct:.1f}%" if pct > 3 else "",
        startangle=90,
        counterclock=False,
        colors=colors,
    )

    # Style the percentage text
    for autotext in autotexts:
        autotext.set_fontsize(9)
        autotext.set_fontweight("bold")

    # Add title
    ax.set_title(title, fontsize=14, fontweight="bold")

    # Add legend with counts
    legend_labels = [f"{label} ({count})" for label, count in sorted_items]
    ax.legend(
        wedges,
        legend_labels,
        title="Apps (count)",
        loc="center left",
        bbox_to_anchor=(1, 0, 0.5, 1),
    )

    plt.tight_layout()

    # Save or show
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        print(f"Chart saved to: {output_path}")
    else:
        plt.show()


def print_summary(app_counter: Counter[str]) -> None:
    """Print a text summary of app usage."""
    total = sum(app_counter.values())
    print("\n" + "=" * 50)
    print("App Usage Summary")
    print("=" * 50)
    print(f"Total app instances across all scenarios: {total}")
    print(f"Number of unique apps: {len(app_counter)}")
    print("-" * 50)
    print(f"{'App Name':<25} {'Count':>8} {'Percentage':>12}")
    print("-" * 50)

    for app_name, count in app_counter.most_common():
        percentage = count / total * 100
        print(f"{app_name:<25} {count:>8} {percentage:>11.1f}%")

    print("=" * 50)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Analyze app usage distribution across PAS scenarios.")
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Output path for the pie chart (e.g., app_usage.png). If not specified, displays interactively.",
    )
    parser.add_argument(
        "--title",
        type=str,
        default="App Usage Distribution in PAS",
        help="Title for the pie chart.",
    )
    parser.add_argument(
        "--no-chart",
        action="store_true",
        help="Only print text summary, skip chart generation.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    # Analyze scenarios
    print("Analyzing registered scenarios...")
    app_counter = get_app_usage_from_scenarios()

    # Print summary
    print_summary(app_counter)

    # Create chart
    if not args.no_chart:
        create_pie_chart(app_counter, args.output, args.title)


if __name__ == "__main__":
    main()
