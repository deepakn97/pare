from __future__ import annotations

from typing import TYPE_CHECKING

from are.simulation.apps.email_client import EmailFolderName

from pas.proactive import InterventionResult
from pas.scenarios import build_contacts_followup_components


class QueueLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.last_prompt: str | None = None

    def complete(self, prompt: str) -> str:
        self.last_prompt = prompt
        if not self._responses:
            raise RuntimeError("QueueLLM received more prompts than responses")
        return self._responses.pop(0)


if TYPE_CHECKING:
    from pytest import MonkeyPatch


def test_llm_plan_executor_sends_email(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")

    user_llm = QueueLLM(['{"actions": [{"tool": "contacts.list_contacts", "args": {"offset": 0}}]}'])
    llm = QueueLLM([
        "Send a follow-up email to Alex Smith about planning lunch.",
        '{"tool": "email.send_email", "args": {"recipients": ["alex.smith@example.com"], "subject": "Lunch follow-up", "content": "Shall we confirm the time?"}}',
    ])

    env, proxy, agent, _decision_maker = build_contacts_followup_components(
        llm=llm, user_llm=user_llm, max_user_turns=5, log_mode="overwrite", primary_app="contacts"
    )
    proxy.init_conversation()
    proxy.reply("list contacts")

    goal = agent.propose_goal()
    assert goal is not None
    assert "follow-up" in goal.lower()

    agent.record_decision(goal, True)
    result = agent.execute(goal, env)
    assert isinstance(result, InterventionResult)
    assert result.success

    email_app = env.get_app("email")
    sent_emails = email_app.folders[EmailFolderName.SENT].emails
    assert sent_emails, "Expected orchestrator to send an email"
    sent_email = sent_emails[0]
    assert "alex.smith@example.com" in sent_email.recipients[0]
    assert sent_email.subject == "Lunch follow-up"
    assert "confirm the time" in sent_email.content
