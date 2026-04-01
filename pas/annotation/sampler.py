"""Balanced sampler for annotation dataset creation."""

from __future__ import annotations

import logging
import random
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import polars as pl

from pas.trajectory.models import DecisionPoint as TernaryDecisionPoint  # noqa: TC001
from pas.trajectory.trace_parser import extract_decision_points as extract_ternary_decision_points

logger = logging.getLogger(__name__)


def extract_model_id_from_dir(dir_name: str) -> str:
    """Extract the proactive model ID from a trace subdirectory name.

    Example: obs_gpt-5_exec_gpt-5_enmi_0_es_42_tfp_0.0 -> gpt-5

    Args:
        dir_name: The subdirectory name.

    Returns:
        The extracted proactive model ID.
    """
    match = re.match(r"obs_([^_]+(?:_[^_]+)?(?:-[^_]+)?)_exec_", dir_name)
    if match:
        return match.group(1)
    return dir_name


def is_no_noise_trace(dir_name: str) -> bool:
    """Check if a trace directory is a no-noise trace.

    No-noise traces have enmi_0 (environment noise = 0).

    Args:
        dir_name: The directory name.

    Returns:
        True if this is a no-noise trace.
    """
    return "enmi_0" in dir_name


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

    # Add tutorial columns with defaults (real samples are never tutorials)
    new_df = new_df.with_columns(
        pl.lit(False).alias("tutorial"),
        pl.lit(None).cast(pl.Utf8).alias("correct_decision"),
        pl.lit(None).cast(pl.Utf8).alias("explanation"),
    )

    if output_file.exists():
        existing_df = pl.read_parquet(output_file)

        # Check schema compatibility
        if "user_agent_decision" in existing_df.columns and existing_df["user_agent_decision"].dtype == pl.Boolean:
            logger.error(
                f"Existing parquet {output_file} uses binary schema (user_agent_decision: bool). "
                "Delete it and re-sample with the ternary pipeline."
            )
            sys.exit(1)

        # Align column order and use diagonal concat to handle type mismatches
        # (e.g., Null vs String when all values in a column are null)
        new_df = new_df.select(existing_df.columns)
        combined_df = pl.concat([existing_df, new_df], how="diagonal_relaxed")
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
