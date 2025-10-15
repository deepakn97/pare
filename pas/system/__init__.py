"""Core runtime utilities shared across PAS scenarios."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .proactive import build_plan_executor
from .session import ProactiveCycleResult, ProactiveSession
from .user import DEFAULT_USER_SYSTEM_PROMPT, build_stateful_user_planner, build_user_system_prompt

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    from .runtime import attach_event_logging, create_environment, create_notification_system, initialise_runtime

__all__ = [
    "DEFAULT_USER_SYSTEM_PROMPT",
    "ProactiveCycleResult",
    "ProactiveSession",
    "attach_event_logging",
    "build_plan_executor",
    "build_stateful_user_planner",
    "build_user_system_prompt",
    "create_environment",
    "create_notification_system",
    "initialise_runtime",
]


def __getattr__(name: str) -> object:
    if name in {"attach_event_logging", "create_environment", "create_notification_system", "initialise_runtime"}:
        from .runtime import attach_event_logging, create_environment, create_notification_system, initialise_runtime

        mapping = {
            "attach_event_logging": attach_event_logging,
            "create_environment": create_environment,
            "create_notification_system": create_notification_system,
            "initialise_runtime": initialise_runtime,
        }
        return mapping[name]
    raise AttributeError(name)
