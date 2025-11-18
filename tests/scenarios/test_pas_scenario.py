"""Tests for PASScenario base class."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from are.simulation.scenarios.utils.scenario_expander import EnvEventsConfig
from are.simulation.types import ToolAugmentationConfig

from pas.scenarios import PASScenario
from pas.scenarios.utils.scenario_expander import default_weight_per_app_class


class TestPASScenarioApplyAugmentationConfigs:
    """Tests for PASScenario.apply_augmentation_configs method."""

    def test_sets_failure_probability_on_apps(self) -> None:
        """Should set failure probability on all apps."""

        class TestScenario(PASScenario):
            def init_and_populate_apps(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
                self.apps = [MagicMock(), MagicMock()]

            def build_events_flow(self) -> None:
                pass

        scenario = TestScenario()
        scenario.tool_augmentation_config = ToolAugmentationConfig(
            tool_failure_probability=0.3,
            apply_tool_name_augmentation=False,
            apply_tool_description_augmentation=False,
        )

        scenario.init_and_populate_apps()
        scenario.apply_augmentation_configs()

        # Verify set_failure_probability called on each app
        for app in scenario.apps:
            app.set_failure_probability.assert_called_once_with(0.3)

    def test_does_nothing_without_config(self) -> None:
        """Should not fail if tool_augmentation_config is None."""

        class TestScenario(PASScenario):
            def init_and_populate_apps(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
                self.apps = [MagicMock()]

            def build_events_flow(self) -> None:
                pass

        scenario = TestScenario()
        scenario.tool_augmentation_config = None

        scenario.init_and_populate_apps()
        # Should not raise
        scenario.apply_augmentation_configs()

        # set_failure_probability should not be called
        scenario.apps[0].set_failure_probability.assert_not_called()


class TestPASScenarioInitialize:
    """Tests for PASScenario.initialize method."""

    def test_calls_init_and_populate_apps(self) -> None:
        """Should call init_and_populate_apps during initialization."""

        class TestScenario(PASScenario):
            init_called = False

            def init_and_populate_apps(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
                self.init_called = True
                self.apps = []

            def build_events_flow(self) -> None:
                pass

        scenario = TestScenario()
        scenario.initialize()

        assert scenario.init_called

    def test_calls_build_events_flow(self) -> None:
        """Should call build_events_flow during initialization."""

        class TestScenario(PASScenario):
            build_called = False

            def init_and_populate_apps(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
                self.apps = []

            def build_events_flow(self) -> None:
                self.build_called = True

        scenario = TestScenario()
        scenario.initialize()

        assert scenario.build_called

    def test_calls_apply_augmentation_configs(self) -> None:
        """Should call apply_augmentation_configs during initialization."""

        class TestScenario(PASScenario):
            def init_and_populate_apps(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
                mock_app = MagicMock()
                mock_app.name = "TestApp"
                mock_app.get_state.return_value = {}  # Return JSON-serializable state
                self.apps = [mock_app]

            def build_events_flow(self) -> None:
                pass

        scenario = TestScenario()
        scenario.tool_augmentation_config = ToolAugmentationConfig(
            tool_failure_probability=0.5,
            apply_tool_name_augmentation=False,
            apply_tool_description_augmentation=False,
        )

        scenario.initialize()

        # Verify failure probability was set
        scenario.apps[0].set_failure_probability.assert_called_once_with(0.5)

    def test_uses_pas_env_events_expander_when_config_set(self) -> None:
        """Should use PASEnvEventsExpander when env_events_config is set."""

        class TestScenario(PASScenario):
            def init_and_populate_apps(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
                self.apps = []

            def build_events_flow(self) -> None:
                pass

        scenario = TestScenario()
        scenario.env_events_config = EnvEventsConfig(
            num_env_events_per_minute=2.0,
            env_events_seed=42,
            weight_per_app_class=default_weight_per_app_class(),
        )

        with patch("pas.scenarios.scenario.PASEnvEventsExpander") as mock_expander_class:
            mock_expander = MagicMock()
            mock_expander_class.return_value = mock_expander

            # Mock augmentation data file
            with patch("builtins.open", create=True) as mock_open:
                import json

                mock_file = MagicMock()
                mock_file.__enter__.return_value.read.return_value = json.dumps({"apps": []})
                mock_open.return_value = mock_file

                with patch.object(Path, "exists", return_value=True):
                    scenario.initialize()

            # Verify PASEnvEventsExpander was instantiated and called
            mock_expander_class.assert_called_once()
            mock_expander.add_env_events_to_scenario.assert_called_once()

    def test_raises_error_when_augmentation_file_missing(self) -> None:
        """Should raise ValueError if augmentation file doesn't exist."""

        class TestScenario(PASScenario):
            def init_and_populate_apps(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
                self.apps = []

            def build_events_flow(self) -> None:
                pass

        scenario = TestScenario()
        scenario.env_events_config = EnvEventsConfig(
            num_env_events_per_minute=2.0,
            env_events_seed=42,
            weight_per_app_class=default_weight_per_app_class(),
        )

        with patch.object(Path, "exists", return_value=False):
            with pytest.raises(ValueError, match="ENV_AUGMENTATION_DATA_PATH"):
                scenario.initialize()

    def test_skips_env_events_when_no_config(self) -> None:
        """Should not add env events when env_events_config is None."""

        class TestScenario(PASScenario):
            def init_and_populate_apps(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
                self.apps = []

            def build_events_flow(self) -> None:
                pass

        scenario = TestScenario()
        scenario.env_events_config = None

        with patch("pas.scenarios.scenario.PASEnvEventsExpander") as mock_expander_class:
            scenario.initialize()

            # PASEnvEventsExpander should not be instantiated
            mock_expander_class.assert_not_called()

    def test_sets_initialized_flag(self) -> None:
        """Should set _initialized to True after initialization."""

        class TestScenario(PASScenario):
            def init_and_populate_apps(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
                self.apps = []

            def build_events_flow(self) -> None:
                pass

        scenario = TestScenario()
        scenario.initialize()

        assert scenario._initialized is True

    def test_does_not_reinitialize(self) -> None:
        """Should not reinitialize if already initialized."""

        class TestScenario(PASScenario):
            init_count = 0

            def init_and_populate_apps(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
                self.init_count += 1
                self.apps = []

            def build_events_flow(self) -> None:
                pass

        scenario = TestScenario()
        scenario.initialize()
        scenario.initialize()  # Second call

        assert scenario.init_count == 1

    def test_sets_seed_on_apps(self) -> None:
        """Should set seed on all apps during initialization."""

        class TestScenario(PASScenario):
            def init_and_populate_apps(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
                mock_app1 = MagicMock()
                mock_app1.name = "App1"
                mock_app1.get_state.return_value = {}
                mock_app2 = MagicMock()
                mock_app2.name = "App2"
                mock_app2.get_state.return_value = {}
                self.apps = [mock_app1, mock_app2]

            def build_events_flow(self) -> None:
                pass

        scenario = TestScenario()
        scenario.seed = 123
        scenario.initialize()

        for app in scenario.apps:
            app.set_seed.assert_called_once_with(123)
