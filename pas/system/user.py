"""Utilities for building user planners across scenarios."""

from __future__ import annotations

import typing
from typing import TYPE_CHECKING

from are.simulation.apps.system import SystemApp

from pas.apps.core import StatefulApp
from pas.user_proxy import LLMUserPlanner, UserToolParameter, UserToolSpec

if TYPE_CHECKING:  # pragma: no cover - imported for type hints only
    import logging

    from are.simulation.tool_utils import AppTool

    from pas.proactive import LLMClientProtocol
    from pas.user_proxy import PlannerCallable, StatefulUserProxy
else:
    AppTool = object  # type: ignore[assignment]


DEFAULT_USER_SYSTEM_PROMPT = (
    "You are manually operating your phone. Choose actions that genuinely reflect what you want to do next. "
    "You may interact with any available app; call the appropriate tool for that app when you need to switch contexts."
)


def build_stateful_user_planner(
    llm_client: LLMClientProtocol,
    apps: typing.Sequence[StatefulApp | SystemApp],
    *,
    initial_app_name: str | None = None,
    include_system_tools: bool,
    logger: logging.Logger,
) -> PlannerCallable:
    """Return a planner callable wired to the provided LLM client and per-app tools."""
    app_map = {app.name: app for app in apps}
    stateful_apps = [app for app in apps if isinstance(app, StatefulApp)]
    if not stateful_apps:
        raise ValueError("build_stateful_user_planner requires at least one stateful app")

    resolved_initial = initial_app_name
    if resolved_initial is not None and resolved_initial not in app_map:
        raise ValueError(f"Unknown initial app '{resolved_initial}'")

    system_app: SystemApp | None = None
    for app in apps:
        if isinstance(app, SystemApp):
            system_app = app
            break
    if include_system_tools and system_app is None:
        raise ValueError("include_system_tools requested but no SystemApp provided")

    def _plan(message: str, proxy: StatefulUserProxy) -> list[tuple[str, str, dict[str, object]]]:
        active_app = _select_active_app(proxy, app_map, resolved_initial)

        available_specs: list[UserToolSpec] = []
        if active_app is not None:
            available_specs.extend(_collect_user_tool_specs([active_app]))

        if include_system_tools and system_app is not None:
            available_specs.extend(_collect_user_tool_specs([system_app], include_system=True))

        if not available_specs:
            raise RuntimeError("No available tools for user planner")

        system_prompt = build_user_system_prompt(active_app)

        local_planner = LLMUserPlanner(llm_client, available_specs, system_prompt=system_prompt, logger=logger)
        return local_planner(message, proxy)

    return _plan


def build_user_system_prompt(active_app: StatefulApp | None) -> str:
    """Create a system prompt that reflects the currently focused app/state."""
    if active_app is None:
        return f"{DEFAULT_USER_SYSTEM_PROMPT} Current context: home_screen."
    state = active_app.current_state
    if state is None:
        raise RuntimeError(f"State for app '{active_app.name}' is not initialised")
    state_name = type(state).__name__
    readable_state = state_name.replace("_", " ")
    return f"{DEFAULT_USER_SYSTEM_PROMPT} Current context: app={active_app.name}, view={readable_state}."


def _select_active_app(
    proxy: StatefulUserProxy, app_map: dict[str, StatefulApp | SystemApp], initial_app_name: str | None
) -> StatefulApp | None:
    for invocation in reversed(proxy.last_tool_invocations):
        app_name = invocation.name.split(".")[0]
        if app_name == "system":
            if invocation.name.endswith(".go_home"):
                return None
            if invocation.name.endswith(".open_app"):
                target = invocation.args.get("app_name") if invocation.args else None
                if isinstance(target, str):
                    candidate = app_map.get(target)
                    if isinstance(candidate, StatefulApp):
                        return candidate
            continue
        candidate = app_map.get(app_name)
        if isinstance(candidate, StatefulApp):
            return candidate

    if initial_app_name is not None:
        candidate = app_map.get(initial_app_name)
        if isinstance(candidate, StatefulApp):
            return candidate

    return None


def _collect_user_tool_specs(
    apps: typing.Sequence[StatefulApp | SystemApp], *, include_system: bool = False
) -> list[UserToolSpec]:
    specs: list[UserToolSpec] = []
    seen: set[str] = set()

    def add_spec(app: StatefulApp | SystemApp, tool: AppTool) -> None:
        try:
            candidate = _app_tool_to_user_spec(app, tool)
        except ValueError:
            return
        if candidate.name in seen:
            return
        specs.append(candidate)
        seen.add(candidate.name)

    for app in apps:
        if isinstance(app, SystemApp):
            if not include_system:
                raise ValueError("System app provided without include_system flag")
            for tool in app.get_user_tools():
                add_spec(app, tool)
            continue

        state = app.current_state
        if state is None:
            raise RuntimeError(f"App '{app.name}' has no current state")

        for tool in state.get_available_actions():
            add_spec(app, tool)

    return specs


def _app_tool_to_user_spec(app: StatefulApp | SystemApp, tool: AppTool) -> UserToolSpec:
    tool_name = f"{app.name}.{tool.function.__name__}"
    if not tool.function_description:
        raise ValueError(f"Tool {tool_name} is missing a description")
    description = tool.function_description
    parameters = []
    for arg in tool.args:
        if arg.description is None:
            raise ValueError(f"Tool {tool_name} argument '{arg.name}' lacks a description")
        parameters.append(
            UserToolParameter(
                name=arg.name,
                description=arg.description,
                type_hint=str(arg.arg_type) if arg.arg_type else "string",
                required=not arg.has_default,
            )
        )
    return UserToolSpec(
        name=tool_name, description=description, app=app.name, method=tool.function.__name__, parameters=parameters
    )


__all__ = ["DEFAULT_USER_SYSTEM_PROMPT", "build_stateful_user_planner", "build_user_system_prompt"]
