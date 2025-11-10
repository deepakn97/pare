from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, cast

from are.simulation.apps.app import App
from are.simulation.tool_utils import AppTool, build_tool

from pas.apps.tool_decorators import pas_event_registered, user_tool

if TYPE_CHECKING:
    from are.simulation.tools import Tool
    from are.simulation.types import CompletedEvent
else:  # pragma: no cover - runtime fallback for typing-only imports
    Tool = object  # type: ignore[misc,assignment]


class AppState(ABC):
    """Base class for navigation states.

    Each state represents a screen/view of the app on the mobile phone.
    Navigation states form an MDP where each state has specific available actions.

    Note: Different from Meta AREs data state (JSON)
    """

    # ! TODO: We should also add a name here.

    def __init__(self) -> None:
        """Initialize the app tools."""
        self._app: App | None = None
        self._cached_tools: list[AppTool] | None = None

    def bind_to_app(self, app: App) -> None:
        """Bind this state to an app (late binding).

        Called automatically by StatefulApp.set_current_state().

        Args:
            app: The app this state belongs to
        """
        self._app = app

    @property
    def app(self) -> App:
        """Get the app this state is bound to."""
        return self._app

    def get_available_actions(self) -> list[AppTool]:
        """Get user tools (actions) available from this navigation state.

        These are valid actions for the user in this App MDP from this state.

        Returns:
            list[AppTool]: A list of AppTool objects representing the available actions.
        """
        if self._cached_tools is None:
            tools = []
            for _, method in inspect.getmembers(self, predicate=inspect.ismethod):
                if hasattr(method, "_is_user_tool"):  # check for user tool decorator
                    # IMPORTANT: For state-bound methods, extract the unbound function
                    # and explicitly set class_instance to the state instance.
                    # `method` is a bound method, but AppTool expects an unbound function
                    # so it can pass class_instance as the first argument.
                    unbound_func = method.__func__
                    tool = build_tool(self._app, unbound_func)
                    # Override class_instance to be the state instance, not the app
                    tool.class_instance = self
                    tools.append(tool)
            self._cached_tools = tools

        return self._cached_tools

    @abstractmethod
    def on_enter(self) -> None:
        """Called when transitioning into this state.

        Override to handle state initialization, load data, update anything, etc. We don't know if this is useful yet.
        """
        raise NotImplementedError("Subclasses must implement on_enter")

    @abstractmethod
    def on_exit(self) -> None:
        """Called when transitioning out of this state.

        Override to handle state cleanup, save data, etc. We don't know if this is useful yet.
        """
        raise NotImplementedError("Subclasses must implement on_exit")


class StatefulApp(App):
    """Base class for a stateful app.

    This class implements the basic functionality needed for a finite state machine based mobile app.
    """

    name: str | None
    description: str | None = None

    def __init__(self, name: str | None = None, *args: Any, **kwargs: Any) -> None:
        """Initialize the stateful app.

        Args:
            name: The name of the app.
            args: The arguments to pass to the app.
            kwargs: The keyword arguments to pass to the app.
        """
        desired_name = name
        super().__init__(name, *args, **kwargs)
        # Workaround for Meta-ARE dataclass apps with __post_init__ that call super().__init__(self.name)
        # where self.name is None (dataclass default), causing App.__init__ to use class name as fallback.
        # We restore the intended name after parent initialization completes.
        actual_name = cast("str | None", getattr(self, "name", None))
        if desired_name is not None and actual_name != desired_name:
            self.name = desired_name
        self.current_state: AppState | None = None
        # Navigation stack is used to track the history of the state transitions.
        # The first state is always the initial state of the app.
        self.navigation_stack: list[AppState] = []

    def set_current_state(self, app_state: AppState) -> None:
        """Set the current state of the app.

        This is called by `handle_state_transition` to update the current state of the app. This function will
        1. Binds the state to app
        2. Calls on_exit on the old state
        3. Pushes the old state to the navigation stack (for go_back())
        4. Calls on_enter on the new state (initialization/data loading)
        5. Sets the current state to the new state

        Args:
            app_state: The state to set.
        """
        if app_state.app is None:
            app_state.bind_to_app(self)  # Late binding: app injects itself into state

        if self.current_state is not None:
            self.current_state.on_exit()
            self.navigation_stack.append(self.current_state)

        app_state.on_enter()
        self.current_state = app_state

    @abstractmethod
    def create_root_state(self) -> AppState:
        """Return a freshly constructed root navigation state."""

    def load_root_state(self) -> None:
        """Reset the app to its root navigation state."""
        self.set_current_state(self.create_root_state())
        self.navigation_stack.clear()

    def reset_to_root(self) -> str:
        """Reset to the root navigation state and report the new view."""
        self.load_root_state()
        state_name = type(self.current_state).__name__ if self.current_state else "UnknownState"
        return f"Reset to {state_name}"

    @user_tool()
    @pas_event_registered()
    def go_back(self) -> str:
        """Navigate back to the previous state of the app.

        Returns:
            str: A message indicating the navigation back action.
        """
        if not self.navigation_stack:
            return "Already at the initial state"

        self.current_state = self.navigation_stack.pop()
        return f"Navigated back to the state {self.current_state.__class__.__name__}"

    def get_user_tools(self) -> list[AppTool]:
        """Get user tools from the current state of the app.

        User tools are state dependent and manage context. Each state will only enable
        some of the available actions in the app.

        Returns:
            list[AppTool]: A list of AppTool objects representing the available user tools.
        """
        tools = []
        if self.current_state is not None:
            tools.extend(self.current_state.get_available_actions())
        # Add go_back tool if navigation stack is not empty
        if self.navigation_stack:
            tools.append(build_tool(self, self.go_back))
        return tools

    # ! NOTE: Why do we need to get meta are user tools?
    def get_meta_are_user_tools(self) -> list[Tool]:
        """Return Meta ARE-compatible tool adapters for the current navigation state."""
        from are.simulation.tool_utils import AppToolAdapter  # Use native Meta ARE adapter

        adapters: list[Tool] = []
        if self.current_state is not None:
            for app_tool in self.current_state.get_available_actions():
                adapters.append(AppToolAdapter(app_tool))

        if self.navigation_stack:
            adapters.append(AppToolAdapter(build_tool(self, self.go_back)))
        return adapters

    def get_tools(self) -> list[AppTool]:
        """Get the tools of the app."""
        return super().get_tools()

    def handle_state_transition(self, event: CompletedEvent) -> None:
        """Update the current state of the app based on the tool events.

        This implements the state transition function T(s,a) -> s' for app specific transitions.

        Args:
            event: The completed event.
        """
        raise NotImplementedError("Subclasses must implement handle_state_transition")

    def get_state_graph(self) -> dict[str, list[str]]:
        """Get the state graph of the app.

        TODO: implement after MVP

        Returns:
            dict[str, list[str]]: The state graph of the app.
        """
        raise NotImplementedError("Subclasses must implement get_state_graph")

    def get_reachable_states(self, from_state: AppState) -> list[type[AppState]]:
        """Get the reachable states from the given state.

        TODO: implement after MVP

        Args:
            from_state: The state to get the reachable states from.

        Returns:
            list[type[AppState]]: The reachable states from the given state.
        """
        raise NotImplementedError("Subclasses must implement get_reachable_states")
