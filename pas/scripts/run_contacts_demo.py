"""Run a single contacts scenario interaction and show log locations."""

from __future__ import annotations

import logging
import typing
from pathlib import Path
from typing import Literal, cast

from dotenv import load_dotenv
from openai import OpenAI

from pas.proactive import LLMBasedProactiveAgent, OpenAILLMClient
from pas.scenarios import build_contacts_followup_components
from pas.system import ProactiveSession


def run_demo(messages: typing.Iterable[str] | None = None, mode: Literal["event", "user"] = "event") -> None:
    """Execute a single scenario run and print high-level results plus log paths."""
    log_dir = (Path("logs") / "pas").resolve()
    load_dotenv(override=False)
    client = OpenAI()
    llm = OpenAILLMClient(client=client, default_parameters={})
    user_llm = OpenAILLMClient(client=client, default_parameters={})

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

    print("\nLogs written to:")
    for path in sorted(log_dir.glob("*.log")):
        print(f"  {path}")


if __name__ == "__main__":
    run_demo()
