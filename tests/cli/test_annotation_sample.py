"""Integration tests for the CLI sample command with ternary pipeline.

Tests the end-to-end flow: CLI command -> trace parsing -> balanced sampling -> parquet output.
Uses real trace fixtures from tests/trajectory/fixtures/.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import polars as pl
from typer.testing import CliRunner

from pare.main import app

FIXTURES_DIR = Path(__file__).parent.parent / "trajectory" / "fixtures"

runner = CliRunner()


def _setup_traces(tmp_path: Path) -> Path:
    """Set up a trace directory with fixture files for testing.

    Args:
        tmp_path: Pytest temporary directory.

    Returns:
        Path to the traces root directory.
    """
    traces_dir = tmp_path / "traces"
    model_dir = traces_dir / "obs_claude-4.5-sonnet_exec_claude-4.5-sonnet_enmi_0_es_42_tfp_0.0"
    model_dir.mkdir(parents=True)
    shutil.copy(FIXTURES_DIR / "apartment_feature_comparison_query_run_4.json", model_dir)
    shutil.copy(FIXTURES_DIR / "cancelled_meeting_note_cleanup_run_4.json", model_dir)
    shutil.copy(FIXTURES_DIR / "add_missing_group_contacts_run_1.json", model_dir)
    return traces_dir


class TestSampleCommand:
    """Integration tests for `pare annotation sample` CLI command."""

    def test_creates_parquet_with_ternary_schema(self, tmp_path: Path) -> None:
        """Output parquet has correct ternary schema columns."""
        traces_dir = _setup_traces(tmp_path)
        output = tmp_path / "samples.parquet"

        result = runner.invoke(app, [
            "annotation", "sample",
            "--traces-dir", str(traces_dir),
            "--output", str(output),
            "--sample-size", "3",
            "--user-model", "gpt-5-mini",
            "--seed", "42",
        ])
        assert result.exit_code == 0, result.output

        df = pl.read_parquet(output)
        assert "user_agent_decision" in df.columns
        assert "llm_input" in df.columns
        assert "final_decision" in df.columns
        assert "gather_context_delta" in df.columns
        assert df["user_agent_decision"].dtype == pl.String

    def test_balanced_ternary_output(self, tmp_path: Path) -> None:
        """Output shows ternary breakdown in CLI output."""
        traces_dir = _setup_traces(tmp_path)
        output = tmp_path / "samples.parquet"

        result = runner.invoke(app, [
            "annotation", "sample",
            "--traces-dir", str(traces_dir),
            "--output", str(output),
            "--sample-size", "3",
            "--user-model", "gpt-5-mini",
            "--seed", "42",
        ])
        assert result.exit_code == 0
        assert "Gather context:" in result.output
        assert "Accepts:" in result.output
        assert "Rejects:" in result.output

    def test_deduplication_on_second_run(self, tmp_path: Path) -> None:
        """Second sampling run deduplicates against existing samples."""
        traces_dir = _setup_traces(tmp_path)
        output = tmp_path / "samples.parquet"

        # First run
        result1 = runner.invoke(app, [
            "annotation", "sample",
            "--traces-dir", str(traces_dir),
            "--output", str(output),
            "--sample-size", "2",
            "--user-model", "gpt-5-mini",
            "--seed", "42",
        ])
        assert result1.exit_code == 0
        df1 = pl.read_parquet(output)
        first_count = len(df1)

        # Second run — should add new samples, not duplicates
        result2 = runner.invoke(app, [
            "annotation", "sample",
            "--traces-dir", str(traces_dir),
            "--output", str(output),
            "--sample-size", "2",
            "--user-model", "gpt-5-mini",
            "--seed", "99",
        ])
        assert result2.exit_code == 0
        df2 = pl.read_parquet(output)
        assert len(df2) >= first_count
        # No duplicate sample_ids
        assert df2["sample_id"].n_unique() == len(df2)

    def test_rejects_binary_schema_parquet(self, tmp_path: Path) -> None:
        """Exits with error if existing parquet has old binary schema."""
        traces_dir = _setup_traces(tmp_path)
        output = tmp_path / "samples.parquet"

        # Create a binary-schema parquet
        old_df = pl.DataFrame({
            "sample_id": ["s1"],
            "user_agent_decision": [True],
        })
        old_df.write_parquet(output)

        result = runner.invoke(app, [
            "annotation", "sample",
            "--traces-dir", str(traces_dir),
            "--output", str(output),
            "--sample-size", "3",
            "--user-model", "gpt-5-mini",
        ])
        assert result.exit_code != 0

    def test_nonexistent_traces_dir(self, tmp_path: Path) -> None:
        """Exits with error if traces directory doesn't exist."""
        result = runner.invoke(app, [
            "annotation", "sample",
            "--traces-dir", str(tmp_path / "nonexistent"),
            "--output", str(tmp_path / "samples.parquet"),
            "--sample-size", "3",
            "--user-model", "gpt-5-mini",
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_parquet_schema_matches_spec(self, tmp_path: Path) -> None:
        """Verify parquet columns match spec including tutorial fields."""
        traces_dir = _setup_traces(tmp_path)
        output = tmp_path / "samples.parquet"

        result = runner.invoke(app, [
            "annotation", "sample",
            "--traces-dir", str(traces_dir),
            "--output", str(output),
            "--sample-size", "3",
            "--user-model", "gpt-5-mini",
            "--seed", "42",
        ])
        assert result.exit_code == 0

        df = pl.read_parquet(output)
        expected_columns = {
            "sample_id",
            "scenario_id",
            "run_number",
            "proactive_model_id",
            "user_model_id",
            "trace_file",
            "user_agent_decision",
            "llm_input",
            "agent_proposal",
            "final_decision",
            "meta_task_description",
            "gather_context_delta",
            "tutorial",
            "correct_decision",
            "explanation",
        }
        assert set(df.columns) == expected_columns
        # Real samples should have tutorial=False
        assert df["tutorial"].to_list() == [False] * len(df)


class TestAddTutorialExamples:
    """Tests for --add-tutorial-examples flag."""

    def test_adds_tutorial_rows_to_output(self, tmp_path: Path) -> None:
        """Tutorial examples are copied into samples.parquet with tutorial=True."""
        import json

        traces_dir = _setup_traces(tmp_path)
        output = tmp_path / "samples.parquet"

        # Create a tutorial parquet with one example
        tutorial_llm_input = [
            {"role": "assistant", "content": "test", "timestamp": 101.0, "msg_type": "user_action"},
            {"role": "user", "content": "[TASK]: test proposal", "timestamp": 103.0, "msg_type": "proposal"},
        ]
        tutorial_df = pl.DataFrame({
            "sample_id": ["tutorial_001"],
            "scenario_id": ["tutorial_scenario"],
            "run_number": [1],
            "proactive_model_id": ["gpt-4o"],
            "user_model_id": ["gpt-4o"],
            "trace_file": ["traces/tutorial.json"],
            "user_agent_decision": ["accept"],
            "agent_proposal": ["test proposal"],
            "meta_task_description": ["Tutorial scenario"],
            "llm_input": [json.dumps(tutorial_llm_input)],
            "final_decision": [True],
            "gather_context_delta": [None],
            "tutorial": [True],
            "correct_decision": ["accept"],
            "explanation": ["This is the correct answer."],
        })
        tutorial_file = tmp_path / "tutorial_samples.parquet"
        tutorial_df.write_parquet(tutorial_file)

        result = runner.invoke(app, [
            "annotation", "sample",
            "--traces-dir", str(traces_dir),
            "--output", str(output),
            "--sample-size", "2",
            "--user-model", "gpt-5-mini",
            "--seed", "42",
            "--add-tutorial-examples", str(tutorial_file),
        ])
        assert result.exit_code == 0, result.output

        df = pl.read_parquet(output)
        tutorial_rows = df.filter(pl.col("tutorial") == True)  # noqa: E712
        real_rows = df.filter(pl.col("tutorial") == False)  # noqa: E712
        assert len(tutorial_rows) == 1
        assert len(real_rows) >= 1
        assert tutorial_rows["sample_id"][0] == "tutorial_001"
        assert tutorial_rows["correct_decision"][0] == "accept"

    def test_tutorial_not_duplicated_on_rerun(self, tmp_path: Path) -> None:
        """Running with --add-tutorial-examples twice does not duplicate tutorial rows."""
        import json

        traces_dir = _setup_traces(tmp_path)
        output = tmp_path / "samples.parquet"

        tutorial_df = pl.DataFrame({
            "sample_id": ["tutorial_001"],
            "scenario_id": ["tutorial_scenario"],
            "run_number": [1],
            "proactive_model_id": ["gpt-4o"],
            "user_model_id": ["gpt-4o"],
            "trace_file": ["traces/tutorial.json"],
            "user_agent_decision": ["accept"],
            "agent_proposal": ["test"],
            "meta_task_description": ["Tutorial"],
            "llm_input": [json.dumps([])],
            "final_decision": [True],
            "gather_context_delta": [None],
            "tutorial": [True],
            "correct_decision": ["accept"],
            "explanation": ["Correct."],
        })
        tutorial_file = tmp_path / "tutorial_samples.parquet"
        tutorial_df.write_parquet(tutorial_file)

        # First run
        runner.invoke(app, [
            "annotation", "sample",
            "--traces-dir", str(traces_dir),
            "--output", str(output),
            "--sample-size", "2",
            "--user-model", "gpt-5-mini",
            "--seed", "42",
            "--add-tutorial-examples", str(tutorial_file),
        ])

        # Second run
        runner.invoke(app, [
            "annotation", "sample",
            "--traces-dir", str(traces_dir),
            "--output", str(output),
            "--sample-size", "2",
            "--user-model", "gpt-5-mini",
            "--seed", "99",
            "--add-tutorial-examples", str(tutorial_file),
        ])

        df = pl.read_parquet(output)
        tutorial_rows = df.filter(pl.col("tutorial") == True)  # noqa: E712
        assert len(tutorial_rows) == 1  # Not duplicated
