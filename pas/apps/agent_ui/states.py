"""Navigation states for agent UI app."""

from __future__ import annotations

from pas.apps.core import AppState


class AgentUIRootState(AppState):
    """Root state for agent-user interface - single view for all agent communication."""

    def __repr__(self) -> str:
        """Return string representation."""
        return "AgentUIRootState()"

    def on_enter(self) -> None:
        """Handle state entry - no action needed for agent UI."""
        pass

    def on_exit(self) -> None:
        """Handle state exit - no action needed for agent UI."""
        pass


__all__ = ["AgentUIRootState"]
