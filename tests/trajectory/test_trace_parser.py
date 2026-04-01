"""Tests for trajectory trace parser."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pare.trajectory.trace_parser import _parse_notification_timestamp, extract_decision_points

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


def test_parse_notification_timestamp_single_event() -> None:
    """Parse timestamp from a single non-None notification line."""
    content = "Environment notifications updates:\n***\n[2025-01-15 09:00:05] Ride completed\n***"
    ts = _parse_notification_timestamp(content)
    expected = datetime(2025, 1, 15, 9, 0, 5, tzinfo=UTC).timestamp()
    assert ts == expected


def test_parse_notification_timestamp_skips_none_lines() -> None:
    """Last non-None line's timestamp is used, None lines are skipped."""
    content = (
        "Environment notifications updates:\n***\n"
        "[2025-11-18 09:00:10] None\n"
        "[2025-11-18 09:00:15] New email from bob@example.com: Hello\n"
        "[2025-11-18 09:00:20] None\n"
        "***"
    )
    ts = _parse_notification_timestamp(content)
    expected = datetime(2025, 11, 18, 9, 0, 15, tzinfo=UTC).timestamp()
    assert ts == expected


def test_parse_notification_timestamp_multiple_events_uses_last() -> None:
    """When multiple non-None events exist, use the last one's timestamp."""
    content = (
        "Environment notifications updates:\n***\n"
        "[2025-11-18 09:00:05] Ride completed\n"
        "[2025-11-18 09:00:10] New email from alice@example.com: Meeting\n"
        "***"
    )
    ts = _parse_notification_timestamp(content)
    expected = datetime(2025, 11, 18, 9, 0, 10, tzinfo=UTC).timestamp()
    assert ts == expected


def test_parse_notification_timestamp_all_none_returns_none() -> None:
    """When all notification lines are None, return None."""
    content = (
        "Environment notifications updates:\n***\n"
        "[2025-11-18 09:00:10] None\n"
        "[2025-11-18 09:00:20] None\n"
        "***"
    )
    ts = _parse_notification_timestamp(content)
    assert ts is None


def test_parse_notification_timestamp_skips_empty_content() -> None:
    """Lines with empty content after timestamp are skipped."""
    content = (
        "Environment notifications updates:\n***\n"
        "[2025-11-18 09:00:10] \n"
        "[2025-11-18 09:00:15] New email from bob@example.com: Hello\n"
        "***"
    )
    ts = _parse_notification_timestamp(content)
    expected = datetime(2025, 11, 18, 9, 0, 15, tzinfo=UTC).timestamp()
    assert ts == expected


def test_parse_notification_timestamp_no_match_returns_none() -> None:
    """Content without timestamp pattern returns None."""
    content = "Some random content"
    ts = _parse_notification_timestamp(content)
    assert ts is None


def test_llm_input_notification_has_timestamp(trace_accept: Path) -> None:
    """Notification messages in llm_input get timestamps parsed from content."""
    dps = extract_decision_points(trace_accept, proactive_model_id="claude-4.5-sonnet", user_model_id="gpt-5-mini")
    dp = dps[0]
    notif_msgs = [m for m in dp.llm_input if m["msg_type"] == "environment_notification"]
    assert len(notif_msgs) == 1
    # The trace_accept fixture has "[2025-01-01 09:00:10] New calendar event"
    expected_ts = datetime(2025, 1, 1, 9, 0, 10, tzinfo=UTC).timestamp()
    assert notif_msgs[0]["timestamp"] == expected_ts
