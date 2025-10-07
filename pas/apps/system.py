"""PAS extensions around the Meta-ARE system app."""

from __future__ import annotations

from typing import TYPE_CHECKING

from are.simulation.apps.system import SystemApp
from are.simulation.tool_utils import AppTool, user_tool

from pas.apps.core import StatefulApp

if TYPE_CHECKING:
    from pas.environment import StateAwareEnvironmentWrapper


class HomeScreenSystemApp(SystemApp):
    """System app that exposes user tools for switching contexts."""

    def __init__(self, *args: object, max_wait_seconds: int = 300, **kwargs: object) -> None:
        """Initialise the system app and prepare environment attachment hook."""
        super().__init__(*args, **kwargs)
        self._environment: StateAwareEnvironmentWrapper | None = None
        self._max_wait_seconds = max_wait_seconds

    def attach_environment(self, env: StateAwareEnvironmentWrapper) -> None:
        """Remember the environment so open_app can resolve stateful apps."""
        self._environment = env

    @user_tool()
    def go_home(self) -> str:
        """Return to the home screen without changing app state."""
        return "Returned to home screen"

    @user_tool()
    def open_app(self, app_name: str) -> str:
        """Switch to the requested app's root view."""
        if self._environment is None:
            raise RuntimeError("System app not attached to environment")
        canonical_name = app_name
        if canonical_name not in self._environment.apps:
            lower_map = {name.lower(): name for name in self._environment.apps}
            lookup = app_name.lower()
            alias_map = {"messages": "messaging", "message": "messaging"}
            if lookup in alias_map:
                lookup = alias_map[lookup]
            match = lower_map.get(lookup)
            if match is None:
                available = ", ".join(sorted(self._environment.apps))
                raise KeyError(f"Unknown app '{app_name}'. Available apps: {available}")
            canonical_name = match
        app = self._environment.get_app(canonical_name)
        if not isinstance(app, StatefulApp):
            raise TypeError(f"App '{app_name}' is not a stateful app")
        message = app.reset_to_root()
        return f"Opened {canonical_name}: {message}"

    @user_tool()
    def wait_for_notification(self, timeout: int = 0) -> None:
        """Clamp the wait timeout to avoid long-running idle periods."""
        bounded = min(int(timeout), self._max_wait_seconds)
        super().wait_for_notification(timeout=bounded)

    def get_user_tools(self) -> list[AppTool]:
        """Return system user tools with argument metadata."""
        tools = super().get_user_tools()
        for tool in tools:
            if tool.function.__name__ == "open_app":
                available = sorted(
                    name
                    for name, candidate in (self._environment.apps.items() if self._environment else [])
                    if isinstance(candidate, StatefulApp)
                )
                for arg in tool.args:
                    if arg.name == "app_name" and arg.description is None:
                        options = ", ".join(available) if available else "(no stateful apps registered)"
                        arg.description = f"Name of the app to open (available: {options})"
        return tools


__all__ = ["HomeScreenSystemApp"]
