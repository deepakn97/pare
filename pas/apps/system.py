"""PAS extensions around the Meta-ARE system app."""

from __future__ import annotations

from are.simulation.apps.system import SystemApp
from are.simulation.tool_utils import user_tool


class HomeScreenSystemApp(SystemApp):
    """System app that exposes user tools for switching contexts."""

    @user_tool()
    def go_home(self) -> str:
        """Return to the home screen without changing app state."""
        return "Returned to home screen"


__all__ = ["HomeScreenSystemApp"]
