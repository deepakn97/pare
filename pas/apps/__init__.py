"""PAS applications extending Meta ARE with stateful navigation."""

from __future__ import annotations

from pas.apps.calendar.app import StatefulCalendarApp
from pas.apps.contacts.app import StatefulContactsApp
from pas.apps.core import AppState, StatefulApp
from pas.apps.email.app import StatefulEmailApp
from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.proactive_aui import PASAgentUserInterface
from pas.apps.system import HomeScreenSystemApp
from pas.apps.tool_decorators import user_tool

__all__ = [
    "AppState",
    "HomeScreenSystemApp",
    "PASAgentUserInterface",
    "StatefulApp",
    "StatefulCalendarApp",
    "StatefulContactsApp",
    "StatefulEmailApp",
    "StatefulMessagingApp",
    "user_tool",
]

ALL_APPS = [
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
    StatefulContactsApp,
    StatefulEmailApp,
    StatefulMessagingApp,
]
