"""Scenario initializing all PARE apps (stateful wrappers around Meta ARE apps)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario

# PARE apps
from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulCalendarApp,
    StatefulContactsApp,
    StatefulEmailApp,
    StatefulMessagingApp,
)
from pare.apps.apartment import StatefulApartmentApp
from pare.apps.cab import StatefulCabApp
from pare.apps.note import StatefulNotesApp
from pare.apps.reminder import StatefulReminderApp
from pare.apps.shopping import StatefulShoppingApp
from pare.scenarios import PAREScenario

if TYPE_CHECKING:
    from are.simulation.types import AbstractEnvironment


@register_scenario("scenario_with_all_pare_apps")
class ScenarioWithAllPAREApps(PAREScenario):
    """Scenario with ALL PARE applications initialized.

    Initializes all core applications defined under `pare.apps`, which provide
    stateful, navigation-aware wrappers around Meta-ARE applications.

    Initialized apps include:
    - Core: PAREAgentUserInterface, HomeScreenSystemApp
    - Communication: StatefulEmailApp, StatefulMessagingApp
    - Organization: StatefulCalendarApp, StatefulContactsApp
    - Commerce & logistics: StatefulShoppingApp, StatefulCabApp
    - Housing: StatefulApartmentApp
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate applications with data."""
        # =============================================================================
        # PARE APPS
        # =============================================================================
        self.agui = PAREAgentUserInterface()  # Proactive agent-user interface
        self.system = HomeScreenSystemApp(name="System")  # PARE system app with navigation helpers

        # Communication apps
        self.email = StatefulEmailApp(name="Emails")
        self.messaging = StatefulMessagingApp(name="Messages")

        # Organization and productivity apps
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.contacts = StatefulContactsApp(name="Contacts")

        # Commerce, transport, housing, and personal organization apps
        self.shopping = StatefulShoppingApp(name="Shopping")
        self.cab = StatefulCabApp(name="Cab")
        self.apartment = StatefulApartmentApp(name="Apartment")
        self.note = StatefulNotesApp(name="Notes")
        self.reminder = StatefulReminderApp(name="Reminders")

        # =============================================================================
        # REGISTER ALL INITIALIZED APPLICATIONS
        # =============================================================================
        self.apps = [
            # Core PARE apps
            self.agui,
            self.system,
            # Communication apps
            self.email,
            self.messaging,
            # Organization and productivity apps
            self.calendar,
            self.contacts,
            # Commerce & logistics
            self.shopping,
            self.cab,
            # Housing and personal organization
            self.apartment,
            self.note,
            self.reminder,
        ]

    def build_events_flow(self) -> None:
        """Build the flow of events for the scenario."""
        # This scenario serves as an initialization example, so no specific events are needed
        # All the work is done in init_and_populate_apps() where all apps are initialized
        aui = self.get_typed_app(PAREAgentUserInterface)
        email = self.get_typed_app(StatefulEmailApp, "Emails")
        calendar = self.get_typed_app(StatefulCalendarApp, "Calendar")
        messaging = self.get_typed_app(StatefulMessagingApp, "Messages")
        contacts = self.get_typed_app(StatefulContactsApp, "Contacts")

        self.events: list[Any] = []  # Empty events list since this is just an initialization scenario

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that all applications are properly initialized."""
        try:
            # Check that we have the expected number of apps
            # Core (2) + communication (2) + org (2) + shopping + cab + apartment + note + reminder = 11
            expected_app_count = 11
            actual_app_count = len(self.apps)

            if actual_app_count != expected_app_count:
                return ScenarioValidationResult(
                    success=False, exception=ValueError(f"Expected {expected_app_count} apps, got {actual_app_count}")
                )

            # Check that all required app types are present
            app_types = {app.__class__.__name__ for app in self.apps}
            required_apps = {
                "PAREAgentUserInterface",
                "HomeScreenSystemApp",
                "StatefulEmailApp",
                "StatefulMessagingApp",
                "StatefulCalendarApp",
                "StatefulContactsApp",
                "StatefulShoppingApp",
                "StatefulCabApp",
                "StatefulApartmentApp",
                "StatefulNotesApp",
                "StatefulReminderApp",
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
