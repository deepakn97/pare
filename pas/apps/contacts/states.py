"""Navigation states for the stateful contacts app."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from are.simulation.apps.contacts import Contact  # noqa: TC002
from are.simulation.tool_utils import user_tool

from pas.apps.core import AppState

if TYPE_CHECKING:
    from pas.apps.contacts.app import StatefulContactsApp


class ContactsList(AppState):
    """Initial navigation state showing the list of contacts."""

    def __init__(self) -> None:
        """Initialise the list state."""
        super().__init__()

    def on_enter(self) -> None:
        """No-op hook for entering the contacts list."""

    def on_exit(self) -> None:
        """No-op hook for exiting the contacts list."""

    @user_tool()
    def list_contacts(self, offset: int = 0) -> dict[str, object]:
        """List contacts using the native paginated API."""
        app = cast("StatefulContactsApp", self.app)
        return app.get_contacts(offset=offset)

    @user_tool()
    def search_contacts(self, query: str) -> list[Contact]:
        """Search contacts by name, phone or email."""
        app = cast("StatefulContactsApp", self.app)
        return app.search_contacts(query=query)

    @user_tool()
    def open_contact(self, contact_id: str) -> Contact:
        """Open a contact from the list, queuing a transition to the detail view."""
        app = cast("StatefulContactsApp", self.app)
        app.queue_contact_transition("detail", contact_id)
        return app.get_contact(contact_id=contact_id)

    @user_tool()
    def view_current_user(self) -> Contact:
        """View the contact card for the current user persona."""
        app = cast("StatefulContactsApp", self.app)
        return app.get_current_user_details()

    @user_tool()
    def create_contact(
        self,
        first_name: str,
        last_name: str,
        gender: str | None = None,
        age: int | None = None,
        nationality: str | None = None,
        city_living: str | None = None,
        country: str | None = None,
        status: str | None = None,
        job: str | None = None,
        description: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        address: str | None = None,
    ) -> str:
        """Create a new contact and return its identifier."""
        app = cast("StatefulContactsApp", self.app)
        return app.add_new_contact(
            first_name=first_name,
            last_name=last_name,
            gender=gender,
            age=age,
            nationality=nationality,
            city_living=city_living,
            country=country,
            status=status,
            job=job,
            description=description,
            phone=phone,
            email=email,
            address=address,
        )


class ContactDetail(AppState):
    """State for viewing a specific contact's details."""

    def __init__(self, contact_id: str) -> None:
        """Bind the detail view to the supplied contact identifier."""
        super().__init__()
        self.contact_id = contact_id

    def on_enter(self) -> None:
        """No-op hook for detail entry; data retrieval happens via user tools."""

    def on_exit(self) -> None:
        """Clear any queued edit intents when leaving detail view."""
        app = cast("StatefulContactsApp", self.app)
        app.clear_contact_transition()

    @user_tool()
    def view_contact(self) -> Contact:
        """Retrieve the currently opened contact."""
        app = cast("StatefulContactsApp", self.app)
        return app.get_contact(contact_id=self.contact_id)

    @user_tool()
    def start_edit_contact(self) -> Contact:
        """Queue an edit transition and return the latest contact data."""
        app = cast("StatefulContactsApp", self.app)
        app.queue_contact_transition("edit", self.contact_id)
        return app.get_contact(contact_id=self.contact_id)

    @user_tool()
    def delete_contact(self) -> str:
        """Delete the currently opened contact."""
        app = cast("StatefulContactsApp", self.app)
        return app.delete_contact(contact_id=self.contact_id)


class ContactEdit(AppState):
    """State representing the contact edit surface."""

    def __init__(self, contact_id: str) -> None:
        """Initialise the edit state for a particular contact."""
        super().__init__()
        self.contact_id = contact_id

    def on_enter(self) -> None:
        """No special entry behaviour for the edit form."""

    def on_exit(self) -> None:
        """Clear edit-specific transition intent when leaving the edit view."""
        app = cast("StatefulContactsApp", self.app)
        app.clear_contact_transition()

    @user_tool()
    def view_contact(self) -> Contact:
        """Read the contact being edited without leaving edit mode."""
        app = cast("StatefulContactsApp", self.app)
        return app.get_contact(contact_id=self.contact_id)

    @user_tool()
    def update_contact(self, updates: dict[str, object]) -> str | None:
        """Persist updates to the contact and stay in edit mode until a transition occurs."""
        app = cast("StatefulContactsApp", self.app)
        return app.edit_contact(contact_id=self.contact_id, updates=updates)
