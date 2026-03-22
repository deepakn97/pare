"""Balanced sampler for annotation dataset creation."""

from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import polars as pl

from pas.annotation.models import DecisionPoint  # noqa: TC001
from pas.annotation.trace_parser import (
    extract_model_id_from_dir,
    extract_user_model_id_from_dir,
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
    target_models: list[str] | None = None,
) -> list[DecisionPoint]:
    """Extract all decision points from all no-noise traces.

    Args:
        traces_dir: The root traces directory.
        exclude_messages_app: If True, skip traces that use the Messages app.
        target_models: If provided, only include traces from these proactive models.

    Returns:
        List of all DecisionPoint objects.
    """
    trace_dirs = discover_trace_directories(traces_dir)

    # Filter by target proactive models if specified
    if target_models:
        target_set = set(target_models)
        trace_dirs = [d for d in trace_dirs if extract_model_id_from_dir(d.name) in target_set]
        logger.info(f"Filtered to {len(trace_dirs)} trace directories for models: {target_models}")

    all_decision_points = []
    messages_excluded = 0

    user_model_id = extract_user_model_id_from_dir(traces_dir.name)

    for trace_dir in trace_dirs:
        proactive_model_id = extract_model_id_from_dir(trace_dir.name)
        logger.info(f"Processing {trace_dir.name} (proactive_model: {proactive_model_id}, user_model: {user_model_id})")

        trace_files = list(trace_dir.glob("*.json"))
        for trace_file in trace_files:
            # Skip traces that use Messages app if requested
            if exclude_messages_app and trace_uses_messages_app(trace_file):
                messages_excluded += 1
                logger.debug(f"Excluding {trace_file.name} (uses Messages app)")
                continue

            try:
                decision_points = parse_trace(trace_file, proactive_model_id, user_model_id)
                all_decision_points.extend(decision_points)
            except Exception as e:
                logger.warning(f"Failed to parse {trace_file}: {e}")

    if messages_excluded > 0:
        logger.info(f"Excluded {messages_excluded} traces that use Messages app")

    logger.info(f"Extracted {len(all_decision_points)} decision points total")
    return all_decision_points


def load_existing_samples(samples_file: Path) -> pl.DataFrame | None:
    """Load existing samples from a parquet file.

    Args:
        samples_file: Path to the samples parquet file.

    Returns:
        DataFrame of existing samples, or None if file doesn't exist.
    """
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
    samples_file: Path,
    sample_size: int | None = None,
    seed: int | None = None,
    per_model_count: dict[str, int] | None = None,
) -> list[DecisionPoint]:
    """Sample new datapoints, avoiding duplicates with existing samples.

    Args:
        traces_dir: Path to the traces directory.
        samples_file: Path to the existing samples parquet file (for dedup).
        sample_size: Number of new samples to add (used when per_model_count is None).
        seed: Random seed for reproducibility.
        per_model_count: If provided, sample this many decision points per proactive model.
            Keys are proactive model IDs, values are sample counts.
            When provided, sample_size is ignored.

    Returns:
        List of newly selected DecisionPoint objects.
    """
    # Load existing samples
    existing_df = load_existing_samples(samples_file)

    existing_ids: set[str] = set()
    existing_scenarios: set[str] = set()

    if existing_df is not None:
        existing_ids = set(existing_df["sample_id"].to_list())
        existing_scenarios = set(existing_df["scenario_id"].to_list())
        logger.info(f"Found {len(existing_ids)} existing samples from {len(existing_scenarios)} scenarios")

    if per_model_count:
        # Sample per proactive model independently
        all_selected: list[DecisionPoint] = []
        for model_id, count in per_model_count.items():
            model_candidates = extract_all_decision_points(traces_dir, target_models=[model_id])
            new_candidates = [c for c in model_candidates if c.sample_id not in existing_ids]
            logger.info(f"Model {model_id}: {len(new_candidates)} new candidates available, sampling {count}")

            if not new_candidates:
                logger.warning(f"No new candidates available for model {model_id}")
                continue

            selected = balanced_sample(new_candidates, count, existing_scenarios, seed)
            all_selected.extend(selected)
            # Update existing scenarios to avoid duplicates across models
            existing_scenarios.update(s.scenario_id for s in selected)

        return all_selected

    # Global sampling (original behavior)
    if sample_size is None:
        raise ValueError("Either sample_size or per_model_count must be provided")

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


def save_samples(samples: list[DecisionPoint], output_file: Path) -> Path:
    """Save samples to a parquet file (append if exists, create if not).

    Args:
        samples: List of DecisionPoint objects to save.
        output_file: Path to the output parquet file.

    Returns:
        Path to the samples file.
    """
    if not samples:
        logger.warning("No samples to save")
        return output_file

    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Convert to DataFrame
    new_df = pl.DataFrame([s.to_sample_dict() for s in samples])

    # Append to existing or create new
    if output_file.exists():
        existing_df = pl.read_parquet(output_file)
        combined_df = pl.concat([existing_df, new_df])
        combined_df.write_parquet(output_file)
        logger.info(f"Appended {len(samples)} samples to {output_file} (total: {len(combined_df)})")
    else:
        new_df.write_parquet(output_file)
        logger.info(f"Created {output_file} with {len(samples)} samples")

    return output_file


def get_sampling_stats(traces_dir: Path, samples_file: Path) -> dict[str, int]:
    """Get statistics about available samples.

    Args:
        traces_dir: Path to the traces directory.
        samples_file: Path to the existing samples parquet file.

    Returns:
        Dictionary with statistics.
    """
    existing_df = load_existing_samples(samples_file)

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
