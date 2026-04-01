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
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from pas.trajectory.models import DecisionPoint, TernaryDecision

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
    """Identify agent IDs by system prompt content.

    Args:
        logs: List of parsed log entries from the trace file.

    Returns:
        Dictionary mapping agent roles (user/observe/execute) to agent IDs.
    """
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
    """Find the timestamp of the execute agent's first tool call.

    Args:
        logs: List of parsed log entries from the trace file.
        execute_id: Agent ID of the execute agent, or None if not found.

    Returns:
        Timestamp of the first execute agent tool call, or float('inf') if none found.
    """
    if not execute_id:
        return float("inf")
    for log in logs:
        if log.get("log_type") == "tool_call" and log.get("agent_id") == execute_id:
            return log.get("timestamp", float("inf"))
    return float("inf")


def _extract_meta_task_description(logs: list[dict[str, Any]]) -> str:
    """Extract meta_task_description from user agent system prompt.

    Args:
        logs: List of parsed log entries from the trace file.

    Returns:
        The meta_task_description text, or empty string if not found.
    """
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


def _collect_proposals(
    logs: list[dict[str, Any]],
    observe_id: str,
    execute_cutoff: float,
) -> list[dict[str, Any]]:
    """Collect observe agent proposals from logs before the execute cutoff.

    Args:
        logs: List of parsed log entries from the trace file.
        observe_id: Agent ID of the observe agent.
        execute_cutoff: Timestamp to truncate trace at.

    Returns:
        List of dicts with 'index' and 'log' keys for each proposal.
    """
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
    return proposals


def _find_matching_decision(
    logs: list[dict[str, Any]],
    prop_idx: int,
    user_id: str,
    execute_cutoff: float,
) -> tuple[int, str] | None:
    """Find the next accept/reject decision from the user after a proposal.

    Args:
        logs: List of parsed log entries from the trace file.
        prop_idx: Index of the proposal in the logs.
        user_id: Agent ID of the user agent.
        execute_cutoff: Timestamp to truncate trace at.

    Returns:
        Tuple of (decision_index, tool_name), or None if no decision found.
    """
    for j in range(prop_idx + 1, len(logs)):
        if logs[j].get("timestamp", 0) >= execute_cutoff:
            break
        log_entry = logs[j]
        if log_entry.get("log_type") == "tool_call" and log_entry.get("agent_id") == user_id:
            tn = log_entry.get("tool_name", "")
            if "accept_proposal" in tn or "reject_proposal" in tn:
                return j, tn
    return None


def _classify_decision(
    logs: list[dict[str, Any]],
    prop_idx: int,
    decision_idx: int,
    decision_tool: str,
    user_id: str,
) -> tuple[TernaryDecision, bool]:
    """Classify a decision as accept, reject, or gather_context.

    Checks for intermediate user tool calls between proposal and decision.
    If any exist, the decision is gather_context. Otherwise, it's the
    direct accept/reject from the decision tool name.

    Args:
        logs: List of parsed log entries from the trace file.
        prop_idx: Index of the proposal in the logs.
        decision_idx: Index of the accept/reject decision in the logs.
        decision_tool: Tool name of the decision (accept_proposal or reject_proposal).
        user_id: Agent ID of the user agent.

    Returns:
        Tuple of (decision_type, final_decision). final_decision is True for accept, False for reject.
    """
    has_intermediate = False
    for k in range(prop_idx + 1, decision_idx):
        log_entry = logs[k]
        if log_entry.get("log_type") == "tool_call" and log_entry.get("agent_id") == user_id:
            has_intermediate = True
            break

    final_decision = "accept_proposal" in decision_tool

    if has_intermediate:
        return "gather_context", final_decision
    elif final_decision:
        return "accept", final_decision
    else:
        return "reject", final_decision


def _compute_gather_delta(
    logs: list[dict[str, Any]],
    decision_idx: int,
    proposal_messages: list[dict[str, Any]],
    user_id: str,
) -> list[dict[str, Any]] | None:
    """Compute the gather_context_delta for a gather_context decision.

    The delta is the messages between the proposal llm_input and the decision
    llm_input — i.e., the additional context the user gathered before deciding.

    Args:
        logs: List of parsed log entries from the trace file.
        decision_idx: Index of the accept/reject decision in the logs.
        proposal_messages: The llm_input messages at the proposal point.
        user_id: Agent ID of the user agent.

    Returns:
        List of additional messages, or None if the decision llm_input could not be found.
    """
    decision_llm = _find_llm_input_before(logs, decision_idx, user_id)
    if decision_llm is None:
        return None
    _, decision_messages = decision_llm
    return decision_messages[len(proposal_messages) :]


def _extract_pairs(
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

    Args:
        logs: List of parsed log entries from the trace file.
        user_id: Agent ID of the user agent.
        observe_id: Agent ID of the observe agent.
        execute_cutoff: Timestamp to truncate trace at (first execute tool call).
        scenario_id: Scenario identifier.
        run_number: Run number for this scenario execution.
        proactive_model_id: Proactive model identifier.
        user_model_id: User model identifier.
        trace_path: Path to the trace file.
        meta_task_description: Meta task description from scenario.

    Returns:
        List of DecisionPoint objects, one per valid proposal-decision pair.
    """
    decision_points: list[DecisionPoint] = []
    proposals = _collect_proposals(logs, observe_id, execute_cutoff)

    for proposal_index, prop in enumerate(proposals):
        prop_idx = prop["index"]
        proposal_content = prop["log"].get("tool_arguments", {}).get("content", "")

        # Find matching accept/reject decision
        match = _find_matching_decision(logs, prop_idx, user_id, execute_cutoff)
        if match is None:
            logger.debug(f"No accept/reject found for proposal at index {prop_idx} in {trace_path}")
            continue
        decision_idx, decision_tool = match

        # Classify the decision
        user_agent_decision, final_decision = _classify_decision(logs, prop_idx, decision_idx, decision_tool, user_id)

        # Extract and annotate llm_input
        llm_input = _find_llm_input_after(logs, prop_idx, user_id)
        if llm_input is None:
            logger.warning(f"No llm_input found after proposal at index {prop_idx} in {trace_path}")
            continue
        llm_input_idx, messages = llm_input
        annotated = _annotate_messages(messages, logs, llm_input_idx, user_id)

        # Compute gather_context_delta if needed
        gather_context_delta = None
        if user_agent_decision == "gather_context":
            gather_context_delta = _compute_gather_delta(logs, decision_idx, messages, user_id)

        decision_points.append(
            DecisionPoint(
                sample_id=DecisionPoint.generate_sample_id(scenario_id, run_number, proposal_index),
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

    return decision_points


def _find_llm_input_after(
    logs: list[dict[str, Any]], start_idx: int, user_id: str
) -> tuple[int, list[dict[str, Any]]] | None:
    """Find the user agent's llm_input after a given index.

    Args:
        logs: List of parsed log entries from the trace file.
        start_idx: Index to start searching from.
        user_id: Agent ID of the user agent.

    Returns:
        Tuple of (log index, message array) if found, None otherwise.
    """
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
    """Find the user agent's llm_input before a given index (searching backward).

    Args:
        logs: List of parsed log entries from the trace file.
        end_idx: Index to start searching backward from.
        user_id: Agent ID of the user agent.

    Returns:
        Tuple of (log index, message array) if found, None otherwise.
    """
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

    Args:
        messages: List of message dicts from llm_input.
        logs: List of parsed log entries from the trace file.
        llm_input_idx: Index of the llm_input log entry.
        user_id: Agent ID of the user agent.

    Returns:
        List of message dicts with added timestamp and msg_type fields.
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
            if msg_type == "environment_notification":
                ts = _parse_notification_timestamp(content)

        annotated.append({**msg, "timestamp": ts, "msg_type": msg_type})

    return annotated


def _collect_timestamps(
    logs: list[dict[str, Any]], llm_input_idx: int, user_id: str
) -> tuple[list[float], list[float]]:
    """Collect llm_output and task timestamps from world logs.

    Args:
        logs: List of parsed log entries from the trace file.
        llm_input_idx: Index of the llm_input log entry.
        user_id: Agent ID of the user agent.

    Returns:
        Tuple of (llm_output_timestamps, task_timestamps) lists.
    """
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
    """Classify message type based on role and content.

    Args:
        role: Message role (user/assistant/system/tool-response).
        content: Message content text.

    Returns:
        Message type string (environment_notification/available_tools/current_app_state/system_prompt/unknown).
    """
    if role == "user" and content.startswith("Environment notifications"):
        return "environment_notification"
    if role == "user" and content.startswith("Available Actions"):
        return "available_tools"
    if role == "user" and content.startswith("Current app state"):
        return "current_app_state"
    if role == "system":
        return "system_prompt"
    return "unknown"


def _parse_notification_timestamp(content: str) -> float | None:
    """Parse the last non-None notification timestamp from content text.

    Searches for ``[YYYY-MM-DD HH:MM:SS]`` prefixed lines, skipping lines
    where the content after the timestamp is just ``None``.

    Args:
        content: Raw notification message content.

    Returns:
        UTC epoch float of the last non-None notification, or None if no valid timestamps found.
    """
    last_ts: float | None = None
    for match in re.finditer(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\][ \t]*([^\n]*)", content):
        timestamp_str, line_content = match.group(1), match.group(2).strip()
        if not line_content or line_content == "None":
            continue
        dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        last_ts = dt.timestamp()
    return last_ts
