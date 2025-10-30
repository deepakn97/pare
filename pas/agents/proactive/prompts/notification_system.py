from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from are.simulation.apps import App
    from are.simulation.notification_system import BaseNotificationSystem

NOTIFICATION_SYSTEM_PROMPTS = {
    "ProactiveObserve": textwrap.dedent(
        """
      Notification policy:
      - All user actions will be notified to you.
      - The environment state may also change over time, but environment events will not be notified to you.
      """
    ),
    "ProactiveObserveVerbose": textwrap.dedent(
        """
      Notification policy:
      - All user actions will be notified to you.
      - Whenever the environment is updated with any of the following tools, you will receive a notification: {notified_tools_list}.
      """
    ),
    "ProactiveExecute": textwrap.dedent(
        """
      Notification policy:
      - All user actions will be notified to you.
      - The environment state may also change over time, but environment events will not be notified to you.
      - You can proactively check for any other update in an App by using the tools given to you.
      """
    ),
    "ProactiveExecuteVerbose": textwrap.dedent(
        """
      Notification policy:
      - All user actions will be notified to you.
      - Whenever the environment is updated with any of the following tools, you will receive a notification: {notified_tools_list}.
      - You can proactively check for any other update in an App by using the tools given to you.
      """
    ),
}


def get_observe_notification_system_prompt(notification_system: BaseNotificationSystem, apps: list[App]) -> str:
    """Get notification prompt for proactive observe agent based on notification system config."""
    if len(notification_system.config.notified_tools) == 0:
        return NOTIFICATION_SYSTEM_PROMPTS["ProactiveObserve"]

    prompt_template = NOTIFICATION_SYSTEM_PROMPTS["ProactiveObserveVerbose"]
    notified_tools_list = []
    if apps:
        for app in apps:
            if app.name in notification_system.config.notified_tools:
                tools_to_add = notification_system.config.notified_tools[app.name]
                tools_to_add = [f"{app.name}__{tool}" for tool in tools_to_add]
                notified_tools_list.extend(tools_to_add)
    return prompt_template.format(notified_tools_list=", ".join(notified_tools_list))


def get_execute_notification_system_prompt(notification_system: BaseNotificationSystem, apps: list[App]) -> str:
    """Get notification prompt for proactive execute agent based on notification system config."""
    if len(notification_system.config.notified_tools) == 0:
        return NOTIFICATION_SYSTEM_PROMPTS["ProactiveExecute"]

    prompt_template = NOTIFICATION_SYSTEM_PROMPTS["ProactiveExecuteVerbose"]
    notified_tools_list = []
    if apps:
        for app in apps:
            if app.name in notification_system.config.notified_tools:
                tools_to_add = notification_system.config.notified_tools[app.name]
                tools_to_add = [f"{app.name}__{tool}" for tool in tools_to_add]
                notified_tools_list.extend(tools_to_add)
    return prompt_template.format(notified_tools_list=", ".join(notified_tools_list))
