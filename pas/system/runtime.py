"""Runtime helpers shared across PAS scenarios."""

from __future__ import annotations

import typing
from typing import TYPE_CHECKING

from pas.environment import StateAwareEnvironmentWrapper
from pas.logging_utils import get_pas_file_logger, initialise_pas_logs
from pas.system.notification import PasNotificationSystem

if TYPE_CHECKING:  # pragma: no cover - typing only
    from are.simulation.notification_system import VerbosityLevel

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
) -> PasNotificationSystem:
    """Instantiate the runtime notification system with optional extra tool subscriptions."""
    return PasNotificationSystem(verbosity=verbosity, extra_notifications=extra_notifications or {})


def create_environment(notification_system: PasNotificationSystem) -> StateAwareEnvironmentWrapper:
    """Create a PAS environment wired with the supplied notification system."""
    return StateAwareEnvironmentWrapper(notification_system=notification_system)


def attach_event_logging(env: StateAwareEnvironmentWrapper, log_file: Path) -> None:
    """Log completed events to disk without duplicating handlers."""
    event_logger = get_pas_file_logger("pas.events", log_file)

    def _log_event(event: CompletedEvent) -> None:
        action = getattr(event, "action", None)
        args = getattr(action, "args", None) if action is not None else None
        event_logger.info(
            "CompletedEvent: type=%s app=%s function=%s args=%s",
            event.event_type,
            event.app_name(),
            event.function_name(),
            args,
        )

    env.subscribe_to_completed_events(_log_event)
