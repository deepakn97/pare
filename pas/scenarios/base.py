"""Shared helpers to assemble PAS proactive runtime stacks."""

from __future__ import annotations

import logging
import typing as t
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from are.simulation.notification_system import VerbosityLevel

from pas.apps.core import StatefulApp
from pas.apps.system import HomeScreenSystemApp
from pas.logging_utils import get_pas_file_logger
from pas.proactive import LLMBasedProactiveAgent
from pas.scenarios.types import OracleAction, ScenarioSetup
from pas.system import (
    attach_event_logging,
    build_plan_executor,
    build_stateful_user_planner,
    create_environment,
    create_notification_system,
    initialise_runtime,
)
from pas.user_proxy import StatefulUserProxy
from pas.user_proxy.decision_maker import LLMDecisionMaker

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

    notification_system = create_notification_system(
        verbosity=notification_verbosity, extra_notifications=extra_notifications
    )

    env = create_environment(notification_system)
    env.register_apps(list(apps))

    for app in env.apps.values():
        if isinstance(app, HomeScreenSystemApp):
            app.attach_environment(env)

    app_names = {getattr(app, "name", None) for app in apps}
    stateful_apps = [app for app in apps if isinstance(app, StatefulApp)]
    if not stateful_apps:
        raise ValueError("build_proactive_stack requires at least one StatefulApp")

    resolved_primary = primary_app
    if resolved_primary is not None and resolved_primary not in app_names:
        raise ValueError(f"Unknown primary_app '{resolved_primary}'")

    user_logger = get_pas_file_logger("pas.user_proxy", user_log, level=logging.DEBUG)
    planner_logger = get_pas_file_logger("pas.user_proxy.planner", user_log, level=logging.DEBUG)
    decision_logger = get_pas_file_logger("pas.user_proxy.decisions", user_log, level=logging.DEBUG)
    executor_logger = get_pas_file_logger("pas.proactive.executor", proactive_log, level=logging.DEBUG)
    agent_logger = get_pas_file_logger("pas.proactive.agent", proactive_log, level=logging.DEBUG)

    planner_cb = build_stateful_user_planner(
        user_llm,
        list(env.apps.values()),
        initial_app_name=resolved_primary,
        include_system_tools=True,
        logger=planner_logger,
    )
    decision_maker = LLMDecisionMaker(user_llm, logger=decision_logger)
    plan_executor_cb = build_plan_executor(llm, logger=executor_logger)

    user_proxy = StatefulUserProxy(
        env, env.notification_system, max_user_turns=max_user_turns, logger=user_logger, planner=planner_cb
    )

    agent = LLMBasedProactiveAgent(
        llm,
        system_prompt=goal_prompt or "",
        max_context_events=200,
        plan_executor=plan_executor_cb,
        summary_builder=lambda result: result.notes,
        logger=agent_logger,
    )

    env.subscribe_to_completed_events(agent.observe)
    attach_event_logging(env, events_log)

    return ScenarioSetup(
        env=env,
        proxy=user_proxy,
        agent=agent,
        decision_maker=decision_maker,
        oracle_actions=list(oracle_actions) if oracle_actions else [],
    )


__all__ = ["build_proactive_stack"]
