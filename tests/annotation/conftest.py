"""Shared fixtures for annotation tests."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import polars as pl
import pytest
from fastapi.testclient import TestClient

from pas.annotation.models import Sample
from pas.annotation.server import create_app

if TYPE_CHECKING:
    from pathlib import Path


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


@pytest.fixture()
def sample_data_with_tutorial() -> list[dict[str, object]]:
    """Sample data including tutorial and real samples."""
    tutorial_llm_input = [
        {"role": "assistant", "content": "Thought: test\nAction: Email__open_email\nAction Input: {}", "timestamp": 101.0, "msg_type": "user_action"},
        {"role": "tool-response", "content": "[OUTPUT OF STEP 1] Observation:\n***\nSubject: Meeting at 3pm\n***", "timestamp": 101.0, "msg_type": "tool_observation"},
        {"role": "user", "content": "[TASK]: Schedule meeting at 3pm", "timestamp": 103.0, "msg_type": "proposal"},
    ]
    return [
        {
            "sample_id": "tutorial_accept_1",
            "scenario_id": "tutorial_scenario_a",
            "run_number": 1,
            "proactive_model_id": "gpt-4o",
            "user_model_id": "gpt-4o",
            "trace_file": "traces/no_noise_gpt-4o/scenario_a.json",
            "user_agent_decision": "accept",
            "agent_proposal": "Schedule meeting at 3pm",
            "meta_task_description": "User is checking email",
            "llm_input": json.dumps(tutorial_llm_input),
            "final_decision": True,
            "gather_context_delta": None,
            "tutorial": True,
            "correct_decision": "accept",
            "explanation": "The user read the email and calendar is free.",
        },
        {
            "sample_id": "tutorial_reject_1",
            "scenario_id": "tutorial_scenario_b",
            "run_number": 1,
            "proactive_model_id": "gpt-4o",
            "user_model_id": "gpt-4o",
            "trace_file": "traces/no_noise_gpt-4o/scenario_b.json",
            "user_agent_decision": "reject",
            "agent_proposal": "Delete all notes",
            "meta_task_description": "User is browsing notes",
            "llm_input": json.dumps([
                {"role": "assistant", "content": "Thought: test\nAction: Notes__open\nAction Input: {}", "timestamp": 101.0, "msg_type": "user_action"},
                {"role": "user", "content": "[TASK]: Delete all notes", "timestamp": 102.0, "msg_type": "proposal"},
            ]),
            "final_decision": False,
            "gather_context_delta": None,
            "tutorial": True,
            "correct_decision": "reject",
            "explanation": "The proposal is destructive and unsolicited.",
        },
        {
            "sample_id": "real_sample_001",
            "scenario_id": "scenario_a",
            "run_number": 1,
            "proactive_model_id": "gpt-4o",
            "user_model_id": "gpt-4o",
            "trace_file": "traces/no_noise_gpt-4o/scenario_a.json",
            "user_agent_decision": "accept",
            "agent_proposal": "I propose X",
            "meta_task_description": "Test scenario",
            "llm_input": json.dumps([
                {"role": "assistant", "content": "Thought: test\nAction: Notes__open\nAction Input: {}", "timestamp": 101.0, "msg_type": "user_action"},
                {"role": "user", "content": "[TASK]: I propose X", "timestamp": 103.0, "msg_type": "proposal"},
            ]),
            "final_decision": True,
            "gather_context_delta": None,
            "tutorial": False,
            "correct_decision": None,
            "explanation": None,
        },
    ]


@pytest.fixture()
def tutorial_server_paths(sample_data_with_tutorial: list[dict[str, object]], tmp_path: Path) -> tuple[Path, Path]:
    """Create temporary samples parquet with tutorial + real samples."""
    samples_file = tmp_path / "samples.parquet"
    annotations_file = tmp_path / "annotations.csv"
    df = pl.DataFrame(sample_data_with_tutorial)
    df.write_parquet(samples_file)
    return samples_file, annotations_file


@pytest.fixture()
def tutorial_client(tutorial_server_paths: tuple[Path, Path]) -> TestClient:
    """Create a test client with tutorial samples in the parquet."""
    samples_file, annotations_file = tutorial_server_paths
    app = create_app(samples_file, annotations_file, annotators_per_sample=2)
    return TestClient(app)
