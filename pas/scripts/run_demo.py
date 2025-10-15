"""Unified entry point for running proactive scenario demos."""

from __future__ import annotations

import argparse
import importlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast

from dotenv import load_dotenv

from pas.proactive import LiteLLMClient
from pas.system import ProactiveSession

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from pas.scenarios.types import ScenarioSetup


def _resolve_attr(path: str) -> object:
    module_path, _, attr = path.rpartition(".")
    if not module_path:
        raise ValueError(f"Invalid import path '{path}'")
    module = importlib.import_module(module_path)
    return getattr(module, attr)


def _parse_kwargs(pairs: Iterable[str]) -> dict[str, object]:
    parsed: dict[str, object] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"Keyword '{pair}' must be in key=value format")
        key, value = pair.split("=", 1)
        parsed[key] = value
    return parsed


def run_proactive_demo(
    builder: Callable[..., ScenarioSetup],
    *,
    scenario_factory: Callable[[], object] | None = None,
    primary_app: str | None = None,
    max_user_turns: int = 25,
    log_mode: str = "overwrite",
    mode: str = "event",
    messages: Iterable[str] | None = None,
    builder_kwargs: Mapping[str, object] | None = None,
) -> None:
    """Run a single proactive demo using the provided scenario builder."""
    log_dir = (Path("logs") / "pas").resolve()
    load_dotenv(override=False)

    llm = LiteLLMClient()
    user_llm = LiteLLMClient()

    kwargs: dict[str, object] = dict(builder_kwargs or {})
    kwargs.update({"llm": llm, "user_llm": user_llm, "max_user_turns": max_user_turns, "log_mode": log_mode})

    if primary_app is not None:
        kwargs["primary_app"] = primary_app

    setup = builder(scenario_factory(), **kwargs) if scenario_factory is not None else builder(**kwargs)

    env, proxy, agent, agent_ui = setup

    session_logger = logging.getLogger("pas.session.demo")
    session_logger.setLevel(logging.INFO)
    session = ProactiveSession(
        env,
        proxy,
        agent,
        agent_ui,
        confirm_goal=lambda goal: True,
        logger=session_logger,
        oracle_actions=setup.oracle_actions,
    )

    proxy.init_conversation()
    if mode == "event":
        notifications = proxy.consume_notifications()
        if not notifications:
            raise RuntimeError("No notifications available to seed event-driven demo")
        reply = proxy.react_to_event(notifications[0])
        print(f"EVENT PROMPT: {notifications[0]}")
        print(f"USER REPLY:  {reply}\n")
    elif mode == "user":
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


def main(argv: list[str] | None = None) -> None:
    """Parse CLI arguments and run the configured demo."""
    parser = argparse.ArgumentParser(description="Run a PAS proactive demo")
    parser.add_argument("--builder", required=True, help="Import path to scenario builder callable")
    parser.add_argument("--scenario-class", help="Optional scenario class to instantiate and pass to the builder")
    parser.add_argument("--primary-app", help="Optional initial app for the user planner")
    parser.add_argument("--max-user-turns", type=int, default=25)
    parser.add_argument("--log-mode", choices=["overwrite", "append"], default="overwrite")
    parser.add_argument("--mode", choices=["event", "user"], default="event")
    parser.add_argument("--message", action="append", help="User message to send when mode=user (can repeat)")
    parser.add_argument(
        "--builder-kw", action="append", default=[], help="Additional builder keyword arguments in key=value form"
    )

    args = parser.parse_args(argv)

    builder = cast("Callable[..., ScenarioSetup]", _resolve_attr(args.builder))
    scenario_factory = cast("Callable[[], object]", _resolve_attr(args.scenario_class)) if args.scenario_class else None
    kwargs = _parse_kwargs(args.builder_kw)

    run_proactive_demo(
        builder,
        scenario_factory=scenario_factory,
        primary_app=args.primary_app,
        max_user_turns=args.max_user_turns,
        log_mode=args.log_mode,
        mode=args.mode,
        messages=args.message,
        builder_kwargs=kwargs,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
