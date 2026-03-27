"""Proposal-centric trace parser for extracting decision points.

Single forward scan algorithm:
1. Identify agents by system prompt content
2. Truncate trace at first execute agent tool call
3. Pair proposals with accept/reject decisions
4. Classify: direct accept/reject vs gather_context
5. Extract and annotate llm_input at proposal point
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from pas.trajectory.models import DecisionPoint

logger = logging.getLogger(__name__)

# Search window sizes for finding llm_input logs near events
# These values balance between finding nearby logs and avoiding full trace scans
FORWARD_SEARCH_WINDOW = 50  # Max logs to search forward from proposal point
BACKWARD_SEARCH_WINDOW = 30  # Max logs to search backward from decision point


def extract_decision_points(
    trace_path: Path,
    proactive_model_id: str,
    user_model_id: str = "unknown",
) -> list[DecisionPoint]:
    """Extract all decision points from a trace file.

    Args:
        trace_path: Path to the trace JSON file.
        proactive_model_id: The proactive model identifier.
        user_model_id: The user model identifier.

    Returns:
        List of DecisionPoint objects, one per valid proposal-decision pair.
    """
    with open(trace_path) as f:
        data = json.load(f)

    logs = data.get("world_logs", [])
    # Parse string-encoded log entries, skip malformed ones
    parsed_logs = []
    for log_entry in logs:
        if isinstance(log_entry, str):
            try:
                parsed_logs.append(json.loads(log_entry))
            except json.JSONDecodeError:
                logger.warning(f"Malformed log entry in {trace_path}, skipping: {log_entry[:100]}")
                continue
        else:
            parsed_logs.append(log_entry)
    logs = parsed_logs

    # Check for RateLimitError
    raw_text = json.dumps(data)
    if "RateLimitError" in raw_text:
        logger.warning(f"Skipping trace with RateLimitError: {trace_path}")
        return []

    # Extract metadata
    metadata = data.get("metadata", {})
    definition = metadata.get("definition", {})
    scenario_id = definition.get("scenario_id", trace_path.stem.rsplit("_run_", 1)[0])
    run_number = definition.get("run_number", 1)

    # Extract meta_task_description from system prompt
    meta_task_description = _extract_meta_task_description(logs)

    # Identify agents
    agents = _identify_agents(logs)
    user_id = agents.get("user")
    observe_id = agents.get("observe")
    execute_id = agents.get("execute")

    if not user_id or not observe_id:
        logger.warning(f"Could not identify user or observe agent in {trace_path}")
        return []

    # Find execute agent cutoff
    execute_cutoff = _find_execute_cutoff(logs, execute_id)

    # Find proposal-decision pairs and build DecisionPoints
    return _extract_pairs(
        logs=logs,
        user_id=user_id,
        observe_id=observe_id,
        execute_cutoff=execute_cutoff,
        scenario_id=scenario_id,
        run_number=run_number,
        proactive_model_id=proactive_model_id,
        user_model_id=user_model_id,
        trace_path=trace_path,
        meta_task_description=meta_task_description,
    )


def _identify_agents(logs: list[dict[str, Any]]) -> dict[str, str]:
    """Identify agent IDs by system prompt content."""
    agents: dict[str, str] = {}
    for log in logs:
        if log.get("log_type") != "system_prompt":
            continue
        content = log.get("content", "")
        aid = log.get("agent_id", "")
        if not isinstance(content, str):
            continue
        if "simulating a real human user" in content:
            agents["user"] = aid
        elif "proactive assistant that monitors" in content:
            agents["observe"] = aid
        elif "proactive assistant executing" in content:
            agents["execute"] = aid
    return agents


def _find_execute_cutoff(logs: list[dict[str, Any]], execute_id: str | None) -> float:
    """Find the timestamp of the execute agent's first tool call."""
    if not execute_id:
        return float("inf")
    for log in logs:
        if log.get("log_type") == "tool_call" and log.get("agent_id") == execute_id:
            return log.get("timestamp", float("inf"))
    return float("inf")


def _extract_meta_task_description(logs: list[dict[str, Any]]) -> str:
    """Extract meta_task_description from user agent system prompt."""
    for log in logs[:50]:
        if log.get("log_type") != "system_prompt":
            continue
        content = log.get("content", "")
        if not isinstance(content, str):
            continue
        if "<meta_task_description>" in content:
            start = content.find("<meta_task_description>") + len("<meta_task_description>")
            end = content.find("</meta_task_description>")
            if start > 0 and end > start:
                return content[start:end].strip()
    return ""


def _extract_pairs(  # noqa: C901
    logs: list[dict[str, Any]],
    user_id: str,
    observe_id: str,
    execute_cutoff: float,
    scenario_id: str,
    run_number: int,
    proactive_model_id: str,
    user_model_id: str,
    trace_path: Path,
    meta_task_description: str,
) -> list[DecisionPoint]:
    """Extract proposal-decision pairs from truncated trace.

    Single forward scan: for each proposal, find the next accept/reject.
    Classify based on whether there are intermediate user tool calls.
    """
    decision_points: list[DecisionPoint] = []
    proposal_index = 0

    # Collect all proposals and decisions in the truncated trace
    proposals: list[dict[str, Any]] = []
    for i, log in enumerate(logs):
        if log.get("timestamp", 0) >= execute_cutoff:
            break
        if (
            log.get("log_type") == "tool_call"
            and log.get("agent_id") == observe_id
            and "send_message_to_user" in log.get("tool_name", "")
        ):
            proposals.append({"index": i, "log": log})

    for prop in proposals:
        prop_idx = prop["index"]
        prop_log = prop["log"]
        proposal_content = prop_log.get("tool_arguments", {}).get("content", "")

        # Find next accept/reject from user after this proposal
        decision_idx = None
        decision_tool = None
        for j in range(prop_idx + 1, len(logs)):
            if logs[j].get("timestamp", 0) >= execute_cutoff:
                break
            log_entry = logs[j]
            if log_entry.get("log_type") == "tool_call" and log_entry.get("agent_id") == user_id:
                tn = log_entry.get("tool_name", "")
                if "accept_proposal" in tn or "reject_proposal" in tn:
                    decision_idx = j
                    decision_tool = tn
                    break

        if decision_idx is None:
            logger.debug(f"No accept/reject found for proposal at index {prop_idx} in {trace_path}")
            continue

        # Check for intermediate user tool calls (gather_context)
        intermediate_tools: list[str] = []
        for k in range(prop_idx + 1, decision_idx):
            log_entry = logs[k]
            if log_entry.get("log_type") == "tool_call" and log_entry.get("agent_id") == user_id:
                intermediate_tools.append(log_entry.get("tool_name", ""))

        # Classify
        if intermediate_tools:
            user_agent_decision = "gather_context"
        elif decision_tool and "accept_proposal" in decision_tool:
            user_agent_decision = "accept"
        else:
            user_agent_decision = "reject"

        final_decision = decision_tool is not None and "accept_proposal" in decision_tool

        # Extract llm_input right after proposal
        llm_input = _find_llm_input_after(logs, prop_idx, user_id)
        if llm_input is None:
            logger.warning(f"No llm_input found after proposal at index {prop_idx} in {trace_path}")
            continue

        llm_input_idx, messages = llm_input

        # Annotate messages with timestamps and types
        annotated = _annotate_messages(messages, logs, llm_input_idx, user_id)

        # For gather_context, compute delta
        gather_context_delta = None
        if user_agent_decision == "gather_context":
            # Find llm_input at decision point
            decision_llm = _find_llm_input_before(logs, decision_idx, user_id)
            if decision_llm is not None:
                _, decision_messages = decision_llm
                gather_context_delta = decision_messages[len(messages) :]

        sample_id = DecisionPoint.generate_sample_id(scenario_id, run_number, proposal_index)

        decision_points.append(
            DecisionPoint(
                sample_id=sample_id,
                scenario_id=scenario_id,
                run_number=run_number,
                proactive_model_id=proactive_model_id,
                user_model_id=user_model_id,
                trace_file=trace_path,
                user_agent_decision=user_agent_decision,
                llm_input=annotated,
                agent_proposal=proposal_content,
                final_decision=final_decision,
                meta_task_description=meta_task_description,
                gather_context_delta=gather_context_delta,
            )
        )
        proposal_index += 1

    return decision_points


def _find_llm_input_after(
    logs: list[dict[str, Any]], start_idx: int, user_id: str
) -> tuple[int, list[dict[str, Any]]] | None:
    """Find the user agent's llm_input after a given index."""
    for i in range(start_idx + 1, min(start_idx + FORWARD_SEARCH_WINDOW, len(logs))):
        log = logs[i]
        if log.get("log_type") == "llm_input" and log.get("agent_id") == user_id:
            content = log.get("content")
            if isinstance(content, str):
                try:
                    messages: list[dict[str, Any]] = json.loads(content)
                except json.JSONDecodeError:
                    logger.warning(f"Malformed llm_input content at index {i}, skipping")
                    continue
            else:
                messages = content if isinstance(content, list) else []
            return i, messages
    return None


def _find_llm_input_before(
    logs: list[dict[str, Any]], end_idx: int, user_id: str
) -> tuple[int, list[dict[str, Any]]] | None:
    """Find the user agent's llm_input before a given index (searching backward)."""
    for i in range(end_idx - 1, max(end_idx - BACKWARD_SEARCH_WINDOW, 0), -1):
        log = logs[i]
        if log.get("log_type") == "llm_input" and log.get("agent_id") == user_id:
            content = log.get("content")
            if isinstance(content, str):
                try:
                    messages: list[dict[str, Any]] = json.loads(content)
                except json.JSONDecodeError:
                    logger.warning(f"Malformed llm_input content at index {i}, skipping")
                    continue
            else:
                messages = content if isinstance(content, list) else []
            return i, messages
    return None


def _annotate_messages(
    messages: list[dict[str, Any]],
    logs: list[dict[str, Any]],
    llm_input_idx: int,
    user_id: str,
) -> list[dict[str, Any]]:
    """Annotate llm_input messages with timestamps and msg_type.

    Timestamps only on event messages:
    - assistant (user_action): from llm_output world_log
    - tool-response (tool_observation): inherits from preceding assistant
    - [TASK]: prefix (proposal): from task world_log
    - Others: no timestamp
    """
    # Collect timestamps from world_logs
    llm_output_timestamps, task_timestamps = _collect_timestamps(logs, llm_input_idx, user_id)

    llm_output_idx = 0
    task_idx = 0
    last_assistant_ts: float | None = None

    annotated: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role", "")
        content = str(msg.get("content", ""))
        ts: float | None = None

        if role == "assistant":
            if llm_output_idx < len(llm_output_timestamps):
                ts = llm_output_timestamps[llm_output_idx]
                llm_output_idx += 1
            last_assistant_ts = ts
            msg_type = "user_action"
        elif role == "tool-response":
            ts = last_assistant_ts
            msg_type = "tool_observation"
        elif role == "user" and content.startswith("[TASK]:"):
            if task_idx < len(task_timestamps):
                ts = task_timestamps[task_idx]
                task_idx += 1
            msg_type = "proposal"
        else:
            msg_type = _classify_user_message(role, content)

        annotated.append({**msg, "timestamp": ts, "msg_type": msg_type})

    return annotated


def _collect_timestamps(
    logs: list[dict[str, Any]], llm_input_idx: int, user_id: str
) -> tuple[list[float], list[float]]:
    """Collect llm_output and task timestamps from world logs."""
    llm_output_timestamps: list[float] = []
    task_timestamps: list[float] = []

    for i in range(0, llm_input_idx):
        log = logs[i]
        if log.get("agent_id") != user_id:
            continue
        lt = log.get("log_type", "")
        ts = log.get("timestamp", 0)
        if lt == "llm_output":
            llm_output_timestamps.append(ts)
        elif lt == "task":
            content = log.get("content", "")
            if content and str(content).strip():
                task_timestamps.append(ts)

    return llm_output_timestamps, task_timestamps


def _classify_user_message(role: str, content: str) -> str:
    """Classify message type based on role and content."""
    if role == "user" and content.startswith("Environment notifications"):
        return "environment_notification"
    if role == "user" and content.startswith("Available Actions"):
        return "available_tools"
    if role == "user" and content.startswith("Current app state"):
        return "current_app_state"
    if role == "system":
        return "system_prompt"
    return "unknown"
