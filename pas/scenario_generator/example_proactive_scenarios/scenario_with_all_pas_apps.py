"""Scenario initializing all PAS apps (stateful wrappers around Meta ARE apps)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# PAS apps
from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
    StatefulContactsApp,
    StatefulEmailApp,
    StatefulMessagingApp,
)

if TYPE_CHECKING:
    from are.simulation.types import AbstractEnvironment
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario


@register_scenario("scenario_with_all_pas_apps")
class ScenarioWithAllPASApps(Scenario):
    """Scenario with ALL PAS applications initialized.

    Initializes all applications defined under pas.apps, which provide stateful,
    navigation-aware wrappers around Meta ARE applications.

    Initialized apps include:
    - Core: PASAgentUserInterface, HomeScreenSystemApp
    - Communication: StatefulEmailApp, StatefulMessagingApp
    - Organization: StatefulCalendarApp, StatefulContactsApp
    """

    start_time: float | None = 0
    duration: float | None = 20

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate applications with data."""
        # =============================================================================
        # PAS APPS
        # =============================================================================
        self.agui = PASAgentUserInterface()  # Proactive agent-user interface
        self.system = HomeScreenSystemApp()  # PAS system app with navigation helpers

        # Communication apps
        self.email = StatefulEmailApp()
        self.messaging = StatefulMessagingApp()

        # Organization and productivity apps
        self.calendar = StatefulCalendarApp()
        self.contacts = StatefulContactsApp()

        # =============================================================================
        # REGISTER ALL INITIALIZED APPLICATIONS
        # =============================================================================
        self.apps = [
            # Core PAS apps
            self.agui,
            self.system,
            # Communication apps
            self.email,
            self.messaging,
            # Organization and productivity apps
            self.calendar,
            self.contacts,
        ]

    def build_events_flow(self) -> None:
        """Build the flow of events for the scenario."""
        # This scenario serves as an initialization example, so no specific events are needed
        # All the work is done in init_and_populate_apps() where all apps are initialized
        self.events: list[Any] = []  # Empty events list since this is just an initialization scenario

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that all applications are properly initialized."""
        try:
            # Check that we have the expected number of apps
            expected_app_count = 6
            actual_app_count = len(self.apps)

            if actual_app_count != expected_app_count:
                return ScenarioValidationResult(
                    success=False, exception=ValueError(f"Expected {expected_app_count} apps, got {actual_app_count}")
                )

            # Check that all required app types are present
            app_types = {app.__class__.__name__ for app in self.apps}
            required_apps = {
                "PASAgentUserInterface",
                "HomeScreenSystemApp",
                "StatefulEmailApp",
                "StatefulMessagingApp",
                "StatefulCalendarApp",
                "StatefulContactsApp",
            }

            missing_apps = required_apps - app_types
            if missing_apps:
                return ScenarioValidationResult(
                    success=False, exception=ValueError(f"Missing required apps: {missing_apps}")
                )

            # Check that we can get tools from all apps
            tools = self.get_tools()
            if not tools:
                return ScenarioValidationResult(
                    success=False, exception=ValueError("No tools available from initialized apps")
                )

            return ScenarioValidationResult(success=True)

        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
