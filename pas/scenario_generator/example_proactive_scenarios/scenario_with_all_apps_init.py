"""Proactive variants of the tutorial scenario.

Contains:
- ScenarioTutorialProactiveConfirm
- ScenarioTutorialProactiveReject
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# Core framework imports
from are.simulation.apps.agent_user_interface import AgentUserInterface

# Lifestyle and service apps
from are.simulation.apps.apartment_listing import ApartmentListingApp, RentAFlat
from are.simulation.apps.cab import CabApp

# Organization and productivity apps
from are.simulation.apps.calendar import Calendar, CalendarApp
from are.simulation.apps.city import CityApp
from are.simulation.apps.contacts import ContactsApp, InternalContacts

# Communication apps
from are.simulation.apps.email_client import EmailClientApp, EmailClientV2
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.messaging_v2 import MessagingAppV2
from are.simulation.apps.reminder import ReminderApp

# File and storage apps
from are.simulation.apps.sandbox_file_system import Files, SandboxLocalFileSystem
from are.simulation.apps.shopping import Shopping, ShoppingApp
from are.simulation.apps.system import SystemApp
from are.simulation.apps.virtual_file_system import VirtualFileSystem

if TYPE_CHECKING:
    from are.simulation.types import AbstractEnvironment
from are.simulation.data.population_scripts.sandbox_file_system_population import default_fs_folders
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario


@register_scenario("scenario_with_all_apps_init")
class ScenarioWithAllAppsInit(Scenario):
    """Scenario with ALL applications from the ARE framework initialized.

    This scenario initializes every available application from the ARE framework,
    providing access to the complete set of tools and functionality. It serves as
    a comprehensive example of how to set up all apps for complex scenarios.

    Initialized apps include:
    - Core: AgentUserInterface, SystemApp
    - Communication: EmailClientApp, EmailClientV2, MessagingApp, MessagingAppV2
    - Organization: CalendarApp, Calendar, ContactsApp, InternalContacts, ReminderApp
    - File Management: SandboxLocalFileSystem, VirtualFileSystem, Files
    - Lifestyle: ApartmentListingApp, RentAFlat, ShoppingApp, Shopping, CabApp, CityApp
    """

    start_time: float | None = 0
    duration: float | None = 20

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate applications with data."""
        # =============================================================================
        # CORE FRAMEWORK APPS
        # =============================================================================
        agui = AgentUserInterface()  # User interface for the agent
        system = SystemApp()  # System application

        # =============================================================================
        # COMMUNICATION APPS
        # =============================================================================
        email_client = EmailClientApp()  # Email client application
        email_client_v2 = EmailClientV2()  # Enhanced email client
        messaging = MessagingApp()  # Messaging application
        messaging_v2 = MessagingAppV2()  # Enhanced messaging application

        # =============================================================================
        # ORGANIZATION AND PRODUCTIVITY APPS
        # =============================================================================
        calendar = CalendarApp()  # Calendar application
        calendar_base = Calendar()  # Base calendar functionality
        contacts = ContactsApp()  # Contacts application
        internal_contacts = InternalContacts()  # Internal contacts
        reminder = ReminderApp()  # Reminder application

        # =============================================================================
        # FILE AND STORAGE APPS
        # =============================================================================
        fs = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))  # File system application
        virtual_fs = VirtualFileSystem()  # Virtual file system
        files = Files()  # File management

        # =============================================================================
        # LIFESTYLE AND SERVICE APPS
        # =============================================================================
        apartment_listing = ApartmentListingApp()  # Apartment listing application
        rent_a_flat = RentAFlat()  # Rental service
        shopping = ShoppingApp()  # Shopping application
        shopping_base = Shopping()  # Base shopping functionality
        cab = CabApp()  # Cab/ride service
        city = CityApp()  # City information and services

        # Set up default folders in the file system
        default_fs_folders(fs)

        # =============================================================================
        # REGISTER ALL INITIALIZED APPLICATIONS
        # =============================================================================
        self.apps = [
            # Core framework apps
            agui,
            system,
            # Communication apps
            email_client,
            messaging,
            # Organization and productivity apps
            calendar,
            contacts,
            internal_contacts,
            reminder,
            # File and storage apps
            fs,
            virtual_fs,
            files,
            # Lifestyle and service apps
            apartment_listing,
            rent_a_flat,
            shopping,
            shopping_base,
            cab,
            city,
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
            expected_app_count = 20
            actual_app_count = len(self.apps)

            if actual_app_count != expected_app_count:
                return ScenarioValidationResult(
                    success=False, exception=ValueError(f"Expected {expected_app_count} apps, got {actual_app_count}")
                )

            # Check that all required app types are present
            app_types = {app.__class__.__name__ for app in self.apps}
            required_apps = {
                "AgentUserInterface",
                "SystemApp",
                "EmailClientApp",
                "EmailClientV2",
                "MessagingApp",
                "MessagingAppV2",
                "CalendarApp",
                "Calendar",
                "ContactsApp",
                "InternalContacts",
                "ReminderApp",
                "SandboxLocalFileSystem",
                "VirtualFileSystem",
                "ApartmentListingApp",
                "RentAFlat",
                "ShoppingApp",
                "Shopping",
                "CabApp",
                "CityApp",
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
