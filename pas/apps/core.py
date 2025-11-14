from __future__ import annotations

import ast
import inspect
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, cast

from are.simulation.apps.app import App, ToolType
from are.simulation.tool_utils import AppTool, ToolAttributeName, build_tool

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

    # NOTE: Extend Meta-ARE tool discovery to support PAS state tools and event-only tools
    def get_tools_with_attribute(
        self, attribute: ToolAttributeName | None, tool_type: ToolType | None
    ) -> list[AppTool]:
        """Return tools by attribute/tool type, extended for PAS stateful apps.

        - If tool_type/attribute correspond to USER tools, include state-bound user tools.
        - Otherwise, defer to Meta-ARE base implementation.
        - Special case: if both tool_type and attribute are None, return "event-only" tools:
          methods decorated with @event_registered-like decorator but without any of
          @app_tool, @user_tool, @env_tool, @data_tool. Detected via AST across the MRO.
        """
        # Special case: event-only tools discovery via AST (no tool decorator present)
        if tool_type is None and attribute is None:
            return self._get_event_only_tools_via_ast()

        # Include state-bound user tools for USER queries
        if tool_type == ToolType.USER and attribute == ToolAttributeName.USER:
            if self.current_state is None:
                return []
            # AppState already builds AppTool objects with class_instance bound to state
            return list(self.current_state.get_available_actions())

        # Fallback to base Meta-ARE behavior for APP/ENV/DATA (and any other cases)
        return super().get_tools_with_attribute(attribute=attribute, tool_type=tool_type)

    # Internal helpers
    def _get_event_only_tools_via_ast(self) -> list[AppTool]:  # noqa: C901
        """Discover event-registered methods without tool decorators across the class MRO."""
        discovered_tools: list[AppTool] = []
        processed_function_names: set[str] = set()

        # Names of decorators to include/exclude (base name, without module prefixes)
        include_event_names = {"event_registered", "pas_event_registered"}
        exclude_tool_names = {"app_tool", "user_tool", "env_tool", "data_tool"}

        def _decorator_base_name(dec: ast.expr) -> str | None:
            # Extract the base name of a decorator (handles Name, Attribute, Call)
            node = dec
            if isinstance(node, ast.Call):
                node = node.func
            if isinstance(node, ast.Name):
                return node.id
            if isinstance(node, ast.Attribute):
                # Get last attribute part (e.g., tool_utils.user_tool -> user_tool)
                return node.attr
            return None

        # Traverse MRO to include inherited methods (ARE base apps)
        for cls in inspect.getmro(self.__class__):
            # Stop once we hit the framework base App class
            if cls is App or cls is ABC or cls is object:
                continue

            try:
                source_file = inspect.getsourcefile(cls) or inspect.getfile(cls)
                if not source_file:
                    continue
                source_text = inspect.getsource(cls)
            except Exception:  # noqa: S112
                # Skip classes without retrievable source (e.g., C extensions)
                continue

            try:
                # Parse the full module, then isolate the class body where possible
                module_source = None
                try:
                    with open(source_file, encoding="utf-8") as f:
                        module_source = f.read()
                except Exception:
                    module_source = source_text

                tree = ast.parse(module_source or source_text)
            except SyntaxError:
                continue

            # Find the class definition node matching this cls
            class_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == cls.__name__]
            if not class_nodes:
                continue

            for class_node in class_nodes:
                for node in class_node.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        func_name = node.name
                        if func_name in processed_function_names:
                            continue

                        decorator_names = {name for d in node.decorator_list if (name := _decorator_base_name(d))}
                        # Must include event decorator, and must NOT include any tool decorator
                        has_event = any(d in include_event_names for d in decorator_names)
                        has_tool = any(d in exclude_tool_names for d in decorator_names)
                        if not has_event or has_tool:
                            continue

                        # Retrieve the bound method from the instance
                        func_obj = getattr(self, func_name, None)
                        if func_obj is None or not callable(func_obj):
                            continue

                        # Build the AppTool (skip if missing docstring or invalid)
                        try:
                            tool = build_tool(self, func_obj)
                        except Exception:  # noqa: S112
                            # Skip functions that cannot be converted (e.g., missing docstrings)
                            continue

                        discovered_tools.append(tool)
                        processed_function_names.add(func_name)

        return discovered_tools
