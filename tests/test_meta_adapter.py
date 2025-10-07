from __future__ import annotations

from typing import TYPE_CHECKING

from are.simulation.scenarios.scenario_tutorial.scenario import ScenarioTutorial

if TYPE_CHECKING:
    from pytest import MonkeyPatch

from pas.meta_adapter import build_meta_scenario_components, build_meta_task_from_scenario
from pas.scenarios.contacts_followup import build_pas_contacts_meta_components
from pas.tasks.types import TaskContext


class StubLLM:
    """Minimal queue-driven LLM stub used in meta adapter tests."""

    def __init__(self, responses: list[str]) -> None:
        """Initialise stub with the responses that should be returned in order."""
        self._responses = responses

    def complete(self, prompt: str) -> str:
        """Return the next canned response or 'none' if the queue is empty."""
        return self._responses.pop(0) if self._responses else "none"


def test_pas_contacts_meta_components_populates_message(monkeypatch: MonkeyPatch) -> None:
    """Ensure PAS-flavoured scenario seeds messaging app and oracle correctly."""
    monkeypatch.setenv("OPENAI_API_KEY", "")
    llm = StubLLM(["none"])
    user_llm = StubLLM(['{"actions": []}'])

    setup = build_pas_contacts_meta_components(
        llm=llm, user_llm=user_llm, max_user_turns=1, log_mode="overwrite", primary_app="messaging"
    )
    env, _proxy, _agent, _decision_maker = setup

    messaging = env.get_app("messaging")
    state = messaging.get_state()
    assert state["conversations"], "Expected seeded messaging conversation"
    assert setup.oracle_actions
    contact_oracle = setup.oracle_actions[0]
    assert contact_oracle.app == "email"
    assert "jordan.lee@example.com" in contact_oracle.args.get("recipients", [])


def test_meta_scenario_tutorial_conversion(monkeypatch: MonkeyPatch) -> None:
    """Ensure Meta tutorial scenarios convert into PAS components with oracles."""
    monkeypatch.setenv("OPENAI_API_KEY", "")
    llm = StubLLM(["none"])
    user_llm = StubLLM(['{"actions": []}'])

    scenario = ScenarioTutorial()
    setup = build_meta_scenario_components(
        scenario, llm=llm, user_llm=user_llm, max_user_turns=1, log_mode="overwrite", primary_app="contacts"
    )
    env, _proxy, _agent, _decision_maker = setup

    assert "contacts" in env.apps
    contacts_state = env.get_app("contacts").get_contacts()
    assert contacts_state["contacts"], "Contacts should be populated from scenario"
    assert setup.oracle_actions
    oracle = setup.oracle_actions[0]
    assert oracle.app == "email"
    assert oracle.function == "forward_email"
    assert oracle.args.get("recipients") == ["johndoe@example.com"]


def test_build_meta_task_from_scenario(monkeypatch: MonkeyPatch) -> None:
    """Meta task factory should expose oracle actions when invoked via TaskDefinition."""
    monkeypatch.setenv("OPENAI_API_KEY", "")
    llm = StubLLM(["none"])
    user_llm = StubLLM(['{"actions": []}'])

    task = build_meta_task_from_scenario(
        scenario_factory=ScenarioTutorial,
        task_id="tutorial",
        description="Transfer music list to John",
        primary_app="contacts",
    )

    context = TaskContext(llm=llm, user_llm=user_llm, max_user_turns=1, log_mode="overwrite", primary_app="contacts")

    setup = task.scenario_builder(context)
    assert setup.oracle_actions
    oracle = setup.oracle_actions[0]
    assert oracle.function in {"forward_email", "send_email"}
