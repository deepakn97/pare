"""Tests for trajectory trace parser."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pas.trajectory.trace_parser import extract_decision_points

if TYPE_CHECKING:
    from pathlib import Path


def test_extract_accept_decision(trace_accept: Path) -> None:
    """Test extracting a direct accept decision."""
    dps = extract_decision_points(trace_accept, proactive_model_id="claude-4.5-sonnet", user_model_id="gpt-5-mini")
    assert len(dps) == 1
    dp = dps[0]
    assert dp.user_agent_decision == "accept"
    assert dp.final_decision is True
    assert dp.gather_context_delta is None
    assert dp.agent_proposal == "I propose to update your note"
    assert len(dp.llm_input) == 7  # system + assistant + tool-response + task + notif + tools + state


def test_extract_reject_decision(trace_reject: Path) -> None:
    """Test extracting a direct reject decision."""
    dps = extract_decision_points(trace_reject, proactive_model_id="gpt-5", user_model_id="gpt-5-mini")
    assert len(dps) == 1
    dp = dps[0]
    assert dp.user_agent_decision == "reject"
    assert dp.final_decision is False
    assert dp.gather_context_delta is None


def test_extract_gather_context_decision(trace_gather_context: Path) -> None:
    """Test extracting a gather_context decision with delta."""
    dps = extract_decision_points(trace_gather_context, proactive_model_id="claude-4.5-sonnet", user_model_id="gpt-5-mini")
    assert len(dps) == 1
    dp = dps[0]
    assert dp.user_agent_decision == "gather_context"
    assert dp.final_decision is True  # eventually accepted
    assert dp.gather_context_delta is not None
    assert len(dp.gather_context_delta) > 0


def test_extract_no_proposal(trace_no_proposal: Path) -> None:
    """Test trace with no proposal returns empty list."""
    dps = extract_decision_points(trace_no_proposal, proactive_model_id="gpt-5", user_model_id="gpt-5-mini")
    assert len(dps) == 0


def test_llm_input_has_timestamp_annotations(trace_accept: Path) -> None:
    """Test that llm_input messages have timestamp and msg_type annotations."""
    dps = extract_decision_points(trace_accept, proactive_model_id="claude-4.5-sonnet", user_model_id="gpt-5-mini")
    dp = dps[0]
    for msg in dp.llm_input:
        assert "msg_type" in msg
        assert "timestamp" in msg
    # System prompt should have no timestamp
    system_msg = [m for m in dp.llm_input if m["msg_type"] == "system_prompt"]
    assert len(system_msg) == 1
    assert system_msg[0]["timestamp"] is None
    # Proposal should have timestamp
    proposal_msgs = [m for m in dp.llm_input if m["msg_type"] == "proposal"]
    assert len(proposal_msgs) == 1
    assert proposal_msgs[0]["timestamp"] is not None
