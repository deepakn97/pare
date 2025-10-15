from __future__ import annotations

from typing import TYPE_CHECKING

from are.simulation.scenarios.scenario_tutorial.scenario import ScenarioTutorial

if TYPE_CHECKING:
    from pytest import MonkeyPatch

from pas.meta_adapter import build_meta_scenario_components


class StubLLM:
    """Minimal queue-driven LLM stub used in meta adapter tests."""

    def __init__(self, responses: list[str]) -> None:
        """Initialise stub with the responses that should be returned in order."""
        self._responses = responses

    def complete(self, prompt: str) -> str:
        """Return the next canned response or 'none' if the queue is empty."""
        return self._responses.pop(0) if self._responses else "none"


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
