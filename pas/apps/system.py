"""PAS extensions around the Meta-ARE system app."""

from __future__ import annotations

from typing import TYPE_CHECKING

from are.simulation.apps.system import SystemApp

from pas.apps.tool_decorators import pas_event_registered, user_tool

if TYPE_CHECKING:
    from collections.abc import Callable


class HomeScreenSystemApp(SystemApp):
    """System app that exposes user tools for switching contexts."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Initialise the system app (callbacks will be set by environment)."""
        super().__init__(*args, **kwargs)
        self._switch_app: Callable[[str], str] | None = None
        self._open_app: Callable[[str], str] | None = None
        self._go_home: Callable[[], str] | None = None

    def set_callbacks(
        self,
        switch_app_callback: Callable[[str], str],
        open_app_callback: Callable[[str], str],
        go_home_callback: Callable[[], str],
    ) -> None:
        """Set the navigation callbacks (called by environment after initialization)."""
        self._switch_app = switch_app_callback
        self._open_app = open_app_callback
        self._go_home = go_home_callback

    @user_tool()
    @pas_event_registered()
    def go_home(self) -> str:
        """Return to the home screen. This will allow the user to open a new app.

        Returns:
            str: A message indicating the home screen action.
        """
        if self._go_home is None:
            raise RuntimeError("Callbacks not set - environment must call set_callbacks() first")
        return self._go_home()

    @user_tool()
    @pas_event_registered()
    def open_app(self, app_name: str) -> str:
        """Open the requested app. If the app is already open and it is in background, then the phone will switch to it. If the app is not open, then a it is opened to the home page of that app.

        Args:
            app_name: The name of the app to open (case-sensitive). The app must be availabe in the environment.

        Returns:
            str: A message indicating the open app action.
        """
        if self._open_app is None:
            raise RuntimeError("Callbacks not set - environment must call set_callbacks() first")
        return self._open_app(app_name)

    @user_tool()
    @pas_event_registered()
    def switch_app(self, app_name: str) -> str:
        """Switch to the requested app and preserve the current app state.

        Args:
            app_name: The name of the app to switch to (case-sensitive). The app must be open and availabe in the environment.

        Returns:
            str: A message indicating the switch app action.
        """
        if self._switch_app is None:
            raise RuntimeError("Callbacks not set - environment must call set_callbacks() first")
        return self._switch_app(app_name)
