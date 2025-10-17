from __future__ import annotations

import logging
from contextlib import suppress
from typing import TYPE_CHECKING, Protocol

from are.simulation.environment import Environment, EnvironmentConfig, EnvironmentType

from pas.apps.core import StatefulApp

if TYPE_CHECKING:
    from collections.abc import Callable

    from are.simulation.notification_system import BaseNotificationSystem
    from are.simulation.tools import Tool
    from are.simulation.types import CompletedEvent


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
        self.logger = logging.getLogger(__name__)
        self.processed_event_ids: set[str] = set()
        self.user_agent: _UserAgentProtocol | None = None

    def register_user_agent(self, agent: _UserAgentProtocol) -> None:
        """Register the user agent for dynamic tool updates.

        Args:
            agent: The user agent (typically StatefulUserAgent) that needs tool updates
        """
        self.user_agent = agent
        self.logger.debug("Registered user agent for dynamic tool updates")

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

            self.logger.debug(
                "StateAwareEnvironmentWrapper observed event: app=%s function=%s type=%s",
                event.app_name(),
                event.function_name(),
                event.event_type,
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
            self.logger.debug("Refreshed tools for app %s: %d tools now available", app_name, len(new_tools))
        except Exception as e:
            self.logger.warning("Failed to refresh tools for app %s: %s", app_name, e)
