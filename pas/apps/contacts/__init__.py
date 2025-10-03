"""Stateful contacts app package."""

from pas.apps.contacts.app import StatefulContactsApp
from pas.apps.contacts.states import ContactDetail, ContactEdit, ContactsList

__all__ = [
    "StatefulContactsApp",
    "ContactsList",
    "ContactDetail",
    "ContactEdit",
]
