"""Tests for the pas benchmark run command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from pare.cli.benchmark import app

runner = CliRunner()


def test_run_command_exists() -> None:
    """The run command should be registered."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--observe-model" in result.output
    assert "--observe-provider" in result.output
    assert "--observe-endpoint" in result.output
    assert "--execute-model" in result.output
    assert "--execute-provider" in result.output
    assert "--execute-endpoint" in result.output
    assert "--user-model" in result.output
    assert "--user-provider" in result.output
    assert "--user-endpoint" in result.output
    assert "--config" in result.output


def test_run_requires_split_or_scenarios() -> None:
    """Run should fail if neither --split nor --scenarios is provided."""
    result = runner.invoke(app, ["run"])
    assert result.exit_code != 0


def test_run_constructs_engine_config_with_endpoint() -> None:
    """Run should pass endpoint through to LLMEngineConfig."""
    with (
        patch("pare.cli.benchmark.probe_llm_endpoint"),
        patch("pare.cli.benchmark.run_single_config") as mock_run,
        patch("pare.cli.benchmark.build_result_key", return_value=("user", "obs_exec", 0.0, 0)),
        patch("pare.cli.benchmark._print_config_result"),
        patch("pare.cli.benchmark.load_scenarios_by_split") as mock_load,
    ):
        mock_load.return_value = MagicMock()
        mock_run.return_value = ("test_descriptor", MagicMock())

        result = runner.invoke(
            app,
            [
                "run",
                "--split", "full",
                "--observe-model", "liquid/lfm2.5-350m",
                "--observe-provider", "hosted_vllm",
                "--observe-endpoint", "http://localhost:8001/v1",
                "--execute-model", "google/gemma-4-26b-a4b-it",
                "--execute-provider", "hosted_vllm",
                "--execute-endpoint", "http://localhost:8002/v1",
            ],
        )

        assert result.exit_code == 0, f"Command failed with: {result.output}"
        config = mock_run.call_args[1].get("config") or mock_run.call_args[0][0]
        assert config.observe_engine_config.endpoint == "http://localhost:8001/v1"
        assert config.observe_engine_config.provider == "hosted_vllm"
        assert config.observe_engine_config.model_name == "liquid/lfm2.5-350m"
        assert config.execute_engine_config.endpoint == "http://localhost:8002/v1"
        assert config.execute_engine_config.provider == "hosted_vllm"
        assert config.execute_engine_config.model_name == "google/gemma-4-26b-a4b-it"


def test_sweep_command_removed() -> None:
    """The sweep command should no longer exist."""
    result = runner.invoke(app, ["sweep", "--help"])
    assert result.exit_code != 0
