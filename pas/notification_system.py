"""Notification system extensions that format PAS notifications."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from are.simulation.agents.multimodal import Attachment
from are.simulation.apps.agent_user_interface import AUIMessage, Sender
from are.simulation.notification_system import (
    BaseNotificationSystem,
    Message,
    NotificationSystemConfig,
    get_args,
    get_content_for_message,
)
from are.simulation.types import Action, CompletedEvent


class PASMessageType(Enum):
    """Extended MessageType enum system for PAS.

    AGENT_MESSAGE denotes any message sent by the agent to the user. This is important because user agent has to either accept or reject the agent's proposal.
    """

    AGENT_MESSAGE = "AGENT_MESSAGE"
    USER_MESSAGE = "USER_MESSAGE"
    ENVIRONMENT_NOTIFICATION = "ENVIRONMENT_NOTIFICATION"
    ENVIRONMENT_STOP = "ENVIRONMENT_STOP"


class PASNotificationSystem(BaseNotificationSystem):
    """Notification system that formats PAS-specific notifications."""

    def __init__(
        self,
        config: NotificationSystemConfig = NotificationSystemConfig(),  # noqa: B008
    ) -> None:
        """Initialise the notification system with optional extra tool subscriptions."""
        super().__init__(config=config)

    def convert_to_message(self, event: CompletedEvent) -> Message | None:
        """Convert a completed event to a notification message with PAS-specific formatting.

        Args:
            event: The completed event to convert to a notification message.

        Returns:
            The notification message.
        """
        # First try parent's default conversion (handles AgentUserInterface, etc.)
        if not isinstance(event, CompletedEvent) or not isinstance(event.action, Action):
            return None

        timestamp = self.get_current_time()

        function_name = event.function_name()
        app_class_name = event.app_class_name()

        if (
            hasattr(event.action, "app")
            and app_class_name == "PASAgentUserInterface"
            and function_name == "send_message_to_user"
        ):
            args: dict[str, Any] = get_args(event)
            message = str(
                AUIMessage(
                    sender=Sender.AGENT,
                    content=args["content"],
                    timestamp=timestamp,
                    time_read=timestamp,
                )
            )
            dumped_attachments: list[dict[str, Any]] = args.get("base64_utf8_encoded_attachment_contents") or []
            attachments: list[Attachment] = [Attachment.model_validate(attachment) for attachment in dumped_attachments]
            return Message(
                message_type=PASMessageType.AGENT_MESSAGE,
                message=message,
                timestamp=datetime.fromtimestamp(timestamp, tz=UTC),
                attachments=attachments,
            )
        elif (
            hasattr(event.action, "app")
            and app_class_name == "PASAgentUserInterface"
            and function_name in ("accept_proposal", "reject_proposal")
        ):
            args = get_args(event)
            dumped_attachments = args.get("base64_utf8_encoded_attachment_contents") or []
            attachments = [Attachment.model_validate(attachment) for attachment in dumped_attachments]
            content = args.get("content", "")
            content = f"[ACCEPT]: {content}" if function_name == "accept_proposal" else f"[REJECT]: {content}"
            message = str(
                AUIMessage(
                    sender=Sender.USER,
                    content=content,
                    timestamp=timestamp,
                    time_read=timestamp,
                )
            )
            return Message(
                message_type=PASMessageType.USER_MESSAGE,
                message=message,
                timestamp=datetime.fromtimestamp(timestamp, tz=UTC),
                attachments=attachments,
            )

        # Handle environment notification events
        message = get_content_for_message(event)
        if (
            app_class_name is not None
            and app_class_name in self.config.notified_tools
            and function_name in self.config.notified_tools[app_class_name]
            and message is not None
        ):
            return Message(
                message_type=PASMessageType.ENVIRONMENT_NOTIFICATION,
                message=message,
                timestamp=datetime.fromtimestamp(timestamp, tz=UTC),
            )

        return None
