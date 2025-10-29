from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from are.simulation.apps import App
    from are.simulation.notification_system import BaseNotificationSystem

    from pas.apps import StatefulApp

USER_AGENT_NOTIFICATION_PROMPT = textwrap.dedent(
    """
  Notification policy:
  - All new messages from other agents (including the proactive assistant) will be notified to you.
  - Environment events (such as incoming messages, emails, etc.) will be notified to you.
  - You can proactively check for updates in any App by using the available apps and navigating through them.
  - You are a human user, so you can interact with the environment in a natural way. For example, if you are in contacts app right now, you cannot directly check the emails. You need to open the emails app to check the emails.
  """
)


def get_notification_system_prompt(notification_system: BaseNotificationSystem, apps: list[StatefulApp | App]) -> str:
    """Get notification prompt for user agent based on notification system config.

    Note: We always return the generic prompt for UserAgent because:
    - Tool availability is state-dependent and communicated via BaseAgent's tools parameter
    - Listing specific tool names would leak information about unreached states
    - The notification policy describes event delivery behavior, not tool availability

    Args:
        notification_system: The notification system configuration (unused but kept for API consistency).
        apps: List of apps in the scenario (unused but kept for API consistency).

    Returns:
        Generic notification policy prompt for UserAgent.
    """
    return USER_AGENT_NOTIFICATION_PROMPT
