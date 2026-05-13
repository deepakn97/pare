"""Tests for scenario generator run-check integration."""

from __future__ import annotations

import importlib
import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from pare.scenarios.config import MultiScenarioRunnerConfig
from pare.scenarios.validation_result import (
    PAREMultiScenarioValidationResult,
    PAREScenarioValidationResult,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


MODULE_NAME = "pare.scenarios.generator.agent.scenario_generating_agent_orchestrator"


def _import_orchestrator_module() -> object:
    sys.modules.pop(MODULE_NAME, None)
    return importlib.import_module(MODULE_NAME)


def test_orchestrator_imports_without_run_scenarios_script() -> None:
    """The generator should not depend on the removed scripts.run_scenarios module."""
    module = _import_orchestrator_module()

    assert not hasattr(module, "run_scenarios")


def test_run_step_check_uses_package_multi_scenario_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generated scenario checks should run through the package runner in oracle mode."""
    module = _import_orchestrator_module()
    artifact = tmp_path / "editable_seed_scenario.py"
    artifact.write_text('@register_scenario("generated_case")\nclass Scenario:\n    pass\n', encoding="utf-8")

    run_config: MultiScenarioRunnerConfig | None = None
    scenarios_iterator = object()
    validation_result = PAREMultiScenarioValidationResult(
        run_config=MultiScenarioRunnerConfig(log_to_file=False),
    )
    export_path = tmp_path / "generated_case.json"
    validation_result.add_result(
        PAREScenarioValidationResult(success=True, rationale="validated", export_path=str(export_path)),
        "generated_case",
    )

    def fake_load_scenarios_from_registry(*, scenario_ids: list[str]) -> object:
        assert scenario_ids == ["generated_case"]
        return scenarios_iterator

    class FakeMultiScenarioRunner:
        def run_with_scenarios(
            self,
            config: MultiScenarioRunnerConfig,
            scenarios: object,
            progress_description: str | None = None,
        ) -> PAREMultiScenarioValidationResult:
            nonlocal run_config
            run_config = config
            assert scenarios is scenarios_iterator
            assert progress_description == "Checking generated scenario"
            return validation_result

    monkeypatch.setattr(module, "load_scenarios_from_registry", fake_load_scenarios_from_registry)
    monkeypatch.setattr(module, "MultiScenarioRunner", FakeMultiScenarioRunner)
    monkeypatch.setenv("PARE_SCENARIOS_DIR", "benchmark")

    orchestrator = module.ScenarioGeneratingAgentOrchestrator.__new__(module.ScenarioGeneratingAgentOrchestrator)
    orchestrator._last_check_result = None
    result = orchestrator._run_step_check("step-check", artifact, require_validation_success=True)

    assert run_config is not None
    assert run_config.oracle is True
    assert run_config.max_turns is None
    assert run_config.max_concurrent_scenarios == 1
    assert run_config.executor_type == "thread"
    assert run_config.enable_caching is False
    assert result.passed is True
    assert result.runtime_error is False
    assert result.validation_reached is True
    assert result.validation_success is True
    assert "Rationale: validated" in result.feedback


def test_run_step_check_reports_package_runner_exceptions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime exceptions from package runner execution should remain actionable."""
    module = _import_orchestrator_module()
    artifact = tmp_path / "editable_seed_scenario.py"
    artifact.write_text('@register_scenario("generated_case")\nclass Scenario:\n    pass\n', encoding="utf-8")

    exception = RuntimeError("boom")
    validation_result = PAREMultiScenarioValidationResult(
        run_config=MultiScenarioRunnerConfig(log_to_file=False),
    )
    validation_result.add_result(PAREScenarioValidationResult(success=False, exception=exception), "generated_case")

    monkeypatch.setattr(module, "load_scenarios_from_registry", lambda *, scenario_ids: object())
    fake_runner = MagicMock()
    fake_runner.run_with_scenarios.return_value = validation_result
    monkeypatch.setattr(module, "MultiScenarioRunner", MagicMock(return_value=fake_runner))
    monkeypatch.setenv("PARE_SCENARIOS_DIR", "benchmark")

    orchestrator = module.ScenarioGeneratingAgentOrchestrator.__new__(module.ScenarioGeneratingAgentOrchestrator)
    orchestrator._last_check_result = None
    result = orchestrator._run_step_check("step-check", artifact)

    assert result.passed is False
    assert result.runtime_error is True
    assert result.validation_reached is True
    assert result.validation_success is False
    assert "Exception: boom" in result.feedback
