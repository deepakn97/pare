"""Tests for runtime type hint resolution in state classes.

This test verifies that get_user_tools() and get_tools() work correctly for all apps.
These methods internally use get_type_hints() to build tool schemas, which requires
type annotations to be available at runtime (not just under TYPE_CHECKING blocks).

Related issue: Types like Note, Apartment, Ride, Reminder were originally under TYPE_CHECKING
which caused NameError when get_type_hints() was called during tool registration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulApartmentApp,
    StatefulCabApp,
    StatefulCalendarApp,
    StatefulContactsApp,
    StatefulEmailApp,
    StatefulMessagingApp,
    StatefulNotesApp,
    StatefulReminderApp,
    StatefulShoppingApp,
)
from pas.environment import StateAwareEnvironmentWrapper

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture()
def env_with_all_apps() -> Generator[StateAwareEnvironmentWrapper, None, None]:
    """Provide an environment with all PAS apps registered."""
    env = StateAwareEnvironmentWrapper()

    apps = [
        HomeScreenSystemApp(name="HomeScreen"),
        PASAgentUserInterface(),
        StatefulContactsApp(name="Contacts"),
        StatefulEmailApp(name="Email"),
        StatefulCalendarApp(name="Calendar"),
        StatefulMessagingApp(name="Messaging"),
        StatefulShoppingApp(name="Shopping"),
        StatefulCabApp(name="Cab"),
        StatefulApartmentApp(name="Apartment"),
        StatefulNotesApp(name="Notes"),
        StatefulReminderApp(name="Reminder"),
    ]

    env.register_apps(apps)
    yield env


class TestTypeHintsResolveAtRuntime:
    """Test that get_user_tools() and get_tools() work for all apps.

    These methods use get_type_hints() internally to build tool schemas.
    If type annotations are only under TYPE_CHECKING, get_type_hints() raises NameError.
    """

    def test_get_tools_works_for_all_apps(self, env_with_all_apps: StateAwareEnvironmentWrapper) -> None:
        """Verify get_tools() works without NameError for all registered apps.

        get_tools() calls get_type_hints() internally for each app's tools.
        This test ensures all type annotations resolve at runtime.
        """
        # This should not raise NameError
        tools = env_with_all_apps.get_tools()

        # Verify we got tools from all apps
        tool_names = {tool.name for tool in tools}
        assert len(tool_names) > 0, "Should have at least some tools"

        # Verify tools from apps that had the type hint issue
        apartment_tools = [name for name in tool_names if name.startswith("Apartment__")]
        assert len(apartment_tools) > 0, "Should have Apartment app tools"

        cab_tools = [name for name in tool_names if name.startswith("Cab__")]
        assert len(cab_tools) > 0, "Should have Cab app tools"

        notes_tools = [name for name in tool_names if name.startswith("Notes__")]
        assert len(notes_tools) > 0, "Should have Notes app tools"

        reminder_tools = [name for name in tool_names if name.startswith("Reminder__")]
        assert len(reminder_tools) > 0, "Should have Reminder app tools"

    def test_get_user_tools_works_for_apartment_app(
        self, env_with_all_apps: StateAwareEnvironmentWrapper
    ) -> None:
        """Verify get_user_tools() works when Apartment app is active."""
        system_app = env_with_all_apps.get_app_with_class(HomeScreenSystemApp)
        system_app.open_app("Apartment")

        # This should not raise NameError
        tools = env_with_all_apps.get_user_tools()
        tool_names = {tool.name for tool in tools}

        # Apartment app uses Apartment type in return annotations
        assert "Apartment__list_apartments" in tool_names
        assert "Apartment__view_apartment" in tool_names

    def test_get_user_tools_works_for_cab_app(
        self, env_with_all_apps: StateAwareEnvironmentWrapper
    ) -> None:
        """Verify get_user_tools() works when Cab app is active."""
        system_app = env_with_all_apps.get_app_with_class(HomeScreenSystemApp)
        system_app.open_app("Cab")

        # This should not raise NameError
        tools = env_with_all_apps.get_user_tools()
        tool_names = {tool.name for tool in tools}

        # Cab app uses Ride type in return annotations
        assert "Cab__list_rides" in tool_names
        assert "Cab__open_current_ride" in tool_names

    def test_get_user_tools_works_for_notes_app(
        self, env_with_all_apps: StateAwareEnvironmentWrapper
    ) -> None:
        """Verify get_user_tools() works when Notes app is active."""
        system_app = env_with_all_apps.get_app_with_class(HomeScreenSystemApp)
        system_app.open_app("Notes")

        # This should not raise NameError
        tools = env_with_all_apps.get_user_tools()
        tool_names = {tool.name for tool in tools}

        # Notes app uses Note and ReturnedNotes types in return annotations
        assert "Notes__list_notes" in tool_names
        assert "Notes__open" in tool_names

    def test_get_user_tools_works_for_reminder_app(
        self, env_with_all_apps: StateAwareEnvironmentWrapper
    ) -> None:
        """Verify get_user_tools() works when Reminder app is active."""
        system_app = env_with_all_apps.get_app_with_class(HomeScreenSystemApp)
        system_app.open_app("Reminder")

        # This should not raise NameError
        tools = env_with_all_apps.get_user_tools()
        tool_names = {tool.name for tool in tools}

        # Reminder app uses Reminder type in return annotations
        assert "Reminder__list_all_reminders" in tool_names
        assert "Reminder__open_reminder" in tool_names
