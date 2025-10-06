"""Run a single contacts scenario interaction and show log locations."""

from __future__ import annotations

import logging
import os
import typing
from pathlib import Path
from typing import Literal, cast

from dotenv import load_dotenv
from openai import OpenAI

from pas.proactive import LLMBasedProactiveAgent, LLMClientProtocol, OpenAILLMClient
from pas.scenarios import build_contacts_followup_components
from pas.system import ProactiveSession


class QueueLLM(LLMClientProtocol):
    """Simple queue-based LLM stub for offline demos."""

    def __init__(self, responses: list[str]) -> None:
        """Store a queue of predetermined responses."""
        self._responses = responses

    def complete(self, prompt: str) -> str:
        """Return the next canned response or a default placeholder."""
        return self._responses.pop(0) if self._responses else "none"


def _create_llm_clients() -> tuple[LLMClientProtocol, LLMClientProtocol, bool]:
    if os.getenv("OPENAI_API_KEY"):
        client = OpenAI()
        real_llm = OpenAILLMClient(client=client, default_parameters={})
        return real_llm, real_llm, False

    responses = [
        "Draft and send Jordan Lee a concise email summarizing the revised launch timeline before the client call.",
        'Thought: Locate Jordan Lee\'s email before drafting anything.\nAction:\n{"action": "contacts__search_contacts", "action_input": {"query": "Jordan Lee"}}<end_action>',
        'Thought: Send the summary now.\nAction:\n{"action": "email__send_email", "action_input": {"recipients": ["jordan.lee@example.com"], "subject": "Revised launch timeline", "content": "Summary of updated milestones before the client call."}}<end_action>',
        'Thought: Task complete.\nAction:\n{"action": "final_answer", "action_input": {"answer": "Email sent to jordan.lee@example.com"}}<end_action>',
    ]
    queue_llm = QueueLLM(responses)
    return queue_llm, QueueLLM(['{"actions": []}']), True


def run_demo(messages: typing.Iterable[str] | None = None, mode: Literal["event", "user"] = "event") -> None:
    """Execute a single scenario run and print high-level results plus log paths."""
    log_dir = (Path("logs") / "pas").resolve()
    load_dotenv(override=False)
    llm, user_llm, using_stub = _create_llm_clients()

    env, proxy, agent_protocol, decision_maker = build_contacts_followup_components(
        llm=llm, user_llm=user_llm, max_user_turns=25, log_mode="overwrite", primary_app="messaging"
    )
    agent = cast("LLMBasedProactiveAgent", agent_protocol)
    session_logger = logging.getLogger("pas.session.demo")
    session_logger.setLevel(logging.INFO)
    session = ProactiveSession(
        env, proxy, agent, decision_maker=decision_maker, confirm_goal=lambda goal: True, logger=session_logger
    )

    proxy.init_conversation()
    if mode == "event":
        event_prompt = proxy.consume_notifications()[0]
        reply = proxy.react_to_event(event_prompt)
        print(f"EVENT PROMPT: {event_prompt}")
        print(f"USER REPLY:  {reply}\n")

    if mode == "user":
        if messages is None:
            raise ValueError("messages must be provided when mode='user'")
        for message in messages:
            reply = proxy.reply(message)
            print(f"USER PROMPT: {message}")
            print(f"USER REPLY:  {reply}\n")

    cycle = session.run_cycle()
    print(f"PROPOSED GOAL: {cycle.goal}")
    if cycle.goal is not None and cycle.accepted:
        print(f"EXECUTION RESULT: {cycle.result}")
        print(f"SUMMARY: {cycle.summary}")
    else:
        print("No proactive intervention executed.")

    if using_stub:
        print("\n(Using stubbed LLM responses; set OPENAI_API_KEY to run with a live model.)")

    print("\nLogs written to:")
    for path in sorted(log_dir.glob("*.log")):
        print(f"  {path}")


if __name__ == "__main__":
    run_demo()
