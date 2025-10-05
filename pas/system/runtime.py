"""Runtime helpers shared across PAS scenarios."""

from __future__ import annotations

import typing
from typing import TYPE_CHECKING

from are.simulation.notification_system import VerboseNotificationSystem, VerbosityLevel

from pas.environment import StateAwareEnvironmentWrapper
from pas.logging_utils import get_pas_file_logger, initialise_pas_logs

if TYPE_CHECKING:
    from pathlib import Path

    from are.simulation.types import CompletedEvent


def initialise_runtime(*, log_paths: typing.Iterable[Path] | None = None, clear_existing: bool = False) -> None:
    """Prepare PAS logging before launching a new scenario run."""
    if log_paths is None:
        return
    initialise_pas_logs(clear_existing=clear_existing, log_paths=list(log_paths))


def create_notification_system(
    *, verbosity: VerbosityLevel, extra_notifications: typing.Mapping[str, typing.Iterable[str]] | None = None
) -> VerboseNotificationSystem:
    """Instantiate the runtime notification system with optional extra tool subscriptions."""
    system = VerboseNotificationSystem(verbosity_level=verbosity)

    if extra_notifications is not None:
        for app_name, tool_names in extra_notifications.items():
            system.config.notified_tools[app_name] = list(tool_names)

    return system


def create_environment(notification_system: VerboseNotificationSystem) -> StateAwareEnvironmentWrapper:
    """Create a PAS environment wired with the supplied notification system."""
    return StateAwareEnvironmentWrapper(notification_system=notification_system)


def attach_event_logging(env: StateAwareEnvironmentWrapper, log_file: Path) -> None:
    """Log completed events to disk without duplicating handlers."""
    event_logger = get_pas_file_logger("pas.events", log_file)

    def _log_event(event: CompletedEvent) -> None:
        action = event.action
        event_logger.info(
            "CompletedEvent: type=%s app=%s function=%s args=%s",
            event.event_type,
            event.app_name(),
            event.function_name(),
            action.args,
        )

    env.subscribe_to_completed_events(_log_event)
