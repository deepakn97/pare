#!/usr/bin/env python3
"""Generate plots for robustness metrics across tool failure probability and environment noise.

Creates two figures:
1. Proposal rate, acceptance rate, and success rate vs tool failure probability
2. Proposal rate, acceptance rate, and success rate vs environment noise (events per minute)

Usage:
    python scripts/plots/plot_ablation_robustness.py --results-dir RESULTS_DIR --output-dir OUTPUT_DIR
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

# Model display names
MODEL_DISPLAY_NAMES = {
    "claude-4.5-sonnet": "Claude 4.5 Sonnet",
    "qwen-3-4b-it": "Qwen3-4B",
    "gemma-3-4b-it": "Gemma3-4B",
    "llama-3.2-3b-it": "Llama3.2-3B",
}

# Markers for different models
MODEL_MARKERS = {
    "claude-4.5-sonnet": "o",
    "qwen-3-4b-it": "s",
    "gemma-3-4b-it": "^",
    "llama-3.2-3b-it": "D",
}

# Colors for different models (colorblind-friendly)
MODEL_COLORS = {
    "claude-4.5-sonnet": "#0072B2",  # blue
    "qwen-3-4b-it": "#E69F00",  # orange
    "gemma-3-4b-it": "#009E73",  # green
    "llama-3.2-3b-it": "#CC79A7",  # pink
}


def extract_model_name(proactive_model: str) -> str:
    """Extract the model name from the proactive_model field.

    Args:
        proactive_model: e.g., "observe-execute_qwen-3-4b-it_qwen-3-4b-it"

    Returns:
        Model name, e.g., "qwen-3-4b-it"
    """
    # Pattern: observe-execute_{model}_{model}
    match = re.search(r"observe-execute_([^_]+(?:-[^_]+)*)_", proactive_model)
    if match:
        return match.group(1)
    return proactive_model


def load_combined_results(results_dir: Path) -> list[dict[str, Any]]:
    """Load results from combined_result.json."""
    combined_file = results_dir / "combined_result.json"
    if not combined_file.exists():
        raise FileNotFoundError(f"Combined results file not found: {combined_file}")

    with open(combined_file) as f:
        data = json.load(f)

    return data["per_config_results"]


def prepare_tfp_data(
    results: list[dict[str, Any]],
) -> dict[str, dict[str, list[float]]]:
    """Prepare data for tool failure probability plots.

    Filters results where num_env_events_per_minute == 0.

    Returns:
        Dictionary mapping model name to metrics:
        {model: {"tfp": [...], "proposal_rate": [...], "acceptance_rate": [...], "success_rate": [...]}}
    """
    data_by_model: dict[str, dict[str, list[float]]] = {}

    for result in results:
        # Only include results with no environment noise
        if result.get("num_env_events_per_minute", 0) != 0:
            continue

        model = extract_model_name(result["proactive_model"])
        tfp = result["tool_failure_probability"]
        proposal_rate = result["aggregate_proposal_rate"] * 100
        acceptance_rate = min(result["aggregate_acceptance_rate"], 1.0) * 100
        success_rate = result["success_rate"]

        if model not in data_by_model:
            data_by_model[model] = {"tfp": [], "proposal_rate": [], "acceptance_rate": [], "success_rate": []}

        data_by_model[model]["tfp"].append(tfp)
        data_by_model[model]["proposal_rate"].append(proposal_rate)
        data_by_model[model]["acceptance_rate"].append(acceptance_rate)
        data_by_model[model]["success_rate"].append(success_rate)

    # Sort each model's data by tfp
    for model in data_by_model:
        sorted_indices = sorted(range(len(data_by_model[model]["tfp"])), key=lambda i: data_by_model[model]["tfp"][i])
        for key in data_by_model[model]:
            data_by_model[model][key] = [data_by_model[model][key][i] for i in sorted_indices]

    return data_by_model


def prepare_enmi_data(
    results: list[dict[str, Any]],
) -> dict[str, dict[str, list[float]]]:
    """Prepare data for environment noise plots.

    Filters results where tool_failure_probability == 0.0.

    Returns:
        Dictionary mapping model name to metrics:
        {model: {"enmi": [...], "proposal_rate": [...], "acceptance_rate": [...], "success_rate": [...]}}
    """
    data_by_model: dict[str, dict[str, list[float]]] = {}

    for result in results:
        # Only include results with no tool failure
        if result.get("tool_failure_probability", 0.0) != 0.0:
            continue

        model = extract_model_name(result["proactive_model"])
        enmi = result.get("num_env_events_per_minute", 0)
        proposal_rate = result["aggregate_proposal_rate"] * 100
        acceptance_rate = min(result["aggregate_acceptance_rate"], 1.0) * 100
        success_rate = result["success_rate"]

        if model not in data_by_model:
            data_by_model[model] = {"enmi": [], "proposal_rate": [], "acceptance_rate": [], "success_rate": []}

        data_by_model[model]["enmi"].append(enmi)
        data_by_model[model]["proposal_rate"].append(proposal_rate)
        data_by_model[model]["acceptance_rate"].append(acceptance_rate)
        data_by_model[model]["success_rate"].append(success_rate)

    # Sort each model's data by enmi
    for model in data_by_model:
        sorted_indices = sorted(range(len(data_by_model[model]["enmi"])), key=lambda i: data_by_model[model]["enmi"][i])
        for key in data_by_model[model]:
            data_by_model[model][key] = [data_by_model[model][key][i] for i in sorted_indices]

    return data_by_model


def plot_tfp_metrics(
    data_by_model: dict[str, dict[str, list[float]]],
    output_path: Path | None = None,
) -> None:
    """Plot proposal rate, acceptance rate, and success rate vs tool failure probability."""
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))

    # Style settings
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.size"] = 10

    # Plot 1: Proposal Rate vs TFP
    ax1 = axes[0]
    lines = []
    labels = []

    for model in sorted(data_by_model.keys()):
        metrics = data_by_model[model]
        display_name = MODEL_DISPLAY_NAMES.get(model, model)
        marker = MODEL_MARKERS.get(model, "o")
        color = MODEL_COLORS.get(model, "#333333")

        (line,) = ax1.plot(
            metrics["tfp"],
            metrics["proposal_rate"],
            marker=marker,
            label=display_name,
            color=color,
            linewidth=1.5,
            markersize=6,
            markerfacecolor=color,
            markeredgecolor=color,
        )
        lines.append(line)
        labels.append(display_name)

    ax1.set_xlabel("Tool Failure Probability", fontsize=11)
    ax1.set_ylabel("Proposal Rate (%)", fontsize=11)
    ax1.set_xlim(-0.02, 0.42)
    ax1.set_ylim(0, None)
    ax1.set_xticks([0.0, 0.1, 0.2, 0.4])

    # Grid style
    ax1.grid(True, linestyle="--", alpha=0.7, color="#cccccc")
    ax1.set_axisbelow(True)

    # Spine style (darker and thicker)
    for spine in ax1.spines.values():
        spine.set_color("#666666")
        spine.set_linewidth(1.2)

    # Plot 2: Acceptance Rate vs TFP
    ax2 = axes[1]

    for model in sorted(data_by_model.keys()):
        metrics = data_by_model[model]
        display_name = MODEL_DISPLAY_NAMES.get(model, model)
        marker = MODEL_MARKERS.get(model, "o")
        color = MODEL_COLORS.get(model, "#333333")

        ax2.plot(
            metrics["tfp"],
            metrics["acceptance_rate"],
            marker=marker,
            label=display_name,
            color=color,
            linewidth=1.5,
            markersize=6,
            markerfacecolor=color,
            markeredgecolor=color,
        )

    ax2.set_xlabel("Tool Failure Probability", fontsize=11)
    ax2.set_ylabel("Acceptance Rate (%)", fontsize=11)
    ax2.set_xlim(-0.02, 0.42)
    ax2.set_ylim(0, 105)
    ax2.set_xticks([0.0, 0.1, 0.2, 0.4])

    # Grid style
    ax2.grid(True, linestyle="--", alpha=0.7, color="#cccccc")
    ax2.set_axisbelow(True)

    # Spine style (darker and thicker)
    for spine in ax2.spines.values():
        spine.set_color("#666666")
        spine.set_linewidth(1.2)

    # Plot 3: Success Rate vs TFP
    ax3 = axes[2]

    for model in sorted(data_by_model.keys()):
        metrics = data_by_model[model]
        display_name = MODEL_DISPLAY_NAMES.get(model, model)
        marker = MODEL_MARKERS.get(model, "o")
        color = MODEL_COLORS.get(model, "#333333")

        ax3.plot(
            metrics["tfp"],
            metrics["success_rate"],
            marker=marker,
            label=display_name,
            color=color,
            linewidth=1.5,
            markersize=6,
            markerfacecolor=color,
            markeredgecolor=color,
        )

    ax3.set_xlabel("Tool Failure Probability", fontsize=11)
    ax3.set_ylabel("Success Rate (%)", fontsize=11)
    ax3.set_xlim(-0.02, 0.42)
    ax3.set_ylim(0, None)
    ax3.set_xticks([0.0, 0.1, 0.2, 0.4])

    # Grid style
    ax3.grid(True, linestyle="--", alpha=0.7, color="#cccccc")
    ax3.set_axisbelow(True)

    # Spine style (darker and thicker)
    for spine in ax3.spines.values():
        spine.set_color("#666666")
        spine.set_linewidth(1.2)

    # Legend at the bottom in horizontal fashion
    fig.legend(
        lines,
        labels,
        loc="lower center",
        ncol=len(labels),
        frameon=True,
        fancybox=False,
        edgecolor="#666666",
        fontsize=10,
        bbox_to_anchor=(0.5, -0.02),
    )

    plt.tight_layout()
    plt.subplots_adjust(bottom=0.18)

    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
        print(f"Saved: {output_path}")
    else:
        plt.show()

    plt.close()


def plot_enmi_metrics(
    data_by_model: dict[str, dict[str, list[float]]],
    output_path: Path | None = None,
) -> None:
    """Plot proposal rate, acceptance rate, and success rate vs environment noise."""
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))

    # Style settings
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.size"] = 10

    # Collect x values to determine axis ticks
    all_enmi_values: set[float] = set()
    for metrics in data_by_model.values():
        all_enmi_values.update(metrics["enmi"])
    enmi_ticks = sorted(all_enmi_values)

    # Plot 1: Proposal Rate vs ENMI
    ax1 = axes[0]
    lines = []
    labels = []

    for model in sorted(data_by_model.keys()):
        metrics = data_by_model[model]
        display_name = MODEL_DISPLAY_NAMES.get(model, model)
        marker = MODEL_MARKERS.get(model, "o")
        color = MODEL_COLORS.get(model, "#333333")

        (line,) = ax1.plot(
            metrics["enmi"],
            metrics["proposal_rate"],
            marker=marker,
            label=display_name,
            color=color,
            linewidth=1.5,
            markersize=6,
            markerfacecolor=color,
            markeredgecolor=color,
        )
        lines.append(line)
        labels.append(display_name)

    ax1.set_xlabel("Environment Noise (events/min)", fontsize=11)
    ax1.set_ylabel("Proposal Rate (%)", fontsize=11)
    ax1.set_ylim(0, None)
    ax1.set_xticks(enmi_ticks)

    # Grid style
    ax1.grid(True, linestyle="--", alpha=0.7, color="#cccccc")
    ax1.set_axisbelow(True)

    # Spine style (darker and thicker)
    for spine in ax1.spines.values():
        spine.set_color("#666666")
        spine.set_linewidth(1.2)

    # Plot 2: Acceptance Rate vs ENMI
    ax2 = axes[1]

    for model in sorted(data_by_model.keys()):
        metrics = data_by_model[model]
        display_name = MODEL_DISPLAY_NAMES.get(model, model)
        marker = MODEL_MARKERS.get(model, "o")
        color = MODEL_COLORS.get(model, "#333333")

        ax2.plot(
            metrics["enmi"],
            metrics["acceptance_rate"],
            marker=marker,
            label=display_name,
            color=color,
            linewidth=1.5,
            markersize=6,
            markerfacecolor=color,
            markeredgecolor=color,
        )

    ax2.set_xlabel("Environment Noise (events/min)", fontsize=11)
    ax2.set_ylabel("Acceptance Rate (%)", fontsize=11)
    ax2.set_ylim(0, 105)
    ax2.set_xticks(enmi_ticks)

    # Grid style
    ax2.grid(True, linestyle="--", alpha=0.7, color="#cccccc")
    ax2.set_axisbelow(True)

    # Spine style (darker and thicker)
    for spine in ax2.spines.values():
        spine.set_color("#666666")
        spine.set_linewidth(1.2)

    # Plot 3: Success Rate vs ENMI
    ax3 = axes[2]

    for model in sorted(data_by_model.keys()):
        metrics = data_by_model[model]
        display_name = MODEL_DISPLAY_NAMES.get(model, model)
        marker = MODEL_MARKERS.get(model, "o")
        color = MODEL_COLORS.get(model, "#333333")

        ax3.plot(
            metrics["enmi"],
            metrics["success_rate"],
            marker=marker,
            label=display_name,
            color=color,
            linewidth=1.5,
            markersize=6,
            markerfacecolor=color,
            markeredgecolor=color,
        )

    ax3.set_xlabel("Environment Noise (events/min)", fontsize=11)
    ax3.set_ylabel("Success Rate (%)", fontsize=11)
    ax3.set_ylim(0, None)
    ax3.set_xticks(enmi_ticks)

    # Grid style
    ax3.grid(True, linestyle="--", alpha=0.7, color="#cccccc")
    ax3.set_axisbelow(True)

    # Spine style (darker and thicker)
    for spine in ax3.spines.values():
        spine.set_color("#666666")
        spine.set_linewidth(1.2)

    # Legend at the bottom in horizontal fashion
    fig.legend(
        lines,
        labels,
        loc="lower center",
        ncol=len(labels),
        frameon=True,
        fancybox=False,
        edgecolor="#666666",
        fontsize=10,
        bbox_to_anchor=(0.5, -0.02),
    )

    plt.tight_layout()
    plt.subplots_adjust(bottom=0.18)

    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
        print(f"Saved: {output_path}")
    else:
        plt.show()

    plt.close()


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate plots for robustness metrics vs tool failure probability and environment noise."
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        required=True,
        help="Directory containing combined_result.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for figures (default: same as results-dir)",
    )

    args = parser.parse_args()

    output_dir = args.output_dir or args.results_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load results
    print(f"Loading results from: {args.results_dir}")
    results = load_combined_results(args.results_dir)

    # Prepare and plot TFP data
    tfp_data = prepare_tfp_data(results)
    if tfp_data:
        print(f"\nTool Failure Probability data - Found {len(tfp_data)} models:")
        for model in sorted(tfp_data.keys()):
            print(f"  - {model}: {len(tfp_data[model]['tfp'])} data points")
        plot_tfp_metrics(tfp_data, output_dir / "ablation_robustness_tfp.pdf")
    else:
        print("No TFP data found (no results with num_env_events_per_minute == 0)")

    # Prepare and plot ENMI data
    enmi_data = prepare_enmi_data(results)
    if enmi_data:
        # Check if there's more than one unique enmi value
        all_enmi = set()
        for metrics in enmi_data.values():
            all_enmi.update(metrics["enmi"])
        if len(all_enmi) > 1:
            print(f"\nEnvironment Noise data - Found {len(enmi_data)} models:")
            for model in sorted(enmi_data.keys()):
                print(f"  - {model}: {len(enmi_data[model]['enmi'])} data points")
            plot_enmi_metrics(enmi_data, output_dir / "ablation_robustness_enmi.pdf")
        else:
            print(f"\nEnvironment Noise data has only one value ({all_enmi}), skipping plot")
    else:
        print("No ENMI data found (no results with tool_failure_probability == 0.0)")

    print("\nDone!")


if __name__ == "__main__":
    main()
