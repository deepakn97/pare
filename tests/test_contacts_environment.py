"""Integration-style tests for contacts navigation via the environment wrapper."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from are.simulation.apps.contacts import Contact

from pas.apps.contacts.app import StatefulContactsApp
from pas.apps.contacts.states import ContactDetail, ContactEdit, ContactsList
from pas.environment import StateAwareEnvironmentWrapper

if TYPE_CHECKING:
    from collections.abc import Generator

    from are.simulation.types import CompletedEvent


def _last_event(env: StateAwareEnvironmentWrapper) -> CompletedEvent:
    """Fetch the most recent completed event recorded by the environment."""
    return cast("CompletedEvent", env.event_log.past_events[-1])


def _list_state(app: StatefulContactsApp) -> ContactsList:
    state = app.current_state
    assert isinstance(state, ContactsList)
    return state


def _detail_state(app: StatefulContactsApp) -> ContactDetail:
    state = app.current_state
    assert isinstance(state, ContactDetail)
    return state


def _edit_state(app: StatefulContactsApp) -> ContactEdit:
    state = app.current_state
    assert isinstance(state, ContactEdit)
    return state


@pytest.fixture()
def env_with_contacts() -> Generator[tuple[StateAwareEnvironmentWrapper, StatefulContactsApp], None, None]:
    """Provide an environment with a pre-populated contacts app."""
    env = StateAwareEnvironmentWrapper()
    app = StatefulContactsApp(name="contacts")
    app.add_contacts([
        Contact(first_name="Ada", last_name="Lovelace", contact_id="contact-ada", phone="111"),
        Contact(first_name="Grace", last_name="Hopper", contact_id="contact-grace", phone="222"),
        Contact(first_name="User", last_name="Persona", contact_id="contact-user", is_user=True, phone="000"),
    ])
    env.register_apps([app])
    yield env, app


class TestEnvironmentTransitions:
    """Verify that CompletedEvents routed through the environment drive state changes."""

    def test_get_contact_event_moves_to_detail(
        self, env_with_contacts: tuple[StateAwareEnvironmentWrapper, StatefulContactsApp]
    ) -> None:
        """Accessing a contact transitions from list view to detail view."""
        env, app = env_with_contacts

        _list_state(app).open_contact("contact-ada")
        env.add_to_log(_last_event(env))

        assert isinstance(app.current_state, ContactDetail)
        assert app.current_state.contact_id == "contact-ada"
        assert len(app.navigation_stack) == 1

    def test_start_edit_flow_enters_edit_state(
        self, env_with_contacts: tuple[StateAwareEnvironmentWrapper, StatefulContactsApp]
    ) -> None:
        """Starting an edit flow navigates into the edit state and records history."""
        env, app = env_with_contacts

        _list_state(app).open_contact("contact-ada")
        env.add_to_log(_last_event(env))

        _detail_state(app).start_edit_contact()
        env.add_to_log(_last_event(env))

        assert isinstance(app.current_state, ContactEdit)
        assert app.current_state.contact_id == "contact-ada"
        assert len(app.navigation_stack) == 2

    def test_edit_contact_returns_to_detail(
        self, env_with_contacts: tuple[StateAwareEnvironmentWrapper, StatefulContactsApp]
    ) -> None:
        """Saving edits returns the navigation stack to the detail view."""
        env, app = env_with_contacts

        _list_state(app).open_contact("contact-ada")
        env.add_to_log(_last_event(env))

        _detail_state(app).start_edit_contact()
        env.add_to_log(_last_event(env))

        _edit_state(app).update_contact({"phone": "999"})
        env.add_to_log(_last_event(env))

        assert isinstance(app.current_state, ContactDetail)
        assert app.current_state.contact_id == "contact-ada"
        assert len(app.navigation_stack) == 1

    def test_delete_contact_returns_to_list(
        self, env_with_contacts: tuple[StateAwareEnvironmentWrapper, StatefulContactsApp]
    ) -> None:
        """Deleting a contact navigates back to the list view and removes the entry."""
        env, app = env_with_contacts

        _list_state(app).open_contact("contact-ada")
        env.add_to_log(_last_event(env))

        _detail_state(app).delete_contact()
        env.add_to_log(_last_event(env))

        assert isinstance(app.current_state, ContactsList)
        assert len(app.navigation_stack) == 0
        assert "contact-ada" not in app.contacts

    def test_get_contacts_event_resets_to_list(
        self, env_with_contacts: tuple[StateAwareEnvironmentWrapper, StatefulContactsApp]
    ) -> None:
        """Refreshing contacts from a nested state resets the app to the list view."""
        env, app = env_with_contacts

        _list_state(app).open_contact("contact-ada")
        env.add_to_log(_last_event(env))
        app.get_contacts()
        env.add_to_log(_last_event(env))

        assert isinstance(app.current_state, ContactsList)

    def test_view_current_user_does_not_change_state(
        self, env_with_contacts: tuple[StateAwareEnvironmentWrapper, StatefulContactsApp]
    ) -> None:
        """Viewing the user contact leaves the navigation state unchanged."""
        env, app = env_with_contacts

        _list_state(app).view_current_user()
        env.add_to_log(_last_event(env))

        assert isinstance(app.current_state, ContactsList)
        assert len(app.navigation_stack) == 0
