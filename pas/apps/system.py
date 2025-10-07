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

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Initialise the system app and prepare environment attachment hook."""
        super().__init__(*args, **kwargs)
        self._environment: StateAwareEnvironmentWrapper | None = None

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
        app = self._environment.get_app(app_name)
        if not isinstance(app, StatefulApp):
            raise TypeError(f"App '{app_name}' is not a stateful app")
        message = app.reset_to_root()
        return f"Opened {app_name}: {message}"

    def get_user_tools(self) -> list[AppTool]:
        """Return system user tools with argument metadata."""
        tools = super().get_user_tools()
        for tool in tools:
            if tool.function.__name__ == "open_app":
                for arg in tool.args:
                    if arg.name == "app_name" and arg.description is None:
                        arg.description = "Name of the app to open"
        return tools


__all__ = ["HomeScreenSystemApp"]
