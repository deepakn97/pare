"""Tests for StateAwareEnvironmentWrapper navigation and tool discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from are.simulation.apps.contacts import Contact

from pare.apps import HomeScreenSystemApp, PAREAgentUserInterface, StatefulContactsApp, StatefulEmailApp
from pare.environment import StateAwareEnvironmentWrapper

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture()
def env_with_apps() -> Generator[StateAwareEnvironmentWrapper, None, None]:
    """Provide an environment with multiple apps registered."""
    env = StateAwareEnvironmentWrapper()

    # Register system app (automatically added)
    system_app = HomeScreenSystemApp(name="HomeScreen")

    # Register PAREAgentUserInterface app
    aui_app = PAREAgentUserInterface()
    # Register contacts app
    contacts_app = StatefulContactsApp(name="Contacts")
    contacts_app.add_contacts([Contact(first_name="Ada", last_name="Lovelace", contact_id="contact-ada", phone="111")])

    # Register email app
    email_app = StatefulEmailApp(name="Email")

    env.register_apps([system_app, aui_app, contacts_app, email_app])
    yield env


class TestToolDiscovery:
    """Test get_user_tools() and get_tools() methods."""

    def test_get_user_tools_on_home_screen(self, env_with_apps: StateAwareEnvironmentWrapper) -> None:
        """When on home screen, user tools should include all system tools including open_app."""
        tools = env_with_apps.get_user_tools()
        tool_names = {tool.name for tool in tools}

        # Should have all three system tools (with app name prefix)
        assert "HomeScreen__go_home" in tool_names
        assert "HomeScreen__open_app" in tool_names
        assert "HomeScreen__switch_app" in tool_names

    def test_get_user_tools_on_contacts_app(self, env_with_apps: StateAwareEnvironmentWrapper) -> None:
        """When on Contacts app, should have Contacts tools + system tools (excluding open_app)."""
        # Open contacts app
        system_app = env_with_apps.get_app_with_class(HomeScreenSystemApp)
        system_app.open_app("Contacts")

        tools = env_with_apps.get_user_tools()
        tool_names = {tool.name for tool in tools}

        # Should have system tools except open_app (with app name prefix)
        assert "HomeScreen__go_home" in tool_names
        assert "HomeScreen__switch_app" in tool_names
        assert "HomeScreen__open_app" not in tool_names

        # Should have contacts app tools (from ContactsList state - the root state)
        assert "Contacts__list_contacts" in tool_names
        assert "Contacts__search_contacts" in tool_names
        assert "Contacts__open_contact" in tool_names

    def test_get_tools_returns_all_privileged_tools(self, env_with_apps: StateAwareEnvironmentWrapper) -> None:
        """get_tools() should return all privileged tools from all apps regardless of active app."""
        tools = env_with_apps.get_tools()
        tool_names = {tool.name for tool in tools}

        # HomeScreen navigation tools are @user_tool, NOT @app_tool, so they won't appear here
        # (proactive agent doesn't need navigation tools - it has direct privileged access)

        # Should have contacts app tools (all privileged @app_tool decorated)
        assert "Contacts__add_new_contact" in tool_names or "Contacts__create_contact" in tool_names
        assert "Contacts__get_contacts" in tool_names

        # Should have email app tools (check for send_email as primary indicator)
        assert "Email__send_email" in tool_names
        # Verify we got tools from all three apps
        email_tools = [name for name in tool_names if name.startswith("Email__")]
        assert len(email_tools) > 0  # At least one email tool


class TestNavigationCallbacks:
    """Test _go_home, _open_app, and _switch_app callbacks."""

    def test_go_home_from_home_screen(self, env_with_apps: StateAwareEnvironmentWrapper) -> None:
        """go_home when already on home screen should return appropriate message."""
        system_app = env_with_apps.get_app_with_class(HomeScreenSystemApp)

        result = system_app.go_home()

        assert result == "You are already on the home screen."
        assert env_with_apps.active_app == system_app

    def test_go_home_from_contacts_app(self, env_with_apps: StateAwareEnvironmentWrapper) -> None:
        """go_home from another app should switch to home screen and add to background."""
        system_app = env_with_apps.get_app_with_class(HomeScreenSystemApp)
        contacts_app = env_with_apps.get_app("Contacts")

        # Open contacts app
        system_app.open_app("Contacts")
        assert env_with_apps.active_app == contacts_app

        # Go home
        result = system_app.go_home()

        assert result == "Switched to home screen."
        assert env_with_apps.active_app == system_app
        assert contacts_app in env_with_apps.background_apps

    def test_open_app_success(self, env_with_apps: StateAwareEnvironmentWrapper) -> None:
        """open_app should open the app at root state and manage background stack."""
        system_app = env_with_apps.get_app_with_class(HomeScreenSystemApp)
        contacts_app = env_with_apps.get_app("Contacts")

        result = system_app.open_app("Contacts")

        assert result == "Opened Contacts App."
        assert env_with_apps.active_app == contacts_app
        assert system_app in env_with_apps.background_apps
        # Should be at root state
        assert contacts_app.current_state is not None

    def test_open_app_already_active(self, env_with_apps: StateAwareEnvironmentWrapper) -> None:
        """open_app when app is already active should not reset state."""
        system_app = env_with_apps.get_app_with_class(HomeScreenSystemApp)
        contacts_app = env_with_apps.get_app("Contacts")

        # Open contacts app
        system_app.open_app("Contacts")

        # Try to open again
        result = system_app.open_app("Contacts")

        assert result == "Contacts App is already open. You are already on it."
        assert env_with_apps.active_app == contacts_app

    def test_open_app_not_found(self, env_with_apps: StateAwareEnvironmentWrapper) -> None:
        """open_app with invalid app name should raise KeyError."""
        system_app = env_with_apps.get_app_with_class(HomeScreenSystemApp)

        with pytest.raises(KeyError, match="App InvalidApp is not available"):
            system_app.open_app("InvalidApp")

    def test_open_app_from_background(self, env_with_apps: StateAwareEnvironmentWrapper) -> None:
        """open_app for a backgrounded app should reset it to root state."""
        system_app = env_with_apps.get_app_with_class(HomeScreenSystemApp)
        contacts_app = env_with_apps.get_app("Contacts")
        email_app = env_with_apps.get_app("Email")

        # Open contacts, then email (contacts goes to background)
        system_app.open_app("Contacts")
        system_app.open_app("Email")

        assert contacts_app in env_with_apps.background_apps
        assert env_with_apps.active_app == email_app

        # Open contacts again - should remove from background and reset to root
        result = system_app.open_app("Contacts")

        assert result == "Opened Contacts App."
        assert env_with_apps.active_app == contacts_app
        assert contacts_app not in env_with_apps.background_apps
        assert email_app in env_with_apps.background_apps

    def test_switch_app_success(self, env_with_apps: StateAwareEnvironmentWrapper) -> None:
        """switch_app should switch to already-open app and preserve state."""
        system_app = env_with_apps.get_app_with_class(HomeScreenSystemApp)
        contacts_app = env_with_apps.get_app("Contacts")
        email_app = env_with_apps.get_app("Email")

        # Open both apps
        system_app.open_app("Contacts")
        system_app.open_app("Email")

        assert contacts_app in env_with_apps.background_apps

        # Switch back to contacts
        result = system_app.switch_app("Contacts")

        assert result == "Switched to Contacts App successfully."
        assert env_with_apps.active_app == contacts_app
        assert email_app in env_with_apps.background_apps
        assert contacts_app not in env_with_apps.background_apps

    def test_switch_app_already_active(self, env_with_apps: StateAwareEnvironmentWrapper) -> None:
        """switch_app when app is already active should return appropriate message."""
        system_app = env_with_apps.get_app_with_class(HomeScreenSystemApp)

        # Open contacts app
        system_app.open_app("Contacts")

        # Try to switch to it again
        result = system_app.switch_app("Contacts")

        assert result == "App Contacts is already active."

    def test_switch_app_not_open(self, env_with_apps: StateAwareEnvironmentWrapper) -> None:
        """switch_app to an app that's not open should raise ValueError."""
        system_app = env_with_apps.get_app_with_class(HomeScreenSystemApp)

        # Contacts is registered but not open
        with pytest.raises(ValueError, match=r"App Contacts is not open. You have to open it first"):
            system_app.switch_app("Contacts")

    def test_switch_app_not_found(self, env_with_apps: StateAwareEnvironmentWrapper) -> None:
        """switch_app with invalid app name should raise KeyError."""
        system_app = env_with_apps.get_app_with_class(HomeScreenSystemApp)

        with pytest.raises(KeyError, match="App InvalidApp is not available"):
            system_app.switch_app("InvalidApp")


class TestCallbackIntegration:
    """Test HomeScreenSystemApp callback setup and validation."""

    def test_callbacks_set_during_initialization(self, env_with_apps: StateAwareEnvironmentWrapper) -> None:
        """Callbacks should be set automatically during environment initialization."""
        system_app = env_with_apps.get_app_with_class(HomeScreenSystemApp)

        # Callbacks should not be None
        assert system_app._go_home is not None
        assert system_app._open_app is not None
        assert system_app._switch_app is not None

    def test_runtime_error_if_callbacks_not_set(self) -> None:
        """Tools should raise RuntimeError if callbacks are not set."""
        # Create system app without environment (callbacks not set)
        system_app = HomeScreenSystemApp(name="HomeScreen")

        with pytest.raises(RuntimeError, match="Callbacks not set"):
            system_app.go_home()

        with pytest.raises(RuntimeError, match="Callbacks not set"):
            system_app.open_app("SomeApp")

        with pytest.raises(RuntimeError, match="Callbacks not set"):
            system_app.switch_app("SomeApp")

    def test_navigation_stack_management(self, env_with_apps: StateAwareEnvironmentWrapper) -> None:
        """Background apps stack should be managed correctly during navigation."""
        system_app = env_with_apps.get_app_with_class(HomeScreenSystemApp)
        contacts_app = env_with_apps.get_app("Contacts")
        email_app = env_with_apps.get_app("Email")

        # Initially empty
        assert len(env_with_apps.background_apps) == 0

        # Open contacts
        system_app.open_app("Contacts")
        assert env_with_apps.active_app == contacts_app
        assert system_app in env_with_apps.background_apps
        assert len(env_with_apps.background_apps) == 1

        # Open email
        system_app.open_app("Email")
        assert env_with_apps.active_app == email_app
        assert contacts_app in env_with_apps.background_apps
        assert system_app in env_with_apps.background_apps
        assert len(env_with_apps.background_apps) == 2

        # Go home
        system_app.go_home()
        assert env_with_apps.active_app == system_app
        assert len(env_with_apps.background_apps) == 3
