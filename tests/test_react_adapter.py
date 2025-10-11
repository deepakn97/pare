from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pas.proactive.react_adapter import react_intervention
from pas.scenarios import build_contacts_followup_components

if TYPE_CHECKING:
    from pytest import MonkeyPatch


class QueueLLM:
    """Mock LLM that returns pre-queued responses."""

    def __init__(self, responses: list[str]) -> None:
        """Initialize with a list of canned responses."""
        self._responses = responses

    def complete(self, prompt: str) -> str:
        """Return the next queued response."""
        if not self._responses:
            raise RuntimeError("QueueLLM ran out of responses")
        return self._responses.pop(0)


def test_react_intervention_executes_multiple_steps(monkeypatch: MonkeyPatch) -> None:
    """Test that the ReAct adapter executes multiple steps to complete a task."""
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")

    # First response triggers contacts search, second finalises with final answer.
    react_llm = QueueLLM([
        'Thought: I should look up Jordan\'s email.\nAction:\n{"action": "contacts__search_contacts", "action_input": {"query": "Jordan Lee"}}<end_action>',
        'Thought: I can now confirm completion.\nAction:\n{"action": "final_answer", "action_input": {"answer": "Email sent to jordan.lee@example.com"}}<end_action>',
    ])

    agent_llm = QueueLLM(["none"])
    user_llm = QueueLLM(['{"actions": []}'])

    env, _proxy, _agent, _decision_maker = build_contacts_followup_components(
        llm=agent_llm, user_llm=user_llm, max_user_turns=1, log_mode="overwrite", primary_app="messaging"
    )

    result = react_intervention(
        goal="Email Jordan Lee a summary of the launch timeline.",
        env=env,
        llm=react_llm,
        logger=logging.getLogger("test-react-adapter"),
        max_iterations=4,
    )

    assert result.success
    assert "jordan.lee@example.com" in result.notes
