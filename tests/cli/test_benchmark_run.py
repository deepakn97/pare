"""Tests for the pas benchmark run command."""

from __future__ import annotations

import tempfile
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from pare.cli.benchmark import app, parse_scenarios_arg
from pare.cli.utils import resolve_model_config
from pare.scenarios.validation_result import PAREMultiScenarioValidationResult

if TYPE_CHECKING:
    from pathlib import Path

    from pare.scenarios.config import MultiScenarioRunnerConfig

runner = CliRunner()


def _mock_run_with_scenarios(
    config: MultiScenarioRunnerConfig, scenarios_iterator: object
) -> PAREMultiScenarioValidationResult:
    """Return an empty but valid result from MultiScenarioRunner."""
    return PAREMultiScenarioValidationResult(run_config=config)


def _invoke_run(args: list[str]) -> object:
    """Invoke the run command with standard boundary mocks."""
    with (
        patch("pare.cli.benchmark.probe_llm_endpoint"),
        patch(
            "pare.multi_scenario_runner.MultiScenarioRunner.run_with_scenarios",
            side_effect=_mock_run_with_scenarios,
        ),
        tempfile.TemporaryDirectory() as tmpdir,
    ):
        return runner.invoke(app, ["run", "--results-dir", tmpdir, *args])


# --- Validation tests ---


def test_run_requires_split_or_scenarios() -> None:
    """Run should fail if neither --split nor --scenarios is provided."""
    result = runner.invoke(app, ["run"])
    assert result.exit_code != 0


def test_run_rejects_both_split_and_scenarios() -> None:
    """Should fail if both --split and --scenarios are provided."""
    result = runner.invoke(
        app,
        ["run", "--split", "full", "--scenarios", "email_notification"],
    )
    assert result.exit_code != 0


def test_run_rejects_invalid_executor_type() -> None:
    """Should reject invalid executor type values."""
    result = runner.invoke(
        app,
        ["run", "--split", "full", "--executor-type", "invalid"],
    )
    assert result.exit_code != 0


def test_run_rejects_invalid_export_format() -> None:
    """Should reject invalid export format values."""
    result = runner.invoke(
        app,
        ["run", "--split", "full", "--export-format", "invalid"],
    )
    assert result.exit_code != 0


# --- Config construction tests ---


def test_run_constructs_engine_config_with_endpoint() -> None:
    """Endpoint, provider, and model_name should flow through to LLMEngineConfig."""
    with (
        patch("pare.cli.benchmark.probe_llm_endpoint"),
        patch(
            "pare.multi_scenario_runner.MultiScenarioRunner.run_with_scenarios",
            side_effect=_mock_run_with_scenarios,
        ) as mock_runner,
        tempfile.TemporaryDirectory() as tmpdir,
    ):
        result = runner.invoke(
            app,
            [
                "run",
                "--split", "full",
                "--results-dir", tmpdir,
                "--observe-model", "liquid/lfm2.5-350m",
                "--observe-provider", "hosted_vllm",
                "--observe-endpoint", "http://localhost:8001/v1",
                "--execute-model", "google/gemma-4-26b-a4b-it",
                "--execute-provider", "hosted_vllm",
                "--execute-endpoint", "http://localhost:8002/v1",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        config = mock_runner.call_args[0][0]
        assert config.observe_engine_config.endpoint == "http://localhost:8001/v1"
        assert config.observe_engine_config.provider == "hosted_vllm"
        assert config.observe_engine_config.model_name == "liquid/lfm2.5-350m"
        assert config.execute_engine_config.endpoint == "http://localhost:8002/v1"
        assert config.execute_engine_config.provider == "hosted_vllm"
        assert config.execute_engine_config.model_name == "google/gemma-4-26b-a4b-it"


def test_run_passes_tool_failure_probability() -> None:
    """Tool failure probability should flow through to config."""
    with (
        patch("pare.cli.benchmark.probe_llm_endpoint"),
        patch(
            "pare.multi_scenario_runner.MultiScenarioRunner.run_with_scenarios",
            side_effect=_mock_run_with_scenarios,
        ) as mock_runner,
        tempfile.TemporaryDirectory() as tmpdir,
    ):
        result = runner.invoke(
            app,
            ["run", "--split", "full", "--results-dir", tmpdir, "--tool-failure-probability", "0.5"],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        config = mock_runner.call_args[0][0]
        assert config.tool_augmentation_config is not None
        assert config.tool_augmentation_config.tool_failure_probability == 0.5


def test_run_passes_env_events_config() -> None:
    """Env events config should flow through to config."""
    with (
        patch("pare.cli.benchmark.probe_llm_endpoint"),
        patch(
            "pare.multi_scenario_runner.MultiScenarioRunner.run_with_scenarios",
            side_effect=_mock_run_with_scenarios,
        ) as mock_runner,
        tempfile.TemporaryDirectory() as tmpdir,
    ):
        result = runner.invoke(
            app,
            [
                "run", "--split", "full", "--results-dir", tmpdir,
                "--env-events-per-min", "3", "--env-events-seed", "99",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        config = mock_runner.call_args[0][0]
        assert config.env_events_config is not None
        assert config.env_events_config.num_env_events_per_minute == 3
        assert config.env_events_config.env_events_seed == 99


def test_run_no_noise_config_by_default() -> None:
    """Noise configs should be None when not specified."""
    with (
        patch("pare.cli.benchmark.probe_llm_endpoint"),
        patch(
            "pare.multi_scenario_runner.MultiScenarioRunner.run_with_scenarios",
            side_effect=_mock_run_with_scenarios,
        ) as mock_runner,
        tempfile.TemporaryDirectory() as tmpdir,
    ):
        result = runner.invoke(app, ["run", "--split", "full", "--results-dir", tmpdir])

        assert result.exit_code == 0, f"Command failed: {result.output}"
        config = mock_runner.call_args[0][0]
        assert config.tool_augmentation_config is None
        assert config.env_events_config is None


# --- Scenario selection tests ---


def test_run_with_scenarios_flag() -> None:
    """Should accept --scenarios and set split_name to custom."""
    result = _invoke_run(["--scenarios", "email_notification,cab_booking"])
    assert result.exit_code == 0, f"Command failed: {result.output}"


# --- Helper function unit tests ---


def test_parse_scenarios_arg_comma_separated() -> None:
    """Should parse comma-separated scenario IDs."""
    result = parse_scenarios_arg("email_notification,cab_booking,reminder_set")
    assert result == ["email_notification", "cab_booking", "reminder_set"]


def test_parse_scenarios_arg_single_id() -> None:
    """Should handle a single scenario ID."""
    result = parse_scenarios_arg("email_notification")
    assert result == ["email_notification"]


def test_parse_scenarios_arg_file_path(tmp_path: Path) -> None:
    """Should load scenario IDs from a file."""
    scenario_file = tmp_path / "scenarios.txt"
    scenario_file.write_text("email_notification\ncab_booking\n")
    result = parse_scenarios_arg(str(scenario_file))
    assert "email_notification" in result
    assert "cab_booking" in result


# --- resolve_model_config unit tests ---


def test_resolve_model_config_models_map_entry() -> None:
    """Should use MODELS_MAP values when model matches a known alias."""
    config, alias = resolve_model_config("gpt-5", None, None)
    assert config.model_name == "gpt-5"
    assert config.provider == "openai"
    assert config.endpoint is None
    assert alias == "gpt-5"


def test_resolve_model_config_models_map_with_cli_override() -> None:
    """CLI provider/endpoint should override MODELS_MAP values."""
    config, alias = resolve_model_config("gpt-5", "custom-provider", "http://localhost:9999/v1")
    assert config.model_name == "gpt-5"
    assert config.provider == "custom-provider"
    assert config.endpoint == "http://localhost:9999/v1"
    assert alias == "gpt-5"


def test_resolve_model_config_unknown_model_with_provider() -> None:
    """Should use raw values for unknown models with explicit provider."""
    config, alias = resolve_model_config("org/team/custom-model", "hosted_vllm", "http://localhost:8001/v1")
    assert config.model_name == "org/team/custom-model"
    assert config.provider == "hosted_vllm"
    assert config.endpoint == "http://localhost:8001/v1"
    assert alias == "custom-model"


def test_resolve_model_config_requires_provider_for_unknown_models() -> None:
    """Should raise ValueError if model not in MODELS_MAP and no provider specified."""
    with pytest.raises(ValueError, match="Provider is required"):
        resolve_model_config("unknown/model", None, None)


def test_resolve_model_config_alias_no_slash() -> None:
    """Alias for models without slashes should be the full model name."""
    _config, alias = resolve_model_config("simple-model", "openai", None)
    assert alias == "simple-model"


def test_resolve_model_config_alias_multiple_slashes() -> None:
    """Alias should use last segment after final slash."""
    _config, alias = resolve_model_config("accounts/fireworks/models/deepseek-v3p2", "fireworks_ai", None)
    assert alias == "deepseek-v3p2"


def test_resolve_model_config_fireworks_via_models_map() -> None:
    """Fireworks models in MODELS_MAP should resolve correctly."""
    config, alias = resolve_model_config("deepseek-v3.2", None, None)
    assert config.model_name == "accounts/fireworks/models/deepseek-v3p2"
    assert config.provider == "fireworks_ai"
    assert alias == "deepseek-v3.2"


# --- Config file tests ---


def test_run_with_yaml_config_file(tmp_path: Path) -> None:
    """Should load parameters from a YAML config file."""
    config_yaml = """\
observe_model: "liquid/lfm2.5-350m"
observe_provider: "hosted_vllm"
observe_endpoint: "http://localhost:8001/v1"
execute_model: "google/gemma-4-26b-a4b-it"
execute_provider: "hosted_vllm"
execute_endpoint: "http://localhost:8002/v1"
user_model: "gpt-5-mini"
user_provider: "openai"
user_endpoint: "http://localhost:8003/v1"
split: "full"
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_yaml)
    results_dir = tmp_path / "results"

    with (
        patch("pare.cli.benchmark.probe_llm_endpoint"),
        patch(
            "pare.multi_scenario_runner.MultiScenarioRunner.run_with_scenarios",
            side_effect=_mock_run_with_scenarios,
        ) as mock_runner,
    ):
        result = runner.invoke(
            app, ["run", "--results-dir", str(results_dir), "--config", str(config_file)]
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        config = mock_runner.call_args[0][0]
        assert config.observe_engine_config.model_name == "liquid/lfm2.5-350m"
        assert config.observe_engine_config.provider == "hosted_vllm"
        assert config.observe_engine_config.endpoint == "http://localhost:8001/v1"
        assert config.execute_engine_config.model_name == "google/gemma-4-26b-a4b-it"
        assert config.execute_engine_config.provider == "hosted_vllm"
        assert config.execute_engine_config.endpoint == "http://localhost:8002/v1"
        assert config.user_engine_config.model_name == "gpt-5-mini"
        assert config.user_engine_config.provider == "openai"
        assert config.user_engine_config.endpoint == "http://localhost:8003/v1"


def test_cli_flags_override_config_file(tmp_path: Path) -> None:
    """CLI flags should take precedence over config file values."""
    config_yaml = """\
observe_model: "original-model"
observe_provider: "original-provider"
split: "full"
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_yaml)
    results_dir = tmp_path / "results"

    with (
        patch("pare.cli.benchmark.probe_llm_endpoint"),
        patch(
            "pare.multi_scenario_runner.MultiScenarioRunner.run_with_scenarios",
            side_effect=_mock_run_with_scenarios,
        ) as mock_runner,
    ):
        result = runner.invoke(
            app,
            [
                "run", "--results-dir", str(results_dir),
                "--config", str(config_file),
                "--observe-model", "override-model",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        config = mock_runner.call_args[0][0]
        # Overridden value
        assert config.observe_engine_config.model_name == "override-model"
        # Non-overridden value should remain from config file
        assert config.observe_engine_config.provider == "original-provider"


# --- Sweep removal test ---


def test_sweep_command_removed() -> None:
    """The sweep command should no longer exist."""
    result = runner.invoke(app, ["sweep", "--help"])
    assert result.exit_code != 0
