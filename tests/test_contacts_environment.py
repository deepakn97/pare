"""Integration-style tests for contacts navigation via the environment wrapper."""

from collections.abc import Generator

import pytest

from are.simulation.apps.contacts import Contact

from pas.apps.contacts.app import StatefulContactsApp
from pas.apps.contacts.states import ContactDetail, ContactEdit, ContactsList
from pas.environment import StateAwareEnvironmentWrapper


def _last_event(env: StateAwareEnvironmentWrapper):
    """Fetch the most recent completed event recorded by the environment."""

    return env.event_log.past_events[-1]


@pytest.fixture()
def env_with_contacts() -> Generator[tuple[StateAwareEnvironmentWrapper, StatefulContactsApp], None, None]:
    """Provide an environment with a pre-populated contacts app."""

    env = StateAwareEnvironmentWrapper()
    app = StatefulContactsApp(name="contacts")
    app.add_contacts(
        [
            Contact(first_name="Ada", last_name="Lovelace", contact_id="contact-ada", phone="111"),
            Contact(first_name="Grace", last_name="Hopper", contact_id="contact-grace", phone="222"),
            Contact(
                first_name="User",
                last_name="Persona",
                contact_id="contact-user",
                is_user=True,
                phone="000",
            ),
        ]
    )
    env.register_apps([app])
    yield env, app


class TestEnvironmentTransitions:
    """Verify that CompletedEvents routed through the environment drive state changes."""

    def test_get_contact_event_moves_to_detail(self, env_with_contacts: tuple[StateAwareEnvironmentWrapper, StatefulContactsApp]) -> None:
        env, app = env_with_contacts

        app.current_state.open_contact("contact-ada")  # type: ignore[attr-defined]
        env.handle_completed_event(_last_event(env))

        assert isinstance(app.current_state, ContactDetail)
        assert app.current_state.contact_id == "contact-ada"
        assert len(app.navigation_stack) == 1

    def test_start_edit_flow_enters_edit_state(self, env_with_contacts: tuple[StateAwareEnvironmentWrapper, StatefulContactsApp]) -> None:
        env, app = env_with_contacts

        app.current_state.open_contact("contact-ada")  # type: ignore[attr-defined]
        env.handle_completed_event(_last_event(env))

        app.current_state.start_edit_contact()  # type: ignore[attr-defined]
        env.handle_completed_event(_last_event(env))

        assert isinstance(app.current_state, ContactEdit)
        assert app.current_state.contact_id == "contact-ada"
        assert len(app.navigation_stack) == 2

    def test_edit_contact_returns_to_detail(self, env_with_contacts: tuple[StateAwareEnvironmentWrapper, StatefulContactsApp]) -> None:
        env, app = env_with_contacts

        app.current_state.open_contact("contact-ada")  # type: ignore[attr-defined]
        env.handle_completed_event(_last_event(env))

        app.current_state.start_edit_contact()  # type: ignore[attr-defined]
        env.handle_completed_event(_last_event(env))

        app.current_state.update_contact({"phone": "999"})  # type: ignore[attr-defined]
        env.handle_completed_event(_last_event(env))

        assert isinstance(app.current_state, ContactDetail)
        assert app.current_state.contact_id == "contact-ada"
        assert len(app.navigation_stack) == 1

    def test_delete_contact_returns_to_list(self, env_with_contacts: tuple[StateAwareEnvironmentWrapper, StatefulContactsApp]) -> None:
        env, app = env_with_contacts

        app.current_state.open_contact("contact-ada")  # type: ignore[attr-defined]
        env.handle_completed_event(_last_event(env))

        app.current_state.delete_contact()  # type: ignore[attr-defined]
        env.handle_completed_event(_last_event(env))

        assert isinstance(app.current_state, ContactsList)
        assert len(app.navigation_stack) == 0
        assert "contact-ada" not in app.contacts

    def test_get_contacts_event_resets_to_list(self, env_with_contacts: tuple[StateAwareEnvironmentWrapper, StatefulContactsApp]) -> None:
        env, app = env_with_contacts

        app.current_state.open_contact("contact-ada")  # type: ignore[attr-defined]
        env.handle_completed_event(_last_event(env))
        app.get_contacts()
        env.handle_completed_event(_last_event(env))

        assert isinstance(app.current_state, ContactsList)

    def test_view_current_user_does_not_change_state(self, env_with_contacts: tuple[StateAwareEnvironmentWrapper, StatefulContactsApp]) -> None:
        env, app = env_with_contacts

        app.current_state.view_current_user()  # type: ignore[attr-defined]
        env.handle_completed_event(_last_event(env))

        assert isinstance(app.current_state, ContactsList)
        assert len(app.navigation_stack) == 0
