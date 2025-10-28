from __future__ import annotations

import logging
from contextlib import suppress
from typing import TYPE_CHECKING, Protocol

from are.simulation.environment import Environment, EnvironmentConfig, EnvironmentType

from pas.apps.core import StatefulApp
from pas.apps.system import HomeScreenSystemApp

if TYPE_CHECKING:
    from collections.abc import Callable

    from are.simulation.apps.app import App
    from are.simulation.notification_system import BaseNotificationSystem
    from are.simulation.tools import AppTool, Tool
    from are.simulation.types import CompletedEvent

logger = logging.getLogger(__name__)


# ! NOTE: Again, not clear why we need this protocol.
class _UserAgentProtocol(Protocol):
    """Protocol for user agents that support dynamic tool updates."""

    def update_tools_for_app(self, app_name: str, new_tools: list[Tool]) -> None:
        """Update tools for a specific app."""
        ...


class StateAwareEnvironmentWrapper(Environment):
    """Environment wrapper that triggers state transitions in StatefulApps.

    // RL NOTE: This is the environment in the RL sense - manages state transitions and
    // provides observations (available actions) to agents based on current navigation state.
    """

    def __init__(
        self,
        config: EnvironmentConfig | None = None,
        environment_type: EnvironmentType = EnvironmentType.UNKNOWN,
        notification_system: BaseNotificationSystem | None = None,
        add_event_to_agent_log: Callable[[CompletedEvent], None] | None = None,
    ) -> None:
        """Initialise the environment and set up completed-event subscribers."""
        super().__init__(
            config=config,
            environment_type=environment_type,
            notification_system=notification_system,
            add_event_to_agent_log=add_event_to_agent_log,
        )

        # PAS extensions (follow Meta ARE naming: no underscores for public attributes)
        self.completed_event_subscribers: list[Callable[[CompletedEvent], None]] = []
        self.processed_event_ids: set[str] = set()
        self.user_agent: _UserAgentProtocol | None = None
        self.active_app: StatefulApp | HomeScreenSystemApp | None = None
        self.background_apps: list[StatefulApp | HomeScreenSystemApp] = []

    def get_user_tools(self) -> list[AppTool]:
        """Get tools available to the user agent from currentlly active app and system app.

        The user can only interact with:
        1. The current state of the active app (if any) - representing the current screen
        2. The system app (HomeScreenSystemApp) - always available (go_home, open_app, switch_app, etc.)

        Returns:
            list[AppTool]: Tools available to the user agent from currently active apps.
        """
        tools: list[AppTool] = []

        # Always add the system app tools
        system_app = self.get_app_with_class(HomeScreenSystemApp)
        system_tools = system_app.get_user_tools()

        # ! Open app tool is only available on the home screen. Similar to how a real phone works.
        if self.active_app != system_app:
            system_tools = [tool for tool in system_tools if tool.function.__name__ != "open_app"]

        # ! maybe need AppToolAdapter here?
        tools.extend(system_tools)
        logger.debug(f"Added system app tools: {len(tools)}")

        # Include active app tools if active app is not the system app
        if self.active_app is not None and self.active_app != system_app:
            tools.extend(self.active_app.get_user_tools())
            logger.debug(f"Added active app tools: {len(tools)}")
        return tools

    def get_tools(self) -> list[AppTool]:
        """Get all tools available to the proactive agent from all registered apps.

        Returns:
            list[AppTool]: Tools available to the proactive agent from all registered apps.
        """
        tools: list[AppTool] = []
        for app_name, app in self.apps.items():
            tools.extend(app.get_tools())
            logger.debug(f"Added app tools: {app_name} - {len(tools)}")
        return tools

    def register_apps(self, apps: list[App]) -> None:
        """Register apps and wire up navigation callbacks to HomeScreenSystemApp.

        Args:
            apps: List of apps to register
        """
        super().register_apps(apps)

        # Wire up navigation callbacks to the HomeScreen system app
        home_screen_app = self.get_app_with_class(HomeScreenSystemApp)
        if home_screen_app is None:
            raise ValueError("HomeScreenSystemApp must be registered in the environment.")

        home_screen_app.set_callbacks(
            switch_app_callback=self._switch_app, open_app_callback=self._open_app, go_home_callback=self._go_home
        )

        # Set initial active app to home screen
        self.active_app = home_screen_app
        logger.debug("Wired up navigation callbacks to HomeScreenSystemApp")

    def _go_home(self) -> str:
        """Go to the home screen and update the background apps stack.

        Returns:
            str: A message indicating the home screen action.
        """
        system_app = self.get_app_with_class(HomeScreenSystemApp)

        if self.active_app == system_app:
            logger.debug("Already on home screen. Preserving current state.")
            return "You are already on the home screen."

        if self.active_app is not None:
            self.background_apps.append(self.active_app)

        self.active_app = system_app
        logger.debug("Switched to home screen.")

        return "Switched to home screen."

    def _open_app(self, app_name: str) -> str:
        """Open the app and update the background apps stack.

        Args:
            app_name: The name of the app to open

        Raises:
            KeyError: If the app is not registered.
            ValueError: If the app is already open.
        """
        if app_name not in self.apps:
            raise KeyError(f"App {app_name} is not available.")

        target_app: StatefulApp = self.get_app(app_name)

        if self.active_app == target_app:
            logger.debug(f"App {app_name} is already active. Preserving current state.")
            return f"{app_name} App is already open. You are already on it."

        if target_app in self.background_apps:
            self.background_apps.remove(target_app)

        if self.active_app is not None:
            self.background_apps.append(self.active_app)

        self.active_app = target_app
        self.active_app.load_root_state()
        logger.debug(f"Opened {app_name} App successfully.")
        return f"Opened {app_name} App."

    def _switch_app(self, app_name: str) -> str:
        """Switch the active app and update the background apps stack.

        The method handles switching between apps. If the provided app is already open (in background_apps), it preservers the app's state. If the target app is not open, then it raises an error.

        Args:
            app_name: The name of the app to switch to

        Raises:
            KeyError: If the app is not registered.
            ValueError: If the app is not open.
        """
        if app_name not in self.apps:
            raise KeyError(f"App {app_name} is not available.")

        target_app: StatefulApp = self.get_app(app_name)

        if self.active_app == target_app:
            logger.debug(f"App {app_name} is already active. Preserving current state.")
            return f"App {app_name} is already active."

        if target_app not in self.background_apps:
            raise ValueError(f"App {app_name} is not open. You have to open it first.")

        self.background_apps.remove(target_app)

        if self.active_app is not None:
            self.background_apps.append(self.active_app)

        self.active_app = target_app
        logger.debug(f"Switched to active app: {app_name}")
        return f"Switched to {app_name} App successfully."

    def register_user_agent(self, agent: _UserAgentProtocol) -> None:
        """Register the user agent for dynamic tool updates.

        Args:
            agent: The user agent (typically StatefulUserAgent) that needs tool updates
        """
        self.user_agent = agent
        logger.debug("Registered user agent for dynamic tool updates")

    def subscribe_to_completed_events(self, callback: Callable[[CompletedEvent], None]) -> None:
        """Register a callback that will receive every completed event."""
        if callback not in self.completed_event_subscribers:
            self.completed_event_subscribers.append(callback)

    def unsubscribe_from_completed_events(self, callback: Callable[[CompletedEvent], None]) -> None:
        """Remove a previously registered completed-event subscriber."""
        with suppress(ValueError):  # pragma: no cover - defensive guard
            self.completed_event_subscribers.remove(callback)

    def add_to_log(self, events: CompletedEvent | list[CompletedEvent]) -> None:
        """Override to add PAS state transition handling.

        // RL NOTE: This is where the environment processes actions and transitions to next state.
        // Log (s, a, r, s') tuples here for RL dataset generation.
        """
        event_list = events if isinstance(events, list) else [events]
        super().add_to_log(event_list)  # Call Meta ARE's native event processing

        for event in event_list:
            # Skip already processed events
            if event.event_id in self.processed_event_ids:
                continue

            logger.debug(
                f"StateAwareEnvironmentWrapper observed event: app={event.app_name()} function={event.function_name()} type={event.event_type}"
            )

            # Handle state transitions for StatefulApps
            app = self.get_app(event.app_name())
            if isinstance(app, StatefulApp):
                app.handle_state_transition(event)
                self._refresh_user_agent_tools(event.app_name(), app)

            # Notify subscribers (used by UserProxy, ProactiveAgent, event logging, and oracles)
            for callback in tuple(self.completed_event_subscribers):
                callback(event)

            self.processed_event_ids.add(event.event_id)

    def _refresh_user_agent_tools(self, app_name: str, app: StatefulApp) -> None:
        """Refresh user agent tools after a stateful app transitions state.

        Args:
            app_name: Name of the app that transitioned
            app: The StatefulApp instance
        """
        if self.user_agent is None:
            return

        if not hasattr(self.user_agent, "update_tools_for_app"):
            return

        try:
            new_tools = app.get_meta_are_user_tools()
            self.user_agent.update_tools_for_app(app_name, new_tools)
            logger.debug(f"Refreshed tools for app {app_name}: {len(new_tools)} tools now available")
        except Exception as e:
            logger.warning(f"Failed to refresh tools for app {app_name}: {e}")
