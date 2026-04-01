"""Stateful contacts app package."""

from __future__ import annotations

from pare.apps.contacts.app import StatefulContactsApp
from pare.apps.contacts.states import ContactDetail, ContactEdit, ContactsList

__all__ = ["ContactDetail", "ContactEdit", "ContactsList", "StatefulContactsApp"]
