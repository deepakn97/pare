"""Trace parser for extracting decision points from PAS traces.

.. deprecated::
    This module is superseded by ``pas.trajectory.trace_parser`` which supports
    ternary decisions (accept/reject/gather_context). Use ``extract_decision_points``
    from ``pas.trajectory`` instead. This module will be removed after the UI update.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from pas.annotation.models import ActionWithObservation, DecisionPoint, Turn
from pas.annotation.observation_formatter import ObservationFormatter, format_notification

logger = logging.getLogger(__name__)


def parse_trace(trace_path: Path, proactive_model_id: str, user_model_id: str = "unknown") -> list[DecisionPoint]:
    """Parse a trace file and extract all decision points.

    Args:
        trace_path: Path to the trace JSON file.
        proactive_model_id: The proactive model identifier (extracted from directory name).
        user_model_id: The user model identifier.

    Returns:
        List of DecisionPoint objects, one per accept/reject event.
    """
    with open(trace_path) as f:
        data = json.load(f)

    # Extract metadata
    metadata = data.get("metadata", {})
    definition = metadata.get("definition", {})
    scenario_id = definition.get("scenario_id", trace_path.stem.rsplit("_run_", 1)[0])
    run_number = definition.get("run_number", 1)

    # Get meta task description (may be empty)
    meta_task_description = ""
    # Try to find it in the system prompt
    for log in data.get("world_logs", [])[:50]:
        if isinstance(log, str):
            log_dict = json.loads(log)
            content = log_dict.get("content", "")
            if isinstance(content, str) and "<meta_task_description>" in content:
                start = content.find("<meta_task_description>") + len("<meta_task_description>")
                end = content.find("</meta_task_description>")
                if start > 0 and end > start:
                    meta_task_description = content[start:end].strip()
                    break

    # Find the user agent ID
    user_agent_id = _find_user_agent_id(data)
    if not user_agent_id:
        logger.warning(f"Could not find user agent ID in {trace_path}")
        return []

    # Find the proactive agent ID
    proactive_agent_id = _find_proactive_agent_id(data)

    # Extract id_to_name mapping from apps (for resolving sender IDs in notifications)
    id_to_name_map = _extract_id_to_name_map(data)

    # Parse world_logs to extract actions, observations, and notifications
    parsed_logs = _parse_world_logs(data, user_agent_id, proactive_agent_id, id_to_name_map)

    # Find all decision points (accept/reject events)
    decision_points = []
    for decision_event in parsed_logs["decisions"]:
        # Get all events before this decision
        decision_ts = decision_event["timestamp"]

        # Group actions into turns based on notifications
        turns = _group_into_turns(parsed_logs, decision_ts, user_agent_id)

        # Find the agent proposal that preceded this decision
        agent_proposal = _find_preceding_proposal(parsed_logs, decision_ts, proactive_agent_id)

        if not agent_proposal:
            logger.debug(f"No proposal found for decision at {decision_ts} in {trace_path}")
            continue

        # Generate sample ID
        sample_id = DecisionPoint.generate_sample_id(scenario_id, run_number, agent_proposal, decision_ts)

        decision_point = DecisionPoint(
            sample_id=sample_id,
            scenario_id=scenario_id,
            run_number=run_number,
            proactive_model_id=proactive_model_id,
            user_model_id=user_model_id,
            trace_file=trace_path,
            meta_task_description=meta_task_description,
            turns=turns,
            agent_proposal=agent_proposal,
            user_agent_decision=decision_event["is_accept"],
            decision_timestamp=decision_ts,
        )
        decision_points.append(decision_point)

    return decision_points


def _find_user_agent_id(data: dict[str, Any]) -> str | None:
    """Find the user agent ID from world_logs."""
    for log in data.get("world_logs", [])[:50]:
        if isinstance(log, str):
            log_dict = json.loads(log)
            content = log_dict.get("content", "")
            if isinstance(content, str) and "simulating a real human user" in content:
                return log_dict.get("agent_id")
    return None


def _find_proactive_agent_id(data: dict[str, Any]) -> str | None:
    """Find the proactive (observe) agent ID from world_logs."""
    for log in data.get("world_logs", [])[:100]:
        if isinstance(log, str):
            log_dict = json.loads(log)
            content = log_dict.get("content", "")
            if isinstance(content, str) and "proactive assistant that monitors" in content:
                return log_dict.get("agent_id")
    return None


def _extract_id_to_name_map(data: dict[str, Any]) -> dict[str, str]:
    """Extract id_to_name mapping from apps (typically from messaging app).

    Returns:
        Dictionary mapping user IDs to human-readable names.
    """
    id_to_name: dict[str, str] = {}

    for app in data.get("apps", []):
        if isinstance(app, dict):
            app_state = app.get("app_state", {})
            if isinstance(app_state, dict) and "id_to_name" in app_state:
                mapping = app_state["id_to_name"]
                if isinstance(mapping, dict):
                    id_to_name.update(mapping)

    return id_to_name


def _parse_world_logs(  # noqa: C901
    data: dict[str, Any],
    user_agent_id: str,
    proactive_agent_id: str | None,
    id_to_name_map: dict[str, str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Parse world_logs into structured events.

    Returns:
        Dictionary with keys: 'tool_calls', 'observations', 'notifications', 'decisions', 'proposals'
    """
    result: dict[str, list[dict[str, Any]]] = {
        "tool_calls": [],
        "observations": [],
        "notifications": [],
        "decisions": [],
        "proposals": [],
    }

    current_tool_call = None

    for log in data.get("world_logs", []):
        if not isinstance(log, str):
            continue

        log_dict = json.loads(log)
        agent_id = log_dict.get("agent_id")
        log_type = log_dict.get("log_type")
        timestamp = log_dict.get("timestamp", 0)

        # User agent tool calls and observations
        if agent_id == user_agent_id:
            if log_type == "tool_call":
                tool_name = log_dict.get("tool_name", "")
                tool_args = log_dict.get("tool_arguments", {})

                # Format tool call as Python function call
                args_str = ", ".join(f"{k}={v!r}" for k, v in tool_args.items())
                action_str = f"{tool_name}({args_str})"

                current_tool_call = {
                    "timestamp": timestamp,
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "action_str": action_str,
                    "is_decision": "accept_proposal" in tool_name or "reject_proposal" in tool_name,
                    "is_accept": "accept_proposal" in tool_name,
                }
                result["tool_calls"].append(current_tool_call)

                if current_tool_call["is_decision"]:
                    result["decisions"].append(current_tool_call)

            elif log_type == "observation" and current_tool_call:
                raw_obs = log_dict.get("content", "")
                tool_args = current_tool_call.get("tool_args", {})
                formatted_obs = ObservationFormatter.format(current_tool_call["tool_name"], raw_obs, tool_args)
                result["observations"].append({
                    "timestamp": timestamp,
                    "tool_name": current_tool_call["tool_name"],
                    "raw": raw_obs,
                    "formatted": formatted_obs,
                })
                current_tool_call = None

            elif log_type == "environment_notifications":
                content = log_dict.get("content", "")
                if content and content.strip():
                    # Filter out lines that are just timestamps with "None"
                    filtered_lines = []
                    for line in content.strip().split("\n"):
                        line = line.strip()
                        # Skip lines that end with "] None" or are just "None"
                        if line.endswith("] None") or line == "None":
                            continue
                        if line:
                            filtered_lines.append(line)

                    # Only add if there's actual content after filtering
                    if filtered_lines:
                        raw_content = "\n".join(filtered_lines)
                        # Format the notification to be human-readable (pass id_to_name for sender resolution)
                        formatted_content = format_notification(raw_content, id_to_name_map)
                        result["notifications"].append({
                            "timestamp": timestamp,
                            "content": formatted_content,
                        })

        # Proactive agent proposals (send_message_to_user)
        if proactive_agent_id and agent_id == proactive_agent_id and log_type == "tool_call":
            tool_name = log_dict.get("tool_name", "")
            if "send_message_to_user" in tool_name:
                tool_args = log_dict.get("tool_arguments", {})
                content = tool_args.get("content", "")
                result["proposals"].append({
                    "timestamp": timestamp,
                    "content": content,
                })

    return result


def _group_into_turns(parsed_logs: dict[str, list[dict[str, Any]]], before_ts: float, user_agent_id: str) -> list[Turn]:
    """Group user actions into turns based on notification boundaries.

    A turn starts when notifications change or at the first action.
    Creates a turn with just notifications if user receives notifications but takes no actions
    (e.g., user accepts/rejects based solely on a notification).
    """
    # Filter events before the decision
    tool_calls = [tc for tc in parsed_logs["tool_calls"] if tc["timestamp"] < before_ts and not tc["is_decision"]]
    observations = parsed_logs["observations"]
    notifications = [n for n in parsed_logs["notifications"] if n["timestamp"] < before_ts]

    # If no tool calls and no notifications, return empty
    if not tool_calls and not notifications:
        return []

    # Create a single turn with all actions (simplified approach)
    # More sophisticated turn detection could be added later
    turns = []
    current_turn = Turn(turn_number=1, notifications=[], actions=[])

    # Get notifications at the start
    if notifications:
        # Use the most recent notification content
        current_turn.notifications = [notifications[-1]["content"]]

    # Add all actions with their observations
    for tc in tool_calls:
        # Find matching observation
        obs = next(
            (o for o in observations if o["tool_name"] == tc["tool_name"] and o["timestamp"] >= tc["timestamp"]), None
        )

        action = ActionWithObservation(
            action=tc["action_str"],
            observation=obs["formatted"] if obs else "No observation recorded.",
            raw_observation=obs["raw"] if obs else None,
            timestamp=tc["timestamp"],
        )
        current_turn.actions.append(action)

    # Include turn if it has notifications OR actions (or both)
    if current_turn.notifications or current_turn.actions:
        turns.append(current_turn)

    return turns


def _find_preceding_proposal(
    parsed_logs: dict[str, list[dict[str, Any]]], decision_ts: float, proactive_agent_id: str | None
) -> str | None:
    """Find the proactive agent's proposal that preceded the decision."""
    proposals = parsed_logs["proposals"]

    # Find the most recent proposal before the decision
    preceding_proposals = [p for p in proposals if p["timestamp"] < decision_ts]

    if not preceding_proposals:
        return None

    # Return the most recent one
    most_recent = max(preceding_proposals, key=lambda p: p["timestamp"])
    return most_recent["content"]


def extract_model_id_from_dir(dir_name: str) -> str:
    """Extract the proactive model ID from a trace subdirectory name.

    Example: obs_gpt-5_exec_gpt-5_enmi_0_es_42_tfp_0.0 -> gpt-5

    Args:
        dir_name: The subdirectory name.

    Returns:
        The extracted proactive model ID.
    """
    # Pattern: obs_{model}_exec_{model}_...
    match = re.match(r"obs_([^_]+(?:_[^_]+)?(?:-[^_]+)?)_exec_", dir_name)
    if match:
        return match.group(1)
    return dir_name


def trace_uses_messages_app(trace_path: Path) -> bool:
    """Check if a trace uses the Messages app.

    Args:
        trace_path: Path to the trace JSON file.

    Returns:
        True if the trace contains Messages app usage.
    """
    try:
        with open(trace_path) as f:
            data = json.load(f)

        # Check world_logs for Messages app tool calls
        for log in data.get("world_logs", []):
            if isinstance(log, str):
                log_dict = json.loads(log)
                tool_name = log_dict.get("tool_name", "")
                if tool_name.startswith("Messages__"):
                    return True

        return False  # noqa: TRY300
    except Exception:
        return False


def is_no_noise_trace(dir_name: str) -> bool:
    """Check if a trace directory is a no-noise trace.

    No-noise traces have enmi_0 (environment noise = 0).

    Args:
        dir_name: The directory name.

    Returns:
        True if this is a no-noise trace.
    """
    return "enmi_0" in dir_name


def is_excluded_model(dir_name: str) -> bool:
    """Check if a trace directory is from an excluded model.

    Currently excludes ministral models due to poor quality.

    Args:
        dir_name: The directory name.

    Returns:
        True if this trace should be excluded.
    """
    return "ministral" in dir_name.lower()
