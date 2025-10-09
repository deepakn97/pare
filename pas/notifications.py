"""Lightweight registry to trigger pop-up notifications on completed events."""

from __future__ import annotations

import typing
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from are.simulation.notification_system import BaseNotificationSystem, Message, MessageType

if TYPE_CHECKING:
    from are.simulation.types import CompletedEvent


@dataclass(frozen=True)
class PopupSpec:
    """Describes an app/channel-specific pop-up message builder."""

    channel: str
    builder: typing.Callable[[CompletedEvent], str | None]


_POPUP_REGISTRY: dict[tuple[str, str], PopupSpec] = {}


def register_popup_for_event(
    identifier: str,
    function_name: str,
    *,
    builder: typing.Callable[[CompletedEvent], str | None],
    channel: str = "system",
) -> None:
    """Associate an identifier (app name or class name) with a pop-up spec."""
    _POPUP_REGISTRY[(identifier, function_name)] = PopupSpec(channel=channel, builder=builder)


def register_popup(
    func: typing.Callable[..., object],
    *,
    builder: typing.Callable[[CompletedEvent], str | None],
    channel: str = "system",
) -> None:
    """Register pop-up behaviour for a callable using its qualified name."""
    qualname = getattr(func, "__qualname__", "")
    class_name = qualname.rsplit(".", 1)[0] if "." in qualname else ""
    if class_name:
        register_popup_for_event(class_name, func.__name__, builder=builder, channel=channel)
    register_popup_for_event(func.__name__, func.__name__, builder=builder, channel=channel)


def get_popup_spec(identifier: str, function_name: str) -> PopupSpec | None:
    """Return the pop-up spec for the given identifier/function pair if registered."""
    return _POPUP_REGISTRY.get((identifier, function_name))


def dispatch_popup(
    notification_system: BaseNotificationSystem | None,
    message: str,
    *,
    channel: str = "system",
    timestamp: float | None = None,
) -> None:
    """Emit a pop-up message through the notification system if both system and message exist."""
    if notification_system is None or not message:
        return

    current = timestamp if timestamp is not None else notification_system.get_current_time()
    notification_system.message_queue.put(
        Message(
            message_type=MessageType.ENVIRONMENT_NOTIFICATION,
            message=message,
            timestamp=datetime.fromtimestamp(current, tz=UTC),
        )
    )


def resolve_popup_spec(event: CompletedEvent) -> PopupSpec | None:
    """Find the first registered pop-up spec matching the completed event."""
    identifiers: list[str] = []
    identifiers.append(event.app_name())
    app_instance = getattr(event.action, "app", None)
    if app_instance is not None:
        identifiers.append(app_instance.__class__.__name__)
    for identifier in identifiers:
        spec = get_popup_spec(identifier, event.function_name())
        if spec is not None:
            return spec
    return None


def format_incoming_message(event: CompletedEvent) -> str | None:
    """Format a human-readable summary for an incoming messaging event."""
    action = event.action
    args = action.resolved_args or action.args or {}
    app = args.get("self")
    sender_id = args.get("sender_id")
    conversation_id = args.get("conversation_id")
    content = args.get("content")

    sender_name = None
    conversation_title = None
    if app is not None:
        sender_name = getattr(app, "id_to_name", {}).get(sender_id, sender_id)
        conversation = getattr(app, "conversations", {}).get(conversation_id)
        conversation_title = getattr(conversation, "title", None) if conversation else None

    parts: list[str] = []
    if conversation_title:
        parts.append(str(conversation_title))
    if sender_name:
        parts.append(str(sender_name))
    elif sender_id:
        parts.append(str(sender_id))

    app_label = getattr(app, "name", None) or event.app_name()

    lines: list[str] = []
    lines.append(f"Notification (app: {app_label})")
    if conversation_title:
        lines.append(f"Conversation: {conversation_title}")
    if conversation_id:
        lines.append(f"Conversation ID: {conversation_id}")
    if sender_name or sender_id:
        lines.append(f"Sender: {sender_name or sender_id}")
    if content:
        lines.append("Message:")
        lines.append(f"  {content}")
    return "\n".join(lines)


def format_agent_ui_prompt(event: CompletedEvent) -> str | None:
    """Render agent UI messages so the user proxy can see the request."""
    action = event.action
    args = action.resolved_args or action.args or {}
    content = args.get("content")
    if not content:
        return None
    lines = ["Agent message:", content]
    return "\n".join(lines)


# Register default pop-ups for apps we rely on
register_popup_for_event("AgentUserInterface", "send_message_to_user", builder=format_agent_ui_prompt)
