from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from are.simulation.agents.agent_log import BaseAgentLog, EnvironmentNotificationLog
from are.simulation.agents.default_agent.base_agent import ConditionalStep
from are.simulation.tool_box import DEFAULT_TOOL_DESCRIPTION_TEMPLATE, Toolbox

from pas.agents.agent_log import USER_AGENT_DYNAMIC_LOG_TYPES, AgentMessageLog, AvailableToolsLog, CurrentAppStateLog
from pas.notification_system import PASMessageType

if TYPE_CHECKING:
    from are.simulation.agents.default_agent.base_agent import BaseAgent
    from are.simulation.notification_system import Message

logger = logging.getLogger(__name__)


def format_notification(notif: Message) -> str:
    """Format notification with timestamp."""
    return f"[{notif.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {notif.message}"


def _filter_dynamic_logs(logs: list[BaseAgentLog]) -> list[BaseAgentLog]:
    """Filter dynamic logs to keep only the latest instance of dynamic log types."""
    latest_dynamic_indices: dict[str, int] = {}
    for i, log in enumerate(logs):
        log_type = log.get_type()
        if log_type in USER_AGENT_DYNAMIC_LOG_TYPES:
            latest_dynamic_indices[log_type] = i

    logs = [
        log
        for i, log in enumerate(logs)
        if log.get_type() not in USER_AGENT_DYNAMIC_LOG_TYPES or latest_dynamic_indices.get(log.get_type(), -1) == i
    ]
    return logs


def pull_notifications_and_tools(agent: BaseAgent) -> None:
    """Pull AGENT_MESSAGE and ENVIRONMENT_NOTIFICATION from notification system."""
    # unhandled_notifications = agent.custom_state.get("notifications", [])

    unhandled_notifications = agent.notification_system.message_queue.get_by_timestamp(
        timestamp=datetime.fromtimestamp(agent.make_timestamp(), tz=UTC)
    )

    agent_messages = []
    env_notifications = []
    for notification in unhandled_notifications:
        if notification.message_type == PASMessageType.AGENT_MESSAGE:
            agent_messages.append(notification)
        elif notification.message_type == PASMessageType.ENVIRONMENT_NOTIFICATION_USER:
            env_notifications.append(notification)

    # All the other messages should be reinserted into the notification system.
    messages_to_put_back = [m for m in unhandled_notifications if m not in agent_messages + env_notifications]
    for message in messages_to_put_back:
        agent.notification_system.message_queue.put(message)
    logger.debug(
        f"User agent pre-step -> message types to put back: {'; '.join([m.message_type.value for m in messages_to_put_back])}"
    )

    if agent_messages:
        agent.append_agent_log(
            AgentMessageLog(
                content="\n".join(msg.message for msg in agent_messages),
                timestamp=agent.make_timestamp(),
                agent_id=agent.agent_id,
            )
        )

    if env_notifications:
        agent.append_agent_log(
            EnvironmentNotificationLog(
                content="\n".join(format_notification(notif) for notif in env_notifications),
                timestamp=agent.make_timestamp(),
                agent_id=agent.agent_id,
            )
        )

    # Add currently available tools to the agent log.
    current_tools = list(agent.tools.values())
    if current_tools:
        toolbox = Toolbox(tools=current_tools)
        tool_descriptions = toolbox.show_tool_descriptions(DEFAULT_TOOL_DESCRIPTION_TEMPLATE)
        agent.append_agent_log(
            AvailableToolsLog(
                content=tool_descriptions,
                timestamp=agent.make_timestamp(),
                agent_id=agent.agent_id,
            )
        )

    # Add active app information to the agent log.
    current_app = agent.custom_state.get("current_app", None)
    current_state = agent.custom_state.get("current_state", None)

    if current_app:
        app_info = f"Current active app: {current_app.name}\n"
        if current_state:
            app_info += f"Current active state: {current_state.__class__.__name__}\n"
        agent.append_agent_log(
            CurrentAppStateLog(
                content=app_info,
                timestamp=agent.make_timestamp(),
                agent_id=agent.agent_id,
            )
        )
    agent.logs = _filter_dynamic_logs(agent.logs)


def get_user_agent_pre_step() -> ConditionalStep:
    """Return ConditionalStep for UserAgent preprocessing."""
    return ConditionalStep(
        condition=None,
        function=pull_notifications_and_tools,
        name="pull_notifications_and_tools",
    )
