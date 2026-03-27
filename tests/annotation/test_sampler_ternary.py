"""Tests for ternary balanced sampling."""

from __future__ import annotations

from pathlib import Path

from pas.annotation.sampler import balanced_sample_ternary
from pas.trajectory.models import DecisionPoint


def _make_dp(scenario: str, run: int, decision: str, model: str = "claude") -> DecisionPoint:
    """Helper to create DecisionPoint for testing."""
    return DecisionPoint(
        sample_id=DecisionPoint.generate_sample_id(scenario, run, 0),
        scenario_id=scenario,
        run_number=run,
        proactive_model_id=model,
        user_model_id="gpt-5-mini",
        trace_file=Path("traces/test.json"),
        user_agent_decision=decision,
        llm_input=[{"role": "system", "content": "test"}],
        agent_proposal="proposal",
        final_decision=decision != "reject",
        meta_task_description="",
    )


def test_balanced_sample_equal_pools() -> None:
    """Test three-way balanced sampling with equal pool sizes."""
    dps = [
        _make_dp(f"s{i}", 1, "accept") for i in range(10)
    ] + [
        _make_dp(f"s{i}", 1, "reject") for i in range(10, 20)
    ] + [
        _make_dp(f"s{i}", 1, "gather_context") for i in range(20, 30)
    ]
    result = balanced_sample_ternary(dps, sample_size=9, seed=42)
    assert len(result) == 9
    decisions = [dp.user_agent_decision for dp in result]
    assert decisions.count("accept") == 3
    assert decisions.count("reject") == 3
    assert decisions.count("gather_context") == 3


def test_balanced_sample_unequal_pools() -> None:
    """Test three-way balanced sampling when one pool is smaller."""
    dps = [
        _make_dp(f"s{i}", 1, "accept") for i in range(10)
    ] + [
        _make_dp(f"s{i}", 1, "reject") for i in range(10, 20)
    ] + [
        _make_dp(f"s{i}", 1, "gather_context") for i in range(20, 22)  # only 2
    ]
    result = balanced_sample_ternary(dps, sample_size=9, seed=42)
    # Can only get 2 gather_context, so 2+2+2=6 balanced, or fill remaining from other pools
    assert len(result) <= 9
    decisions = [dp.user_agent_decision for dp in result]
    assert decisions.count("gather_context") == 2


def test_balanced_sample_empty_pool() -> None:
    """Test when one category has zero samples."""
    dps = [
        _make_dp(f"s{i}", 1, "accept") for i in range(10)
    ] + [
        _make_dp(f"s{i}", 1, "reject") for i in range(10, 20)
    ]
    result = balanced_sample_ternary(dps, sample_size=6, seed=42)
    assert len(result) == 6
    decisions = [dp.user_agent_decision for dp in result]
    assert decisions.count("gather_context") == 0
    assert decisions.count("accept") == 3
    assert decisions.count("reject") == 3
