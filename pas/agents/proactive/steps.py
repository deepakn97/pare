from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from are.simulation.agents.agent_log import EnvironmentNotificationLog
from are.simulation.agents.default_agent.base_agent import ConditionalStep

from pas.agents.agent_log import UserActionLog
from pas.notification_system import PASMessageType

if TYPE_CHECKING:
    from are.simulation.agents.default_agent.base_agent import BaseAgent
    from are.simulation.notification_system import Message

logger = logging.getLogger(__name__)


def format_notification(notif: Message) -> str:
    """Format notification with timestamp."""
    return f"[{notif.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {notif.message}"


def pull_proactive_agent_messages(agent: BaseAgent) -> None:
    """Pull USER_ACTIONS and ENVIRONMENT_NOTIFICATION from notification system."""
    # unhandled_notifications = agent.custom_state.get("notifications", [])
    unhandled_notifications = agent.notification_system.message_queue.get_by_timestamp(
        timestamp=datetime.fromtimestamp(agent.make_timestamp(), tz=UTC)
    )

    env_notifications = []
    user_actions = []
    for notification in unhandled_notifications:
        logger.debug(f"Proactive pre-step recieved: {notification.message_type}")
        if notification.message_type == PASMessageType.ENVIRONMENT_NOTIFICATION_AGENT:
            env_notifications.append(notification)
        elif notification.message_type == PASMessageType.USER_ACTION:
            user_actions.append(notification)

    # All the other messages should be reinserted into the notification system.
    # ! NOTE: Although by this point, all the messages should have been consumed I think.
    messages_to_put_back = [m for m in unhandled_notifications if m not in env_notifications + user_actions]
    for message in messages_to_put_back:
        agent.notification_system.message_queue.put(message)
    logger.debug(
        f"Proactive agent pre-step -> message types to put back: {'; '.join([m.message_type.value for m in messages_to_put_back])}"
    )

    if env_notifications:
        agent.append_agent_log(
            EnvironmentNotificationLog(
                content="\n".join(format_notification(notif) for notif in env_notifications),
                timestamp=agent.make_timestamp(),
                agent_id=agent.agent_id,
            )
        )
    if user_actions:
        agent.append_agent_log(
            UserActionLog(
                content="\n".join(format_notification(action) for action in user_actions),
                timestamp=agent.make_timestamp(),
                agent_id=agent.agent_id,
            )
        )


def get_proactive_agent_pre_step() -> ConditionalStep:
    """Return ConditionalStep for ProactiveAgent preprocessing."""
    return ConditionalStep(
        condition=None,
        function=pull_proactive_agent_messages,
        name="pull_proactive_agent_messages",
    )
