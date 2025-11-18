from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

pytest.importorskip("are.simulation")

from are.simulation.apps.contacts import Contact, Gender, Status

from pas.apps.contacts.app import StatefulContactsApp
from pas.environment import StateAwareEnvironmentWrapper
from pas.user_proxy import StatefulUserAgent, StatefulUserAgentRuntime, ToolInvocation, TurnLimitReached


def _setup_contacts_env(
    max_turns: int = 2,
) -> tuple[StateAwareEnvironmentWrapper, StatefulContactsApp, StatefulUserAgentRuntime, StatefulUserAgent]:
    """Return a configured contacts environment, user agent, and proxy."""
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

    logger = logging.getLogger("tests.user_proxy")
    logger.setLevel(logging.DEBUG)

    user_tools = {}
    for tool in contacts.get_meta_are_user_tools():
        user_tools[tool.name] = tool

    def _stub_llm(*_args: object, **_kwargs: object) -> str:
        return "Stub response"

    agent = StatefulUserAgent(llm_engine=_stub_llm, tools=user_tools, max_turns=max_turns)

    runtime = StatefulUserAgentRuntime(
        agent=agent, notification_system=env.notification_system, logger=logger, max_user_turns=max_turns
    )
    env.register_user_agent(agent)
    env.subscribe_to_completed_events(runtime._on_event)
    # StatefulUserAgentRuntime now directly implements UserProxy
    return env, contacts, runtime, agent


def test_stateful_user_proxy_executes_tool_and_records_event() -> None:
    """Proxy executes planner actions and surfaces resulting event."""
    _env, _contacts, proxy, agent = _setup_contacts_env()
    proxy.init_conversation()

    def _mock_run(task: str, **_kwargs: object) -> str:
        agent.record_tool_invocation(
            ToolInvocation(app="contacts", method="list_contacts", args={}, result={"items": []}, event=None)
        )
        return "contacts.list_contacts -> done"

    with patch.object(agent, "run", side_effect=_mock_run):
        reply = proxy.reply("List contacts")

    assert "contacts.list_contacts" in reply

    invocations = proxy.last_tool_invocations
    assert len(invocations) == 1
    invocation = invocations[0]
    assert isinstance(invocation.result, dict)


def test_stateful_user_proxy_enforces_turn_limit() -> None:
    """Proxy raises when exceeding configured turn allowance."""
    _env, _contacts, proxy, agent = _setup_contacts_env(max_turns=1)
    proxy.init_conversation()
    with patch.object(agent, "run", return_value="ok"):
        proxy.reply("List contacts")
    with pytest.raises(TurnLimitReached), patch.object(agent, "run", return_value="ok"):
        proxy.reply("Again")
