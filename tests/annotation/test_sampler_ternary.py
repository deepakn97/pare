"""Tests for ternary balanced sampling."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from pas.annotation.sampler import (
    balanced_sample_ternary,
    extract_all_decision_points_ternary,
    sample_new_datapoints_ternary,
    save_samples_ternary,
)
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


def test_balanced_sample_multiple_models() -> None:
    """Test three-way balanced sampling with candidates from multiple proactive models."""
    dps = (
        [_make_dp(f"s{i}", 1, "accept", model="claude") for i in range(5)]
        + [_make_dp(f"s{i}", 1, "accept", model="gpt") for i in range(5, 10)]
        + [_make_dp(f"s{i}", 1, "reject", model="claude") for i in range(10, 15)]
        + [_make_dp(f"s{i}", 1, "reject", model="gpt") for i in range(15, 20)]
        + [_make_dp(f"s{i}", 1, "gather_context", model="claude") for i in range(20, 25)]
        + [_make_dp(f"s{i}", 1, "gather_context", model="gpt") for i in range(25, 30)]
    )
    result = balanced_sample_ternary(dps, sample_size=12, seed=42)
    assert len(result) == 12

    # Decision types should be balanced
    decisions = [dp.user_agent_decision for dp in result]
    assert decisions.count("accept") == 4
    assert decisions.count("reject") == 4
    assert decisions.count("gather_context") == 4

    # Both models should be represented
    models = {dp.proactive_model_id for dp in result}
    assert "claude" in models
    assert "gpt" in models


def test_balanced_sample_model_with_fewer_candidates() -> None:
    """Test sampling when one model has fewer candidates than another."""
    dps = (
        [_make_dp(f"s{i}", 1, "accept", model="claude") for i in range(10)]
        + [_make_dp(f"s{i}", 1, "reject", model="claude") for i in range(10, 20)]
        + [_make_dp(f"s{i}", 1, "gather_context", model="claude") for i in range(20, 30)]
        + [_make_dp(f"s{i}", 1, "accept", model="gpt") for i in range(30, 32)]  # only 2
        + [_make_dp(f"s{i}", 1, "reject", model="gpt") for i in range(32, 34)]  # only 2
    )
    result = balanced_sample_ternary(dps, sample_size=9, seed=42)
    assert len(result) == 9

    # Both models should appear even though gpt has fewer candidates
    models = [dp.proactive_model_id for dp in result]
    assert "gpt" in models


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


def test_balanced_sample_request_more_than_available() -> None:
    """Test when sample_size exceeds total candidates."""
    dps = [
        _make_dp(f"s{i}", 1, "accept") for i in range(2)
    ] + [
        _make_dp(f"s{i}", 1, "reject") for i in range(2, 4)
    ]
    result = balanced_sample_ternary(dps, sample_size=10, seed=42)
    # Should return all 4 candidates, not 10
    assert len(result) == 4


def test_balanced_sample_deterministic_with_seed() -> None:
    """Same seed produces identical results."""
    dps = [
        _make_dp(f"s{i}", 1, "accept") for i in range(10)
    ] + [
        _make_dp(f"s{i}", 1, "reject") for i in range(10, 20)
    ] + [
        _make_dp(f"s{i}", 1, "gather_context") for i in range(20, 30)
    ]
    result1 = balanced_sample_ternary(dps, sample_size=9, seed=123)
    result2 = balanced_sample_ternary(dps, sample_size=9, seed=123)
    assert [dp.sample_id for dp in result1] == [dp.sample_id for dp in result2]


def test_balanced_sample_empty_candidates() -> None:
    """Empty candidate list returns empty result."""
    result = balanced_sample_ternary([], sample_size=5, seed=42)
    assert len(result) == 0


FIXTURES_DIR = Path(__file__).parent.parent / "trajectory" / "fixtures"


class TestExtractAllDecisionPointsTernary:
    """Tests for extract_all_decision_points_ternary using real trace fixtures."""

    def test_extracts_from_fixture_traces(self, tmp_path: Path) -> None:
        """Extracts decision points from a directory of trace files."""
        import shutil

        model_dir = tmp_path / "obs_claude-4.5-sonnet_exec_claude-4.5-sonnet_enmi_0_es_42_tfp_0.0"
        model_dir.mkdir(parents=True)
        shutil.copy(FIXTURES_DIR / "apartment_feature_comparison_query_run_4.json", model_dir)

        dps = extract_all_decision_points_ternary(tmp_path, "gpt-5-mini")
        assert len(dps) >= 1
        assert all(dp.proactive_model_id == "claude-4.5-sonnet" for dp in dps)
        assert all(dp.user_model_id == "gpt-5-mini" for dp in dps)

    def test_filters_by_target_models(self, tmp_path: Path) -> None:
        """Only extracts from target model directories."""
        import shutil

        sonnet_dir = tmp_path / "obs_claude-4.5-sonnet_exec_claude-4.5-sonnet_enmi_0_es_42_tfp_0.0"
        sonnet_dir.mkdir(parents=True)
        gpt_dir = tmp_path / "obs_gpt-5_exec_gpt-5_enmi_0_es_42_tfp_0.0"
        gpt_dir.mkdir(parents=True)
        shutil.copy(FIXTURES_DIR / "apartment_feature_comparison_query_run_4.json", sonnet_dir)
        shutil.copy(FIXTURES_DIR / "add_missing_group_contacts_run_1.json", gpt_dir)

        dps = extract_all_decision_points_ternary(tmp_path, "gpt-5-mini", target_models=["claude-4.5-sonnet"])
        assert all(dp.proactive_model_id == "claude-4.5-sonnet" for dp in dps)

    def test_skips_rate_limit_traces(self, tmp_path: Path) -> None:
        """Skips traces with RateLimitError."""
        import shutil

        model_dir = tmp_path / "obs_gpt-5_exec_gpt-5_enmi_0_es_42_tfp_0.0"
        model_dir.mkdir(parents=True)
        shutil.copy(FIXTURES_DIR / "urgent_meeting_bumps_personal_errand_run_3.json", model_dir)

        dps = extract_all_decision_points_ternary(tmp_path, "gpt-5-mini")
        assert len(dps) == 0


class TestSaveSamplesTernary:
    """Tests for save_samples_ternary with parquet schema validation."""

    def test_creates_new_parquet(self, tmp_path: Path) -> None:
        """Creates a new parquet file with ternary schema."""
        samples = [_make_dp("s1", 1, "accept"), _make_dp("s2", 1, "reject")]
        output = tmp_path / "samples.parquet"

        save_samples_ternary(samples, output)

        assert output.exists()
        df = pl.read_parquet(output)
        assert len(df) == 2
        assert "user_agent_decision" in df.columns
        assert "llm_input" in df.columns
        assert "final_decision" in df.columns
        assert df["user_agent_decision"].dtype == pl.String

    def test_appends_to_existing_parquet(self, tmp_path: Path) -> None:
        """Appends to existing parquet with compatible schema."""
        output = tmp_path / "samples.parquet"
        first_batch = [_make_dp("s1", 1, "accept")]
        save_samples_ternary(first_batch, output)

        second_batch = [_make_dp("s2", 1, "reject")]
        save_samples_ternary(second_batch, output)

        df = pl.read_parquet(output)
        assert len(df) == 2

    def test_rejects_incompatible_binary_parquet(self, tmp_path: Path) -> None:
        """Raises error if existing parquet has old binary schema."""
        output = tmp_path / "samples.parquet"
        old_df = pl.DataFrame({
            "sample_id": ["s1"],
            "user_agent_decision": [True],
        })
        old_df.write_parquet(output)

        samples = [_make_dp("s2", 1, "accept")]
        with pytest.raises(SystemExit):
            save_samples_ternary(samples, output)


    def test_empty_samples_does_not_write(self, tmp_path: Path) -> None:
        """Empty samples list returns path without creating file."""
        output = tmp_path / "samples.parquet"
        result = save_samples_ternary([], output)
        assert result == output
        assert not output.exists()


class TestSampleNewDatapointsTernary:
    """Tests for sample_new_datapoints_ternary end-to-end."""

    def test_samples_from_traces(self, tmp_path: Path) -> None:
        """End-to-end: extracts and samples from trace files."""
        import shutil

        model_dir = tmp_path / "traces" / "obs_claude-4.5-sonnet_exec_claude-4.5-sonnet_enmi_0_es_42_tfp_0.0"
        model_dir.mkdir(parents=True)
        shutil.copy(FIXTURES_DIR / "apartment_feature_comparison_query_run_4.json", model_dir)
        shutil.copy(FIXTURES_DIR / "cancelled_meeting_note_cleanup_run_4.json", model_dir)

        output = tmp_path / "samples.parquet"
        samples = sample_new_datapoints_ternary(
            traces_dir=tmp_path / "traces",
            samples_file=output,
            user_model_id="gpt-5-mini",
            sample_size=3,
            seed=42,
        )
        assert len(samples) <= 3
        assert all(isinstance(dp, DecisionPoint) for dp in samples)

    def test_deduplicates_existing_samples(self, tmp_path: Path) -> None:
        """Existing samples in parquet are excluded from new sampling."""
        import shutil

        model_dir = tmp_path / "traces" / "obs_claude-4.5-sonnet_exec_claude-4.5-sonnet_enmi_0_es_42_tfp_0.0"
        model_dir.mkdir(parents=True)
        shutil.copy(FIXTURES_DIR / "apartment_feature_comparison_query_run_4.json", model_dir)
        shutil.copy(FIXTURES_DIR / "cancelled_meeting_note_cleanup_run_4.json", model_dir)

        output = tmp_path / "samples.parquet"

        # First sampling
        first = sample_new_datapoints_ternary(
            traces_dir=tmp_path / "traces",
            samples_file=output,
            user_model_id="gpt-5-mini",
            sample_size=2,
            seed=42,
        )
        assert len(first) > 0
        first_ids = {dp.sample_id for dp in first}

        # Second sampling — should not duplicate
        second = sample_new_datapoints_ternary(
            traces_dir=tmp_path / "traces",
            samples_file=output,
            user_model_id="gpt-5-mini",
            sample_size=2,
            seed=42,
        )
        second_ids = {dp.sample_id for dp in second}
        assert first_ids.isdisjoint(second_ids)
