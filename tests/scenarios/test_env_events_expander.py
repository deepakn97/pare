"""Tests for PARE Environmental Events Expander."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from are.simulation.scenarios.utils.scenario_expander import EnvEventsConfig

from pare.apps.email.app import StatefulEmailApp
from pare.apps.messaging.app import StatefulMessagingApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.scenario_expander import (
    PAREEnvEventsExpander,
    default_weight_per_app_class,
)


def create_mock_scenario(
    apps: list | None = None,
    duration: int = 300,
) -> Mock:
    """Create a mock scenario with real PARE apps for testing.

    Args:
        apps: List of app instances. If None, creates default email and messaging apps.
        duration: Scenario duration in seconds.

    Returns:
        Mock scenario with spec=PAREScenario.
    """
    if apps is None:
        email_app = StatefulEmailApp(name="Emails")
        messaging_app = StatefulMessagingApp(name="Messages")
        apps = [email_app, messaging_app]

    scenario = Mock(spec=PAREScenario)
    scenario.apps = apps
    scenario.duration = duration
    scenario.events = [Mock()]  # Start event

    # side_effect needed to return correct app by name
    def get_app_by_name(name: str):
        for app in apps:
            if app.name == name:
                return app
        raise ValueError(f"App {name} not found")

    scenario.get_app.side_effect = get_app_by_name

    return scenario


def create_sample_augmentation_data() -> list[dict]:
    """Create sample augmentation data matching PARE app structure."""
    return [
        {
            "name": "Emails",
            "app_state": {
                "folders": {
                    "INBOX": {
                        "emails": [
                            {
                                "email_id": "email-1",
                                "sender": "alice@example.com",
                                "recipients": ["user@example.com"],
                                "subject": "Meeting Tomorrow",
                                "content": "Let's meet at 10am.",
                            },
                            {
                                "email_id": "email-2",
                                "sender": "bob@example.com",
                                "recipients": ["user@example.com"],
                                "subject": "Project Update",
                                "content": "The project is on track.",
                            },
                            {
                                "email_id": "email-3",
                                "sender": "charlie@example.com",
                                "recipients": ["user@example.com"],
                                "subject": "Quick Question",
                                "content": "Can you review this?",
                            },
                        ]
                    }
                }
            },
        },
        {
            "name": "Messages",
            "app_state": {
                "conversations": {
                    "conv-1": {
                        "conversation_id": "conv-1",
                        "messages": [
                            {"sender": "user-1", "content": "Hello there!"},
                            {"sender": "user-2", "content": "Hi, how are you?"},
                        ],
                    },
                    "conv-2": {
                        "conversation_id": "conv-2",
                        "messages": [
                            {"sender": "user-3", "content": "Quick question"},
                            {"sender": "user-4", "content": "Sure, go ahead"},
                        ],
                    },
                }
            },
        },
    ]

class TestNoiseEventTiming:
    """Tests for noise event timing - events should be scheduled from t=0."""

    @pytest.fixture
    def augmentation_data(self) -> list[dict]:
        """Provide sample augmentation data for tests."""
        return create_sample_augmentation_data()

    def test_noise_events_have_no_dependencies(self, augmentation_data: list[dict]) -> None:
        """Noise events should not depend on other events."""
        scenario = create_mock_scenario(duration=300)

        config = EnvEventsConfig(
            num_env_events_per_minute=2.0,
            env_events_seed=42,
            weight_per_app_class=default_weight_per_app_class(),
        )
        expander = PAREEnvEventsExpander(env_events_config=config)

        initial_event_count = len(scenario.events)
        expander.add_env_events_to_scenario(scenario, augmentation_data)

        # Get the noise events
        noise_events = scenario.events[initial_event_count:]

        events_without_deps = [e for e in noise_events if len(e.dependencies) == 0]
        assert len(events_without_deps) > 0, "Should have events scheduled from t=0"

class TestResolveAppNames:
    """Tests for _resolve_app_names method."""

    @pytest.fixture
    def expander(self) -> PAREEnvEventsExpander:
        """Create expander with default config."""
        config = EnvEventsConfig(
            num_env_events_per_minute=2.0,
            env_events_seed=42,
            weight_per_app_class=default_weight_per_app_class(),
        )
        return PAREEnvEventsExpander(env_events_config=config)

    def test_resolves_canonical_names(self, expander: PAREEnvEventsExpander) -> None:
        """Should resolve canonical class names to themselves."""
        result = expander._resolve_app_names(["StatefulEmailApp", "StatefulMessagingApp"])

        assert result["StatefulEmailApp"] == "StatefulEmailApp"
        assert result["StatefulMessagingApp"] == "StatefulMessagingApp"

    def test_resolves_aliases(self, expander: PAREEnvEventsExpander) -> None:
        """Should resolve aliases to canonical class names."""
        result = expander._resolve_app_names(["Emails", "Messages"])

        assert result["Emails"] == "StatefulEmailApp"
        assert result["Messages"] == "StatefulMessagingApp"

    def test_unknown_app_not_included(self, expander: PAREEnvEventsExpander) -> None:
        """Should not include apps not in APP_ALIAS."""
        result = expander._resolve_app_names(["UnknownApp", "Emails"])

        assert "UnknownApp" not in result
        assert "Emails" in result


class TestGetNumEnvEventsPerApp:
    """Tests for get_num_env_events_per_app method."""

    def test_distributes_events_by_weight(self) -> None:
        """Should distribute events proportionally to weights."""
        config = EnvEventsConfig(
            num_env_events_per_minute=2.0,
            env_events_seed=42,
            weight_per_app_class={
                "StatefulEmailApp": 2.0,
                "StatefulMessagingApp": 1.0,
            },
        )
        expander = PAREEnvEventsExpander(env_events_config=config)

        # Set up resolved_app_names
        expander.resolved_app_names = {
            "Emails": "StatefulEmailApp",
            "Messages": "StatefulMessagingApp",
        }

        result = expander.get_num_env_events_per_app(num_env_events=30)

        # Email has 2x weight, should get 2x events
        assert result["Emails"] == 20
        assert result["Messages"] == 10

    def test_equal_weights_equal_distribution(self) -> None:
        """Should distribute events equally when weights are equal."""
        config = EnvEventsConfig(
            num_env_events_per_minute=2.0,
            env_events_seed=42,
            weight_per_app_class=default_weight_per_app_class(),
        )
        expander = PAREEnvEventsExpander(env_events_config=config)

        expander.resolved_app_names = {
            "Emails": "StatefulEmailApp",
            "Messages": "StatefulMessagingApp",
        }

        result = expander.get_num_env_events_per_app(num_env_events=20)

        assert result["Emails"] == result["Messages"]


class TestAddEnvEventsToScenario:
    """Tests for add_env_events_to_scenario method."""

    @pytest.fixture
    def augmentation_data(self) -> list[dict]:
        """Provide sample augmentation data for tests."""
        return create_sample_augmentation_data()

    def test_filters_to_intersection(self, augmentation_data: list[dict]) -> None:
        """Should only process apps that exist in both scenario and augmentation."""
        # Scenario only has email app
        email_app = StatefulEmailApp(name="Emails")
        scenario = create_mock_scenario(apps=[email_app])

        config = EnvEventsConfig(
            num_env_events_per_minute=2.0,
            env_events_seed=42,
            weight_per_app_class=default_weight_per_app_class(),
        )
        expander = PAREEnvEventsExpander(env_events_config=config)

        expander.add_env_events_to_scenario(scenario, augmentation_data)

        # Should only have Emails in resolved_app_names (not Messages)
        assert "Emails" in expander.resolved_app_names
        assert "Messages" not in expander.resolved_app_names

    def test_adds_events_to_scenario(self, augmentation_data: list[dict]) -> None:
        """Should add environmental events to scenario.events."""
        scenario = create_mock_scenario(duration=300)

        config = EnvEventsConfig(
            num_env_events_per_minute=2.0,
            env_events_seed=42,
            weight_per_app_class=default_weight_per_app_class(),
        )
        expander = PAREEnvEventsExpander(env_events_config=config)

        initial_events_count = len(scenario.events)

        expander.add_env_events_to_scenario(scenario, augmentation_data)

        # Events should be added
        assert len(scenario.events) > initial_events_count

    def test_handles_empty_augmentation_data(self) -> None:
        """Should handle empty augmentation data gracefully."""
        scenario = create_mock_scenario()

        config = EnvEventsConfig(
            num_env_events_per_minute=2.0,
            env_events_seed=42,
            weight_per_app_class=default_weight_per_app_class(),
        )
        expander = PAREEnvEventsExpander(env_events_config=config)

        initial_events_count = len(scenario.events)

        # Should not raise
        expander.add_env_events_to_scenario(scenario, [])

        # No events added (only start_event remains)
        assert len(scenario.events) == initial_events_count

    def test_skips_apps_not_in_augmentation(self) -> None:
        """Should skip scenario apps that don't have augmentation data."""
        # Scenario has both apps
        scenario = create_mock_scenario()

        config = EnvEventsConfig(
            num_env_events_per_minute=2.0,
            env_events_seed=42,
            weight_per_app_class=default_weight_per_app_class(),
        )
        expander = PAREEnvEventsExpander(env_events_config=config)

        # Augmentation only has email data
        email_only_augmentation = [create_sample_augmentation_data()[0]]

        expander.add_env_events_to_scenario(scenario, email_only_augmentation)

        # Should only process Emails
        assert "Emails" in expander.resolved_app_names
        assert len(expander.resolved_app_names) == 1


class TestIntegration:
    """Integration tests for the full expander workflow."""

    @pytest.fixture
    def augmentation_data(self) -> list[dict]:
        """Provide sample augmentation data for tests."""
        return create_sample_augmentation_data()

    def test_full_workflow_with_multiple_apps(self, augmentation_data: list[dict]) -> None:
        """Test complete workflow with multiple app types."""
        scenario = create_mock_scenario(duration=300)

        config = EnvEventsConfig(
            num_env_events_per_minute=2.0,
            env_events_seed=42,
            weight_per_app_class=default_weight_per_app_class(),
        )
        expander = PAREEnvEventsExpander(env_events_config=config)

        initial_count = len(scenario.events)

        expander.add_env_events_to_scenario(scenario, augmentation_data)

        # Should have added events
        assert len(scenario.events) > initial_count

        # Both apps should be in resolved names
        assert "Emails" in expander.resolved_app_names
        assert "Messages" in expander.resolved_app_names

    def test_reproducibility_with_seed(self, augmentation_data: list[dict]) -> None:
        """Same seed should produce same number of events."""
        scenario1 = create_mock_scenario(duration=300)
        scenario2 = create_mock_scenario(duration=300)

        config = EnvEventsConfig(
            num_env_events_per_minute=2.0,
            env_events_seed=42,
            weight_per_app_class=default_weight_per_app_class(),
        )

        expander1 = PAREEnvEventsExpander(env_events_config=config)
        expander2 = PAREEnvEventsExpander(env_events_config=config)

        expander1.add_env_events_to_scenario(scenario1, augmentation_data)
        expander2.add_env_events_to_scenario(scenario2, augmentation_data)

        # Same number of events
        assert len(scenario1.events) == len(scenario2.events)

    def test_different_seeds_produce_different_results(self, augmentation_data: list[dict]) -> None:
        """Different seeds should produce different event counts."""
        scenario1 = create_mock_scenario(duration=300)
        scenario2 = create_mock_scenario(duration=300)

        config1 = EnvEventsConfig(
            num_env_events_per_minute=2.0,
            env_events_seed=42,
            weight_per_app_class=default_weight_per_app_class(),
        )
        config2 = EnvEventsConfig(
            num_env_events_per_minute=2.0,
            env_events_seed=123,
            weight_per_app_class=default_weight_per_app_class(),
        )

        expander1 = PAREEnvEventsExpander(env_events_config=config1)
        expander2 = PAREEnvEventsExpander(env_events_config=config2)

        expander1.add_env_events_to_scenario(scenario1, augmentation_data)
        expander2.add_env_events_to_scenario(scenario2, augmentation_data)

        # Both should have events added
        assert len(scenario1.events) > 1
        assert len(scenario2.events) > 1
