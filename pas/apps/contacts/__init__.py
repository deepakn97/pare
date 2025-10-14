"""Stateful contacts app package."""

from __future__ import annotations

from pas.apps.contacts.app import StatefulContactsApp
from pas.apps.contacts.states import ContactDetail, ContactEdit, ContactsList

__all__ = ["ContactDetail", "ContactEdit", "ContactsList", "StatefulContactsApp"]
