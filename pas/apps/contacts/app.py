"""Stateful contacts app built on top of the Meta-ARE ContactsApp."""

from __future__ import annotations

from typing import Any

from are.simulation.apps.contacts import ContactsApp
from are.simulation.types import CompletedEvent

from pas.apps.contacts.states import ContactDetail, ContactEdit, ContactsList
from pas.apps.core import StatefulApp


class StatefulContactsApp(StatefulApp, ContactsApp):
    """Contacts application with explicit navigation states."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._pending_transition: tuple[str, str] | None = None
        super().__init__(*args, **kwargs)
        self.set_current_state(ContactsList())

    def queue_contact_transition(self, intent: str, contact_id: str) -> None:
        """Record a desired transition that should fire after the next contacts API call."""
        self._pending_transition = (intent, contact_id)

    def clear_contact_transition(self) -> None:
        """Reset any queued contact transition intent."""
        self._pending_transition = None

    def handle_state_transition(self, event: CompletedEvent) -> None:
        """Update navigation state based on completed contact operations."""
        function_name = event.function_name()
        if function_name is None:
            return

        # Extract args safely – event.action may be ConditionCheckAction in other contexts.
        event_args = {}
        if hasattr(event, "action") and getattr(event, "action") is not None:  # type: ignore[truthy-function]
            event_args = getattr(event.action, "args", {})  # type: ignore[attr-defined]

        match function_name:
            case "get_contact":
                self._handle_get_contact(event_args)
            case "edit_contact":
                self._handle_edit_contact(event_args)
            case "delete_contact":
                self._handle_delete_contact()
            case "get_contacts":
                self._handle_get_contacts()

    def _handle_get_contact(self, event_args: dict[str, Any]) -> None:
        contact_id = event_args.get("contact_id")
        if contact_id is None:
            return

        if self._pending_transition is not None:
            intent, intent_contact_id = self._pending_transition
            self.clear_contact_transition()

            # Only use queued intent if it matches the event's contact context.
            if intent_contact_id != contact_id:
                intent_contact_id = contact_id

            if intent == "detail":
                if not isinstance(self.current_state, ContactDetail) or self.current_state.contact_id != intent_contact_id:
                    self.set_current_state(ContactDetail(intent_contact_id))
            elif intent == "edit":
                if not isinstance(self.current_state, ContactEdit) or self.current_state.contact_id != intent_contact_id:
                    self.set_current_state(ContactEdit(intent_contact_id))
            return

        # Fallback: if we are still on the list and a contact is accessed directly, open the detail view.
        if isinstance(self.current_state, ContactsList):
            self.set_current_state(ContactDetail(contact_id))

    def _handle_edit_contact(self, event_args: dict[str, Any]) -> None:
        contact_id = event_args.get("contact_id")
        if contact_id is None:
            return

        # After saving edits we should return to the detail view.
        if isinstance(self.current_state, ContactEdit):
            # go_back returns to the previous detail state on the stack if present.
            if self.navigation_stack:
                self.go_back()

        if isinstance(self.current_state, ContactDetail):
            self.current_state.contact_id = contact_id
            self.clear_contact_transition()
        else:
            self.set_current_state(ContactDetail(contact_id))

    def _handle_delete_contact(self) -> None:
        self.clear_contact_transition()
        # Prefer using the navigation stack to respect user history
        if self.navigation_stack:
            self.go_back()
        else:
            self.set_current_state(ContactsList())

    def _handle_get_contacts(self) -> None:
        if not isinstance(self.current_state, ContactsList):
            self.set_current_state(ContactsList())
