"""Run the Meta ARE tutorial scenario through the PAS proactive stack."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import cast

from are.simulation.scenarios.scenario_tutorial.scenario import ScenarioTutorial
from dotenv import load_dotenv
from openai import OpenAI

from pas.meta_adapter import build_meta_scenario_components
from pas.proactive import LLMBasedProactiveAgent, LLMClientProtocol, OpenAILLMClient
from pas.system import ProactiveSession


class QueueLLM(LLMClientProtocol):
    """Queue-based stub for offline demonstrations."""

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
        "Review the latest notifications and offer next steps to keep the user on track.",
        'Thought: I will summarize the outstanding to-dos and ask the user to confirm the next action.\nAction:\n{\n  "action": "final_answer",\n  "action_input": {\n    "answer": "Greg is waiting for the music PDF. Please confirm when you receive it so I can forward it to him."\n  }\n}<end_action>',
    ]
    return QueueLLM(responses), QueueLLM(['{"actions": []}']), True


def run_demo() -> None:
    """Execute the tutorial scenario once and print high-level results."""
    log_dir = (Path("logs") / "pas").resolve()
    load_dotenv(override=False)

    llm, user_llm, using_stub = _create_llm_clients()

    scenario = ScenarioTutorial()

    env, proxy, agent_protocol, decision_maker = build_meta_scenario_components(
        scenario, llm=llm, user_llm=user_llm, max_user_turns=25, log_mode="overwrite", primary_app="contacts"
    )
    agent = cast("LLMBasedProactiveAgent", agent_protocol)

    session_logger = logging.getLogger("pas.session.meta_tutorial")
    session_logger.setLevel(logging.INFO)
    session = ProactiveSession(
        env, proxy, agent, decision_maker=decision_maker, confirm_goal=lambda goal: True, logger=session_logger
    )

    proxy.init_conversation()
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
