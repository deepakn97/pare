"""Notification system extensions that format PAS notifications."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

from are.simulation.notification_system import Message, MessageType, VerboseNotificationSystem, VerbosityLevel
from are.simulation.types import CompletedEvent


class PASMessageType(Enum):
    """Extended MessageType enum system for PAS.

    AGENT_MESSAGE denotes any message sent by the agent to the user. This is important because user agent has to either accept or reject the agent's proposal.
    """

    AGENT_MESSAGE = "AGENT_MESSAGE"
    USER_MESSAGE = "USER_MESSAGE"
    ENVIRONMENT_NOTIFICATION = "ENVIRONMENT_NOTIFICATION"
    ENVIRONMENT_STOP = "ENVIRONMENT_STOP"


class PasNotificationSystem(VerboseNotificationSystem):
    """Notification system that formats PAS-specific notifications."""

    def __init__(
        self,
        *,
        verbosity: VerbosityLevel = VerbosityLevel.MEDIUM,
        extra_notifications: Mapping[str, Iterable[str]] | None = None,
    ) -> None:
        """Initialise the notification system with optional extra tool subscriptions."""
        super().__init__(verbosity_level=verbosity)
        if extra_notifications is not None:
            for app_name, tool_names in extra_notifications.items():
                self.config.notified_tools[app_name] = list(tool_names)

    def convert_to_message(self, event: CompletedEvent) -> Message | None:
        """Convert a completed event to a notification message with PAS-specific formatting."""
        # First try parent's default conversion (handles AgentUserInterface, etc.)
        message = super().convert_to_message(event)
        if message is not None:
            return message

        # Handle PAS-specific notification formatting
        if not isinstance(event, CompletedEvent):
            return None

        function_name = event.function_name()
        if function_name is None:
            return None

        app_name = event.app_name()
        content = self._format_notification_content(event, app_name, function_name)
        if content is None:
            return None

        timestamp = self.get_current_time()
        return Message(
            message_type=MessageType.ENVIRONMENT_NOTIFICATION,
            message=content,
            timestamp=datetime.fromtimestamp(timestamp, tz=UTC),
        )

    def _format_notification_content(
        self, event: CompletedEvent, app_name: str | None, function_name: str
    ) -> str | None:
        """Format notification content for PAS-specific events."""
        # Check if this event should trigger a notification based on app/function
        if (
            app_name in ("AgentUserInterface", "ProactiveAgentUserInterface")
            and function_name == "send_message_to_user"
        ):
            return self._format_agent_ui_message(event)

        if (
            app_name in ("AgentUserInterface", "ProactiveAgentUserInterface")
            and function_name == "send_proposal_to_user"
        ):
            return self._format_proactive_proposal(event)

        if app_name in ("StatefulMessagingApp", "messaging", "MessagingApp") and function_name in (
            "create_and_add_message",
            "add_message",
        ):
            return self._format_incoming_message(event)

        return None

    def _format_agent_ui_message(self, event: CompletedEvent) -> str | None:
        """Format agent UI messages for the user proxy."""
        action = event.action
        args = action.resolved_args or action.args or {}
        content = args.get("content")
        if not content:
            return None
        lines = ["Agent message:", str(content)]
        return "\n".join(lines)

    def _format_proactive_proposal(self, event: CompletedEvent) -> str | None:
        """Format proactive proposal notifications."""
        action = event.action
        args = action.resolved_args or action.args or {}
        goal = args.get("goal")
        if not goal:
            return None
        lines = ["Proactive assistant proposal:", str(goal)]
        return "\n".join(lines)

    def _format_incoming_message(self, event: CompletedEvent) -> str | None:
        """Format incoming messaging events as human-readable notifications."""
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

        lines: list[str] = []
        app_label = getattr(app, "name", None) or event.app_name()
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
