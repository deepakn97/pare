from __future__ import annotations

import logging

import pytest
from are.simulation.apps.contacts import Contact, Gender, Status
from are.simulation.types import CompletedEvent, EventType

from pas.apps.contacts.app import StatefulContactsApp
from pas.environment import StateAwareEnvironmentWrapper
from pas.user_proxy import StatefulUserProxy, TurnLimitReached


def _setup_contacts_env(
    max_turns: int = 2,
) -> tuple[StateAwareEnvironmentWrapper, StatefulContactsApp, StatefulUserProxy]:
    env = StateAwareEnvironmentWrapper()
    contacts = StatefulContactsApp(name="contacts")
    env.register_apps([contacts])
    contacts.add_contact(
        Contact(
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.com",
            phone="+1-202-555-0182",
            gender=Gender.FEMALE,
            status=Status.EMPLOYED,
        )
    )

    def planner(_message: str, _proxy: StatefulUserProxy) -> list[tuple[str, str, dict[str, object]]]:
        return [("contacts", "list_contacts", {"offset": 0})]

    logger = logging.getLogger("tests.user_proxy")
    logger.setLevel(logging.DEBUG)

    proxy = StatefulUserProxy(env, env.notification_system, logger=logger, planner=planner, max_user_turns=max_turns)
    return env, contacts, proxy


def test_stateful_user_proxy_executes_tool_and_records_event() -> None:
    env, _contacts, proxy = _setup_contacts_env()
    proxy.init_conversation()

    captured: list[CompletedEvent] = []
    env.subscribe_to_completed_events(captured.append)

    reply = proxy.reply("List contacts")
    assert "contacts.list_contacts" in reply

    invocations = proxy.last_tool_invocations
    assert len(invocations) == 1
    invocation = invocations[0]
    if invocation.event is not None:
        assert invocation.event.event_type is EventType.USER
    assert isinstance(invocation.result, dict)
    # Ensure external subscriber saw the same event
    if invocation.event is not None:
        assert captured and captured[-1] is invocation.event


def test_stateful_user_proxy_enforces_turn_limit() -> None:
    _env, _contacts, proxy = _setup_contacts_env(max_turns=1)
    proxy.init_conversation()
    proxy.reply("List contacts")
    with pytest.raises(TurnLimitReached):
        proxy.reply("Again")
