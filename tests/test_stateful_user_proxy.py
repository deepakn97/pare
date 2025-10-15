from __future__ import annotations

import logging

import pytest
from are.simulation.apps.contacts import Contact, Gender, Status
from are.simulation.types import CompletedEvent, EventType
from pytest import MonkeyPatch

from pas.apps.contacts.app import StatefulContactsApp
from pas.apps.contacts.states import ContactDetail
from pas.environment import StateAwareEnvironmentWrapper
from pas.proactive import LLMClientProtocol
from pas.system.user import build_stateful_user_planner
from pas.user_proxy import StatefulUserProxy, TurnLimitReached


def _setup_contacts_env(
    max_turns: int = 2,
) -> tuple[StateAwareEnvironmentWrapper, StatefulContactsApp, StatefulUserProxy]:
    """Return a configured contacts environment and proxy."""
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
    """Proxy executes planner actions and surfaces resulting event."""
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
    """Proxy raises when exceeding configured turn allowance."""
    _env, _contacts, proxy = _setup_contacts_env(max_turns=1)
    proxy.init_conversation()
    proxy.reply("List contacts")
    with pytest.raises(TurnLimitReached):
        proxy.reply("Again")


def test_user_planner_exposes_go_back(monkeypatch: MonkeyPatch) -> None:
    """Planner includes go_back option once stack has history."""
    env = StateAwareEnvironmentWrapper()
    contacts = StatefulContactsApp(name="contacts")
    env.register_apps([contacts])

    contacts.add_contact(
        Contact(first_name="Ada", last_name="Lovelace", contact_id="contact-ada", phone="111", email="ada@example.com")
    )

    contacts.set_current_state(ContactDetail("contact-ada"))

    captured_names: list[str] = []

    class FakePlanner:
        def __init__(self, _llm: object, tools: list[object], *, system_prompt: str, logger: logging.Logger) -> None:
            del system_prompt, logger
            captured_names.clear()
            captured_names.extend(getattr(tool, "name", "") for tool in tools)

        def __call__(self, _message: str, _proxy: StatefulUserProxy) -> list[tuple[str, str, dict[str, object]]]:
            return []

    monkeypatch.setattr("pas.system.user.LLMUserPlanner", FakePlanner)

    class _StubLLM(LLMClientProtocol):  # pragma: no cover - simple stub
        def complete(self, prompt: str) -> str:
            return ""

    planner = build_stateful_user_planner(
        llm_client=_StubLLM(),
        apps=[contacts],
        initial_app_name="contacts",
        include_system_tools=False,
        logger=logging.getLogger("tests.user_planner"),
    )

    proxy_logger = logging.getLogger("tests.user_proxy.go_back")
    proxy_logger.setLevel(logging.DEBUG)
    proxy = StatefulUserProxy(env, env.notification_system, logger=proxy_logger, planner=None)

    planner("inspect", proxy)

    assert any(name.endswith(".go_back") for name in captured_names), "Expected go_back to be exposed to planner"
