"""Tests for trajectory DecisionPoint model."""
from __future__ import annotations

from pathlib import Path

from pare.trajectory.models import DecisionPoint


def test_decision_point_creation_accept() -> None:
    """Test creating a DecisionPoint with accept decision."""
    dp = DecisionPoint(
        sample_id="test_scenario_run_1_p0",
        scenario_id="test_scenario",
        run_number=1,
        proactive_model_id="claude-4.5-sonnet",
        user_model_id="gpt-5-mini",
        trace_file=Path("traces/test.json"),
        user_agent_decision="accept",
        llm_input=[{"role": "system", "content": "test"}],
        agent_proposal="I propose to do X",
        final_decision=True,
        meta_task_description="Test task",
    )
    assert dp.user_agent_decision == "accept"
    assert dp.final_decision is True
    assert dp.gather_context_delta is None


def test_decision_point_creation_gather_context() -> None:
    """Test creating a DecisionPoint with gather_context decision."""
    dp = DecisionPoint(
        sample_id="test_scenario_run_1_p0",
        scenario_id="test_scenario",
        run_number=1,
        proactive_model_id="claude-4.5-sonnet",
        user_model_id="gpt-5-mini",
        trace_file=Path("traces/test.json"),
        user_agent_decision="gather_context",
        llm_input=[{"role": "system", "content": "test"}],
        agent_proposal="I propose to do X",
        final_decision=True,
        meta_task_description="Test task",
        gather_context_delta=[{"role": "assistant", "content": "Thought: check email"}],
    )
    assert dp.user_agent_decision == "gather_context"
    assert dp.final_decision is True
    assert dp.gather_context_delta is not None
    assert len(dp.gather_context_delta) == 1


def test_decision_point_generate_sample_id() -> None:
    """Test sample ID generation."""
    sample_id = DecisionPoint.generate_sample_id("my_scenario", 2, 0)
    assert sample_id == "my_scenario_run_2_p0"

    sample_id_p1 = DecisionPoint.generate_sample_id("my_scenario", 2, 1)
    assert sample_id_p1 == "my_scenario_run_2_p1"


def test_decision_point_to_sample_dict() -> None:
    """Test serialization to dict for parquet."""
    dp = DecisionPoint(
        sample_id="test_run_1_p0",
        scenario_id="test",
        run_number=1,
        proactive_model_id="gpt-5",
        user_model_id="gpt-5-mini",
        trace_file=Path("traces/test.json"),
        user_agent_decision="reject",
        llm_input=[{"role": "system", "content": "prompt"}],
        agent_proposal="proposal text",
        final_decision=False,
        meta_task_description="",
    )
    d = dp.to_sample_dict()
    assert d["user_agent_decision"] == "reject"
    assert d["final_decision"] is False
    assert isinstance(d["llm_input"], str)  # JSON serialized
    assert d["gather_context_delta"] is None
