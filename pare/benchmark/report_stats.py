"""Statistics and reporting utilities for PARE benchmark results."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import polars as pl

if TYPE_CHECKING:
    from pare.scenarios.validation_result import PAREMultiScenarioValidationResult


def _safe_mean_to_float(mean_value: Any) -> float | None:  # noqa: ANN401
    """Safely convert polars mean() result to float or None.

    Args:
        mean_value: Result from polars .mean() operation.

    Returns:
        Float value or None if conversion fails.
    """
    if mean_value is None:
        return None
    if isinstance(mean_value, (int, float)):
        return float(mean_value)
    return None


def _count_runs_by_type(df: pl.DataFrame) -> dict[str, int]:
    """Count different types of runs in the dataframe.

    Args:
        df: DataFrame with scenario results.

    Returns:
        Dictionary with run counts by type.
    """
    if df.is_empty():
        return {
            "total_runs": 0,
            "validated_runs": 0,
            "success_runs": 0,
            "failed_runs": 0,
            "exception_runs": 0,
            "no_validation_runs": 0,
        }

    return {
        "total_runs": len(df),
        "validated_runs": len(df.filter(pl.col("success_numeric").is_not_null())),
        "success_runs": len(df.filter(pl.col("status") == "success")),
        "failed_runs": len(df.filter(pl.col("status") == "failed")),
        "exception_runs": len(df.filter(pl.col("status") == "exception")),
        "no_validation_runs": len(df.filter(pl.col("status") == "no_validation")),
    }


def _calculate_success_rate_stats(df: pl.DataFrame) -> dict[str, float]:
    """Calculate success rate statistics from validated runs only.

    Args:
        df: DataFrame with scenario results.

    Returns:
        Dictionary with success rate, STD, and SEM.
    """
    validated_df = df.filter(pl.col("success_numeric").is_not_null())

    if validated_df.is_empty():
        return {
            "success_rate": 0.0,
            "success_rate_std": 0.0,
            "success_rate_sem": 0.0,
        }

    success_values = validated_df.select("success_numeric").to_series()
    mean_success = _safe_mean_to_float(success_values.mean())
    success_rate = (mean_success * 100.0) if mean_success is not None else 0.0

    # Calculate STD across run-level means
    run_numbers = validated_df.select("run_number").unique().to_series().sort()
    run_level_means = []

    for run_num in run_numbers:
        run_df = validated_df.filter(pl.col("run_number") == run_num)
        if not run_df.is_empty():
            run_mean = _safe_mean_to_float(run_df.select("success_numeric").to_series().mean())
            if run_mean is not None:
                run_level_means.append(run_mean * 100.0)

    success_rate_std = float(np.std(run_level_means, ddof=1)) if len(run_level_means) > 1 else 0.0
    success_rate_sem = success_rate_std / float(np.sqrt(len(run_level_means))) if len(run_level_means) > 1 else 0.0

    return {
        "success_rate": success_rate,
        "success_rate_std": success_rate_std,
        "success_rate_sem": success_rate_sem,
    }


def _calculate_pass_at_k_stats(df: pl.DataFrame) -> dict[str, Any]:
    """Calculate Pass@k and Pass^k statistics.

    Pass@k: scenarios with at least 1 success
    Pass^k: scenarios with all successes

    Args:
        df: DataFrame with scenario results.

    Returns:
        Dictionary with pass@k statistics.
    """
    validated_df = df.filter(pl.col("success_numeric").is_not_null())

    if validated_df.is_empty():
        total_scenarios = df.select("base_scenario_id").n_unique()
        return {
            "pass_at_k": 0,
            "pass_at_k_percent": 0.0,
            "pass_k": 0,
            "pass_k_percent": 0.0,
            "total_scenarios": total_scenarios,
            "k": 1,
        }

    total_scenarios = df.select("base_scenario_id").n_unique()

    # Calculate per-scenario success rates
    scenario_stats = validated_df.group_by("base_scenario_id").agg([
        pl.col("success_numeric").mean().alias("scenario_success_rate")
    ])

    pass_at_k = len(scenario_stats.filter(pl.col("scenario_success_rate") > 0.0))
    pass_k = len(scenario_stats.filter(pl.col("scenario_success_rate") == 1.0))

    # Determine k (runs per scenario)
    runs_per_scenario = df.group_by("base_scenario_id").agg(pl.len().alias("count"))
    k_values = runs_per_scenario.select("count").to_series().to_list()
    k = k_values[0] if k_values and len(set(k_values)) == 1 else max(k_values) if k_values else 1

    return {
        "pass_at_k": pass_at_k,
        "pass_at_k_percent": (pass_at_k / total_scenarios * 100) if total_scenarios > 0 else 0.0,
        "pass_k": pass_k,
        "pass_k_percent": (pass_k / total_scenarios * 100) if total_scenarios > 0 else 0.0,
        "total_scenarios": total_scenarios,
        "k": k,
    }


def _calculate_run_duration_stats(df: pl.DataFrame) -> dict[str, float]:
    """Calculate run duration statistics.

    Args:
        df: DataFrame with scenario results.

    Returns:
        Dictionary with average duration and STD.
    """
    duration_df = df.filter(pl.col("run_duration").is_not_null())

    if duration_df.is_empty():
        return {
            "avg_run_duration": 0.0,
            "avg_run_duration_std": 0.0,
        }

    avg_duration = _safe_mean_to_float(duration_df.select("run_duration").to_series().mean())
    duration_std = _safe_mean_to_float(duration_df.select("run_duration").to_series().std())

    return {
        "avg_run_duration": avg_duration if avg_duration is not None else 0.0,
        "avg_run_duration_std": duration_std if duration_std is not None else 0.0,
    }


def _calculate_pare_totals(df: pl.DataFrame) -> dict[str, int]:
    """Calculate PARE total counts.

    Args:
        df: DataFrame with scenario results.

    Returns:
        Dictionary with total counts.
    """
    if df.is_empty():
        return {
            "total_proposals": 0,
            "total_acceptances": 0,
            "total_turns": 0,
            "total_read_only_actions": 0,
            "total_write_actions": 0,
        }

    return {
        "total_proposals": df.select("proposal_count").sum().item(),
        "total_acceptances": df.select("acceptance_count").sum().item(),
        "total_turns": df.select("number_of_turns").sum().item(),
        "total_read_only_actions": df.select("read_only_actions").sum().item(),
        "total_write_actions": df.select("write_actions").sum().item(),
    }


def _calculate_proposal_rate_stats(df: pl.DataFrame) -> dict[str, float]:
    """Calculate proposal rate statistics with STD and SEM across run-level means.

    Args:
        df: DataFrame with scenario results.

    Returns:
        Dictionary with proposal rate, STD, and SEM.
    """
    if df.is_empty():
        return {
            "aggregate_proposal_rate": 0.0,
            "aggregate_proposal_rate_std": 0.0,
            "aggregate_proposal_rate_sem": 0.0,
        }

    total_proposals = df.select("proposal_count").sum().item()
    total_turns = df.select("number_of_turns").sum().item()
    aggregate_proposal_rate = total_proposals / total_turns if total_turns > 0 else 0.0

    # Calculate STD/SEM across run-level means
    run_numbers = df.select("run_number").unique().to_series().sort()
    run_proposal_rates = []

    for run_num in run_numbers:
        run_df = df.filter(pl.col("run_number") == run_num)
        if not run_df.is_empty():
            run_proposals = run_df.select("proposal_count").sum().item()
            run_turns = run_df.select("number_of_turns").sum().item()
            if run_turns > 0:
                run_proposal_rates.append(run_proposals / run_turns)

    proposal_rate_std = float(np.std(run_proposal_rates, ddof=1)) if len(run_proposal_rates) > 1 else 0.0
    proposal_rate_sem = (
        proposal_rate_std / float(np.sqrt(len(run_proposal_rates))) if len(run_proposal_rates) > 1 else 0.0
    )

    return {
        "aggregate_proposal_rate": aggregate_proposal_rate,
        "aggregate_proposal_rate_std": proposal_rate_std,
        "aggregate_proposal_rate_sem": proposal_rate_sem,
    }


def _calculate_acceptance_rate_stats(df: pl.DataFrame) -> dict[str, float]:
    """Calculate acceptance rate statistics with STD and SEM across run-level means.

    Args:
        df: DataFrame with scenario results.

    Returns:
        Dictionary with acceptance rate, STD, and SEM.
    """
    if df.is_empty():
        return {
            "aggregate_acceptance_rate": 0.0,
            "aggregate_acceptance_rate_std": 0.0,
            "aggregate_acceptance_rate_sem": 0.0,
        }

    total_proposals = df.select("proposal_count").sum().item()
    total_acceptances = df.select("acceptance_count").sum().item()
    aggregate_acceptance_rate = total_acceptances / total_proposals if total_proposals > 0 else 0.0

    # Calculate STD/SEM across run-level means
    run_numbers = df.select("run_number").unique().to_series().sort()
    run_acceptance_rates = []

    for run_num in run_numbers:
        run_df = df.filter(pl.col("run_number") == run_num)
        if not run_df.is_empty():
            run_proposals = run_df.select("proposal_count").sum().item()
            run_acceptances = run_df.select("acceptance_count").sum().item()
            if run_proposals > 0:
                run_acceptance_rates.append(run_acceptances / run_proposals)

    acceptance_rate_std = float(np.std(run_acceptance_rates, ddof=1)) if len(run_acceptance_rates) > 1 else 0.0
    acceptance_rate_sem = (
        acceptance_rate_std / float(np.sqrt(len(run_acceptance_rates))) if len(run_acceptance_rates) > 1 else 0.0
    )

    return {
        "aggregate_acceptance_rate": aggregate_acceptance_rate,
        "aggregate_acceptance_rate_std": acceptance_rate_std,
        "aggregate_acceptance_rate_sem": acceptance_rate_sem,
    }


def _calculate_action_stats(df: pl.DataFrame) -> dict[str, float]:
    """Calculate action statistics (avg per scenario) with STD and SEM across run-level means.

    Args:
        df: DataFrame with scenario results.

    Returns:
        Dictionary with avg actions per scenario, STD, and SEM.
    """
    if df.is_empty():
        return {
            "avg_read_only_actions": 0.0,
            "avg_read_only_actions_std": 0.0,
            "avg_read_only_actions_sem": 0.0,
            "avg_write_actions": 0.0,
            "avg_write_actions_std": 0.0,
            "avg_write_actions_sem": 0.0,
        }

    # Calculate overall averages per scenario
    total_scenarios = len(df)
    total_read_only = df.select("read_only_actions").sum().item()
    total_write = df.select("write_actions").sum().item()
    avg_read_only = total_read_only / total_scenarios if total_scenarios > 0 else 0.0
    avg_write = total_write / total_scenarios if total_scenarios > 0 else 0.0

    # Calculate STD/SEM across run-level means
    run_numbers = df.select("run_number").unique().to_series().sort()
    run_avg_read_only = []
    run_avg_write = []

    for run_num in run_numbers:
        run_df = df.filter(pl.col("run_number") == run_num)
        if not run_df.is_empty():
            run_scenario_count = len(run_df)
            run_read_only = run_df.select("read_only_actions").sum().item()
            run_write = run_df.select("write_actions").sum().item()
            if run_scenario_count > 0:
                run_avg_read_only.append(run_read_only / run_scenario_count)
                run_avg_write.append(run_write / run_scenario_count)

    read_only_std = float(np.std(run_avg_read_only, ddof=1)) if len(run_avg_read_only) > 1 else 0.0
    read_only_sem = read_only_std / float(np.sqrt(len(run_avg_read_only))) if len(run_avg_read_only) > 1 else 0.0

    write_std = float(np.std(run_avg_write, ddof=1)) if len(run_avg_write) > 1 else 0.0
    write_sem = write_std / float(np.sqrt(len(run_avg_write))) if len(run_avg_write) > 1 else 0.0

    return {
        "avg_read_only_actions": avg_read_only,
        "avg_read_only_actions_std": read_only_std,
        "avg_read_only_actions_sem": read_only_sem,
        "avg_write_actions": avg_write,
        "avg_write_actions_std": write_std,
        "avg_write_actions_sem": write_sem,
    }


# ! TODO: Add _calculate_capability_stats() when scenario categories are implemented
# ! TODO: Add _calculate_global_macro_stats() for macro success rate by category
# ! TODO: Add _calculate_global_micro_stats() for micro success rate by category
# ! TODO: Add per-scenario metrics breakdown by category
# ! TODO: Add action type distribution stats (read vs write by app)


def calculate_statistics(df: pl.DataFrame) -> dict[str, Any]:
    """Calculate comprehensive statistics for PARE benchmark results.

    Args:
        df: DataFrame with scenario results.

    Returns:
        Dictionary with comprehensive statistics.
    """
    if df.is_empty():
        return {
            "global": {
                "total_runs": 0,
                "validated_runs": 0,
                "success_runs": 0,
                "failed_runs": 0,
                "exception_runs": 0,
                "no_validation_runs": 0,
                "success_rate": 0.0,
                "success_rate_std": 0.0,
                "success_rate_sem": 0.0,
                "pass_at_k": 0,
                "pass_at_k_percent": 0.0,
                "pass_k": 0,
                "pass_k_percent": 0.0,
                "total_scenarios": 0,
                "k": 1,
                "avg_run_duration": 0.0,
                "avg_run_duration_std": 0.0,
                "job_duration": 0.0,
            },
            "pas_metrics": {
                "total_proposals": 0,
                "total_acceptances": 0,
                "total_turns": 0,
                "total_read_only_actions": 0,
                "total_write_actions": 0,
                "aggregate_proposal_rate": 0.0,
                "aggregate_proposal_rate_std": 0.0,
                "aggregate_proposal_rate_sem": 0.0,
                "aggregate_acceptance_rate": 0.0,
                "aggregate_acceptance_rate_std": 0.0,
                "aggregate_acceptance_rate_sem": 0.0,
                "avg_read_only_actions": 0.0,
                "avg_read_only_actions_std": 0.0,
                "avg_read_only_actions_sem": 0.0,
                "avg_write_actions": 0.0,
                "avg_write_actions_std": 0.0,
                "avg_write_actions_sem": 0.0,
            },
        }

    run_counts = _count_runs_by_type(df)
    success_rate_stats = _calculate_success_rate_stats(df)
    pass_k_stats = _calculate_pass_at_k_stats(df)
    duration_stats = _calculate_run_duration_stats(df)

    pas_totals = _calculate_pare_totals(df)
    proposal_rate_stats = _calculate_proposal_rate_stats(df)
    acceptance_rate_stats = _calculate_acceptance_rate_stats(df)
    action_stats = _calculate_action_stats(df)

    job_duration = _safe_mean_to_float(df.select("job_duration").to_series().mean())

    return {
        "global": {
            **run_counts,
            **success_rate_stats,
            **pass_k_stats,
            **duration_stats,
            "job_duration": job_duration if job_duration is not None else 0.0,
        },
        "pas_metrics": {
            **pas_totals,
            **proposal_rate_stats,
            **acceptance_rate_stats,
            **action_stats,
        },
    }


def _format_config_header(config: dict[str, Any]) -> str:
    """Format the config section header line.

    Args:
        config: Dictionary with config identifiers.

    Returns:
        Formatted config header line.
    """
    header = f"\n=== Config: {config['user_model']} | {config['proactive_model']} | "
    header += f"tool_fail={config['tool_failure_probability']} | env_events={config['num_env_events_per_minute']} ===\n"
    return header


def _format_config_content(config: dict[str, Any]) -> str:
    """Format the config section content with Metadata and Metrics.

    Args:
        config: Dictionary with config statistics.

    Returns:
        Formatted content with Metadata and Metrics sections.
    """
    content = ""

    # Metadata section
    content += "\n=== Metadata ===\n"
    content += f"  - Scenarios: {config['total_scenarios']} unique ({config['total_runs']} total runs)\n"

    # Show breakdown of run types if there are non-validated runs
    if config["no_validation_runs"] > 0 or config["exception_runs"] > 0:
        content += f"    - Validated runs (counted in success rate): {config['validated_runs']}\n"
        if config["no_validation_runs"] > 0:
            content += f"    - No validation runs (not counted): {config['no_validation_runs']}\n"
        if config["exception_runs"] > 0:
            content += f"    - Exception runs (counted as failures): {config['exception_runs']}\n"

    # Metrics section (both success/pass@k and PARE metrics)
    content += "\n=== Metrics ===\n"
    k = config["k"]
    content += f"  - Success rate: {config['success_rate']:.1f}% +/- {config['success_rate_sem']:.1f}% (STD: {config['success_rate_std']:.1f}%)\n"
    content += f"  - Pass@{k}: {config['pass_at_k']} scenarios ({config['pass_at_k_percent']:.1f}%)\n"
    content += f"  - Pass^{k}: {config['pass_k']} scenarios ({config['pass_k_percent']:.1f}%)\n"
    content += f"  - Avg run duration: {config['avg_run_duration']:.1f}s (STD: {config['avg_run_duration_std']:.1f}s)\n"
    content += f"  - Job duration: {config['job_duration']:.1f}s\n"
    content += f"  - Total proposals: {config['total_proposals']}\n"
    content += f"  - Total acceptances: {config['total_acceptances']}\n"
    content += f"  - Total turns: {config['total_turns']}\n"
    content += f"  - Proposal rate: {config['aggregate_proposal_rate']:.3f} +/- {config['aggregate_proposal_rate_sem']:.3f} (STD: {config['aggregate_proposal_rate_std']:.3f})\n"
    content += f"  - Acceptance rate: {config['aggregate_acceptance_rate'] * 100:.1f}% +/- {config['aggregate_acceptance_rate_sem'] * 100:.1f}% (STD: {config['aggregate_acceptance_rate_std'] * 100:.1f}%)\n"
    content += f"  - Avg read-only actions: {config['avg_read_only_actions']:.1f} +/- {config['avg_read_only_actions_sem']:.1f} (STD: {config['avg_read_only_actions_std']:.1f})\n"
    content += f"  - Avg write actions: {config['avg_write_actions']:.1f} +/- {config['avg_write_actions_sem']:.1f} (STD: {config['avg_write_actions_std']:.1f})\n"

    return content


def generate_validation_report(
    df: pl.DataFrame,
    split: str = "full",
    weight_per_app_class: dict[str, float] | None = None,
) -> str:
    """Generate a validation report for PARE benchmark results.

    Uses generate_json_stats_report() as the source of truth and formats as text.

    Args:
        df: DataFrame with scenario results (can have multiple configs).
        split: Dataset split name (e.g., "full", "ablation").
        weight_per_app_class: Weight per app class from EnvEventsConfig.

    Returns:
        Formatted report string.
    """
    # Get structured stats from JSON report
    json_report = generate_json_stats_report(df, split, weight_per_app_class)

    # Build text report header
    report = "\n=== PARE Validation Report ===\n"
    report += f"Split: {json_report['metadata']['split']}\n"
    if json_report["metadata"]["weight_per_app_class"]:
        report += f"Weight per app class: {json_report['metadata']['weight_per_app_class']}\n"
    report += f"Generated: {json_report['metadata']['timestamp']}\n"

    # Add each config's section
    for config in json_report["per_config_results"]:
        report += _format_config_header(config)
        report += _format_config_content(config)

    return report


def combine_results_to_dataframe(
    results: dict[tuple[str, str, float, int], PAREMultiScenarioValidationResult],
) -> pl.DataFrame:
    """Combine multiple PAREMultiScenarioValidationResult objects into a single DataFrame.

    Args:
        results: Dictionary mapping (user_model, proactive_model, tool_failure_probability,
                 num_env_events_per_minute) tuples to PAREMultiScenarioValidationResult objects.

    Returns:
        Polars DataFrame with all scenario runs combined, or empty DataFrame with
        correct schema if no results.
    """
    from pare.scenarios.validation_result import PARE_RESULT_SCHEMA

    dataframes = []

    for multi_result in results.values():
        df = multi_result.to_polars()
        if not df.is_empty():
            dataframes.append(df)

    if not dataframes:
        return pl.DataFrame(schema=PARE_RESULT_SCHEMA)

    return pl.concat(dataframes, how="vertical")


def generate_json_stats_report(
    df: pl.DataFrame,
    split: str = "full",
    weight_per_app_class: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Generate a computer-readable JSON report for PARE benchmark results.

    Args:
        df: Combined DataFrame with scenario results (can have multiple configs).
        split: Dataset split name (e.g., "full", "ablation").
        weight_per_app_class: Weight per app class from EnvEventsConfig (for metadata).

    Returns:
        Dictionary containing per-config statistics with STD/SEM.
    """
    import datetime

    per_config_results = []

    if not df.is_empty():
        # Get unique config combinations
        config_keys = df.select([
            "user_model",
            "proactive_model",
            "tool_failure_probability",
            "num_env_events_per_minute",
        ]).unique()

        for row in config_keys.iter_rows(named=True):
            # Filter to this config
            config_df = df.filter(
                (pl.col("user_model") == row["user_model"])
                & (pl.col("proactive_model") == row["proactive_model"])
                & (pl.col("tool_failure_probability") == row["tool_failure_probability"])
                & (pl.col("num_env_events_per_minute") == row["num_env_events_per_minute"])
            )

            # Get full stats for this config (includes STD/SEM across runs)
            stats = calculate_statistics(config_df)

            per_config_results.append({
                "user_model": row["user_model"],
                "proactive_model": row["proactive_model"],
                "tool_failure_probability": row["tool_failure_probability"],
                "num_env_events_per_minute": row["num_env_events_per_minute"],
                **stats["global"],
                **stats["pas_metrics"],
            })

    return {
        "metadata": {
            "split": split,
            "timestamp": datetime.datetime.now().isoformat(),
            "report_version": "1.0",
            "weight_per_app_class": weight_per_app_class,
        },
        "per_config_results": per_config_results,
    }
