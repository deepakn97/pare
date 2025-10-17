"""PAS applications extending Meta ARE with stateful navigation."""

from pas.apps.calendar.app import StatefulCalendarApp
from pas.apps.contacts.app import StatefulContactsApp
from pas.apps.core import AppState, StatefulApp
from pas.apps.email.app import StatefulEmailApp
from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.proactive_agent_ui import ProactiveAgentUserInterface
from pas.apps.system import HomeScreenSystemApp
from pas.apps.tool_decorators import user_tool

__all__ = [
    "AppState",
    "HomeScreenSystemApp",
    "ProactiveAgentUserInterface",
    "StatefulApp",
    "StatefulCalendarApp",
    "StatefulContactsApp",
    "StatefulEmailApp",
    "StatefulMessagingApp",
    "user_tool",
]
