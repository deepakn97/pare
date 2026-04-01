"""Tests for trace parser against real benchmark traces.

These tests use actual trace files from benchmark runs (stored in fixtures/)
to verify the parser handles real-world trace structures correctly.
"""

from __future__ import annotations

from pathlib import Path

from pare.trajectory.trace_parser import extract_decision_points

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestDirectReject:
    """Tests using add_missing_group_contacts_run_1.json.

    Trace has one proposal followed by a direct reject (no intermediate tools).
    Also has orphan reject/accept decisions without preceding proposals,
    which the parser should correctly skip.
    """

    def test_single_reject_decision_point(self) -> None:
        """Parser extracts exactly one decision point."""
        trace = FIXTURES_DIR / "add_missing_group_contacts_run_1.json"
        dps = extract_decision_points(trace, "claude-4.5-sonnet", "gpt-5-mini")
        assert len(dps) == 1

    def test_reject_classification(self) -> None:
        """Decision is classified as direct reject."""
        trace = FIXTURES_DIR / "add_missing_group_contacts_run_1.json"
        dp = extract_decision_points(trace, "claude-4.5-sonnet", "gpt-5-mini")[0]
        assert dp.user_agent_decision == "reject"
        assert dp.final_decision is False

    def test_reject_has_no_gather_delta(self) -> None:
        """Direct reject has no gather_context_delta."""
        trace = FIXTURES_DIR / "add_missing_group_contacts_run_1.json"
        dp = extract_decision_points(trace, "claude-4.5-sonnet", "gpt-5-mini")[0]
        assert dp.gather_context_delta is None

    def test_reject_metadata(self) -> None:
        """Metadata fields are populated correctly."""
        trace = FIXTURES_DIR / "add_missing_group_contacts_run_1.json"
        dp = extract_decision_points(trace, "claude-4.5-sonnet", "gpt-5-mini")[0]
        assert dp.scenario_id == "add_missing_group_contacts"
        assert dp.run_number == 1
        assert dp.proactive_model_id == "claude-4.5-sonnet"
        assert dp.user_model_id == "gpt-5-mini"
        assert dp.sample_id == "add_missing_group_contacts_run_1_p0"


class TestGatherContextSingleIntermediate:
    """Tests using apartment_feature_comparison_query_run_4.json.

    Trace has one proposal where the user calls one intermediate tool
    (list_recent_conversations) before accepting.
    """

    def test_single_gather_context_decision(self) -> None:
        """Parser extracts exactly one decision point."""
        trace = FIXTURES_DIR / "apartment_feature_comparison_query_run_4.json"
        dps = extract_decision_points(trace, "claude-4.5-sonnet", "gpt-5-mini")
        assert len(dps) == 1

    def test_gather_context_classification(self) -> None:
        """Decision is classified as gather_context with final accept."""
        trace = FIXTURES_DIR / "apartment_feature_comparison_query_run_4.json"
        dp = extract_decision_points(trace, "claude-4.5-sonnet", "gpt-5-mini")[0]
        assert dp.user_agent_decision == "gather_context"
        assert dp.final_decision is True

    def test_gather_context_has_delta(self) -> None:
        """gather_context decision has a non-empty delta."""
        trace = FIXTURES_DIR / "apartment_feature_comparison_query_run_4.json"
        dp = extract_decision_points(trace, "claude-4.5-sonnet", "gpt-5-mini")[0]
        assert dp.gather_context_delta is not None
        assert len(dp.gather_context_delta) == 3

    def test_llm_input_has_annotations(self) -> None:
        """llm_input messages have timestamp and msg_type annotations."""
        trace = FIXTURES_DIR / "apartment_feature_comparison_query_run_4.json"
        dp = extract_decision_points(trace, "claude-4.5-sonnet", "gpt-5-mini")[0]
        for msg in dp.llm_input:
            assert "msg_type" in msg
            assert "timestamp" in msg

    def test_llm_input_message_count(self) -> None:
        """llm_input has expected number of messages."""
        trace = FIXTURES_DIR / "apartment_feature_comparison_query_run_4.json"
        dp = extract_decision_points(trace, "claude-4.5-sonnet", "gpt-5-mini")[0]
        assert len(dp.llm_input) == 8


class TestMultipleProposals:
    """Tests using cancelled_meeting_note_cleanup_run_4.json.

    Trace has two proposals before execute agent starts:
    - First proposal: direct reject
    - Second proposal: gather_context then accept
    """

    def test_two_decision_points(self) -> None:
        """Parser extracts two decision points."""
        trace = FIXTURES_DIR / "cancelled_meeting_note_cleanup_run_4.json"
        dps = extract_decision_points(trace, "claude-4.5-sonnet", "gpt-5-mini")
        assert len(dps) == 2

    def test_first_proposal_is_reject(self) -> None:
        """First proposal is a direct reject."""
        trace = FIXTURES_DIR / "cancelled_meeting_note_cleanup_run_4.json"
        dp = extract_decision_points(trace, "claude-4.5-sonnet", "gpt-5-mini")[0]
        assert dp.user_agent_decision == "reject"
        assert dp.final_decision is False
        assert dp.gather_context_delta is None

    def test_second_proposal_is_gather_context(self) -> None:
        """Second proposal is gather_context with final accept."""
        trace = FIXTURES_DIR / "cancelled_meeting_note_cleanup_run_4.json"
        dp = extract_decision_points(trace, "claude-4.5-sonnet", "gpt-5-mini")[1]
        assert dp.user_agent_decision == "gather_context"
        assert dp.final_decision is True
        assert dp.gather_context_delta is not None
        assert len(dp.gather_context_delta) == 2

    def test_sample_ids_increment(self) -> None:
        """Sample IDs use incrementing proposal indices."""
        trace = FIXTURES_DIR / "cancelled_meeting_note_cleanup_run_4.json"
        dps = extract_decision_points(trace, "claude-4.5-sonnet", "gpt-5-mini")
        assert dps[0].sample_id.endswith("_p0")
        assert dps[1].sample_id.endswith("_p1")

    def test_different_llm_input_per_proposal(self) -> None:
        """Each decision point has distinct llm_input."""
        trace = FIXTURES_DIR / "cancelled_meeting_note_cleanup_run_4.json"
        dps = extract_decision_points(trace, "claude-4.5-sonnet", "gpt-5-mini")
        assert dps[0].llm_input != dps[1].llm_input
        assert len(dps[0].llm_input) == 7
        assert len(dps[1].llm_input) == 21


class TestGatherContextManyIntermediates:
    """Tests using duplicate_order_cancellation_check_run_4.json.

    Trace has one proposal where the user makes multiple tool calls
    before eventually rejecting. gather_context with final_decision=False.
    """

    def test_single_decision_point(self) -> None:
        """Parser extracts exactly one decision point."""
        trace = FIXTURES_DIR / "duplicate_order_cancellation_check_run_4.json"
        dps = extract_decision_points(trace, "claude-4.5-sonnet", "gpt-5-mini")
        assert len(dps) == 1

    def test_gather_context_then_reject(self) -> None:
        """Decision is gather_context with final reject."""
        trace = FIXTURES_DIR / "duplicate_order_cancellation_check_run_4.json"
        dp = extract_decision_points(trace, "claude-4.5-sonnet", "gpt-5-mini")[0]
        assert dp.user_agent_decision == "gather_context"
        assert dp.final_decision is False

    def test_large_gather_delta(self) -> None:
        """gather_context_delta captures all intermediate messages."""
        trace = FIXTURES_DIR / "duplicate_order_cancellation_check_run_4.json"
        dp = extract_decision_points(trace, "claude-4.5-sonnet", "gpt-5-mini")[0]
        assert dp.gather_context_delta is not None
        assert len(dp.gather_context_delta) == 6


class TestRateLimitError:
    """Tests using urgent_meeting_bumps_personal_errand_run_3.json.

    Trace contains a RateLimitError and should be skipped entirely.
    """

    def test_returns_empty_list(self) -> None:
        """Parser returns empty list for RateLimitError traces."""
        trace = FIXTURES_DIR / "urgent_meeting_bumps_personal_errand_run_3.json"
        dps = extract_decision_points(trace, "gpt-5", "gpt-5-mini")
        assert len(dps) == 0
