"""Shared fixtures for trajectory tests."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pathlib import Path


def _make_log(log_type: str, agent_id: str, content: Any = "", timestamp: float = 0.0, **kwargs: Any) -> str:  # noqa: ANN401
    """Create a JSON-serialized world_log entry."""
    entry = {
        "log_type": log_type,
        "agent_id": agent_id,
        "content": content,
        "timestamp": timestamp,
        **kwargs,
    }
    return json.dumps(entry)


@pytest.fixture()
def user_agent_id() -> str:
    """Return test user agent ID."""
    return "user_001"


@pytest.fixture()
def observe_agent_id() -> str:
    """Return test observe agent ID."""
    return "observe_001"


@pytest.fixture()
def execute_agent_id() -> str:
    """Return test execute agent ID."""
    return "execute_001"


@pytest.fixture()
def trace_accept(user_agent_id: str, observe_agent_id: str, execute_agent_id: str, tmp_path: Path) -> Path:
    """Trace with a direct accept decision (no intermediate tool calls)."""
    logs = [
        # User agent system prompt
        _make_log("system_prompt", user_agent_id, "You are simulating a real human user", timestamp=100.0),
        # Observe agent system prompt
        _make_log("system_prompt", observe_agent_id, "You are a proactive assistant that monitors", timestamp=100.0),
        # Execute agent system prompt
        _make_log("system_prompt", execute_agent_id, "You are a proactive assistant executing", timestamp=100.0),
        # User agent first turn context
        _make_log("task", user_agent_id, "", timestamp=100.0),
        _make_log("available_tools", user_agent_id, "- accept_proposal\n- reject_proposal", timestamp=100.0),
        _make_log("current_app_state", user_agent_id, "Current active app: System", timestamp=100.0),
        _make_log("llm_input", user_agent_id, json.dumps([
            {"role": "system", "content": "You are simulating a real human user"},
            {"role": "user", "content": "Available Actions from current state:\n***\n- accept\n***"},
            {"role": "user", "content": "Current app state:\n***\nSystem\n***"},
        ]), timestamp=100.0),
        _make_log("llm_output", user_agent_id, "Thought: I will open notes", timestamp=101.0),
        _make_log("tool_call", user_agent_id, "", timestamp=101.0, tool_name="System__open_app", tool_arguments={"app_name": "Notes"}),
        _make_log("observation", user_agent_id, "Opened Notes App.", timestamp=101.0),
        # Observe agent proposes
        _make_log("tool_call", observe_agent_id, "", timestamp=102.0, tool_name="PASAgentUserInterface__send_message_to_user", tool_arguments={"content": "I propose to update your note"}),
        _make_log("observation", observe_agent_id, "None", timestamp=102.0),
        # User agent receives proposal and gets new llm_input
        _make_log("task", user_agent_id, "Received at: 2025-01-01\nSender: Agent\nMessage: I propose to update your note", timestamp=103.0),
        _make_log("environment_notifications", user_agent_id, "[2025-01-01 09:00:10] New calendar event", timestamp=103.0),
        _make_log("available_tools", user_agent_id, "- accept_proposal\n- reject_proposal\n- Notes__open", timestamp=103.0),
        _make_log("current_app_state", user_agent_id, "Current active app: Notes", timestamp=103.0),
        _make_log("llm_input", user_agent_id, json.dumps([
            {"role": "system", "content": "You are simulating a real human user"},
            {"role": "assistant", "content": "Thought: I will open notes"},
            {"role": "tool-response", "content": "[OUTPUT OF STEP 1] Observation:\n***\nOpened Notes App.\n***"},
            {"role": "user", "content": "[TASK]: \nReceived at: 2025-01-01\nSender: Agent\nMessage: I propose to update your note"},
            {"role": "user", "content": "Environment notifications updates:\n***\n[2025-01-01 09:00:10] New calendar event\n***"},
            {"role": "user", "content": "Available Actions from current state:\n***\n- accept_proposal\n***"},
            {"role": "user", "content": "Current app state:\n***\nNotes\n***"},
        ]), timestamp=103.0),
        _make_log("llm_output", user_agent_id, "Thought: The proposal looks good, I accept", timestamp=104.0),
        # User directly accepts (no intermediate tool calls)
        _make_log("tool_call", user_agent_id, "", timestamp=104.0, tool_name="PASAgentUserInterface__accept_proposal", tool_arguments={"content": "Yes, update the note"}),
        _make_log("observation", user_agent_id, "accepted-uuid", timestamp=104.0),
        # Execute agent starts
        _make_log("tool_call", execute_agent_id, "", timestamp=105.0, tool_name="Notes__update_note", tool_arguments={"note_id": "abc"}),
    ]
    trace_data = {
        "world_logs": logs,
        "metadata": {"definition": {"scenario_id": "test_accept", "run_number": 1}},
    }
    trace_file = tmp_path / "test_accept_run_1.json"
    trace_file.write_text(json.dumps(trace_data))
    return trace_file


@pytest.fixture()
def trace_reject(user_agent_id: str, observe_agent_id: str, tmp_path: Path) -> Path:
    """Trace with a direct reject decision."""
    logs = [
        _make_log("system_prompt", user_agent_id, "You are simulating a real human user", timestamp=100.0),
        _make_log("system_prompt", observe_agent_id, "You are a proactive assistant that monitors", timestamp=100.0),
        # Observe agent proposes
        _make_log("task", user_agent_id, "", timestamp=100.0),
        _make_log("available_tools", user_agent_id, "- accept_proposal\n- reject_proposal", timestamp=100.0),
        _make_log("current_app_state", user_agent_id, "Current active app: System", timestamp=100.0),
        _make_log("llm_input", user_agent_id, json.dumps([
            {"role": "system", "content": "You are simulating a real human user"},
            {"role": "user", "content": "Available Actions from current state:\n***\n- accept\n***"},
            {"role": "user", "content": "Current app state:\n***\nSystem\n***"},
        ]), timestamp=100.0),
        _make_log("llm_output", user_agent_id, "Thought: waiting", timestamp=101.0),
        _make_log("tool_call", user_agent_id, "", timestamp=101.0, tool_name="System__open_app", tool_arguments={"app_name": "Calendar"}),
        _make_log("observation", user_agent_id, "Opened Calendar.", timestamp=101.0),
        _make_log("tool_call", observe_agent_id, "", timestamp=102.0, tool_name="PASAgentUserInterface__send_message_to_user", tool_arguments={"content": "I propose to book a cab"}),
        _make_log("observation", observe_agent_id, "None", timestamp=102.0),
        # User receives proposal
        _make_log("task", user_agent_id, "Received at: 2025-01-01\nSender: Agent\nMessage: I propose to book a cab", timestamp=103.0),
        _make_log("available_tools", user_agent_id, "- accept_proposal\n- reject_proposal", timestamp=103.0),
        _make_log("current_app_state", user_agent_id, "Current active app: Calendar", timestamp=103.0),
        _make_log("llm_input", user_agent_id, json.dumps([
            {"role": "system", "content": "You are simulating a real human user"},
            {"role": "assistant", "content": "Thought: waiting"},
            {"role": "tool-response", "content": "[OUTPUT OF STEP 1] Observation:\n***\nOpened Calendar.\n***"},
            {"role": "user", "content": "[TASK]: \nReceived at: 2025-01-01\nSender: Agent\nMessage: I propose to book a cab"},
            {"role": "user", "content": "Available Actions from current state:\n***\n- accept_proposal\n***"},
            {"role": "user", "content": "Current app state:\n***\nCalendar\n***"},
        ]), timestamp=103.0),
        _make_log("llm_output", user_agent_id, "Thought: This is wrong, reject", timestamp=104.0),
        # User rejects directly
        _make_log("tool_call", user_agent_id, "", timestamp=104.0, tool_name="PASAgentUserInterface__reject_proposal", tool_arguments={"content": "No thanks"}),
        _make_log("observation", user_agent_id, "rejected-uuid", timestamp=104.0),
    ]
    trace_data = {
        "world_logs": logs,
        "metadata": {"definition": {"scenario_id": "test_reject", "run_number": 1}},
    }
    trace_file = tmp_path / "test_reject_run_1.json"
    trace_file.write_text(json.dumps(trace_data))
    return trace_file


@pytest.fixture()
def trace_gather_context(user_agent_id: str, observe_agent_id: str, execute_agent_id: str, tmp_path: Path) -> Path:
    """Trace where user gathers context before accepting."""
    logs = [
        _make_log("system_prompt", user_agent_id, "You are simulating a real human user", timestamp=100.0),
        _make_log("system_prompt", observe_agent_id, "You are a proactive assistant that monitors", timestamp=100.0),
        _make_log("system_prompt", execute_agent_id, "You are a proactive assistant executing", timestamp=100.0),
        # Initial user turn
        _make_log("task", user_agent_id, "", timestamp=100.0),
        _make_log("available_tools", user_agent_id, "- accept_proposal\n- reject_proposal", timestamp=100.0),
        _make_log("current_app_state", user_agent_id, "Current active app: System", timestamp=100.0),
        _make_log("llm_input", user_agent_id, json.dumps([
            {"role": "system", "content": "You are simulating a real human user"},
            {"role": "user", "content": "Available Actions from current state:\n***\n- accept\n***"},
            {"role": "user", "content": "Current app state:\n***\nSystem\n***"},
        ]), timestamp=100.0),
        _make_log("llm_output", user_agent_id, "Thought: opening messages", timestamp=101.0),
        _make_log("tool_call", user_agent_id, "", timestamp=101.0, tool_name="System__open_app", tool_arguments={"app_name": "Messages"}),
        _make_log("observation", user_agent_id, "Opened Messages.", timestamp=101.0),
        # Observe proposes
        _make_log("tool_call", observe_agent_id, "", timestamp=102.0, tool_name="PASAgentUserInterface__send_message_to_user", tool_arguments={"content": "I found relevant info in your messages"}),
        _make_log("observation", observe_agent_id, "None", timestamp=102.0),
        # User receives proposal - this is the llm_input we store
        _make_log("task", user_agent_id, "Received at: 2025-01-01\nSender: Agent\nMessage: I found relevant info", timestamp=103.0),
        _make_log("available_tools", user_agent_id, "- accept_proposal\n- Messages__list_recent", timestamp=103.0),
        _make_log("current_app_state", user_agent_id, "Current active app: Messages", timestamp=103.0),
        _make_log("llm_input", user_agent_id, json.dumps([
            {"role": "system", "content": "You are simulating a real human user"},
            {"role": "assistant", "content": "Thought: opening messages"},
            {"role": "tool-response", "content": "[OUTPUT OF STEP 1] Observation:\n***\nOpened Messages.\n***"},
            {"role": "user", "content": "[TASK]: \nReceived at: 2025-01-01\nSender: Agent\nMessage: I found relevant info"},
            {"role": "user", "content": "Available Actions from current state:\n***\n- accept_proposal\n- Messages__list_recent\n***"},
            {"role": "user", "content": "Current app state:\n***\nMessages\n***"},
        ]), timestamp=103.0),
        _make_log("llm_output", user_agent_id, "Thought: let me check messages first", timestamp=104.0),
        # User gathers context (intermediate tool call)
        _make_log("tool_call", user_agent_id, "", timestamp=104.0, tool_name="Messages__list_recent_conversations", tool_arguments={}),
        _make_log("observation", user_agent_id, "Conversation with Alice", timestamp=104.5),
        # Second llm_input (after gathering)
        _make_log("available_tools", user_agent_id, "- accept_proposal\n- Messages__list_recent", timestamp=105.0),
        _make_log("current_app_state", user_agent_id, "Current active app: Messages", timestamp=105.0),
        _make_log("llm_input", user_agent_id, json.dumps([
            {"role": "system", "content": "You are simulating a real human user"},
            {"role": "assistant", "content": "Thought: opening messages"},
            {"role": "tool-response", "content": "[OUTPUT OF STEP 1] Observation:\n***\nOpened Messages.\n***"},
            {"role": "user", "content": "[TASK]: \nReceived at: 2025-01-01\nSender: Agent\nMessage: I found relevant info"},
            {"role": "user", "content": "Available Actions from current state:\n***\n- accept_proposal\n***"},
            {"role": "user", "content": "Current app state:\n***\nMessages\n***"},
            {"role": "assistant", "content": "Thought: let me check messages first"},
            {"role": "tool-response", "content": "[OUTPUT OF STEP 2] Observation:\n***\nConversation with Alice\n***"},
            {"role": "user", "content": "Available Actions from current state:\n***\n- accept_proposal\n***"},
            {"role": "user", "content": "Current app state:\n***\nMessages\n***"},
        ]), timestamp=105.0),
        _make_log("llm_output", user_agent_id, "Thought: OK now I accept", timestamp=106.0),
        # User accepts after gathering
        _make_log("tool_call", user_agent_id, "", timestamp=106.0, tool_name="PASAgentUserInterface__accept_proposal", tool_arguments={"content": "Yes"}),
        _make_log("observation", user_agent_id, "accepted-uuid", timestamp=106.0),
        # Execute agent starts
        _make_log("tool_call", execute_agent_id, "", timestamp=107.0, tool_name="Messages__send_message", tool_arguments={}),
    ]
    trace_data = {
        "world_logs": logs,
        "metadata": {"definition": {"scenario_id": "test_gather", "run_number": 1}},
    }
    trace_file = tmp_path / "test_gather_run_1.json"
    trace_file.write_text(json.dumps(trace_data))
    return trace_file


@pytest.fixture()
def trace_no_proposal(user_agent_id: str, observe_agent_id: str, tmp_path: Path) -> Path:
    """Trace where observe agent never proposes."""
    logs = [
        _make_log("system_prompt", user_agent_id, "You are simulating a real human user", timestamp=100.0),
        _make_log("system_prompt", observe_agent_id, "You are a proactive assistant that monitors", timestamp=100.0),
        _make_log("tool_call", observe_agent_id, "", timestamp=101.0, tool_name="PASAgentUserInterface__wait", tool_arguments={}),
        _make_log("observation", observe_agent_id, "Continuing to observe.", timestamp=101.0),
    ]
    trace_data = {
        "world_logs": logs,
        "metadata": {"definition": {"scenario_id": "test_no_proposal", "run_number": 1}},
    }
    trace_file = tmp_path / "test_no_proposal_run_1.json"
    trace_file.write_text(json.dumps(trace_data))
    return trace_file
