"""Utilities for building user planners across scenarios."""

from __future__ import annotations

import typing
from typing import TYPE_CHECKING

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.system import SystemApp

from pas.apps.core import StatefulApp
from pas.apps.proactive_agent_ui import ProactiveAgentUserInterface
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
    "You may interact with any available app; call the appropriate tool for that app when you need to switch contexts. "
    "You prefer taps and menus over typing and generally keep replies brief. "
    "When a notification begins with 'Proactive assistant proposal:' prioritise the available accept_proposal or "
    "decline_proposal tools before doing anything else unless another action is absolutely required."
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
    app_map: dict[str, StatefulApp | SystemApp] = {}
    for app in apps:
        app_name = getattr(app, "name", None)
        if isinstance(app_name, str) and app_name:
            app_map[app_name] = app
    stateful_apps = [app for app in apps if isinstance(app, StatefulApp)]
    agent_ui_apps = [app for app in apps if isinstance(app, AgentUserInterface)]
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
        metadata = proxy.current_notification_metadata() if hasattr(proxy, "current_notification_metadata") else None
        available_specs = _select_available_specs(metadata, active_app, agent_ui_apps, system_app, include_system_tools)

        if not available_specs:
            raise RuntimeError("No available tools for user planner")

        system_prompt = build_user_system_prompt(active_app)

        local_planner = LLMUserPlanner(llm_client, available_specs, system_prompt=system_prompt, logger=logger)
        return local_planner(message, proxy)

    return _plan


def _select_available_specs(
    metadata: tuple[str, str] | None,
    active_app: StatefulApp | None,
    agent_ui_apps: typing.Sequence[AgentUserInterface],
    system_app: SystemApp | None,
    include_system_tools: bool,
) -> list[UserToolSpec]:
    if metadata == ("AgentUserInterface", "send_message_to_user") and agent_ui_apps:
        return _deduplicate_specs(_collect_user_tool_specs(agent_ui_apps))

    specs = list(_collect_initial_specs(active_app, agent_ui_apps))
    seen = {spec.name for spec in specs}

    if agent_ui_apps:
        _extend_with_new_specs(specs, seen, _collect_user_tool_specs(agent_ui_apps))

    if include_system_tools and system_app is not None:
        _extend_with_new_specs(specs, seen, _collect_user_tool_specs([system_app], include_system=True))

    return specs


def _extend_with_new_specs(
    accumulator: list[UserToolSpec], seen: set[str], candidates: typing.Iterable[UserToolSpec]
) -> None:
    for spec in candidates:
        if spec.name in seen:
            continue
        accumulator.append(spec)
        seen.add(spec.name)


def _deduplicate_specs(specs: typing.Iterable[UserToolSpec]) -> list[UserToolSpec]:
    unique: dict[str, UserToolSpec] = {}
    for spec in specs:
        unique.setdefault(spec.name, spec)
    return list(unique.values())


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


def _collect_initial_specs(
    active_app: StatefulApp | None, agent_ui_apps: typing.Sequence[AgentUserInterface]
) -> typing.Iterable[UserToolSpec]:
    if active_app is not None:
        return _collect_user_tool_specs([active_app])
    if agent_ui_apps:
        return _collect_user_tool_specs(agent_ui_apps)
    return []


def _collect_user_tool_specs(apps: typing.Sequence[object], *, include_system: bool = False) -> list[UserToolSpec]:
    specs: list[UserToolSpec] = []
    seen: set[str] = set()

    for app in apps:
        for tool in _iter_user_tools_for_app(app, include_system):
            if not _should_include_tool(app, tool):
                continue
            try:
                candidate = _app_tool_to_user_spec(app, tool)
            except ValueError:
                continue
            if candidate.name in seen:
                continue
            specs.append(candidate)
            seen.add(candidate.name)

    return specs


def _iter_user_tools_for_app(app: object, include_system: bool) -> typing.Iterable[AppTool]:
    if isinstance(app, SystemApp):
        if not include_system:
            raise ValueError("System app provided without include_system flag")
        yield from app.get_user_tools()
        return

    if isinstance(app, AgentUserInterface):
        yield from app.get_user_tools()
        return

    if isinstance(app, StatefulApp):
        yield from app.get_user_tools()
        return

    tool_getter = getattr(app, "get_user_tools", None)
    if callable(tool_getter):
        yield from tool_getter()


def _should_include_tool(app: object, tool: AppTool) -> bool:
    """Return True when the tool should be surfaced to the planner."""
    if isinstance(app, ProactiveAgentUserInterface):
        func_name = getattr(getattr(tool, "function", None), "__name__", "")
        if func_name == "go_back":
            return False
        if func_name in {"accept_proposal", "decline_proposal"}:
            pending = getattr(app, "pending_proposal", None)
            if pending is None:
                return False
    return True


def _app_tool_to_user_spec(app: object, tool: AppTool) -> UserToolSpec:
    app_name = getattr(app, "name", None)
    if not isinstance(app_name, str):
        raise TypeError("Tool host app is missing a name attribute")
    function = tool.function
    func_name = getattr(function, "__name__", None)
    if not isinstance(func_name, str):
        raise TypeError("Tool is missing a callable function")
    tool_name = f"{app_name}.{func_name}"
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
    return UserToolSpec(name=tool_name, description=description, app=app_name, method=func_name, parameters=parameters)


__all__ = ["DEFAULT_USER_SYSTEM_PROMPT", "build_stateful_user_planner", "build_user_system_prompt"]
