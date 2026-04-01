"""Shared helpers to assemble PAS proactive runtime stacks."""

from __future__ import annotations

import logging
import typing as t
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from are.simulation.agents.default_agent.default_tools import FinalAnswerTool
from are.simulation.notification_system import VerbosityLevel

from pas.apps.core import StatefulApp
from pas.apps.proactive_agent_ui import ProactiveAgentUserInterface
from pas.apps.system import HomeScreenSystemApp
from pas.llm_adapter import PasLLMEngine
from pas.logging_utils import get_pas_file_logger
from pas.proactive import LLMBasedProactiveAgent
from pas.scenarios.types import OracleAction, ScenarioSetup
from pas.system import (
    attach_event_logging,
    build_plan_executor,
    create_environment,
    create_notification_system,
    initialise_runtime,
)
from pas.user_proxy import StatefulUserAgent, StatefulUserAgentRuntime

if TYPE_CHECKING:
    from pas.proactive import LLMClientProtocol


def build_proactive_stack(
    *,
    apps: t.Sequence[object],
    llm: LLMClientProtocol,
    user_llm: LLMClientProtocol,
    max_user_turns: int,
    log_mode: Literal["overwrite", "append"],
    primary_app: str | None = None,
    oracle_actions: t.Sequence[OracleAction] | None = None,
    notification_verbosity: VerbosityLevel = VerbosityLevel.MEDIUM,
    extra_notifications: dict[str, t.Iterable[str]] | None = None,
    goal_prompt: str | None = "You summarise recent completed events and suggest helpful follow-ups.",
) -> ScenarioSetup:
    """Assemble environment, user proxy, and proactive agent around supplied apps."""
    log_dir = Path("logs") / "pas"
    user_log = log_dir / "user_proxy.log"
    proactive_log = log_dir / "proactive_agent.log"
    events_log = log_dir / "events.log"

    initialise_runtime(log_paths=[user_log, proactive_log, events_log], clear_existing=log_mode == "overwrite")

    merged_notifications = dict(extra_notifications or {})
    agent_ui_notifications = merged_notifications.get("ProactiveAgentUserInterface", [])
    if "send_proposal_to_user" not in agent_ui_notifications:
        merged_notifications["ProactiveAgentUserInterface"] = [*agent_ui_notifications, "send_proposal_to_user"]

    notification_system = create_notification_system(
        verbosity=notification_verbosity, extra_notifications=merged_notifications
    )

    env = create_environment(notification_system)
    env.register_apps(list(apps))

    for app in env.apps.values():
        if isinstance(app, HomeScreenSystemApp):
            app.attach_environment(env)

    app_names = set(env.apps.keys())
    stateful_apps = [app for app in apps if isinstance(app, StatefulApp)]
    if not stateful_apps:
        raise ValueError("build_proactive_stack requires at least one StatefulApp")

    resolved_primary = primary_app
    if resolved_primary is not None and resolved_primary not in app_names:
        raise ValueError(f"Unknown primary_app '{resolved_primary}'")

    user_logger = get_pas_file_logger("pas.user_proxy", user_log, level=logging.DEBUG)
    executor_logger = get_pas_file_logger("pas.proactive.executor", proactive_log, level=logging.DEBUG)
    agent_logger = get_pas_file_logger("pas.proactive.agent", proactive_log, level=logging.DEBUG)

    # Create user tools from all registered apps (including stateful and system apps)
    user_tools = {}
    for app in env.apps.values():
        # Get user tools from both StatefulApp and SystemApp instances
        if hasattr(app, "get_meta_are_user_tools"):
            app_user_tools = app.get_meta_are_user_tools()
        elif hasattr(app, "get_user_tools"):
            app_user_tools = app.get_user_tools()
        else:
            continue

        for tool in app_user_tools:
            user_tools[tool.name] = tool

    # Add native Meta ARE control-flow tool for task termination
    user_tools["final_answer"] = FinalAnswerTool()

    llm_engine = PasLLMEngine(user_llm, logger=user_logger)

    user_agent = StatefulUserAgent(llm_engine=llm_engine, tools=user_tools, max_turns=max_user_turns, wait_timeout=2.0)

    user_proxy = StatefulUserAgentRuntime(
        agent=user_agent,
        notification_system=notification_system,
        logger=user_logger,
        max_user_turns=max_user_turns,
        event_timeout=2.0,
    )

    # Register agent with environment for dynamic tool updates
    env.register_user_agent(user_agent)

    # Subscribe to environment events
    env.subscribe_to_completed_events(user_proxy._on_event)

    agent_ui = ProactiveAgentUserInterface(user_proxy=user_proxy)
    env.register_apps([agent_ui])

    plan_executor_cb = build_plan_executor(llm, logger=executor_logger)

    proactive_agent = LLMBasedProactiveAgent(
        llm,
        system_prompt=goal_prompt or "",
        max_context_events=200,
        plan_executor=plan_executor_cb,
        summary_builder=lambda result: result.notes,
        logger=agent_logger,
    )

    env.subscribe_to_completed_events(proactive_agent.observe)
    attach_event_logging(env, events_log)

    return ScenarioSetup(
        env=env,
        proxy=user_proxy,
        agent=proactive_agent,
        agent_ui=agent_ui,
        oracle_actions=list(oracle_actions) if oracle_actions else [],
    )


__all__ = ["build_proactive_stack"]
