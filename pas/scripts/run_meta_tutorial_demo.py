"""Run the Meta ARE tutorial scenario through the PAS proactive stack."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

from are.simulation.scenarios.scenario_tutorial.scenario import ScenarioTutorial
from dotenv import load_dotenv
from openai import OpenAI

from pas.meta_adapter import build_meta_scenario_components
from pas.proactive import LLMBasedProactiveAgent, OpenAILLMClient
from pas.system import ProactiveSession


def run_demo() -> None:
    """Execute the tutorial scenario once and print high-level results."""
    log_dir = (Path("logs") / "pas").resolve()
    load_dotenv(override=False)
    client = OpenAI()
    llm = OpenAILLMClient(client=client, default_parameters={})
    user_llm = OpenAILLMClient(client=client, default_parameters={})

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

    print("\nLogs written to:")
    for path in sorted(log_dir.glob("*.log")):
        print(f"  {path}")


if __name__ == "__main__":
    run_demo()
