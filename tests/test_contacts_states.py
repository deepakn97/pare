"""Tests for the stateful contacts app navigation flow."""

from collections.abc import Generator

import pytest

from are.simulation.apps.contacts import Contact
from are.simulation.types import Action, CompletedEvent, EventMetadata, EventType

from pas.apps.contacts.app import StatefulContactsApp
from pas.apps.contacts.states import ContactDetail, ContactEdit, ContactsList


def _make_event(app: StatefulContactsApp, func, **kwargs) -> CompletedEvent:
    """Utility to build a minimal CompletedEvent for state transition tests."""

    action = Action(function=func, args={"self": app, **kwargs}, app=app)
    return CompletedEvent(
        event_type=EventType.USER,
        action=action,
        metadata=EventMetadata(),
        event_time=0,
        event_id="test-event",
    )


@pytest.fixture()
def contacts_app() -> Generator[StatefulContactsApp, None, None]:
    """Create a contacts app populated with a couple of records for testing."""

    app = StatefulContactsApp(name="contacts")
    app.add_contacts(
        [
            Contact(
                first_name="Ada",
                last_name="Lovelace",
                contact_id="contact-ada",
                phone="111",
                email="ada@example.com",
            ),
            Contact(
                first_name="Grace",
                last_name="Hopper",
                contact_id="contact-grace",
                phone="222",
                email="grace@example.com",
            ),
            Contact(
                first_name="User",
                last_name="Persona",
                contact_id="contact-user",
                is_user=True,
                phone="000",
                email="user@example.com",
            ),
        ]
    )
    yield app


class TestInitialState:
    """Initialisation behaviour."""

    def test_app_starts_in_contacts_list(self, contacts_app: StatefulContactsApp) -> None:
        """App should boot into ContactsList with an empty navigation stack."""

        assert isinstance(contacts_app.current_state, ContactsList)
        assert contacts_app.navigation_stack == []


class TestStateTransitions:
    """State transition handling through CompletedEvent inputs."""

    def test_open_contact_moves_to_detail(self, contacts_app: StatefulContactsApp) -> None:
        """get_contact events should push the detail state for the requested contact."""

        contacts_app.current_state.open_contact("contact-ada")  # type: ignore[attr-defined]
        event = _make_event(contacts_app, contacts_app.get_contact, contact_id="contact-ada")
        contacts_app.handle_state_transition(event)

        assert isinstance(contacts_app.current_state, ContactDetail)
        assert contacts_app.current_state.contact_id == "contact-ada"
        assert len(contacts_app.navigation_stack) == 1
        assert isinstance(contacts_app.navigation_stack[0], ContactsList)

    def test_start_edit_contact_moves_to_edit_state(self, contacts_app: StatefulContactsApp) -> None:
        """Invoking start_edit_contact should switch to ContactEdit via get_contact."""

        contacts_app.current_state.open_contact("contact-ada")  # type: ignore[attr-defined]
        contacts_app.handle_state_transition(_make_event(contacts_app, contacts_app.get_contact, contact_id="contact-ada"))

        contacts_app.current_state.start_edit_contact()  # type: ignore[attr-defined]
        edit_prep_event = _make_event(contacts_app, contacts_app.get_contact, contact_id="contact-ada")
        contacts_app.handle_state_transition(edit_prep_event)

        assert isinstance(contacts_app.current_state, ContactEdit)
        assert contacts_app.current_state.contact_id == "contact-ada"
        # ContactsList (initial) and ContactDetail should now be on the stack
        assert len(contacts_app.navigation_stack) == 2
        assert isinstance(contacts_app.navigation_stack[0], ContactsList)
        assert isinstance(contacts_app.navigation_stack[1], ContactDetail)

    def test_edit_contact_returns_to_detail(self, contacts_app: StatefulContactsApp) -> None:
        """edit_contact events should drop back into ContactDetail for the same contact."""

        contacts_app.current_state.open_contact("contact-ada")  # type: ignore[attr-defined]
        contacts_app.handle_state_transition(_make_event(contacts_app, contacts_app.get_contact, contact_id="contact-ada"))

        contacts_app.current_state.start_edit_contact()  # type: ignore[attr-defined]
        contacts_app.handle_state_transition(_make_event(contacts_app, contacts_app.get_contact, contact_id="contact-ada"))

        contacts_app.current_state.update_contact({"phone": "999"})  # type: ignore[attr-defined]
        edit_event = _make_event(
            contacts_app,
            contacts_app.edit_contact,
            contact_id="contact-ada",
            updates={"phone": "999"},
        )
        contacts_app.handle_state_transition(edit_event)

        assert isinstance(contacts_app.current_state, ContactDetail)
        assert contacts_app.current_state.contact_id == "contact-ada"
        assert len(contacts_app.navigation_stack) == 1
        assert isinstance(contacts_app.navigation_stack[0], ContactsList)

    def test_delete_contact_returns_to_list(self, contacts_app: StatefulContactsApp) -> None:
        """delete_contact should restore the ContactsList state."""

        contacts_app.current_state.open_contact("contact-ada")  # type: ignore[attr-defined]
        contacts_app.handle_state_transition(_make_event(contacts_app, contacts_app.get_contact, contact_id="contact-ada"))

        contacts_app.current_state.delete_contact()  # type: ignore[attr-defined]
        delete_event = _make_event(contacts_app, contacts_app.delete_contact, contact_id="contact-ada")
        contacts_app.handle_state_transition(delete_event)

        assert isinstance(contacts_app.current_state, ContactsList)
        assert len(contacts_app.navigation_stack) == 0


class TestUserToolsFiltering:
    """Ensure only relevant user tools surface per state."""

    def _tool_names(self, contacts_app: StatefulContactsApp) -> list[str]:
        return [tool.name for tool in contacts_app.get_user_tools()]

    def test_contacts_list_tools(self, contacts_app: StatefulContactsApp) -> None:
        """ContactsList exposes list/search/open/create tools and hides go_back by default."""

        names = self._tool_names(contacts_app)
        assert any("list_contacts" in name for name in names)
        assert any("search_contacts" in name for name in names)
        assert any("open_contact" in name for name in names)
        assert any("create_contact" in name for name in names)
        assert any("view_current_user" in name for name in names)
        assert not any("update_contact" in name for name in names)
        assert not any("go_back" in name for name in names)

    def test_view_current_user_tool_returns_contact(self, contacts_app: StatefulContactsApp) -> None:
        """ContactsList view_current_user should surface the user persona contact."""

        result = contacts_app.current_state.view_current_user()  # type: ignore[attr-defined]
        assert isinstance(result, Contact)
        assert result.contact_id == "contact-user"

    def test_contact_detail_tools(self, contacts_app: StatefulContactsApp) -> None:
        """ContactDetail exposes view/delete/edit actions and enables go_back."""

        contacts_app.current_state.open_contact("contact-ada")  # type: ignore[attr-defined]
        contacts_app.handle_state_transition(_make_event(contacts_app, contacts_app.get_contact, contact_id="contact-ada"))
        names = self._tool_names(contacts_app)

        assert any("view_contact" in name for name in names)
        assert any("delete_contact" in name for name in names)
        assert any("start_edit_contact" in name for name in names)
        assert any("go_back" in name for name in names)
        assert not any("list_contacts" in name for name in names)

    def test_contact_edit_tools(self, contacts_app: StatefulContactsApp) -> None:
        """ContactEdit exposes update helpers and keeps go_back enabled."""

        contacts_app.current_state.open_contact("contact-ada")  # type: ignore[attr-defined]
        contacts_app.handle_state_transition(_make_event(contacts_app, contacts_app.get_contact, contact_id="contact-ada"))
        contacts_app.current_state.start_edit_contact()  # type: ignore[attr-defined]
        contacts_app.handle_state_transition(_make_event(contacts_app, contacts_app.get_contact, contact_id="contact-ada"))

        names = self._tool_names(contacts_app)
        assert any("update_contact" in name for name in names)
        assert any("view_contact" in name for name in names)
        assert not any("create_contact" in name for name in names)
        assert any("go_back" in name for name in names)
