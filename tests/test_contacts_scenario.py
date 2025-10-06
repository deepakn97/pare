from __future__ import annotations

import typing
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pytest import MonkeyPatch

from pas.proactive import InterventionResult
from pas.scenarios import build_contacts_followup_components, build_contacts_followup_task
from pas.tasks.types import TaskContext


@dataclass
class QueueLLM:
    responses: list[str]
    last_prompt: str | None = None

    def complete(self, prompt: str) -> str:
        self.last_prompt = prompt
        if not self.responses:
            raise RuntimeError("QueueLLM received more prompts than stubbed responses")
        return self.responses.pop(0)


def test_build_contacts_followup_components_sets_up_defaults(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    agent_llm = QueueLLM(["none"])
    user_llm = QueueLLM(['{"actions": [{"tool": "contacts.list_contacts", "args": {"offset": 0}}]}'])
    setup = build_contacts_followup_components(
        llm=agent_llm, user_llm=user_llm, max_user_turns=5, log_mode="overwrite", primary_app="contacts"
    )
    env, proxy, agent, _decision_maker = setup
    contacts_app = env.get_app("contacts")

    proxy.init_conversation()
    reply = proxy.reply("list contacts")
    assert "Completed" in reply
    assert contacts_app.get_contacts()["contacts"]
    assert agent.propose_goal() is None
    assert setup.oracle_actions


def test_llm_agent_uses_plan_executor_and_summary(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    user_llm = QueueLLM(['{"actions": [{"tool": "contacts.list_contacts", "args": {"offset": 0}}]}'])
    llm = QueueLLM([
        "Follow up with Alex Smith",
        '{"tool": "email.send_email", "args": {"recipients": ["alex.smith@example.com"], "subject": "Lunch follow-up", "content": "Shall we confirm the time?"}}',
    ])
    executed: list[str] = []

    def executor(task: str, _env: Any) -> InterventionResult:
        executed.append(task)
        return InterventionResult(success=True, notes=f"Executed: {task}")

    def plan_executor_factory(
        _llm: Any, _specs: Any, *, system_prompt: str, logger: Any
    ) -> typing.Callable[[str, Any], InterventionResult]:
        return executor

    monkeypatch.setattr("pas.scenarios.base.build_plan_executor", plan_executor_factory)
    setup = build_contacts_followup_components(
        llm=llm, user_llm=user_llm, max_user_turns=5, log_mode="overwrite", primary_app="contacts"
    )
    env, proxy, agent, _decision_maker = setup
    proxy.init_conversation()
    proxy.reply("list contacts")

    goal = agent.propose_goal()
    assert goal == "Follow up with Alex Smith"

    agent.record_decision(goal, True)
    result = agent.execute(goal, env)
    assert result.success
    assert executed == [goal]
    summary = agent.pop_summary()
    assert summary == f"Executed: {goal}"
    agent.handoff(env)
    assert setup.oracle_actions
    expected_recipient = setup.oracle_actions[0].args["recipients"][0]
    assert expected_recipient.endswith("@example.com")


def test_contacts_followup_task_definition(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    agent_llm = QueueLLM(["none"])
    user_llm = QueueLLM(['{"actions": []}'])

    task = build_contacts_followup_task()
    context = TaskContext(
        llm=agent_llm, user_llm=user_llm, max_user_turns=3, log_mode="overwrite", primary_app="contacts"
    )

    setup = task.scenario_builder(context)
    assert setup.oracle_actions
    assert setup.env.get_app("contacts")
