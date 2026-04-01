"""Tests for two-phase retry execution in MultiScenarioRunner."""

from __future__ import annotations

import errno
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

from pas.multi_scenario_runner import MultiScenarioRunner
from pas.scenarios.validation_result import PASScenarioValidationResult

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pas.scenarios.scenario import PASScenario


def _make_scenario(scenario_id: str, run_number: int | None = None) -> MagicMock:
    """Create a mock PASScenario."""
    s = MagicMock()
    s.scenario_id = scenario_id
    s.run_number = run_number
    s._initialized = True
    s.nb_turns = None
    return s


def _make_config(max_concurrent: int = 2) -> MagicMock:
    """Create a minimal MultiScenarioRunnerConfig mock."""
    config = MagicMock()
    config.output_dir = "/tmp/test"  # noqa: S108
    config.max_concurrent_scenarios = max_concurrent
    config.timeout_seconds = None
    config.executor_type = "thread"
    config.log_level = "WARNING"
    config.log_to_file = False
    config.enable_caching = False
    config.experiment_name = "test"
    config.user_model_alias = "test-user"
    config.observe_model_alias = "test-observe"
    config.execute_model_alias = "test-execute"
    config.max_turns = 10
    config.tool_augmentation_config = None
    config.env_events_config = None
    return config


class TestRetryExecution:
    """Tests for two-phase retry execution in MultiScenarioRunner."""

    def test_retryable_error_triggers_phase2(self) -> None:
        """Scenario with EMFILE error in phase 1 should be retried in phase 2."""
        scenario = _make_scenario("test_retry")
        emfile_result = PASScenarioValidationResult(
            success=False,
            exception=OSError(errno.EMFILE, "Too many open files"),
        )
        success_result = PASScenarioValidationResult(success=True)

        call_count = 0
        scenarios_per_phase: list[list[MagicMock]] = []

        def mock_stream_pool(
            scenarios: Iterator[PASScenario], process_func: Any, max_workers: int, **kwargs: Any  # noqa: ANN401
        ) -> MagicMock:
            nonlocal call_count
            call_count += 1
            scenario_list = list(scenarios)
            scenarios_per_phase.append(scenario_list)

            ctx = MagicMock()
            if call_count == 1:
                ctx.__enter__ = MagicMock(return_value=iter([(scenario, emfile_result, None)]))
            else:
                ctx.__enter__ = MagicMock(return_value=iter([(scenario, success_result, None)]))
            ctx.__exit__ = MagicMock(return_value=False)
            return ctx

        runner = MultiScenarioRunner()

        with (
            patch("pas.multi_scenario_runner.stream_pool", side_effect=mock_stream_pool),
            patch("pas.multi_scenario_runner.gc.collect") as mock_gc,
        ):
            config = _make_config()
            scenarios_iter = [scenario]
            result = runner.run_with_scenarios(config, scenarios_iter)

        assert call_count == 2  # phase 1 + phase 2
        mock_gc.assert_called_once()
        assert result.successful_count == 1
        assert result.failed_count == 0
        # Verify the right scenarios were passed to each phase
        assert len(scenarios_per_phase[0]) == 1  # phase 1: original scenario
        assert scenarios_per_phase[0][0].scenario_id == "test_retry"
        assert len(scenarios_per_phase[1]) == 1  # phase 2: retried scenario
        assert scenarios_per_phase[1][0].scenario_id == "test_retry"

    def test_non_retryable_error_not_retried(self) -> None:
        """Scenario with TypeError should NOT be retried."""
        scenario = _make_scenario("test_no_retry")
        type_error_result = PASScenarioValidationResult(
            success=False,
            exception=TypeError("bad type"),
        )

        call_count = 0

        def mock_stream_pool(
            scenarios: Iterator[PASScenario], process_func: Any, max_workers: int, **kwargs: Any  # noqa: ANN401
        ) -> MagicMock:
            nonlocal call_count
            call_count += 1

            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=iter([(scenario, type_error_result, None)]))
            ctx.__exit__ = MagicMock(return_value=False)
            return ctx

        runner = MultiScenarioRunner()

        with patch("pas.multi_scenario_runner.stream_pool", side_effect=mock_stream_pool):
            config = _make_config()
            scenarios_iter = [scenario]
            result = runner.run_with_scenarios(config, scenarios_iter)

        assert call_count == 1  # only phase 1, no retry
        assert result.failed_count == 1

    def test_retry_budget_exhausted_after_max_retries(self) -> None:
        """Scenario should finalize as failed after exhausting retry budget."""
        scenario = _make_scenario("test_budget")
        emfile_result = PASScenarioValidationResult(
            success=False,
            exception=OSError(errno.EMFILE, "Too many open files"),
        )

        call_count = 0
        scenarios_per_phase: list[list[MagicMock]] = []

        def mock_stream_pool(
            scenarios: Iterator[PASScenario], process_func: Any, max_workers: int, **kwargs: Any  # noqa: ANN401
        ) -> MagicMock:
            nonlocal call_count
            call_count += 1
            scenarios_per_phase.append(list(scenarios))

            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=iter([(scenario, emfile_result, None)]))
            ctx.__exit__ = MagicMock(return_value=False)
            return ctx

        runner = MultiScenarioRunner()

        with (
            patch("pas.multi_scenario_runner.stream_pool", side_effect=mock_stream_pool),
            patch("pas.multi_scenario_runner.gc.collect"),
        ):
            config = _make_config()
            scenarios_iter = [scenario]
            result = runner.run_with_scenarios(config, scenarios_iter)

        assert call_count == 3  # phase 1 + phase 2 + phase 3
        assert result.failed_count == 1  # finalized as failed
        # Each phase received exactly the one scenario
        for phase_scenarios in scenarios_per_phase:
            assert len(phase_scenarios) == 1
            assert phase_scenarios[0].scenario_id == "test_budget"

    def test_phase2_uses_half_workers(self) -> None:
        """Phase 2 should use max(1, original_workers // 2)."""
        scenario = _make_scenario("test_workers")
        emfile_result = PASScenarioValidationResult(
            success=False,
            exception=OSError(errno.EMFILE, "Too many open files"),
        )
        success_result = PASScenarioValidationResult(success=True)

        call_count = 0
        workers_per_call: list[int] = []

        def mock_stream_pool(
            scenarios: Iterator[PASScenario], process_func: Any, max_workers: int, **kwargs: Any  # noqa: ANN401
        ) -> MagicMock:
            nonlocal call_count
            call_count += 1
            workers_per_call.append(max_workers)
            list(scenarios)  # consume iterator

            ctx = MagicMock()
            if call_count == 1:
                ctx.__enter__ = MagicMock(return_value=iter([(scenario, emfile_result, None)]))
            else:
                ctx.__enter__ = MagicMock(return_value=iter([(scenario, success_result, None)]))
            ctx.__exit__ = MagicMock(return_value=False)
            return ctx

        runner = MultiScenarioRunner()

        with (
            patch("pas.multi_scenario_runner.stream_pool", side_effect=mock_stream_pool),
            patch("pas.multi_scenario_runner.gc.collect"),
        ):
            config = _make_config(max_concurrent=10)
            scenarios_iter = [scenario]
            runner.run_with_scenarios(config, scenarios_iter)

        assert workers_per_call[0] == 10  # phase 1: full workers
        assert workers_per_call[1] == 5  # phase 2: half workers

    def test_run_number_scenarios_have_independent_retry_budgets(self) -> None:
        """Different run_numbers of the same scenario should have independent retry budgets."""
        run1 = _make_scenario("test_multi_run", run_number=1)
        run2 = _make_scenario("test_multi_run", run_number=2)

        emfile_result = PASScenarioValidationResult(
            success=False,
            exception=OSError(errno.EMFILE, "Too many open files"),
        )
        success_result = PASScenarioValidationResult(success=True)

        call_count = 0
        scenarios_per_phase: list[list[MagicMock]] = []

        def mock_stream_pool(
            scenarios: Iterator[PASScenario], process_func: Any, max_workers: int, **kwargs: Any  # noqa: ANN401
        ) -> MagicMock:
            nonlocal call_count
            call_count += 1
            scenario_list = list(scenarios)
            scenarios_per_phase.append(scenario_list)

            # Build results based on which scenarios are in this phase
            results = []
            for s in scenario_list:
                if call_count == 1:
                    # Phase 1: all fail
                    results.append((s, emfile_result, None))
                elif s.run_number == 1:
                    # Phase 2+: run1 succeeds
                    results.append((s, success_result, None))
                else:
                    # Phase 2+: run2 keeps failing
                    results.append((s, emfile_result, None))

            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=iter(results))
            ctx.__exit__ = MagicMock(return_value=False)
            return ctx

        runner = MultiScenarioRunner()

        with (
            patch("pas.multi_scenario_runner.stream_pool", side_effect=mock_stream_pool),
            patch("pas.multi_scenario_runner.gc.collect"),
        ):
            config = _make_config()
            scenarios_iter = [run1, run2]
            result = runner.run_with_scenarios(config, scenarios_iter)

        assert call_count == 3  # phase 1 + phase 2 + phase 3

        # Phase 1: both scenarios
        assert len(scenarios_per_phase[0]) == 2
        phase1_ids = {(s.scenario_id, s.run_number) for s in scenarios_per_phase[0]}
        assert phase1_ids == {("test_multi_run", 1), ("test_multi_run", 2)}

        # Phase 2: both retried (both failed in phase 1)
        assert len(scenarios_per_phase[1]) == 2
        phase2_ids = {(s.scenario_id, s.run_number) for s in scenarios_per_phase[1]}
        assert phase2_ids == {("test_multi_run", 1), ("test_multi_run", 2)}

        # Phase 3: only run2 (run1 succeeded in phase 2)
        assert len(scenarios_per_phase[2]) == 1
        assert scenarios_per_phase[2][0].run_number == 2

        # Final results
        assert result.successful_count == 1  # run1 succeeded in phase 2
        assert result.failed_count == 1  # run2 exhausted budget
