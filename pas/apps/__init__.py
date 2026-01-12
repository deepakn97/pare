"""PAS applications extending Meta ARE with stateful navigation."""

from __future__ import annotations

from are.simulation.apps import App

from pas.apps.apartment import StatefulApartmentApp
from pas.apps.cab import StatefulCabApp
from pas.apps.calendar.app import StatefulCalendarApp
from pas.apps.contacts.app import StatefulContactsApp
from pas.apps.core import AppState, StatefulApp
from pas.apps.email.app import StatefulEmailApp
from pas.apps.food_delivery import StatefulFoodDeliveryApp
from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.note import StatefulNotesApp
from pas.apps.proactive_aui import PASAgentUserInterface
from pas.apps.reminder import StatefulReminderApp
from pas.apps.shopping import StatefulShoppingApp
from pas.apps.system import HomeScreenSystemApp
from pas.apps.tool_decorators import user_tool

__all__ = [
    "App",
    "AppState",
    "HomeScreenSystemApp",
    "PASAgentUserInterface",
    "StatefulApartmentApp",
    "StatefulApp",
    "StatefulCabApp",
    "StatefulCalendarApp",
    "StatefulContactsApp",
    "StatefulEmailApp",
    "StatefulFoodDeliveryApp",
    "StatefulMessagingApp",
    "StatefulNotesApp",
    "StatefulReminderApp",
    "StatefulShoppingApp",
    "user_tool",
]

ALL_APPS = [
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
    StatefulContactsApp,
    StatefulEmailApp,
    StatefulShoppingApp,
    StatefulCabApp,
    StatefulApartmentApp,
    StatefulMessagingApp,
    StatefulNotesApp,
    StatefulReminderApp,
    StatefulFoodDeliveryApp,
]
