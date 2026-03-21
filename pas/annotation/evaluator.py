"""Single-shot user model evaluator for accept/reject decision points.

Loads llm_input messages from traces, fires them at candidate user models
via LLMEngineBuilder, and parses responses with JsonActionExecutor.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl
from are.simulation.agents.are_simulation_agent_config import LLMEngineConfig
from are.simulation.agents.default_agent.tools.json_action_executor import (
    parse_json_tool_call,
)
from are.simulation.agents.llm.llm_engine_builder import LLMEngineBuilder
from are.simulation.exceptions import JsonParsingAgentError

if TYPE_CHECKING:
    from are.simulation.agents.llm.llm_engine import LLMEngine

logger = logging.getLogger(__name__)

ACTION_TOKEN = "Action:"  # noqa: S105
THOUGHT_TOKEN = "Thought:"  # noqa: S105
STOP_SEQUENCES = ["<end_action>", "Observation:"]
MAX_RETRIES = 10


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

    Uses the same retry logic as BaseAgent: retries up to MAX_RETRIES times
    if the output doesn't contain Action:/Thought: tokens.

    Args:
        messages: The llm_input message array.
        engine: An LLMEngine instance.

    Returns:
        Tuple of (decision: True=accept/False=reject/None=unparseable, valid_response: bool).
    """
    llm_output = None
    for attempt in range(MAX_RETRIES):
        try:
            response = engine.chat_completion(messages, stop_sequences=STOP_SEQUENCES)
            llm_output = response[0] if isinstance(response, tuple) and len(response) == 2 else response

            if llm_output and (ACTION_TOKEN in llm_output or THOUGHT_TOKEN in llm_output):
                break

            logger.debug(f"Attempt {attempt + 1}: output missing Action:/Thought: tokens, retrying")
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}: LLM call failed: {e}")
            llm_output = None

    if not llm_output or ACTION_TOKEN not in llm_output:
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
            logger.debug(f"Unexpected tool call: {tool_name}")
            return None, False
    except (JsonParsingAgentError, Exception) as e:
        logger.debug(f"Failed to parse action: {e}")
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
    print(f"Valid responses: {len(valid_df)} ({len(valid_df) / len(eval_df) * 100:.1f}%)")

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
