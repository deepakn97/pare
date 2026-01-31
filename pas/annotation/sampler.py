"""Balanced sampler for annotation dataset creation."""

from __future__ import annotations

import logging
import random
from pathlib import Path  # noqa: TC003

import polars as pl

from pas.annotation.config import ensure_annotations_dir, get_samples_file
from pas.annotation.models import DecisionPoint  # noqa: TC001
from pas.annotation.trace_parser import (
    extract_model_id_from_dir,
    is_excluded_model,
    is_no_noise_trace,
    parse_trace,
    trace_uses_messages_app,
)

logger = logging.getLogger(__name__)


def discover_trace_directories(traces_dir: Path) -> list[Path]:
    """Discover all no-noise trace directories, excluding low-quality models.

    Args:
        traces_dir: The root traces directory.

    Returns:
        List of paths to valid no-noise trace directories.
    """
    if not traces_dir.exists():
        raise FileNotFoundError(f"Traces directory not found: {traces_dir}")

    valid_dirs = []
    excluded_count = 0
    for subdir in traces_dir.iterdir():
        if subdir.is_dir() and is_no_noise_trace(subdir.name):
            # Skip excluded models (e.g., ministral)
            if is_excluded_model(subdir.name):
                excluded_count += 1
                logger.debug(f"Excluding {subdir.name} (excluded model)")
                continue
            valid_dirs.append(subdir)

    if excluded_count > 0:
        logger.info(f"Excluded {excluded_count} trace directories from low-quality models")

    if not valid_dirs:
        raise ValueError(f"No valid no-noise trace directories found in {traces_dir}")

    logger.info(f"Found {len(valid_dirs)} valid no-noise trace directories")
    return valid_dirs


def extract_all_decision_points(
    traces_dir: Path,
    exclude_messages_app: bool = True,
) -> list[DecisionPoint]:
    """Extract all decision points from all no-noise traces.

    Args:
        traces_dir: The root traces directory.
        exclude_messages_app: If True, skip traces that use the Messages app.

    Returns:
        List of all DecisionPoint objects.
    """
    trace_dirs = discover_trace_directories(traces_dir)

    all_decision_points = []
    messages_excluded = 0

    for trace_dir in trace_dirs:
        model_id = extract_model_id_from_dir(trace_dir.name)
        logger.info(f"Processing {trace_dir.name} (model: {model_id})")

        trace_files = list(trace_dir.glob("*.json"))
        for trace_file in trace_files:
            # Skip traces that use Messages app if requested
            if exclude_messages_app and trace_uses_messages_app(trace_file):
                messages_excluded += 1
                logger.debug(f"Excluding {trace_file.name} (uses Messages app)")
                continue

            try:
                decision_points = parse_trace(trace_file, model_id)
                all_decision_points.extend(decision_points)
            except Exception as e:
                logger.warning(f"Failed to parse {trace_file}: {e}")

    if messages_excluded > 0:
        logger.info(f"Excluded {messages_excluded} traces that use Messages app")

    logger.info(f"Extracted {len(all_decision_points)} decision points total")
    return all_decision_points


def load_existing_samples() -> pl.DataFrame | None:
    """Load existing samples from the samples file.

    Returns:
        DataFrame of existing samples, or None if no samples exist.
    """
    samples_file = get_samples_file()
    if not samples_file.exists():
        return None

    return pl.read_parquet(samples_file)


def balanced_sample(  # noqa: C901
    candidates: list[DecisionPoint],
    sample_size: int,
    existing_scenarios: set[str],
    seed: int | None = None,
) -> list[DecisionPoint]:
    """Sample decision points with balanced accept/reject and unique scenario priority.

    Algorithm:
    1. Separate candidates into accept and reject pools
    2. Alternate between pools, prioritizing unique scenarios
    3. Only reuse scenarios when all unique ones are exhausted

    Args:
        candidates: List of candidate decision points.
        sample_size: Number of samples to select.
        existing_scenarios: Set of scenario IDs already used (from previous sampling).
        seed: Random seed for reproducibility.

    Returns:
        List of selected DecisionPoint objects.
    """
    if seed is not None:
        random.seed(seed)

    # Separate by accept/reject
    accepts = [c for c in candidates if c.user_agent_decision]
    rejects = [c for c in candidates if not c.user_agent_decision]

    # Shuffle both pools
    random.shuffle(accepts)
    random.shuffle(rejects)

    selected: list[DecisionPoint] = []
    scenarios_used = set(existing_scenarios)

    def pick_from_pool(pool: list[DecisionPoint]) -> DecisionPoint | None:
        """Pick a candidate, prioritizing unused scenarios."""
        if not pool:
            return None

        # Try to find a candidate from an unused scenario
        for i, candidate in enumerate(pool):
            if candidate.scenario_id not in scenarios_used:
                return pool.pop(i)

        # Fall back to any candidate (scenario reuse)
        return pool.pop(0)

    # Alternate between accept and reject
    target_accepts = 0
    target_rejects = 0

    while len(selected) < sample_size:
        # Determine which pool to pick from (balance accept/reject)
        accepts_selected = len([s for s in selected if s.user_agent_decision])
        rejects_selected = len(selected) - accepts_selected

        # Try to balance
        if accepts_selected <= rejects_selected:
            # Try to pick an accept
            pick = pick_from_pool(accepts)
            if not pick:
                # Accept pool empty, try reject
                pick = pick_from_pool(rejects)
        else:
            # Try to pick a reject
            pick = pick_from_pool(rejects)
            if not pick:
                # Reject pool empty, try accept
                pick = pick_from_pool(accepts)

        if not pick:
            # Both pools empty
            logger.warning(f"Ran out of candidates after selecting {len(selected)} samples")
            break

        selected.append(pick)
        scenarios_used.add(pick.scenario_id)

    # Log balance statistics
    accepts_count = len([s for s in selected if s.user_agent_decision])
    rejects_count = len(selected) - accepts_count
    logger.info(f"Selected {len(selected)} samples: {accepts_count} accepts, {rejects_count} rejects")

    return selected


def sample_new_datapoints(
    traces_dir: Path,
    sample_size: int,
    seed: int | None = None,
) -> list[DecisionPoint]:
    """Sample new datapoints, avoiding duplicates with existing samples.

    Args:
        traces_dir: Path to the traces directory.
        sample_size: Number of new samples to add.
        seed: Random seed for reproducibility.

    Returns:
        List of newly selected DecisionPoint objects.
    """
    # Load existing samples
    existing_df = load_existing_samples()

    existing_ids: set[str] = set()
    existing_scenarios: set[str] = set()

    if existing_df is not None:
        existing_ids = set(existing_df["sample_id"].to_list())
        existing_scenarios = set(existing_df["scenario_id"].to_list())
        logger.info(f"Found {len(existing_ids)} existing samples from {len(existing_scenarios)} scenarios")

    # Extract all decision points
    all_candidates = extract_all_decision_points(traces_dir)

    # Filter out already-sampled decision points
    new_candidates = [c for c in all_candidates if c.sample_id not in existing_ids]
    logger.info(
        f"Found {len(new_candidates)} new candidates (filtered {len(all_candidates) - len(new_candidates)} existing)"
    )

    if not new_candidates:
        logger.warning("No new candidates available for sampling")
        return []

    # Apply balanced sampling
    selected = balanced_sample(new_candidates, sample_size, existing_scenarios, seed)

    return selected


def save_samples(samples: list[DecisionPoint]) -> Path:
    """Save samples to the parquet file (append mode).

    Args:
        samples: List of DecisionPoint objects to save.

    Returns:
        Path to the samples file.
    """
    if not samples:
        logger.warning("No samples to save")
        return get_samples_file()

    ensure_annotations_dir()
    samples_file = get_samples_file()

    # Convert to DataFrame
    new_df = pl.DataFrame([s.to_sample_dict() for s in samples])

    # Append to existing or create new
    if samples_file.exists():
        existing_df = pl.read_parquet(samples_file)
        combined_df = pl.concat([existing_df, new_df])
        combined_df.write_parquet(samples_file)
        logger.info(f"Appended {len(samples)} samples to {samples_file} (total: {len(combined_df)})")
    else:
        new_df.write_parquet(samples_file)
        logger.info(f"Created {samples_file} with {len(samples)} samples")

    return samples_file


def get_sampling_stats(traces_dir: Path) -> dict[str, int]:
    """Get statistics about available samples.

    Args:
        traces_dir: Path to the traces directory.

    Returns:
        Dictionary with statistics.
    """
    existing_df = load_existing_samples()

    # Count existing
    existing_count = len(existing_df) if existing_df is not None else 0
    existing_scenarios = len(existing_df["scenario_id"].unique()) if existing_df is not None else 0
    existing_accepts = len(existing_df.filter(pl.col("user_agent_decision"))) if existing_df is not None else 0
    existing_rejects = existing_count - existing_accepts

    # Count available candidates
    try:
        all_candidates = extract_all_decision_points(traces_dir)
        existing_ids = set(existing_df["sample_id"].to_list()) if existing_df is not None else set()
        new_candidates = [c for c in all_candidates if c.sample_id not in existing_ids]

        available_accepts = len([c for c in new_candidates if c.user_agent_decision])
        available_rejects = len(new_candidates) - available_accepts
    except Exception as e:
        logger.warning(f"Could not count available candidates: {e}")
        available_accepts = -1
        available_rejects = -1

    return {
        "existing_samples": existing_count,
        "existing_scenarios": existing_scenarios,
        "existing_accepts": existing_accepts,
        "existing_rejects": existing_rejects,
        "available_accepts": available_accepts,
        "available_rejects": available_rejects,
    }
