#!/usr/bin/env python3
"""Analyze app usage distribution across registered PAS scenarios.

Creates a pie chart showing which apps are used how many times.
"""

from __future__ import annotations

import argparse
import logging
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from dotenv import load_dotenv

# Load environment variables before importing registry
load_dotenv()

from pas.benchmark.scenario_loader import Split, get_splits_dir, load_scenario_ids_from_file  # noqa: E402
from pas.scenarios.utils.registry import registry  # noqa: E402

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Colorblind-friendly palettes
PALETTES = {
    "set2": [  # ColorBrewer Set2
        "#66C2A5",
        "#FC8D62",
        "#8DA0CB",
        "#E78AC3",
        "#A6D854",
        "#FFD92F",
        "#E5C494",
        "#B3B3B3",
    ],
    "ibm": [  # IBM Color Blind Safe
        "#648FFF",
        "#785EF0",
        "#DC267F",
        "#FE6100",
        "#FFB000",
    ],
    "tol-muted": [  # Paul Tol Muted Extended
        "#332288",  # indigo
        "#88CCEE",  # cyan
        "#44AA99",  # teal
        "#117733",  # green
        "#999933",  # olive
        "#DDCC77",  # sand
        "#CC6677",  # rose
        "#882255",  # wine
        "#AA4499",  # purple
        "#DD77CC",  # pinkish-mauve
        "#7799DD",  # soft blue
        "#66AA55",  # light muted green
    ],
    "pastel": [  # Seaborn Pastel
        "#A1C9F4",  # light blue
        "#FFB482",  # light orange
        "#8DE5A1",  # light green
        "#FF9F9B",  # light red/pink
        "#D0BBFF",  # light purple
        "#DEBB9B",  # light brown
        "#FAB0E4",  # light magenta
        "#CFCFCF",  # light gray
        "#FFFEA3",  # light yellow
        "#B9F2F0",  # light cyan
    ],
}

# Apps to exclude (present in all scenarios)
EXCLUDED_APPS = {"PASAgentUserInterface", "HomeScreenSystem"}


def get_app_usage_from_scenarios(scenario_ids: list[str] | None = None) -> Counter[str]:
    """Analyze registered scenarios and count app usage.

    Args:
        scenario_ids: If provided, only analyze scenarios with these IDs.

    Returns:
        Counter mapping app class names to usage counts.
    """
    app_counter: Counter[str] = Counter()

    # Get all registered scenarios
    all_scenarios = registry.get_all_scenarios()
    logger.info(f"Found {len(all_scenarios)} registered scenarios")

    # Filter by scenario IDs if provided
    if scenario_ids is not None:
        scenario_id_set = set(scenario_ids)
        scenarios_to_analyze = {sid: cls for sid, cls in all_scenarios.items() if sid in scenario_id_set}
    else:
        scenarios_to_analyze = all_scenarios

    for scenario_id, scenario_class in scenarios_to_analyze.items():
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
                    # Abbreviate long names
                    if app_name == "SandboxLocalFileSystem":
                        app_name = "FileSystem"

                    # Filter out ubiquitous apps
                    if app_name in EXCLUDED_APPS:
                        continue

                    app_counter[app_name] += 1

            logger.info(f"Processed scenario: {scenario_id}")

        except Exception as e:
            logger.warning(f"Failed to process scenario {scenario_id}: {e}")

    return app_counter


def create_pie_chart(
    app_counter: Counter[str],
    output_path: str | None = None,
    palette: str = "set2",
) -> None:
    """Create a pie chart of app usage distribution.

    Args:
        app_counter: Counter mapping app names to usage counts.
        output_path: Path to save the chart. If None, displays interactively.
        palette: Color palette name ('set2', 'ibm', or 'tol-muted').
    """
    if not app_counter:
        print("No app data to visualize.")
        return

    # Set seaborn style
    sns.set_theme(style="white")

    # Sort by count (descending) for better visualization
    sorted_items = app_counter.most_common()
    labels = [item[0] for item in sorted_items]
    sizes = [item[1] for item in sorted_items]
    num_apps = len(labels)

    # Get colors from palette (cycle if needed)
    palette_colors = PALETTES.get(palette, PALETTES["set2"])
    colors = [palette_colors[i % len(palette_colors)] for i in range(num_apps)]

    # Create figure
    _fig, ax = plt.subplots(figsize=(8, 8))

    # Create pie chart (returns 3 values when autopct is set)
    wedges, texts, autotexts = ax.pie(  # type: ignore[misc]
        sizes,
        labels=labels,
        autopct=lambda pct: f"{pct:.1f}",
        startangle=90,
        counterclock=False,
        colors=colors,
        wedgeprops={"linewidth": 0.8, "edgecolor": "white"},
        pctdistance=0.75,
        labeldistance=1.05,
    )

    # Style the percentage text (black, inside wedges)
    for autotext in autotexts:
        autotext.set_fontsize(12)
        autotext.set_color("black")

    # Style the labels and manually center them on their wedges
    label_distance = 1.10
    for text, wedge in zip(texts, wedges, strict=True):
        text.set_fontsize(14)
        # Calculate the center angle of the wedge
        angle = (wedge.theta1 + wedge.theta2) / 2
        # Convert to radians for positioning
        angle_rad = np.deg2rad(angle)
        # Calculate position
        x = label_distance * np.cos(angle_rad)
        y = label_distance * np.sin(angle_rad)
        text.set_position((x, y))
        # Set alignment based on angle (in degrees, 0=right, 90=top, 180=left, 270=bottom)
        # Normalize angle to 0-360
        norm_angle = angle % 360
        # Right side (315-45 degrees): left align
        # Left side (135-225 degrees): right align
        # Top/bottom: center align
        if norm_angle >= 315 or norm_angle <= 45:
            text.set_ha("left")
            text.set_va("center")
        elif 135 <= norm_angle <= 225:
            text.set_ha("right")
            text.set_va("center")
        elif 45 < norm_angle < 135:
            text.set_ha("center")
            text.set_va("bottom")
        else:  # 225 < norm_angle < 315
            text.set_ha("center")
            text.set_va("top")

    ax.axis("equal")

    plt.tight_layout()

    # Save or show
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
        print(f"Chart saved to: {output_path}")
    else:
        plt.show()

    plt.close()


def print_summary(app_counter: Counter[str], split_name: str | None = None) -> None:
    """Print a text summary of app usage."""
    total = sum(app_counter.values())
    print("\n" + "=" * 50)
    title = "App Usage Summary"
    if split_name:
        title += f" ({split_name})"
    print(title)
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
        "--split",
        type=str,
        choices=[s.value for s in Split],
        default=None,
        help="Benchmark split to analyze (e.g., 'full', 'ablation').",
    )
    parser.add_argument(
        "--palette",
        type=str,
        choices=list(PALETTES.keys()),
        default="set2",
        help="Color palette to use (default: set2).",
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

    # Load scenario IDs from split if provided
    scenario_ids = None
    split_name = None
    if args.split:
        split = Split(args.split)
        split_file = get_splits_dir() / f"{split.value}.txt"
        scenario_ids = load_scenario_ids_from_file(split_file)
        split_name = split.value
        print(f"Analyzing scenarios from split: {split_name} ({len(scenario_ids)} scenarios)")
    else:
        print("Analyzing all registered scenarios...")

    # Analyze scenarios
    app_counter = get_app_usage_from_scenarios(scenario_ids)

    # Print summary
    print_summary(app_counter, split_name)

    # Create chart
    if not args.no_chart:
        create_pie_chart(app_counter, args.output, args.palette)


if __name__ == "__main__":
    main()
