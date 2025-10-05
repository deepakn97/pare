from __future__ import annotations

from typing import TYPE_CHECKING

from are.simulation.scenarios.scenario_tutorial.scenario import ScenarioTutorial

if TYPE_CHECKING:
    from pytest import MonkeyPatch

from pas.meta_adapter import build_meta_scenario_components, build_pas_contacts_meta_components


class StubLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses

    def complete(self, prompt: str) -> str:
        """Return the next canned response."""

        return self._responses.pop(0) if self._responses else "none"


def test_pas_contacts_meta_components_populates_message(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    llm = StubLLM(["none"])
    user_llm = StubLLM(['{"actions": []}'])

    env, _proxy, _agent, _decision_maker = build_pas_contacts_meta_components(
        llm=llm, user_llm=user_llm, max_user_turns=1, log_mode="overwrite", primary_app="messaging"
    )

    messaging = env.get_app("messaging")
    state = messaging.get_state()
    assert state["conversations"], "Expected seeded messaging conversation"


def test_meta_scenario_tutorial_conversion(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    llm = StubLLM(["none"])
    user_llm = StubLLM(['{"actions": []}'])

    scenario = ScenarioTutorial()
    env, _proxy, _agent, _decision_maker = build_meta_scenario_components(
        scenario, llm=llm, user_llm=user_llm, max_user_turns=1, log_mode="overwrite", primary_app="contacts"
    )

    assert "contacts" in env.apps
    contacts_state = env.get_app("contacts").get_contacts()
    assert contacts_state["contacts"], "Contacts should be populated from scenario"
