from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from are.simulation.environment import Environment, EnvironmentConfig, EnvironmentType
from are.simulation.types import EventType

from pare.apps import PAREAgentUserInterface
from pare.apps.core import StatefulApp
from pare.apps.reminder.app import StatefulReminderApp
from pare.apps.system import HomeScreenSystemApp
from pare.data_handler.models import PAREEventMetadata

if TYPE_CHECKING:
    from collections.abc import Callable

    from are.simulation.apps.app import App
    from are.simulation.notification_system import BaseNotificationSystem
    from are.simulation.tools import AppTool
    from are.simulation.types import CompletedEvent

logger = logging.getLogger(__name__)


class StateAwareEnvironmentWrapper(Environment):
    """Environment wrapper that triggers state transitions in StatefulApps."""

    def __init__(
        self,
        config: EnvironmentConfig | None = None,
        environment_type: EnvironmentType = EnvironmentType.UNKNOWN,
        notification_system: BaseNotificationSystem | None = None,
        add_event_to_agent_log: Callable[[CompletedEvent], None] | None = None,
    ) -> None:
        """Initialise the environment with active app tracking."""
        super().__init__(
            config=config,
            environment_type=environment_type,
            notification_system=notification_system,
            add_event_to_agent_log=add_event_to_agent_log,
        )

        # PARE extensions (follow Meta ARE naming: no underscores for public attributes)
        self.active_app: App | None = None
        self.background_apps: list[App] = []

        # Proactive context getter (returns current mode at event time)
        self._get_proactive_context: Callable[[], tuple[str | None, int]] | None = None

    def set_proactive_context_getter(
        self,
        getter: Callable[[], tuple[str | None, int]] | None,
    ) -> None:
        """Set callback to get current proactive context at event time.

        Args:
            getter: Callable returning (proactive_mode, turn_number).
        """
        self._get_proactive_context = getter

    def get_user_tools(self) -> list[AppTool]:
        """Get tools available to the user agent from currentlly active app and system app.

        The user can only interact with:
        1. The current state of the active app (if any) - representing the current screen
        2. The system app (HomeScreenSystemApp) - always available (go_home, open_app, switch_app, etc.)

        Returns:
            list[AppTool]: Tools available to the user agent from currently active apps.
        """
        tools: list[AppTool] = []

        aui_tools = self.get_app_with_class(PAREAgentUserInterface).get_user_tools()
        tools.extend(aui_tools)

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
        """Registers apps to the environment and wires up navigation callbacks to HomeScreenSystemApp.

        Args:
            apps: List of apps to register
        """
        for app in apps:
            app.register_time_manager(self.time_manager)
            app.register_to_env("environment", self.add_to_log)
            if app.__class__ == PAREAgentUserInterface:
                app.pause_env = self.pause
                app.resume_env = self.resume
            if isinstance(app, StatefulReminderApp):
                self.notification_system.setup_reminder_app(app)
            if isinstance(app, HomeScreenSystemApp):
                self.notification_system.setup_system_app(app)
                app.wait_for_next_notification = self.wait_for_next_notification

            for protocol in app.get_implemented_protocols():
                if protocol in self.protocol_to_app:
                    old_app = self.protocol_to_app[protocol].__class__.__name__
                    logger.warning(
                        f"Protocol {protocol} already registered by {old_app} also provided by {app.__class__.__name__}."
                    )
                    continue
                self.protocol_to_app[protocol] = app
            self.apps[app.name] = app

        # connect apps to protocol
        for app in self.apps.values():
            app.connect_to_protocols(self.protocol_to_app)

        # Wire up navigation callbacks to the HomeScreen System App
        home_screen_app = self.get_app_with_class(HomeScreenSystemApp)
        if home_screen_app is None:
            raise ValueError("HomeScreenSystemApp must be registered in the environment.")

        home_screen_app.set_callbacks(
            switch_app_callback=self._switch_app, open_app_callback=self._open_app, go_home_callback=self._go_home
        )

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
            ValueError: If the app is not a StatefulApp (system apps cannot be opened).
        """
        if app_name not in self.apps:
            raise KeyError(f"App {app_name} is not available.")

        target_app: App = self.get_app(app_name)

        # Only StatefulApps can be opened (system apps use go_home or are always available)
        if not isinstance(target_app, StatefulApp):
            raise TypeError(
                f"Cannot open {app_name}: system apps cannot be opened directly. "
                f"Use go_home() for HomeScreen or access AgentUI tools directly."
            )

        if self.active_app == target_app:
            logger.debug(f"App {app_name} is already active. Preserving current state.")
            return f"{app_name} App is already open. You are already on it."

        if target_app in self.background_apps:
            self.background_apps.remove(target_app)

        if self.active_app is not None:
            self.background_apps.append(self.active_app)

        self.active_app = target_app
        target_app.load_root_state()  # Safe to call because we validated StatefulApp
        logger.debug(f"Opened {app_name} App successfully.")
        return f"Opened {app_name} App."

    def _switch_app(self, app_name: str) -> str:
        """Switch the active app and update the background apps stack.

        The method handles switching between apps. If the provided app is already open (in background_apps), it preservers the app's state. If the target app is not open, then it raises an error.

        Args:
            app_name: The name of the app to switch to

        Raises:
            KeyError: If the app is not registered.
            ValueError: If the app is not open or is not a StatefulApp.
        """
        if app_name not in self.apps:
            raise KeyError(f"App {app_name} is not available.")

        target_app: App = self.get_app(app_name)

        # Only StatefulApps can be switched to (system apps use go_home or are always available)
        if not isinstance(target_app, StatefulApp):
            raise TypeError(
                f"Cannot switch to {app_name}: system apps cannot be switched to directly. "
                f"Use go_home() for HomeScreen or access AgentUI tools directly."
            )

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

    def add_to_log(self, events: CompletedEvent | list[CompletedEvent]) -> None:
        """Override to add PARE state transition handling and proactive metadata injection.

        This function is run while processing each event.

        // RL NOTE: This is where the environment processes actions and transitions to next state.
        // Log (s, a, r, s') tuples here for RL dataset generation.
        """
        # ! FIXME: I don't understand where add_to_log is called from. Is it called automatically at each event or do we need to call it manually somewhere?
        event_list = events if isinstance(events, list) else [events]

        # Inject proactive context into event metadata (getter ensures current mode at event time)
        if self._get_proactive_context is not None:
            proactive_mode, turn_number = self._get_proactive_context()
            for event in event_list:
                event_proactive_mode = proactive_mode if event.event_type == EventType.AGENT else None
                event.metadata = PAREEventMetadata(
                    return_value=event.metadata.return_value,
                    exception=event.metadata.exception,
                    exception_stack_trace=event.metadata.exception_stack_trace,
                    completed=event.metadata.completed,
                    proactive_mode=event_proactive_mode,
                    turn_number=turn_number,
                )
        else:
            logger.warning("Proactive context getter is None, skipping metadata injection")

        super().add_to_log(event_list)  # Call Meta ARE's native event processing

        for event in event_list:
            logger.debug(
                f"StateAwareEnvironmentWrapper observed event: app={event.app_name()} "
                f"function={event.function_name()} type={event.event_type}"
            )

            # Handle state transitions for StatefulApps only triggered by a user action.
            if event.event_type == EventType.USER:
                app = self.get_app(event.app_name())
                if isinstance(app, StatefulApp):
                    app.handle_state_transition(event)
