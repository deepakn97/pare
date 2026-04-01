"""Single-shot user model evaluator for accept/reject decision points.

Loads llm_input messages from traces, fires them at candidate user models
via LLMEngineBuilder, and parses responses with JsonActionExecutor.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl
from are.simulation.agents.are_simulation_agent_config import LLMEngineConfig
from are.simulation.agents.default_agent.tools.json_action_executor import (
    parse_json_tool_call,
)
from are.simulation.agents.llm.llm_engine_builder import LLMEngineBuilder
from are.simulation.exceptions import JsonParsingAgentError
from tqdm import tqdm

if TYPE_CHECKING:
    from are.simulation.agents.llm.llm_engine import LLMEngine

    from pare.trajectory.models import TernaryDecision

logger = logging.getLogger(__name__)

ACTION_TOKEN = "Action:"  # noqa: S105
THOUGHT_TOKEN = "Thought:"  # noqa: S105
STOP_SEQUENCES = ["<end_action>", "Observation:"]
MAX_RETRIES = 10


# ===== DEPRECATED BINARY PIPELINE FUNCTIONS =====
# The functions below are superseded by the ternary pipeline functions
# (evaluate_single_decision_ternary, evaluate_samples_ternary, etc.)
# They will be removed after the UI update.


def _parse_trace_logs(trace_file: Path) -> list[dict[str, Any]]:
    """Parse world_logs from a trace file."""
    with open(trace_file) as f:
        data = json.load(f)
    logs = data.get("world_logs", [])
    return [json.loads(log) if isinstance(log, str) else log for log in logs]


def _find_user_agent_id(parsed_logs: list[dict[str, Any]]) -> str | None:
    """Find the user agent ID from system prompt logs."""
    for log in parsed_logs:
        if log.get("log_type") == "system_prompt":
            content = log.get("content", "")
            if isinstance(content, str) and "simulating a real human user" in content:
                return log.get("agent_id")
    return None


def _is_decision_log(log: dict[str, Any], user_agent_id: str, decision_timestamp: float) -> bool:
    """Check if a log entry is the target accept/reject decision."""
    if log.get("log_type") != "tool_call" or log.get("agent_id") != user_agent_id:
        return False
    if abs(log.get("timestamp", 0) - decision_timestamp) >= 0.01:
        return False
    tool_name = log.get("tool_name", "")
    return "accept_proposal" in tool_name or "reject_proposal" in tool_name


def extract_llm_input_from_trace(
    trace_file: Path,
    decision_timestamp: float,
) -> list[dict[str, Any]] | None:
    """Extract the llm_input message array preceding a decision point from a trace.

    .. deprecated::
        Ternary pipeline reads llm_input from parquet directly. Will be removed after UI update.

    Finds the llm_input log entry for the user agent immediately before
    the accept/reject decision at the given timestamp.

    Args:
        trace_file: Path to the trace JSON file.
        decision_timestamp: Timestamp of the accept/reject decision event.

    Returns:
        The message array (list of dicts with role/content), or None if not found.
    """
    parsed_logs = _parse_trace_logs(trace_file)

    user_agent_id = _find_user_agent_id(parsed_logs)
    if not user_agent_id:
        logger.warning(f"Could not find user agent ID in {trace_file}")
        return None

    # Find the accept/reject decision at the given timestamp
    decision_idx = None
    for i, log in enumerate(parsed_logs):
        if _is_decision_log(log, user_agent_id, decision_timestamp):
            decision_idx = i
            break

    if decision_idx is None:
        logger.warning(f"Could not find decision at timestamp {decision_timestamp} in {trace_file}")
        return None

    # Find the llm_input immediately preceding this decision (same agent)
    for j in range(decision_idx - 1, max(decision_idx - 30, 0), -1):
        log = parsed_logs[j]
        if log.get("log_type") == "llm_input" and log.get("agent_id") == user_agent_id:
            content = log.get("content")
            return json.loads(content) if isinstance(content, str) else content

    logger.warning(f"Could not find llm_input before decision at index {decision_idx} in {trace_file}")
    return None


def evaluate_single_decision(
    messages: list[dict[str, Any]],
    engine: LLMEngine,
) -> tuple[bool | None, bool]:
    """Fire a single-shot query and parse the accept/reject decision.

    .. deprecated::
        Use ``evaluate_single_decision_ternary`` for ternary classification. Will be removed after UI update.

    Uses the same retry logic as BaseAgent: retries up to MAX_RETRIES times
    if the output doesn't contain Action:/Thought: tokens.

    Args:
        messages: The llm_input message array.
        engine: An LLMEngine instance.

    Returns:
        Tuple of (decision: True=accept/False=reject/None=unparseable, valid_response: bool).
    """
    llm_output = None
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response = engine.chat_completion(messages, stop_sequences=STOP_SEQUENCES)
            llm_output = response[0] if isinstance(response, tuple) and len(response) == 2 else response

            if llm_output and (ACTION_TOKEN in llm_output or THOUGHT_TOKEN in llm_output):
                break

            logger.debug(f"Attempt {attempt + 1}: output missing Action:/Thought: tokens, retrying")
        except Exception as e:
            last_error = e
            logger.warning(f"Attempt {attempt + 1}: LLM call failed: {e}")
            llm_output = None

    if not llm_output or ACTION_TOKEN not in llm_output:
        if last_error:
            logger.warning(f"LLM evaluation failed after {MAX_RETRIES} attempts.")
        elif llm_output:
            logger.warning(f"LLM output missing Action: token after {MAX_RETRIES} attempts")
        else:
            logger.warning(f"LLM produced no output after {MAX_RETRIES} attempts")
        return None, False

    # Parse the action
    try:
        action_text = llm_output.split(ACTION_TOKEN)[-1]
        tool_name, _arguments = parse_json_tool_call(action_text)

        if "accept_proposal" in tool_name:
            return True, True
        elif "reject_proposal" in tool_name:
            return False, True
        else:
            logger.warning(f"Unexpected tool call: {tool_name}")
            return None, False
    except (JsonParsingAgentError, Exception) as e:
        logger.warning(f"Failed to parse action: {e}")
        return None, False


def evaluate_samples(
    samples_df: pl.DataFrame,
    user_models: list[str],
    models_map: dict[str, dict[str, str]],
    runs: int = 4,
    target_models: list[str] | None = None,
    smoke_test: bool = False,
) -> pl.DataFrame:
    """Evaluate multiple user models on sampled decision points.

    .. deprecated::
        Use ``evaluate_samples_ternary`` for ternary evaluation with ThreadPoolExecutor. Will be removed after UI update.

    Args:
        samples_df: DataFrame from samples.parquet with decision point context.
        user_models: List of user model aliases to evaluate.
        models_map: MODELS_MAP dict mapping aliases to model_name/provider.
        runs: Number of runs per (sample, user_model) pair.
        target_models: If provided, filter samples to these proactive models.
        smoke_test: If True, only process 10 samples.

    Returns:
        DataFrame with columns: sample_id, scenario_id, proactive_model_id,
        user_model_id, user_agent_decision, run, valid_response.
    """
    # Filter by target proactive models
    df = samples_df
    if target_models:
        df = df.filter(pl.col("proactive_model_id").is_in(target_models))
        logger.info(f"Filtered to {len(df)} samples from models: {target_models}")

    if smoke_test:
        df = df.head(10)
        logger.info("Smoke test mode: using only 10 samples")

    # Build engines for each user model
    engines: dict[str, LLMEngine] = {}
    for model_alias in user_models:
        model_info = models_map.get(model_alias, {"model_name": model_alias, "provider": "openai"})
        engine_config = LLMEngineConfig(
            model_name=model_info["model_name"],
            provider=model_info["provider"],
        )
        engines[model_alias] = LLMEngineBuilder().create_engine(engine_config)
        logger.info(f"Created engine for {model_alias} ({model_info['model_name']}, {model_info['provider']})")

    # Evaluate each sample with each model
    results: list[dict[str, Any]] = []
    total = len(df) * len(user_models) * runs
    completed = 0

    for row in df.iter_rows(named=True):
        sample_results, count = _evaluate_single_sample(row, user_models, engines, runs)
        results.extend(sample_results)
        completed += count
        if completed % 50 == 0:
            logger.info(f"Progress: {completed}/{total} evaluations complete")

    return pl.DataFrame(results)


def _evaluate_single_sample(
    row: dict[str, Any],
    user_models: list[str],
    engines: dict[str, LLMEngine],
    runs: int,
) -> tuple[list[dict[str, Any]], int]:
    """Evaluate a single sample across all user models and runs."""
    sample_id = row["sample_id"]
    scenario_id = row["scenario_id"]
    proactive_model_id = row["proactive_model_id"]
    trace_file = Path(row["trace_file"])
    decision_timestamp = row["decision_timestamp"]

    results: list[dict[str, Any]] = []
    messages = extract_llm_input_from_trace(trace_file, decision_timestamp)

    if messages is None:
        logger.warning(f"Skipping {sample_id}: could not extract llm_input")
        for model_alias in user_models:
            for run_num in range(1, runs + 1):
                results.append(
                    _make_result(sample_id, scenario_id, proactive_model_id, model_alias, None, run_num, valid=False)
                )
        return results, len(user_models) * runs

    for model_alias in user_models:
        engine = engines[model_alias]
        for run_num in range(1, runs + 1):
            decision, valid = evaluate_single_decision(messages, engine)
            results.append(
                _make_result(sample_id, scenario_id, proactive_model_id, model_alias, decision, run_num, valid)
            )

    return results, len(user_models) * runs


def _make_result(
    sample_id: str,
    scenario_id: str,
    proactive_model_id: str,
    user_model_id: str,
    decision: bool | None,
    run: int,
    valid: bool,
) -> dict[str, Any]:
    """Create a single evaluation result dict."""
    return {
        "sample_id": sample_id,
        "scenario_id": scenario_id,
        "proactive_model_id": proactive_model_id,
        "user_model_id": user_model_id,
        "user_agent_decision": decision,
        "run": run,
        "valid_response": valid,
    }


def print_evaluation_summary(eval_df: pl.DataFrame, original_samples_df: pl.DataFrame | None = None) -> None:
    """Print a summary of evaluation results.

    .. deprecated::
        Use ``print_evaluation_summary_ternary`` for ternary output. Will be removed after UI update.

    Args:
        eval_df: Evaluation results DataFrame.
        original_samples_df: Original samples DataFrame for sanity check comparison.
    """
    # Per-model acceptance rate
    valid_df = eval_df.filter(pl.col("valid_response"))

    summary = (
        valid_df.group_by("user_model_id")
        .agg(
            pl.col("user_agent_decision").mean().alias("acceptance_rate"),
            pl.col("valid_response").count().alias("total_valid"),
        )
        .sort("user_model_id")
    )

    print("\n=== Evaluation Summary ===")
    print(f"Total evaluations: {len(eval_df)}")
    valid_pct = (len(valid_df) / len(eval_df) * 100) if len(eval_df) > 0 else 0.0
    print(f"Valid responses: {len(valid_df)} ({valid_pct:.1f}%)")

    print("\n--- Acceptance Rate by User Model ---")
    for row in summary.iter_rows(named=True):
        rate = row["acceptance_rate"]
        rate_str = f"{rate * 100:.1f}%" if rate is not None else "N/A"
        print(f"  {row['user_model_id']:<25} {rate_str:>8}  ({row['total_valid']} valid)")

    # Per proactive model breakdown
    breakdown = (
        valid_df.group_by(["user_model_id", "proactive_model_id"])
        .agg(pl.col("user_agent_decision").mean().alias("acceptance_rate"))
        .sort(["user_model_id", "proactive_model_id"])
    )

    print("\n--- Acceptance Rate by User Model x Proactive Model ---")
    for row in breakdown.iter_rows(named=True):
        rate = row["acceptance_rate"]
        rate_str = f"{rate * 100:.1f}%" if rate is not None else "N/A"
        print(f"  {row['user_model_id']:<25} x {row['proactive_model_id']:<25} {rate_str}")

    # Invalid response rate
    invalid_summary = (
        eval_df.group_by("user_model_id")
        .agg((~pl.col("valid_response")).mean().alias("invalid_rate"))
        .sort("user_model_id")
    )

    print("\n--- Invalid Response Rate ---")
    for row in invalid_summary.iter_rows(named=True):
        rate = row["invalid_rate"]
        rate_str = f"{rate * 100:.1f}%" if rate is not None else "N/A"
        print(f"  {row['user_model_id']:<25} {rate_str}")

    # Sanity check: compare original model's evaluator decisions with trace decisions
    if original_samples_df is not None:
        original_user_model = (
            original_samples_df["user_model_id"][0] if "user_model_id" in original_samples_df.columns else None
        )
        if original_user_model and original_user_model in eval_df["user_model_id"].unique().to_list():
            # Get majority vote from evaluator runs for original model
            original_eval = (
                valid_df.filter(pl.col("user_model_id") == original_user_model)
                .group_by("sample_id")
                .agg(pl.col("user_agent_decision").mean().alias("eval_accept_rate"))
            )
            original_eval = original_eval.with_columns(
                (pl.col("eval_accept_rate") >= 0.5).alias("eval_majority_decision")
            )

            # Join with original decisions
            comparison = original_eval.join(
                original_samples_df.select(["sample_id", "user_agent_decision"]),
                on="sample_id",
                how="inner",
            )

            if len(comparison) > 0:
                agreement = (
                    comparison.filter(pl.col("eval_majority_decision") == pl.col("user_agent_decision")).height
                    / comparison.height
                    * 100
                )
                print(f"\n--- Sanity Check: {original_user_model} ---")
                print(
                    f"  Evaluator majority vote vs original trace decision: {agreement:.1f}% agreement ({comparison.height} samples)"
                )


# ===== NEW TERNARY PIPELINE FUNCTIONS =====


def evaluate_single_decision_ternary(
    messages: list[dict[str, Any]],
    engine: LLMEngine,
) -> tuple[TernaryDecision | None, bool]:
    """Fire a single-shot query and parse the ternary decision.

    Classifies decision based on first tool call only:
    - accept_proposal in tool name -> "accept"
    - reject_proposal in tool name -> "reject"
    - Any other valid tool call -> "gather_context"
    - No valid tool call -> None (invalid)

    Only retries on unparseable output (no Action: token, API error).
    Does NOT retry on valid tool calls.

    Args:
        messages: The llm_input message array.
        engine: An LLMEngine instance.

    Returns:
        Tuple of (decision: "accept"/"reject"/"gather_context"/None, valid_response: bool).
    """
    llm_output = None
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response = engine.chat_completion(messages, stop_sequences=STOP_SEQUENCES)
            llm_output = response[0] if isinstance(response, tuple) and len(response) == 2 else response

            if llm_output and (ACTION_TOKEN in llm_output or THOUGHT_TOKEN in llm_output):
                break

            logger.debug(f"Attempt {attempt + 1}: output missing Action:/Thought: tokens, retrying")
        except Exception as e:
            last_error = e
            logger.warning(f"Attempt {attempt + 1}: LLM call failed: {e}")
            llm_output = None

    if not llm_output or ACTION_TOKEN not in llm_output:
        if last_error:
            logger.warning(f"LLM evaluation failed after {MAX_RETRIES} attempts.")
        elif llm_output:
            logger.warning(f"LLM output missing Action: token after {MAX_RETRIES} attempts")
        else:
            logger.warning(f"LLM produced no output after {MAX_RETRIES} attempts")
        return None, False

    # Parse the action - first tool call determines decision
    try:
        action_text = llm_output.split(ACTION_TOKEN)[-1]
        tool_name, _arguments = parse_json_tool_call(action_text)

        if "accept_proposal" in tool_name:
            return "accept", True
        elif "reject_proposal" in tool_name:
            return "reject", True
        else:
            # Any other valid tool call is classified as gather_context
            return "gather_context", True
    except (JsonParsingAgentError, Exception) as e:
        logger.warning(f"Failed to parse action: {e}")
        return None, False


def evaluate_samples_ternary(
    samples_df: pl.DataFrame,
    user_models: list[str],
    models_map: dict[str, dict[str, str]],
    runs: int = 3,
    target_models: list[str] | None = None,
    smoke_test: bool = False,
    max_workers: int | None = None,
) -> pl.DataFrame:
    """Evaluate multiple user models on sampled decision points with parallelism.

    Pre-deserializes all llm_input from parquet, then uses ThreadPoolExecutor
    to parallelize evaluation across models and runs.

    Args:
        samples_df: DataFrame from samples.parquet with llm_input column.
        user_models: List of user model aliases to evaluate.
        models_map: MODELS_MAP dict mapping aliases to model_name/provider.
        runs: Number of runs per (sample, user_model) pair.
        target_models: If provided, filter samples to these proactive models.
        smoke_test: If True, only process 10 samples.
        max_workers: Number of threads (default: min(len(user_models), cpu_count)).

    Returns:
        DataFrame with columns: sample_id, scenario_id, proactive_model_id,
        user_model_id, user_agent_decision, run, valid_response.
    """
    # Filter by target proactive models
    df = samples_df
    if target_models:
        df = df.filter(pl.col("proactive_model_id").is_in(target_models))
        logger.info(f"Filtered to {len(df)} samples from models: {target_models}")

    if smoke_test:
        df = df.head(10)
        logger.info("Smoke test mode: using only 10 samples")

    # Pre-deserialize all llm_input upfront
    logger.info("Pre-deserializing llm_input from parquet...")
    llm_inputs: dict[str, list[dict[str, Any]]] = {}
    for row in df.iter_rows(named=True):
        sample_id = row["sample_id"]
        llm_input_str = row["llm_input"]
        llm_inputs[sample_id] = json.loads(llm_input_str)
    logger.info(f"Deserialized {len(llm_inputs)} llm_input arrays")

    # Build engines for each user model
    engines: dict[str, LLMEngine] = {}
    for model_alias in user_models:
        model_info = models_map.get(model_alias, {"model_name": model_alias, "provider": "openai"})
        engine_config = LLMEngineConfig(
            model_name=model_info["model_name"],
            provider=model_info["provider"],
        )
        engines[model_alias] = LLMEngineBuilder().create_engine(engine_config)
        logger.info(f"Created engine for {model_alias} ({model_info['model_name']}, {model_info['provider']})")

    # Create flat list of jobs
    jobs: list[dict[str, Any]] = []
    for row in df.iter_rows(named=True):
        sample_id = row["sample_id"]
        scenario_id = row["scenario_id"]
        proactive_model_id = row["proactive_model_id"]
        messages = llm_inputs[sample_id]

        for model_alias in user_models:
            for run_num in range(1, runs + 1):
                jobs.append({
                    "sample_id": sample_id,
                    "scenario_id": scenario_id,
                    "proactive_model_id": proactive_model_id,
                    "user_model_id": model_alias,
                    "run": run_num,
                    "messages": messages,
                    "engine": engines[model_alias],
                })

    # Determine max_workers
    if max_workers is None:
        max_workers = min(len(user_models), os.cpu_count() or 4)
    logger.info(f"Starting parallel evaluation with {max_workers} workers for {len(jobs)} jobs")

    # Submit jobs to ThreadPoolExecutor
    results: list[dict[str, Any]] = []
    total = len(jobs)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_job = {executor.submit(_evaluate_job_ternary, job): job for job in jobs}

        for future in tqdm(as_completed(future_to_job), total=total, desc="Evaluating"):
            results.append(future.result())

    return pl.DataFrame(results)


def _evaluate_job_ternary(job: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a single job (sample x model x run).

    Args:
        job: Job dictionary with sample_id, scenario_id, proactive_model_id, user_model_id, run, messages, engine.

    Returns:
        Result dictionary with sample_id, scenario_id, proactive_model_id, user_model_id, user_agent_decision, run, valid_response.
    """
    decision, valid = evaluate_single_decision_ternary(job["messages"], job["engine"])
    return {
        "sample_id": job["sample_id"],
        "scenario_id": job["scenario_id"],
        "proactive_model_id": job["proactive_model_id"],
        "user_model_id": job["user_model_id"],
        "user_agent_decision": decision,
        "run": job["run"],
        "valid_response": valid,
    }


def aggregate_evaluations(eval_df: pl.DataFrame) -> pl.DataFrame:
    """Aggregate raw evaluation results to soft labels and hard labels.

    Computes per (sample_id, user_model_id):
    - Raw counts: accept_count, reject_count, gather_context_count
    - Soft labels: accept_prob, reject_prob, gather_context_prob
    - Hard label: argmax of counts (tie-break with hash of sample_id)

    Pairs with fewer valid responses than total runs are logged as warnings.
    Pairs with zero valid responses are excluded from the output entirely
    (also logged as warnings).

    Args:
        eval_df: Raw evaluation DataFrame with one row per run.

    Returns:
        Aggregated DataFrame with one row per (sample_id, user_model_id).
    """
    # Check for pairs with fewer valid responses than requested runs
    total_runs_per_pair = eval_df.group_by(["sample_id", "user_model_id"]).agg(
        pl.col("valid_response").sum().alias("valid_count"),
        pl.col("valid_response").count().alias("total_count"),
    )
    incomplete = total_runs_per_pair.filter(pl.col("valid_count") < pl.col("total_count"))
    for row in incomplete.iter_rows(named=True):
        logger.warning(
            f"Sample {row['sample_id']} x {row['user_model_id']}: "
            f"only {row['valid_count']}/{row['total_count']} valid responses"
        )
    dropped = total_runs_per_pair.filter(pl.col("valid_count") == 0)
    for row in dropped.iter_rows(named=True):
        logger.warning(
            f"Sample {row['sample_id']} x {row['user_model_id']}: all responses invalid, pair excluded from aggregation"
        )

    # Filter to valid responses only
    valid_df = eval_df.filter(pl.col("valid_response"))

    # Count decisions per category
    aggregated = valid_df.group_by(["sample_id", "scenario_id", "user_model_id", "proactive_model_id"]).agg([
        (pl.col("user_agent_decision") == "accept").sum().alias("accept_count"),
        (pl.col("user_agent_decision") == "reject").sum().alias("reject_count"),
        (pl.col("user_agent_decision") == "gather_context").sum().alias("gather_context_count"),
        pl.col("valid_response").sum().alias("valid_runs"),
    ])

    # Compute soft labels (probabilities)
    aggregated = aggregated.with_columns([
        (pl.col("accept_count") / pl.col("valid_runs")).alias("accept_prob"),
        (pl.col("reject_count") / pl.col("valid_runs")).alias("reject_prob"),
        (pl.col("gather_context_count") / pl.col("valid_runs")).alias("gather_context_prob"),
    ])

    # Compute hard label (argmax with deterministic tie-breaking)
    def determine_hard_label(row: dict[str, Any]) -> str:
        counts = {
            "accept": row["accept_count"],
            "reject": row["reject_count"],
            "gather_context": row["gather_context_count"],
        }
        max_count = max(counts.values())
        tied = [label for label, count in counts.items() if count == max_count]

        if len(tied) == 1:
            return tied[0]

        # Tie-break using hash of sample_id
        sample_id = row["sample_id"]
        seed = int(hashlib.md5(sample_id.encode(), usedforsecurity=False).hexdigest(), 16) % len(tied)
        return sorted(tied)[seed]

    aggregated = aggregated.with_columns(
        pl.struct(["sample_id", "accept_count", "reject_count", "gather_context_count"])
        .map_elements(determine_hard_label, return_dtype=pl.Utf8)
        .alias("hard_label")
    )

    return aggregated


def print_evaluation_summary_ternary(eval_df: pl.DataFrame, original_samples_df: pl.DataFrame | None = None) -> None:
    """Print a summary of ternary evaluation results.

    Args:
        eval_df: Evaluation results DataFrame (raw, one row per run).
        original_samples_df: Original samples DataFrame for sanity check comparison.

    Returns:
        None. Prints summary to stdout.
    """
    # Per-model decision rates
    valid_df = eval_df.filter(pl.col("valid_response"))

    summary = (
        valid_df.group_by("user_model_id")
        .agg([
            (pl.col("user_agent_decision") == "accept").mean().alias("accept_rate"),
            (pl.col("user_agent_decision") == "reject").mean().alias("reject_rate"),
            (pl.col("user_agent_decision") == "gather_context").mean().alias("gather_context_rate"),
            pl.col("valid_response").count().alias("total_valid"),
        ])
        .sort("user_model_id")
    )

    print("\n=== Ternary Evaluation Summary ===")
    print(f"Total evaluations: {len(eval_df)}")
    valid_pct = (len(valid_df) / len(eval_df) * 100) if len(eval_df) > 0 else 0.0
    print(f"Valid responses: {len(valid_df)} ({valid_pct:.1f}%)")

    print("\n--- Decision Rates by User Model ---")
    print(f"  {'User Model':<25} {'Accept':>8} {'Reject':>8} {'Gather':>8} {'Valid':>8}")
    for row in summary.iter_rows(named=True):
        accept_str = f"{row['accept_rate'] * 100:.1f}%" if row["accept_rate"] is not None else "N/A"
        reject_str = f"{row['reject_rate'] * 100:.1f}%" if row["reject_rate"] is not None else "N/A"
        gather_str = f"{row['gather_context_rate'] * 100:.1f}%" if row["gather_context_rate"] is not None else "N/A"
        print(f"  {row['user_model_id']:<25} {accept_str:>8} {reject_str:>8} {gather_str:>8} {row['total_valid']:>8}")

    # Per proactive model breakdown
    breakdown = (
        valid_df.group_by(["user_model_id", "proactive_model_id"])
        .agg([
            (pl.col("user_agent_decision") == "accept").mean().alias("accept_rate"),
            (pl.col("user_agent_decision") == "reject").mean().alias("reject_rate"),
            (pl.col("user_agent_decision") == "gather_context").mean().alias("gather_context_rate"),
        ])
        .sort(["user_model_id", "proactive_model_id"])
    )

    print("\n--- Decision Rates by User Model x Proactive Model ---")
    for row in breakdown.iter_rows(named=True):
        accept_str = f"{row['accept_rate'] * 100:.1f}%" if row["accept_rate"] is not None else "N/A"
        reject_str = f"{row['reject_rate'] * 100:.1f}%" if row["reject_rate"] is not None else "N/A"
        gather_str = f"{row['gather_context_rate'] * 100:.1f}%" if row["gather_context_rate"] is not None else "N/A"
        print(f"  {row['user_model_id']:<25} x {row['proactive_model_id']:<25}")
        print(f"    Accept: {accept_str}, Reject: {reject_str}, Gather: {gather_str}")

    # Invalid response rate
    invalid_summary = (
        eval_df.group_by("user_model_id")
        .agg((~pl.col("valid_response")).mean().alias("invalid_rate"))
        .sort("user_model_id")
    )

    print("\n--- Invalid Response Rate ---")
    for row in invalid_summary.iter_rows(named=True):
        rate = row["invalid_rate"]
        rate_str = f"{rate * 100:.1f}%" if rate is not None else "N/A"
        print(f"  {row['user_model_id']:<25} {rate_str}")

    # Sanity check: compare original model's evaluator decisions with trace decisions
    if original_samples_df is not None:
        original_user_model = (
            original_samples_df["user_model_id"][0] if "user_model_id" in original_samples_df.columns else None
        )
        if original_user_model and original_user_model in eval_df["user_model_id"].unique().to_list():
            # Get majority vote from evaluator runs for original model
            aggregated = aggregate_evaluations(valid_df.filter(pl.col("user_model_id") == original_user_model))

            # Join with original decisions
            comparison = aggregated.join(
                original_samples_df.select(["sample_id", "user_agent_decision"]),
                on="sample_id",
                how="inner",
            )

            if len(comparison) > 0:
                agreement = (
                    comparison.filter(pl.col("hard_label") == pl.col("user_agent_decision")).height
                    / comparison.height
                    * 100
                )
                print(f"\n--- Sanity Check: {original_user_model} ---")
                print(
                    f"  Evaluator hard label vs original trace decision: {agreement:.1f}% agreement ({comparison.height} samples)"
                )
