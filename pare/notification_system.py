"""Notification system extensions that format PARE notifications."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from are.simulation.agents.multimodal import Attachment
from are.simulation.apps.agent_user_interface import AUIMessage, Sender
from are.simulation.notification_system import (
    Message,
    VerboseNotificationSystem,
    VerbosityLevel,
    get_args,
)
from are.simulation.types import AbstractEvent, Action, CompletedEvent, EventType
from jinja2 import Template, TemplateError

from pare.apps.notification_templates import NOTIFICATION_TEMPLATES

logger = logging.getLogger(__name__)


class PAREMessageType(Enum):
    """Extended MessageType enum system for PARE.

    AGENT_MESSAGE denotes any message sent by the agent to the user. This is important because user agent has to either accept or reject the agent's proposal.
    """

    AGENT_MESSAGE = "AGENT_MESSAGE"
    USER_MESSAGE = "USER_MESSAGE"
    USER_ACTION = "USER_ACTION"
    ENVIRONMENT_NOTIFICATION_USER = "ENVIRONMENT_NOTIFICATION_USER"
    ENVIRONMENT_NOTIFICATION_AGENT = "ENVIRONMENT_NOTIFICATION_AGENT"
    ENVIRONMENT_STOP = "ENVIRONMENT_STOP"


class PARENotificationSystem(VerboseNotificationSystem):
    """Notification system that formats PARE-specific notifications."""

    def __init__(self, verbosity_level: VerbosityLevel = VerbosityLevel.MEDIUM) -> None:
        """Initialize the PARE notification system.

        Args:
            verbosity_level: The verbosity level to use for the notification system.
        """
        super().__init__(verbosity_level=verbosity_level)
        if verbosity_level == VerbosityLevel.HIGH:
            self.notify_all = True

    def _split_message(self, message: Message) -> tuple[Message, Message]:
        """Split a message into a user and agent facing message."""
        user_message = replace(message, message_type=PAREMessageType.ENVIRONMENT_NOTIFICATION_USER)
        agent_message = replace(message, message_type=PAREMessageType.ENVIRONMENT_NOTIFICATION_AGENT)
        return user_message, agent_message

    def handle_event(self, event: AbstractEvent) -> None:
        """Override to handle tuple of messages.

        Add both user and agent facing environment notification messages to the message queue.
        """
        if not self._initialized:
            raise ValueError("Notification system is not initialized.")
        messages = self.convert_to_message(event)
        if messages is None:
            return
        user_message, agent_message = messages
        if user_message is not None:
            self.message_queue.put(user_message)
        if agent_message is not None:
            self.message_queue.put(agent_message)

    def handle_time_based_notifications(self) -> None:
        """Handle time-based notifications.

        Add both user and agent facing environment notification messages to the message queue.
        """
        if self.reminder_app:
            due_reminders = self.reminder_app.get_due_reminders()
            new_due_reminders = [reminder for reminder in due_reminders if not reminder.already_notified]
            if new_due_reminders:
                message = self.convert_reminders_to_message(new_due_reminders)
                if message is not None:
                    user_message, agent_message = self._split_message(message)
                    self.message_queue.put(user_message)
                    self.message_queue.put(agent_message)

    def handle_timeout_after_events(self) -> None:
        """Handle timeout notifications after all events in the current tick have been processed.

        This ensures that timeout notifications are only triggered if no other notifications
        were generated during the same tick.
        """
        current_timestamp = datetime.fromtimestamp(self.get_current_time(), tz=UTC)
        if self.system_app:
            if not self.message_queue.has_new_messages(timestamp=current_timestamp):
                wait_for_notification_timeout = self.system_app.get_wait_for_notification_timeout()
                if wait_for_notification_timeout is not None:
                    # Insert a wait for notification timeout message
                    message = self.convert_wait_for_notification_timeout_to_message(wait_for_notification_timeout)
                    if message is not None:
                        user_message, agent_message = self._split_message(message)
                        self.message_queue.put(user_message)
                        self.message_queue.put(agent_message)
                    self.system_app.reset_wait_for_notification_timeout()
            else:
                # If there are new messages, reset the wait for notification timeout
                self.system_app.reset_wait_for_notification_timeout()

    def convert_to_message(self, event: CompletedEvent) -> tuple[Message | None, Message | None] | None:
        """Convert a completed event to a notification message with PARE-specific formatting.

        Args:
            event: The completed event to convert to a notification message.

        Returns:
            The notification messages tuple for the user and the agent respectively.
        """
        if not isinstance(event, CompletedEvent) or not isinstance(event.action, Action):
            return None

        timestamp = self.get_current_time()

        function_name = event.function_name()
        app_class_name = event.app_class_name()
        event_type = event.event_type
        logger.debug(f"convert_to_message: app={app_class_name}, function={function_name}")

        if (
            hasattr(event.action, "app")
            and app_class_name == "PAREAgentUserInterface"
            and function_name == "send_message_to_user"
        ):
            args: dict[str, Any] = get_args(event)
            message = str(
                AUIMessage(
                    sender=Sender.AGENT,
                    content=args["content"],
                    timestamp=timestamp,
                )
            )
            dumped_attachments: list[dict[str, Any]] = args.get("base64_utf8_encoded_attachment_contents") or []
            attachments: list[Attachment] = [Attachment.model_validate(attachment) for attachment in dumped_attachments]
            logger.debug(f"Created Agent message: {message}")
            return (
                Message(
                    message_type=PAREMessageType.AGENT_MESSAGE,
                    message=message,
                    timestamp=datetime.fromtimestamp(timestamp, tz=UTC),
                    attachments=attachments,
                ),
                None,
            )
        elif (
            hasattr(event.action, "app")
            and app_class_name == "PAREAgentUserInterface"
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
                )
            )
            logger.debug(f"Created User message for accept/reject proposal: {message}")
            return (
                None,
                Message(
                    message_type=PAREMessageType.USER_MESSAGE,
                    message=message,
                    timestamp=datetime.fromtimestamp(timestamp, tz=UTC),
                    attachments=attachments,
                ),
            )
        elif (
            hasattr(event.action, "app")
            and app_class_name == "PAREAgentUserInterface"
            and function_name == "send_message_to_agent"
        ):
            args = get_args(event)
            dumped_attachments = args.get("base64_utf8_encoded_attachment_contents") or []
            attachments = [Attachment.model_validate(attachment) for attachment in dumped_attachments]
            content = args.get("content", "")
            message = str(
                AUIMessage(
                    sender=Sender.USER,
                    content=content,
                    timestamp=timestamp,
                    time_read=timestamp,
                )
            )
            logger.debug(f"Create User message for send_message_to_agent: {message}")
            return (
                None,
                Message(
                    message_type=PAREMessageType.USER_MESSAGE,
                    message=message,
                    timestamp=datetime.fromtimestamp(timestamp, tz=UTC),
                    attachments=attachments,
                ),
            )
        elif hasattr(event.action, "app") and event_type == EventType.USER:
            logger.info(f"USER ACTION DETECTED: {app_class_name}__{function_name}")
            args = get_args(event)
            args_str = ", ".join([f"{k}={v!r}" for k, v in args.items() if k != "self"])
            message = f"{app_class_name}__{function_name}({args_str})"
            logger.debug(f"Created User action message: {message}")
            return (
                None,
                Message(
                    message_type=PAREMessageType.USER_ACTION,
                    message=message,
                    timestamp=datetime.fromtimestamp(timestamp, tz=UTC),
                ),
            )

        # Handle environment notification events
        user_message = get_content_for_environment_message(event, "user")
        agent_message = get_content_for_environment_message(event, "agent")
        should_notify = getattr(self, "notify_all", False) or (
            app_class_name is not None
            and app_class_name in self.config.notified_tools
            and function_name in self.config.notified_tools[app_class_name]
            and user_message is not None
        )
        if should_notify:
            logger.debug(f"Created Environment notification message for user: {user_message}")
            logger.debug(f"Created Environment notification message for agent: {agent_message}")
            return (
                Message(
                    message_type=PAREMessageType.ENVIRONMENT_NOTIFICATION_USER,
                    message=user_message,
                    timestamp=datetime.fromtimestamp(timestamp, tz=UTC),
                ),
                Message(
                    message_type=PAREMessageType.ENVIRONMENT_NOTIFICATION_AGENT,
                    message=agent_message,
                    timestamp=datetime.fromtimestamp(timestamp, tz=UTC),
                ),
            )

        logger.debug("No handler matched.")
        return None


def get_content_for_environment_message(event: AbstractEvent, view: Literal["user", "agent"] = "user") -> str | None:
    """Format the event and return the contents for the LLM.

    Args:
        event: The event to format.
        view: The view to format the event for.
            - "user": The user view. Truncated content for the notification.
            - "agent": The agent view.

    Returns:
        The formatted event contents.
    """
    if type(event) is not CompletedEvent or type(event.action) is not Action:
        return None

    app_class_name = event.app_class_name()
    function_name = event.function_name()
    args = get_args(event)

    view_templates = NOTIFICATION_TEMPLATES.get(view, {})
    app_templates = view_templates.get(app_class_name, {})
    template_str = app_templates.get(function_name, None)

    if template_str is None:
        return None

    try:
        template = Template(template_str)
        return template.render({**args})
    except TemplateError as e:
        logger.exception(f"Error rendering template for {app_class_name}.{function_name}")
        return None
