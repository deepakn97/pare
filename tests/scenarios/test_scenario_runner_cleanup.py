"""Tests for guaranteed env.stop() cleanup in TwoAgentScenarioRunner."""

from unittest.mock import MagicMock, patch

from pas.scenario_runner import TwoAgentScenarioRunner


class TestRunPasScenarioCleanup:
    def test_env_stop_called_on_export_exception(self):
        """env.stop() must be called even if trace export throws."""
        runner = TwoAgentScenarioRunner()

        mock_env = MagicMock()
        mock_env.time_manager.time_passed.return_value = 1.0
        mock_env.state = "RUNNING"

        mock_scenario = MagicMock()
        mock_scenario.scenario_id = "test_scenario"
        mock_scenario.start_time = 1000000.0
        mock_scenario.time_increment_in_seconds = 1

        mock_config = MagicMock()
        mock_config.oracle = False
        mock_config.export = True
        mock_config.output_dir = "/tmp/test"  # noqa: S108
        mock_config.trace_dump_format = "hf"
        mock_config.use_custom_logger = False

        # Make _run_with_two_agents succeed but _export_pas_trace raise
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.exception = None

        with (
            patch.object(runner, "_run_with_two_agents", return_value=(mock_result, MagicMock(), MagicMock())),
            patch.object(runner, "_export_pas_trace", side_effect=OSError("Too many open files")),
            patch("pas.scenario_runner.StateAwareEnvironmentWrapper", return_value=mock_env),
        ):
            result = runner._run_pas_scenario(mock_config, mock_scenario)

        mock_env.stop.assert_called_once()
        # The original validation_result should be returned, not destroyed by export error
        assert result.success is True
