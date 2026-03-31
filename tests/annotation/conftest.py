"""Shared fixtures for annotation tests."""

from __future__ import annotations

import json

import pytest

from pas.annotation.models import Sample


@pytest.fixture()
def sample_llm_input() -> list[dict[str, object]]:
    """Raw llm_input message array with msg_type annotations."""
    return [
        {"role": "system", "content": "You are simulating a real human user", "timestamp": None, "msg_type": "system_prompt"},
        {"role": "assistant", "content": "Thought: I will open notes\nAction: Notes__open\nAction Input: {\"note_id\": \"abc\"}", "timestamp": 101.0, "msg_type": "user_action"},
        {"role": "tool-response", "content": "[OUTPUT OF STEP 1] Observation:\n***\nOpened Notes App.\n***", "timestamp": 101.0, "msg_type": "tool_observation"},
        {"role": "user", "content": "Environment notifications updates:\n***\n[2025-01-01 09:00:10] New message from 22c41f3ff12fe5f2a0a02c1da9d15b57 in conversation abc123: Hello!\n***", "timestamp": None, "msg_type": "environment_notification"},
        {"role": "user", "content": "[TASK]: \nReceived at: 2025-01-01\nSender: Agent\nMessage: I propose to update your note", "timestamp": 103.0, "msg_type": "proposal"},
        {"role": "user", "content": "Available Actions from current state:\n***\n- accept_proposal\n***", "timestamp": None, "msg_type": "available_tools"},
        {"role": "user", "content": "Current app state:\n***\nNotes\n***", "timestamp": None, "msg_type": "current_app_state"},
        {"role": "assistant", "content": "Some unknown message", "timestamp": 104.0, "msg_type": "unknown"},
    ]


@pytest.fixture()
def sample_with_llm_input(sample_llm_input: list[dict[str, object]]) -> Sample:
    """A Sample instance with llm_input containing various msg_types."""
    return Sample(
        sample_id="test_scenario_run_1_p0",
        scenario_id="test_scenario",
        run_number=1,
        proactive_model_id="gpt-4o",
        user_model_id="gpt-4o",
        trace_file="traces/no_noise_gpt-4o/scenario_a.json",
        user_agent_decision="accept",
        agent_proposal="I propose to update your note",
        meta_task_description="User needs to take notes",
        llm_input=json.dumps(sample_llm_input),
        final_decision=True,
        gather_context_delta=None,
    )
