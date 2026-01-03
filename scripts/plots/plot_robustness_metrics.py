#!/usr/bin/env python3
"""Generate plots for proposal rate and acceptance rate across robustness conditions.

Creates two figures:
1. Proposal Rate and Acceptance Rate vs Tool Failure Probability
2. Proposal Rate and Acceptance Rate vs Environmental Noise

Usage:
    python analyses/plot_robustness_metrics.py [--output-dir OUTPUT_DIR]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import seaborn as sns

# Type aliases for clarity
ModelMetricsData = dict[str, dict[str, list[float]]]  # model -> {metric_name -> [values]}

# Open-source models use different markers (specific patterns)
OPEN_SOURCE_MODEL_PATTERNS = {"llama-3.2", "qwen"}
MARKER_OPEN_SOURCE = "s"  # square
MARKER_CLOSED_SOURCE = "o"  # circle


def get_marker_for_model(model: str) -> str:
    """Return marker style based on whether model is open-source."""
    model_lower = model.lower()
    for pattern in OPEN_SOURCE_MODEL_PATTERNS:
        if pattern in model_lower:
            return MARKER_OPEN_SOURCE
    return MARKER_CLOSED_SOURCE


def load_metrics(results_dir: Path, pattern: str) -> list[dict[str, Any]]:
    """Load metrics from JSON files matching a pattern."""
    metrics: list[dict[str, Any]] = []
    for file_path in results_dir.glob(pattern):
        with open(file_path) as f:
            data = json.load(f)
            # Extract config from filename
            filename = file_path.stem
            metrics.append({"filename": filename, "data": data})
    return metrics


def extract_tfp_from_filename(filename: str) -> float:
    """Extract tool failure probability from filename."""
    match = re.search(r"tfp_(\d+\.?\d*)", filename)
    if match:
        return float(match.group(1))
    return 0.0


def extract_enmi_from_filename(filename: str) -> float:
    """Extract environmental noise per minute from filename."""
    match = re.search(r"enmi_(\d+\.?\d*)", filename)
    if match:
        return float(match.group(1))
    return 0.0


def aggregate_metrics_by_model(data: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Aggregate metrics by model from a single results file."""
    model_metrics: dict[str, dict[str, float]] = {}
    for m in data["model_metrics"]:
        # Cap acceptance rate at 100% (can exceed due to tool failure retries)
        acceptance_rate = min(m["acceptance_rate"], 1.0) * 100
        model_metrics[m["model"]] = {
            "proposal_rate": m["proposal_rate"] * 100,
            "acceptance_rate": acceptance_rate,
            "accuracy": m["accuracy"] * 100,
        }
    return model_metrics


def prepare_tfp_data(results_dir: Path) -> ModelMetricsData:
    """Prepare data for tool failure probability plots."""
    # Load base results (tfp=0.0)
    base_file = (
        results_dir / "paper_draft_user_gpt-5-mini_mt_10_umi_1_omi_5_emi_10_enmi_0.0_es_42_tfp_0.0_noise_subset.json"
    )

    # Load TFP sweep results
    tfp_files = list(results_dir.glob("*_tfp_*_noise_subset.json"))
    tfp_files = [f for f in tfp_files if "enmi_0.0" in f.name]

    data_by_model: ModelMetricsData = {}

    for file_path in sorted(tfp_files, key=lambda x: extract_tfp_from_filename(x.name)):
        tfp = extract_tfp_from_filename(file_path.name)

        with open(file_path) as f:
            data = json.load(f)

        model_metrics = aggregate_metrics_by_model(data)

        for model, metrics in model_metrics.items():
            if model not in data_by_model:
                data_by_model[model] = {"tfp": [], "proposal_rate": [], "acceptance_rate": []}

            data_by_model[model]["tfp"].append(tfp)
            data_by_model[model]["proposal_rate"].append(metrics["proposal_rate"])
            data_by_model[model]["acceptance_rate"].append(metrics["acceptance_rate"])

    return data_by_model


def prepare_noise_data(results_dir: Path) -> ModelMetricsData:
    """Prepare data for environmental noise plots."""
    # Load noise sweep results (including base with enmi=0.0)
    noise_files = list(results_dir.glob("*_noise_subset.json"))
    noise_files = [f for f in noise_files if "tfp_0.0" in f.name]

    data_by_model: ModelMetricsData = {}

    for file_path in sorted(noise_files, key=lambda x: extract_enmi_from_filename(x.name)):
        enmi = extract_enmi_from_filename(file_path.name)

        with open(file_path) as f:
            data = json.load(f)

        model_metrics = aggregate_metrics_by_model(data)

        for model, metrics in model_metrics.items():
            if model not in data_by_model:
                data_by_model[model] = {"enmi": [], "proposal_rate": [], "acceptance_rate": []}

            data_by_model[model]["enmi"].append(enmi)
            data_by_model[model]["proposal_rate"].append(metrics["proposal_rate"])
            data_by_model[model]["acceptance_rate"].append(metrics["acceptance_rate"])

    return data_by_model


def plot_tfp_metrics(
    data_by_model: ModelMetricsData, output_path: Path | None = None, exclude_models: list[str] | None = None
) -> None:
    """Plot proposal rate and acceptance rate vs tool failure probability."""
    exclude_models = exclude_models or []
    filtered_data = {k: v for k, v in data_by_model.items() if k not in exclude_models}

    sns.set_theme(style="whitegrid")
    colors = sns.color_palette("deep", n_colors=len(filtered_data))

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Plot 1: Proposal Rate vs TFP
    ax1 = axes[0]
    lines = []
    labels = []
    for i, (model, metrics) in enumerate(sorted(filtered_data.items())):
        marker = get_marker_for_model(model)
        (line,) = ax1.plot(
            metrics["tfp"],
            metrics["proposal_rate"],
            marker=marker,
            label=model,
            color=colors[i],
            linewidth=2,
            markersize=5,
        )
        lines.append(line)
        labels.append(model)

    ax1.set_xlabel("Tool Failure Probability", fontsize=12)
    ax1.set_ylabel("Proposal Rate (%)", fontsize=12)
    ax1.set_title("Proposal Rate vs Tool Failure Probability", fontsize=14, fontweight="bold")
    ax1.set_xlim(-0.05, max(metrics["tfp"]) + 0.05)

    # Plot 2: Acceptance Rate vs TFP
    ax2 = axes[1]
    for i, (model, metrics) in enumerate(sorted(filtered_data.items())):
        marker = get_marker_for_model(model)
        ax2.plot(
            metrics["tfp"],
            metrics["acceptance_rate"],
            marker=marker,
            label=model,
            color=colors[i],
            linewidth=2,
            markersize=5,
        )

    ax2.set_xlabel("Tool Failure Probability", fontsize=12)
    ax2.set_ylabel("Acceptance Rate (%)", fontsize=12)
    ax2.set_title("Acceptance Rate vs Tool Failure Probability", fontsize=14, fontweight="bold")
    ax2.set_xlim(-0.05, max(metrics["tfp"]) + 0.05)

    # Common legend below both plots
    fig.legend(
        lines,
        labels,
        loc="lower center",
        ncol=len(labels),
        frameon=True,
        fancybox=True,
        shadow=True,
        bbox_to_anchor=(0.5, -0.02),
    )

    plt.tight_layout()
    plt.subplots_adjust(bottom=0.15)

    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        print(f"Saved: {output_path}")
    else:
        plt.show()

    plt.close()


def plot_noise_metrics(
    data_by_model: ModelMetricsData, output_path: Path | None = None, exclude_models: list[str] | None = None
) -> None:
    """Plot proposal rate and acceptance rate vs environmental noise."""
    exclude_models = exclude_models or []
    filtered_data = {k: v for k, v in data_by_model.items() if k not in exclude_models}

    sns.set_theme(style="whitegrid")
    colors = sns.color_palette("deep", n_colors=len(filtered_data))

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Plot 1: Proposal Rate vs Noise
    ax1 = axes[0]
    lines = []
    labels = []
    for i, (model, metrics) in enumerate(sorted(filtered_data.items())):
        marker = get_marker_for_model(model)
        (line,) = ax1.plot(
            metrics["enmi"],
            metrics["proposal_rate"],
            marker=marker,
            label=model,
            color=colors[i],
            linewidth=2,
            markersize=5,
        )
        lines.append(line)
        labels.append(model)

    ax1.set_xlabel("Environmental Noise (events/min)", fontsize=12)
    ax1.set_ylabel("Proposal Rate (%)", fontsize=12)
    ax1.set_title("Proposal Rate vs Environmental Noise", fontsize=14, fontweight="bold")

    # Plot 2: Acceptance Rate vs Noise
    ax2 = axes[1]
    for i, (model, metrics) in enumerate(sorted(filtered_data.items())):
        marker = get_marker_for_model(model)
        ax2.plot(
            metrics["enmi"],
            metrics["acceptance_rate"],
            marker=marker,
            label=model,
            color=colors[i],
            linewidth=2,
            markersize=5,
        )

    ax2.set_xlabel("Environmental Noise (events/min)", fontsize=12)
    ax2.set_ylabel("Acceptance Rate (%)", fontsize=12)
    ax2.set_title("Acceptance Rate vs Environmental Noise", fontsize=14, fontweight="bold")

    # Common legend below both plots
    fig.legend(
        lines,
        labels,
        loc="lower center",
        ncol=len(labels),
        frameon=True,
        fancybox=True,
        shadow=True,
        bbox_to_anchor=(0.5, -0.02),
    )

    plt.tight_layout()
    plt.subplots_adjust(bottom=0.15)

    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        print(f"Saved: {output_path}")
    else:
        plt.show()

    plt.close()


def main() -> None:
    """Generate robustness metric plots from command line."""
    parser = argparse.ArgumentParser(
        description="Generate plots for proposal rate and acceptance rate across robustness conditions."
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("results"),
        help="Directory containing metrics JSON files (default: results)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/figures"),
        help="Directory to save plots (default: results/figures)",
    )

    args = parser.parse_args()

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Models to exclude (incomplete data)
    exclude_models = ["gpt-4o"]

    # Prepare and plot TFP data
    print("Preparing tool failure probability data...")
    tfp_data = prepare_tfp_data(args.results_dir)
    if tfp_data:
        plot_tfp_metrics(tfp_data, args.output_dir / "robustness_tfp.pdf", exclude_models)
    else:
        print("Warning: No TFP data found")

    # Prepare and plot noise data
    print("Preparing environmental noise data...")
    noise_data = prepare_noise_data(args.results_dir)
    if noise_data:
        plot_noise_metrics(noise_data, args.output_dir / "robustness_noise.pdf", exclude_models)
    else:
        print("Warning: No noise data found")

    print("Done!")


if __name__ == "__main__":
    main()
