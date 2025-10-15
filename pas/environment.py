from __future__ import annotations

import logging
from contextlib import suppress
from typing import TYPE_CHECKING

from are.simulation.environment import Environment, EnvironmentConfig, EnvironmentType

from pas.apps.core import StatefulApp

if TYPE_CHECKING:
    from collections.abc import Callable

    from are.simulation.notification_system import BaseNotificationSystem
    from are.simulation.types import CompletedEvent


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
        self._completed_event_subscribers: list[Callable[[CompletedEvent], None]] = []
        self._logger = logging.getLogger(__name__)
        self._processed_event_ids: set[str] = set()

    def subscribe_to_completed_events(self, callback: Callable[[CompletedEvent], None]) -> None:
        """Register a callback that will receive every completed event."""
        if callback not in self._completed_event_subscribers:
            self._completed_event_subscribers.append(callback)

    def unsubscribe_from_completed_events(self, callback: Callable[[CompletedEvent], None]) -> None:
        """Remove a previously registered completed-event subscriber."""
        with suppress(ValueError):  # pragma: no cover - defensive guard
            self._completed_event_subscribers.remove(callback)

    def add_to_log(self, events: CompletedEvent | list[CompletedEvent]) -> None:
        """Route logged events through the PAS state layer and subscriber hooks."""
        event_list = events if isinstance(events, list) else [events]
        super().add_to_log(event_list)

        for event in event_list:
            self._process_completed_event(event)

    def _process_completed_event(self, event: CompletedEvent) -> None:
        """Intercept events to trigger navigation state transitions in StatefulApps.

        // RL NOTE: This is where the environment processes actions and transitions to next state.
        // Log (s, a, r, s') tuples here for RL dataset generation.

        Args:
            event: Completed event from tool execution
        """
        if event.event_id in self._processed_event_ids:
            return

        self._logger.debug(
            "StateAwareEnvironmentWrapper observed event: app=%s function=%s type=%s",
            event.app_name(),
            event.function_name(),
            event.event_type,
        )

        app = self.get_app(event.app_name())

        if isinstance(app, StatefulApp):
            app.handle_state_transition(event)

        for callback in tuple(self._completed_event_subscribers):
            callback(event)

        self._processed_event_ids.add(event.event_id)

    def handle_completed_event(self, event: CompletedEvent) -> None:  # pragma: no cover - legacy hook
        """Maintain compatibility with tests invoking the legacy hook directly."""
        self._process_completed_event(event)
