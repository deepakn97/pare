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
    is_no_noise_trace,
    parse_trace,
    trace_uses_messages_app,
)
from pas.trajectory.models import DecisionPoint as TernaryDecisionPoint  # noqa: TC001
from pas.trajectory.trace_parser import extract_decision_points as extract_ternary_decision_points

logger = logging.getLogger(__name__)


def discover_trace_directories(traces_dir: Path) -> list[Path]:
    """Discover all no-noise trace directories.

    .. deprecated::
        Part of old binary pipeline. Use ``extract_all_decision_points_ternary`` instead.

    Args:
        traces_dir: The root traces directory.

    Returns:
        List of paths to valid no-noise trace directories.
    """
    if not traces_dir.exists():
        raise FileNotFoundError(f"Traces directory not found: {traces_dir}")

    valid_dirs = [subdir for subdir in traces_dir.iterdir() if subdir.is_dir() and is_no_noise_trace(subdir.name)]

    if not valid_dirs:
        raise ValueError(f"No valid no-noise trace directories found in {traces_dir}")

    logger.info(f"Found {len(valid_dirs)} no-noise trace directories")
    return valid_dirs


def extract_all_decision_points(
    traces_dir: Path,
    user_model_id: str,
    exclude_messages_app: bool = True,
    target_models: list[str] | None = None,
) -> list[DecisionPoint]:
    """Extract all decision points from all no-noise traces.

    .. deprecated::
        Part of old binary pipeline. Use ``extract_all_decision_points_ternary`` instead.

    Args:
        traces_dir: The root traces directory.
        user_model_id: The user model that generated these traces.
        exclude_messages_app: If True, skip traces that use the Messages app.
        target_models: If provided, only include traces from these proactive models.
            Missing models are warned and skipped.

    Returns:
        List of all DecisionPoint objects.
    """
    trace_dirs = discover_trace_directories(traces_dir)

    # Filter by target proactive models if specified
    if target_models:
        available_models = {extract_model_id_from_dir(d.name) for d in trace_dirs}
        target_set = set(target_models)
        missing = target_set - available_models
        if missing:
            logger.warning(
                f"Target models not found in traces, skipping: {sorted(missing)}. Available: {sorted(available_models)}"
            )
        trace_dirs = [d for d in trace_dirs if extract_model_id_from_dir(d.name) in target_set]
        logger.info(f"Filtered to {len(trace_dirs)} trace directories for models: {sorted(target_set - missing)}")

    all_decision_points = []
    messages_excluded = 0

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

    .. deprecated::
        Part of old binary pipeline. Ternary pipeline handles dedup internally.

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

    .. deprecated::
        Part of old binary pipeline. Use ``balanced_sample_ternary`` instead.

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


def _draw_one_cycle(
    model_ids: list[str],
    decision_types: list[str],
    model_pools: dict[str, dict[str, list[TernaryDecisionPoint]]],
    selected: list[TernaryDecisionPoint],
    sample_size: int,
) -> bool:
    """Draw one sample per decision type per model in a single cycle.

    Args:
        model_ids: Sorted list of proactive model IDs.
        decision_types: List of decision type strings.
        model_pools: Nested dict of model -> decision_type -> candidate list.
        selected: Accumulator list to append drawn samples to (mutated in place).
        sample_size: Maximum number of samples to select.

    Returns:
        True if any sample was drawn in this cycle, False if all pools exhausted.
    """
    any_picked = False
    for model_id in model_ids:
        for dt in decision_types:
            if len(selected) >= sample_size:
                return any_picked
            pool = model_pools[model_id][dt]
            if pool:
                selected.append(pool.pop(0))
                any_picked = True
    return any_picked


def balanced_sample_ternary(
    candidates: list[TernaryDecisionPoint],
    sample_size: int,
    seed: int | None = None,
) -> list[TernaryDecisionPoint]:
    """Sample decision points balanced by both decision type and proactive model.

    Algorithm: For each proactive model, create three pools (accept, reject, gather_context).
    Cycle through models, and within each model cycle through decision type pools, drawing
    one sample per pool per cycle. If a pool is exhausted, skip it. Stop when target count
    reached or all pools across all models are empty.

    Args:
        candidates: List of candidate decision points.
        sample_size: Number of samples to select.
        seed: Random seed for reproducibility.

    Returns:
        List of selected TernaryDecisionPoint objects.
    """
    if seed is not None:
        random.seed(seed)

    decision_types = ["accept", "reject", "gather_context"]

    # Group by model, then by decision type
    model_ids = sorted({c.proactive_model_id for c in candidates})
    model_pools: dict[str, dict[str, list[TernaryDecisionPoint]]] = {}
    for model_id in model_ids:
        model_pools[model_id] = {}
        for dt in decision_types:
            pool = [c for c in candidates if c.proactive_model_id == model_id and c.user_agent_decision == dt]
            random.shuffle(pool)
            model_pools[model_id][dt] = pool

    selected: list[TernaryDecisionPoint] = []

    # Cycle: for each model, draw one from each decision type pool
    while len(selected) < sample_size:
        any_picked = _draw_one_cycle(model_ids, decision_types, model_pools, selected, sample_size)
        if not any_picked:
            logger.warning(f"Ran out of candidates after selecting {len(selected)} samples")
            break

    # Log balance statistics
    accepts_count = len([s for s in selected if s.user_agent_decision == "accept"])
    rejects_count = len([s for s in selected if s.user_agent_decision == "reject"])
    gather_context_count = len([s for s in selected if s.user_agent_decision == "gather_context"])
    model_counts = {m: len([s for s in selected if s.proactive_model_id == m]) for m in model_ids}
    logger.info(
        f"Selected {len(selected)} samples: {accepts_count} accepts, {rejects_count} rejects, "
        f"{gather_context_count} gather_context. Per model: {model_counts}"
    )

    return selected


def _distribute_equally(total: int, models: list[str]) -> dict[str, int]:
    """Distribute a total sample count equally across models.

    Remainder is distributed across the first N models.

    Args:
        total: Total number of samples to distribute.
        models: List of model IDs.

    Returns:
        Dict mapping model ID to sample count.
    """
    if not models:
        raise ValueError("Cannot distribute samples across empty model list")
    per_model = total // len(models)
    remainder = total % len(models)
    result = dict.fromkeys(models, per_model)
    for i, model in enumerate(models):
        if i < remainder:
            result[model] += 1
    logger.info(f"Distributing {total} samples equally across {len(models)} models")
    return result


def sample_new_datapoints(
    traces_dir: Path,
    samples_file: Path,
    user_model_id: str,
    sample_size: int | None = None,
    seed: int | None = None,
    per_model_count: dict[str, int] | None = None,
    target_models: list[str] | None = None,
) -> list[DecisionPoint]:
    """Sample new datapoints, avoiding duplicates with existing samples.

    .. deprecated::
        Part of old binary pipeline. Use ``sample_new_datapoints_ternary`` instead.

    Args:
        traces_dir: Path to the traces directory.
        samples_file: Path to the existing samples parquet file (for dedup).
        user_model_id: The user model that generated these traces.
        sample_size: Number of new samples to add. When used with target_models,
            distributes equally across target models.
        seed: Random seed for reproducibility.
        per_model_count: If provided, sample this many decision points per proactive model.
            Keys are proactive model IDs, values are sample counts.
            Mutually exclusive with sample_size.
        target_models: If provided with sample_size, distributes samples equally
            across these proactive models.

    Returns:
        List of newly selected DecisionPoint objects.
    """
    if sample_size is not None and per_model_count is not None:
        raise ValueError("Cannot specify both sample_size and per_model_count")
    if sample_size is None and per_model_count is None:
        raise ValueError("Either sample_size or per_model_count must be provided")

    # Load existing samples
    existing_df = load_existing_samples(samples_file)

    existing_ids: set[str] = set()
    existing_scenarios: set[str] = set()

    if existing_df is not None:
        existing_ids = set(existing_df["sample_id"].to_list())
        existing_scenarios = set(existing_df["scenario_id"].to_list())
        logger.info(f"Found {len(existing_ids)} existing samples from {len(existing_scenarios)} scenarios")

    # When target_models is provided with sample_size, distribute equally across models
    if target_models and sample_size is not None:
        per_model_count = _distribute_equally(sample_size, target_models)

    if per_model_count:
        # Sample per proactive model independently
        all_selected: list[DecisionPoint] = []
        for model_id, count in per_model_count.items():
            model_candidates = extract_all_decision_points(traces_dir, user_model_id, target_models=[model_id])
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

    # Global sampling (no target_models, no per_model_count) — sample from all models
    # sample_size cannot be None here: validation ensures exactly one of sample_size/per_model_count is set
    all_candidates = extract_all_decision_points(traces_dir, user_model_id)

    new_candidates = [c for c in all_candidates if c.sample_id not in existing_ids]
    logger.info(
        f"Found {len(new_candidates)} new candidates (filtered {len(all_candidates) - len(new_candidates)} existing)"
    )

    if not new_candidates:
        logger.warning("No new candidates available for sampling")
        return []

    selected = balanced_sample(new_candidates, sample_size, existing_scenarios, seed)  # type: ignore[arg-type]

    return selected


def save_samples(samples: list[DecisionPoint], output_file: Path) -> Path:
    """Save samples to a parquet file (append if exists, create if not).

    .. deprecated::
        Part of old binary pipeline. Use ``save_samples_ternary`` instead.

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


# ===== TERNARY PIPELINE FUNCTIONS =====


def extract_all_decision_points_ternary(
    traces_dir: Path,
    user_model_id: str,
    target_models: list[str] | None = None,
) -> list[TernaryDecisionPoint]:
    """Extract ternary decision points from all trace files in a directory.

    Walks the traces directory, identifies model subdirectories, and extracts
    decision points from each no-noise trace file using the ternary parser.

    Args:
        traces_dir: Root directory containing model subdirectories with traces.
        user_model_id: The user model that generated these traces.
        target_models: If provided, only extract from these proactive model IDs.

    Returns:
        List of TernaryDecisionPoint objects from all matching traces.
    """
    all_dps: list[TernaryDecisionPoint] = []

    for model_dir in sorted(traces_dir.iterdir()):
        if not model_dir.is_dir() or not is_no_noise_trace(model_dir.name):
            continue

        model_id = extract_model_id_from_dir(model_dir.name)
        if not model_id:
            continue

        if target_models and model_id not in target_models:
            continue

        trace_files = sorted(model_dir.glob("*.json"))

        for trace_file in trace_files:
            dps = extract_ternary_decision_points(trace_file, model_id, user_model_id)
            all_dps.extend(dps)

        logger.info(f"Extracted {len(all_dps)} decision points from {model_id} ({len(trace_files)} traces)")

    logger.info(f"Total: {len(all_dps)} ternary decision points from {traces_dir}")
    return all_dps


def save_samples_ternary(samples: list[TernaryDecisionPoint], output_file: Path) -> Path:
    """Save ternary samples to parquet, checking schema compatibility.

    If the output file already exists, validates that it uses the ternary schema
    (user_agent_decision as String, not Boolean). Raises SystemExit if an
    incompatible binary-schema parquet is found.

    Args:
        samples: List of TernaryDecisionPoint objects to save.
        output_file: Path to the output parquet file.

    Returns:
        Path to the samples file.
    """
    import sys

    if not samples:
        logger.warning("No samples to save")
        return output_file

    output_file.parent.mkdir(parents=True, exist_ok=True)
    new_df = pl.DataFrame([s.to_sample_dict() for s in samples])

    if output_file.exists():
        existing_df = pl.read_parquet(output_file)

        # Check schema compatibility
        if "user_agent_decision" in existing_df.columns and existing_df["user_agent_decision"].dtype == pl.Boolean:
            logger.error(
                f"Existing parquet {output_file} uses binary schema (user_agent_decision: bool). "
                "Delete it and re-sample with the ternary pipeline."
            )
            sys.exit(1)

        combined_df = pl.concat([existing_df, new_df])
        combined_df.write_parquet(output_file)
        logger.info(f"Appended {len(samples)} samples to {output_file} (total: {len(combined_df)})")
    else:
        new_df.write_parquet(output_file)
        logger.info(f"Created {output_file} with {len(samples)} samples")

    return output_file


def sample_new_datapoints_ternary(
    traces_dir: Path,
    samples_file: Path,
    user_model_id: str,
    sample_size: int,
    seed: int | None = None,
    target_models: list[str] | None = None,
) -> list[TernaryDecisionPoint]:
    """Extract, sample, and save ternary decision points.

    End-to-end function: extracts all ternary decision points from traces,
    deduplicates against existing samples, applies three-way balanced sampling,
    and saves the result to parquet.

    Args:
        traces_dir: Root directory containing model subdirectories with traces.
        samples_file: Path to the output parquet file (for dedup and save).
        user_model_id: The user model that generated these traces.
        sample_size: Number of new samples to select.
        seed: Random seed for reproducibility.
        target_models: If provided, only extract from these proactive model IDs.

    Returns:
        List of newly selected TernaryDecisionPoint objects.
    """
    # Extract all decision points
    all_dps = extract_all_decision_points_ternary(traces_dir, user_model_id, target_models)

    if not all_dps:
        logger.warning("No decision points found in traces")
        return []

    # Deduplicate against existing samples
    existing_ids: set[str] = set()
    if samples_file.exists():
        existing_df = pl.read_parquet(samples_file)
        existing_ids = set(existing_df["sample_id"].to_list())
        logger.info(f"Found {len(existing_ids)} existing samples for deduplication")

    new_candidates = [dp for dp in all_dps if dp.sample_id not in existing_ids]
    logger.info(f"Found {len(new_candidates)} new candidates (filtered {len(all_dps) - len(new_candidates)} existing)")

    if not new_candidates:
        logger.warning("No new candidates available for sampling")
        return []

    # Three-way balanced sampling
    selected = balanced_sample_ternary(new_candidates, sample_size, seed)

    # Save to parquet
    save_samples_ternary(selected, samples_file)

    return selected
