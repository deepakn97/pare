"""PARE applications extending Meta ARE with stateful navigation."""

from __future__ import annotations

from are.simulation.apps import App

from pare.apps.apartment import StatefulApartmentApp
from pare.apps.cab import StatefulCabApp
from pare.apps.calendar.app import StatefulCalendarApp
from pare.apps.contacts.app import StatefulContactsApp
from pare.apps.core import AppState, StatefulApp
from pare.apps.email.app import StatefulEmailApp
from pare.apps.messaging.app import StatefulMessagingApp
from pare.apps.note import StatefulNotesApp
from pare.apps.proactive_aui import PAREAgentUserInterface
from pare.apps.reminder import StatefulReminderApp
from pare.apps.shopping import StatefulShoppingApp
from pare.apps.system import HomeScreenSystemApp
from pare.apps.tool_decorators import user_tool

__all__ = [
    "App",
    "AppState",
    "HomeScreenSystemApp",
    "PAREAgentUserInterface",
    "StatefulApartmentApp",
    "StatefulApp",
    "StatefulCabApp",
    "StatefulCalendarApp",
    "StatefulContactsApp",
    "StatefulEmailApp",
    "StatefulMessagingApp",
    "StatefulNotesApp",
    "StatefulReminderApp",
    "StatefulShoppingApp",
    "user_tool",
]

ALL_APPS = [
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulCalendarApp,
    StatefulContactsApp,
    StatefulEmailApp,
    StatefulShoppingApp,
    StatefulCabApp,
    StatefulApartmentApp,
    StatefulMessagingApp,
    StatefulNotesApp,
    StatefulReminderApp,
]
