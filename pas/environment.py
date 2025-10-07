from __future__ import annotations

import logging
from collections import deque
from contextlib import suppress
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from are.simulation.environment import Environment, EnvironmentConfig, EnvironmentType

from pas.apps.core import StatefulApp
from pas.notifications import dispatch_popup, resolve_popup_spec

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
        self._notification_metadata: deque[tuple[datetime, str, str]] = deque()

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

        action = event.action
        spec = resolve_popup_spec(event)
        if spec is not None:
            message = spec.builder(event)
            if message:
                current_time = self.time_manager.time()
                timestamp = datetime.fromtimestamp(current_time, tz=UTC)
                self._notification_metadata.append((timestamp, event.app_name(), event.function_name()))
                dispatch_popup(self.notification_system, message, channel=spec.channel, timestamp=current_time)
        app = self.get_app(event.app_name())

        if isinstance(app, StatefulApp):
            app.handle_state_transition(event)

        for callback in tuple(self._completed_event_subscribers):
            callback(event)

        self._processed_event_ids.add(event.event_id)

    def handle_completed_event(self, event: CompletedEvent) -> None:  # pragma: no cover - legacy hook
        """Maintain compatibility with tests invoking the legacy hook directly."""
        self._process_completed_event(event)

    def pop_notification_metadata(self, timestamp: datetime) -> tuple[str, str] | None:
        """Return and remove metadata for the notification emitted at ``timestamp`` if available."""
        for _ in range(len(self._notification_metadata)):
            stored_timestamp, app_name, function_name = self._notification_metadata.popleft()
            if stored_timestamp == timestamp:
                return app_name, function_name
            self._notification_metadata.append((stored_timestamp, app_name, function_name))
        return None
