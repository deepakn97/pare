"""PAS extensions around the Meta-ARE system app."""

from __future__ import annotations

from typing import TYPE_CHECKING

from are.simulation.apps.system import SystemApp
from are.simulation.tool_utils import user_tool

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
        """Reset the requested stateful app to its root state and report the view."""
        if self._environment is None:
            raise RuntimeError("System app not attached to environment")
        app = self._environment.get_app(app_name)
        if not isinstance(app, StatefulApp):
            raise TypeError(f"App '{app_name}' is not a stateful app")
        message = app.reset_to_root()
        return f"Opened {app_name}: {message}"


__all__ = ["HomeScreenSystemApp"]
