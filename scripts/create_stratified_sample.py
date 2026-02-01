#!/usr/bin/env python3
"""Create a stratified sample of PAS scenarios maintaining app distribution proportionally.

This script uses iterative stratified sampling (from scikit-multilearn) to sample
scenarios while preserving the proportional representation of all apps.

Usage:
    uv run python scripts/create_stratified_sample.py --sample-size 50 --seed 42
"""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from skmultilearn.model_selection import iterative_train_test_split

# Load environment variables before importing registry
load_dotenv()

from pas import PROJECT_ROOT  # noqa: E402
from pas.scenarios.utils.registry import registry  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Apps to exclude from app matrix (they appear in all scenarios)
SYSTEM_APPS = {"HomeScreenSystemApp", "PASAgentUserInterface"}


def extract_app_name(class_name: str) -> str:
    """Extract clean app name from class name.

    Args:
        class_name: Full class name like 'StatefulEmailApp'.

    Returns:
        Clean app name like 'Email'.
    """
    name = class_name
    if name.startswith("Stateful"):
        name = name[8:]  # Remove "Stateful" prefix
    if name.endswith("App"):
        name = name[:-3]  # Remove "App" suffix
    return name


def normalize_app_class_name(class_name: str) -> str:
    """Normalize app class name for grouping.

    This treats 'ContactsApp' and 'StatefulContactsApp' as the same app.

    Args:
        class_name: Full class name like 'StatefulEmailApp' or 'ContactsApp'.

    Returns:
        Normalized class name like 'StatefulContactsApp'.
    """
    # Special cases that don't follow Stateful*App pattern
    if class_name == "SandboxLocalFileSystem":
        return class_name

    # Extract base name
    base = extract_app_name(class_name)
    # Return normalized form (StatefulXApp)
    return f"Stateful{base}App"


def load_scenarios_and_build_matrix() -> tuple[list[str], np.ndarray, list[str]]:
    """Load all scenarios and build a binary app presence matrix.

    Returns:
        Tuple of (scenario_ids, binary_app_matrix, app_names).
        - scenario_ids: List of scenario IDs in matrix row order
        - binary_app_matrix: Shape (n_scenarios, n_apps), 1 if app present, 0 otherwise
        - app_names: List of app names in matrix column order
    """
    # Get all registered scenarios
    all_scenarios = registry.get_all_scenarios()
    logger.info(f"Found {len(all_scenarios)} registered scenarios")

    # First pass: collect all unique apps and scenario app sets
    scenario_apps: dict[str, set[str]] = {}
    all_apps: set[str] = set()

    for scenario_id, scenario_class in all_scenarios.items():
        try:
            # Instantiate and initialize the scenario
            scenario = scenario_class()
            scenario.init_and_populate_apps(sandbox_dir=Path("sandbox"))

            if scenario.apps:
                # Get app names, excluding system apps and normalizing
                apps = {
                    normalize_app_class_name(app.__class__.__name__)
                    for app in scenario.apps
                    if app.__class__.__name__ not in SYSTEM_APPS
                }
                scenario_apps[scenario_id] = apps
                all_apps.update(apps)
                logger.debug(f"Processed scenario {scenario_id}: {len(apps)} apps")
            else:
                logger.warning(f"Scenario {scenario_id} has no apps")

        except Exception as e:
            logger.warning(f"Failed to process scenario {scenario_id}: {e}")

    # Sort for reproducibility
    scenario_ids = sorted(scenario_apps.keys())
    app_names = sorted(all_apps)

    logger.info(f"Total scenarios: {len(scenario_ids)}, unique apps: {len(app_names)}")

    # Build binary matrix
    n_scenarios = len(scenario_ids)
    n_apps = len(app_names)
    app_matrix = np.zeros((n_scenarios, n_apps), dtype=int)

    app_to_idx = {app: idx for idx, app in enumerate(app_names)}

    for row_idx, scenario_id in enumerate(scenario_ids):
        for app in scenario_apps[scenario_id]:
            col_idx = app_to_idx[app]
            app_matrix[row_idx, col_idx] = 1

    return scenario_ids, app_matrix, app_names


def create_stratified_sample(
    scenario_ids: list[str],
    app_matrix: np.ndarray,
    sample_size: int = 50,
    seed: int = 42,
) -> list[str]:
    """Use iterative stratification to sample scenarios.

    Args:
        scenario_ids: List of all scenario IDs.
        app_matrix: Binary matrix of shape (n_scenarios, n_apps).
        sample_size: Number of scenarios to sample.
        seed: Random seed for reproducibility.

    Returns:
        List of sampled scenario IDs.
    """
    n_total = len(scenario_ids)

    if sample_size >= n_total:
        logger.warning(f"Sample size ({sample_size}) >= total scenarios ({n_total}), returning all")
        return scenario_ids

    # Calculate test size ratio for iterative_train_test_split
    # We want sample_size in the "test" set
    test_ratio = sample_size / n_total

    # Create dummy X array (just indices, not used for stratification)
    X = np.arange(n_total).reshape(-1, 1)

    # Set random state
    np.random.seed(seed)

    # iterative_train_test_split returns (X_train, y_train, X_test, y_test)
    # We want the "test" set to be our sample
    _, _, X_sample, _ = iterative_train_test_split(X, app_matrix, test_size=test_ratio)

    # Extract scenario indices from X_sample
    sample_indices = X_sample.flatten().tolist()

    # Map back to scenario IDs
    sampled_ids = [scenario_ids[idx] for idx in sample_indices]

    logger.info(f"Sampled {len(sampled_ids)} scenarios using iterative stratification")

    return sampled_ids


def compute_app_distribution(
    scenario_ids: list[str],
    app_matrix: np.ndarray,
    app_names: list[str],
) -> dict[str, float]:
    """Compute the percentage of scenarios containing each app.

    Args:
        scenario_ids: List of scenario IDs.
        app_matrix: Binary matrix of shape (n_scenarios, n_apps).
        app_names: List of app names.

    Returns:
        Dict mapping app name to percentage (0-100).
    """
    n_scenarios = len(scenario_ids)
    app_counts = app_matrix.sum(axis=0)
    return {app_names[i]: (app_counts[i] / n_scenarios) * 100 for i in range(len(app_names))}


def verify_and_report(
    full_ids: list[str],
    sample_ids: list[str],
    app_matrix: np.ndarray,
    app_names: list[str],
) -> float:
    """Print distribution comparison and return max difference.

    Args:
        full_ids: List of all scenario IDs.
        sample_ids: List of sampled scenario IDs.
        app_matrix: Binary matrix for full set.
        app_names: List of app names.

    Returns:
        Maximum absolute difference in percentage points.
    """
    # Create sample matrix
    full_id_to_idx = {sid: idx for idx, sid in enumerate(full_ids)}
    sample_indices = [full_id_to_idx[sid] for sid in sample_ids]
    sample_matrix = app_matrix[sample_indices]

    # Compute distributions
    full_dist = compute_app_distribution(full_ids, app_matrix, app_names)
    sample_dist = compute_app_distribution(sample_ids, sample_matrix, app_names)

    # Print comparison table
    print("\nApp Distribution Comparison:")
    print(f"{'App Name':<20} {'Full(%)':>10} {'Sample(%)':>10} {'Diff(pp)':>10}")
    print("-" * 52)

    max_diff = 0.0
    for app in app_names:
        full_pct = full_dist[app]
        sample_pct = sample_dist[app]
        diff = sample_pct - full_pct
        max_diff = max(max_diff, abs(diff))

        clean_name = extract_app_name(app)
        print(f"{clean_name:<20} {full_pct:>9.1f}% {sample_pct:>9.1f}% {diff:>+9.1f}")

    print("-" * 52)
    print(f"Max difference: {max_diff:.1f} pp")

    return max_diff


def write_sample_file(
    sample_ids: list[str],
    output_path: Path,
    seed: int,
    sample_size: int,
) -> None:
    """Write sampled scenario IDs to output file.

    Args:
        sample_ids: List of sampled scenario IDs.
        output_path: Path to output file.
        seed: Random seed used.
        sample_size: Requested sample size.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Sort alphabetically for consistency
    sorted_ids = sorted(sample_ids)

    with open(output_path, "w") as f:
        # Write header comment
        timestamp = datetime.now(UTC).isoformat()
        f.write(f"# Stratified sample of {len(sorted_ids)} scenarios\n")
        f.write(f"# Generated: {timestamp}\n")
        f.write(f"# Seed: {seed}, Requested size: {sample_size}\n")
        f.write("#\n")

        # Write scenario IDs
        for scenario_id in sorted_ids:
            f.write(f"{scenario_id}\n")

    print(f"\nSample written to: {output_path}")
    print(f"Total scenarios: {len(sorted_ids)}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Create a stratified sample of PAS scenarios maintaining app distribution."
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=50,
        help="Number of scenarios to sample (default: 50).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="ablation.txt",
        help="Output filename in data/splits/ (default: ablation.txt).",
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

    # Load scenarios and build app matrix
    print("Loading and analyzing scenarios...")
    scenario_ids, app_matrix, app_names = load_scenarios_and_build_matrix()

    print(f"Found {len(scenario_ids)} scenarios with {len(app_names)} unique apps")

    # Create stratified sample
    print(f"\nCreating stratified sample of {args.sample_size} scenarios (seed={args.seed})...")
    sample_ids = create_stratified_sample(
        scenario_ids,
        app_matrix,
        sample_size=args.sample_size,
        seed=args.seed,
    )

    # Verify and report distribution
    max_diff = verify_and_report(scenario_ids, sample_ids, app_matrix, app_names)

    if max_diff < 5.0:
        print(f"\nDistribution quality: GOOD (max diff {max_diff:.1f}pp < 5pp)")
    else:
        print(f"\nDistribution quality: ACCEPTABLE (max diff {max_diff:.1f}pp >= 5pp)")

    # Write output file
    output_path = PROJECT_ROOT / "data" / "splits" / args.output
    write_sample_file(sample_ids, output_path, args.seed, args.sample_size)


if __name__ == "__main__":
    main()
