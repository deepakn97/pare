from __future__ import annotations

import argparse
import inspect
import json
import logging
from collections.abc import Iterable  # noqa: TC003
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Mapping, Sequence, cast, get_type_hints  # noqa: UP035

import docstring_parser
from are.simulation.agents.are_simulation_agent_config import LLMEngineConfig
from are.simulation.agents.llm.llm_engine_builder import LLMEngineBuilder
from are.simulation.apps.app import ToolType
from are.simulation.tool_box import DEFAULT_TOOL_DESCRIPTION_TEMPLATE, Toolbox
from are.simulation.tool_utils import AppTool, AppToolAdapter, OperationType, ToolAttributeName, format_type_name

from pas.apps.core import AppState
from pas.apps.notification_templates import NOTIFICATION_TEMPLATES
from pas.scenario_generator.agent.multi_step_scenario_generating_agent import (
    MultiStepScenarioGeneratingAgentsOrchestrator,
)
from pas.scenario_generator.example_proactive_scenarios.scenario_with_all_pas_apps import (
    ScenarioWithAllPASApps,
)
from pas.scenario_generator.prompt.multi_step_scenario_generating_agent_prompts.prompts import (
    APP_IMPORT_INSTRUCTIONS,
    build_app_initialization_block,
)

if TYPE_CHECKING:
    from are.simulation.agents.llm.llm_engine import LLMEngine


SYSTEM_APPS = {"PASAgentUserInterface", "HomeScreenSystemApp"}
_STATE_USER_TOOL_CACHE: dict[type, list[tuple[str, str, Any]]] = {}


def build_engine(model: str, provider: str | None, endpoint: str | None) -> LLMEngine:
    """Build an `LLMEngine` instance from simple CLI arguments."""
    config = LLMEngineConfig(model_name=model, provider=provider, endpoint=endpoint)
    return LLMEngineBuilder().create_engine(engine_config=config)


def build_import_instructions_block(app_names: list[str]) -> str:
    """Return a formatted block with import instructions for the selected apps.

    Uses the hard-coded `APP_IMPORT_INSTRUCTIONS` mapping so prompts stay stable
    even if the underlying packages change.
    """
    ordered: list[str] = []
    for name in app_names:
        if name not in ordered:
            ordered.append(name)

    lines: list[str] = []
    for name in ordered:
        spec_obj = APP_IMPORT_INSTRUCTIONS.get(name)
        if spec_obj is None:
            continue
        spec = cast("Mapping[str, object]", spec_obj)
        instr = spec.get("import instruction")
        if not instr:
            continue

        # Normalize to a list of strings to support single or multiple imports.
        if isinstance(instr, str):
            imports = [instr]
        elif isinstance(instr, (list, tuple, set)):
            imports = [str(item) for item in instr]
        else:
            imports = [str(instr)]

        lines.append(f"{name}:")
        for imp in imports:
            lines.append(f"  - {imp}")

    if not lines:
        return "(none)"
    return "\n".join(lines)


def determine_selected_apps(app_instances: dict[str, object], requested: Iterable[str] | None) -> list[str]:
    """Choose which apps to expose to the generator based on availability and CLI overrides."""
    available = [name for name in app_instances if name not in SYSTEM_APPS]
    available.sort()
    if not available:
        return []
    if not requested:
        return available
    requested_unique: list[str] = []
    for item in requested:
        if item not in requested_unique:
            requested_unique.append(item)
    valid = [name for name in requested_unique if name in available]
    invalid = sorted(set(requested_unique) - set(valid))
    if invalid:
        logging.warning("Ignoring unknown apps: %s (available: %s)", ", ".join(invalid), ", ".join(available))
    return valid or available


def build_tool_descriptions(app_def_scenario: object, target_apps: list[str]) -> str:
    """Summarize tools for the given apps so the LLM knows what it can call."""
    try:
        tools = app_def_scenario.get_tools()  # type: ignore[attr-defined]  # naq: app_def_scenario is a PASScenario
    except Exception:
        tools = []
    filtered = []
    target_set = set(target_apps)
    for tool in tools:
        inst = getattr(tool, "class_instance", None)
        inst_name = getattr(inst, "__class__", type("", (), {})).__name__ if inst else None
        if inst_name in target_set:
            filtered.append(tool)
    if not filtered:
        return "(none)"
    toolbox = Toolbox(tools=[AppToolAdapter(t) for t in filtered])
    return toolbox.show_tool_descriptions(DEFAULT_TOOL_DESCRIPTION_TEMPLATE)


def _summarize_docstring(doc: str | None) -> str:  # noqa: C901
    """Extract a short human-readable summary from an arbitrary docstring."""
    if not doc:
        return "No description provided."
    cleaned = inspect.cleandoc(doc).strip()
    if not cleaned:
        return "No description provided."
    lines: list[str] = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            if lines:
                break
            continue
        lower = stripped.lower()
        if lower.startswith(("args:", "returns:", "return:", "raises:", "examples:", "parameters:")):
            break
        param_markers = [":param", ":returns", ":return", ":raises", ":rtype", ":type"]
        cut_index = min(
            (stripped.lower().find(marker) for marker in param_markers if marker in stripped.lower()), default=-1
        )
        if cut_index != -1:
            before = stripped[:cut_index].strip()
            if before:
                lines.append(before)
            break
        lines.append(stripped)
    summary = " ".join(lines).strip()
    if summary:
        return summary
    first_line = cleaned.splitlines()[0].strip()
    for marker in (":param", ":returns", ":return", ":raises", ":rtype", ":type"):
        idx = first_line.lower().find(marker)
        if idx != -1:
            first_line = first_line[:idx].strip()
            break
    return first_line or "No description provided."


def _format_signature(name: str, arg_names: Sequence[str]) -> str:
    if arg_names:
        return f"{name}({', '.join(arg_names)})"
    return f"{name}()"


def _signature_from_callable(name: str, method: Callable[..., object] | None) -> str:
    if method is None:
        return f"{name}(...)"
    try:
        signature = inspect.signature(method)
    except (ValueError, TypeError):
        return f"{name}(...)"
    arg_names: list[str] = []
    for param in signature.parameters.values():
        if param.name == "self":
            continue
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            arg_names.append(f"*{param.name}")
        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            arg_names.append(f"**{param.name}")
        else:
            arg_names.append(param.name)
    return _format_signature(name, arg_names)


def _type_label(type_obj: object) -> str:
    if type_obj in (None, inspect._empty):
        return "None"
    if type_obj is Any:
        return "Any"
    try:
        return format_type_name(type_obj)
    except Exception:
        if isinstance(type_obj, str):
            return type_obj
        return getattr(type_obj, "__name__", str(type_obj))


def _format_args_dict(args_dict: Mapping[str, Mapping[str, Any]] | None) -> str:
    if not args_dict:
        return "{}"
    return repr(args_dict)


def _format_tool_entry(
    signature: str,
    *,
    description: str,
    args_dict: Mapping[str, Mapping[str, Any]] | None,
    return_info: Mapping[str, Any],
    note: str | None = None,
) -> str:
    desc = description.strip() if description else "No description provided."
    if not desc:
        desc = "No description provided."
    lines = [
        f"{signature}: {desc}",
        f"    Takes inputs: {_format_args_dict(args_dict)}",
        f"    Returns: {return_info}",
    ]
    if note:
        lines.append(f"    Notes: {note}")
    return "\n".join(lines)


def _operation_label(operation: object) -> str | None:
    if isinstance(operation, OperationType):
        return operation.value.upper()
    if isinstance(operation, str):
        return operation.upper()
    if isinstance(operation, bool):
        return "WRITE" if operation else "READ"
    return None


def _args_from_apptool(tool: AppTool) -> dict[str, dict[str, Any]]:
    args_info: dict[str, dict[str, Any]] = {}
    for arg in getattr(tool, "args", []):
        if not getattr(arg, "name", None):
            continue
        entry: dict[str, Any] = {
            "description": getattr(arg, "description", None) or "",
            "type": str(getattr(arg, "arg_type", "Any")),
        }
        if getattr(arg, "has_default", False):
            entry["default"] = arg.default
        args_info[arg.name] = entry
    return args_info


def _args_from_callable(method: Callable[..., object] | None) -> dict[str, dict[str, Any]]:
    if method is None:
        return {}
    param_docs, _ = _docstring_metadata(method)
    try:
        signature = inspect.signature(method)
    except (ValueError, TypeError):
        return {}
    try:
        type_hints = get_type_hints(method)
    except Exception:
        type_hints = {}
    args_info: dict[str, dict[str, Any]] = {}
    for name, param in signature.parameters.items():
        if name == "self":
            continue
        hint = type_hints.get(name, Any)
        entry: dict[str, Any] = {
            "description": param_docs.get(name, ""),
            "type": _type_label(hint),
        }
        if param.default is not inspect._empty:
            entry["default"] = param.default
        args_info[name] = entry
    return args_info


def _docstring_metadata(method: Callable[..., object]) -> tuple[dict[str, str], str]:
    doc = inspect.getdoc(method)
    if not doc:
        return {}, ""
    try:
        parsed = docstring_parser.parse(doc)
    except Exception:
        return {}, ""
    params = {param.arg_name: param.description or "" for param in parsed.params}
    return_desc = (parsed.returns.description or "") if parsed.returns else ""
    return params, return_desc


def _return_info_from_callable(method: Callable[..., object]) -> dict[str, Any]:
    _, return_doc = _docstring_metadata(method)
    try:
        type_hints = get_type_hints(method)
    except Exception:
        type_hint = Any
    else:
        type_hint = type_hints.get("return", Any)
    return {
        "description": return_doc or "",
        "type": _type_label(type_hint),
    }


def _describe_callable(method: Callable[..., object]) -> tuple[str, dict[str, dict[str, Any]], dict[str, Any]]:
    app_tool = None
    try:
        app_tool = AppTool.get_tool_for_function(method)
    except Exception:
        app_tool = None
    if app_tool is not None:
        description = _summarize_docstring(getattr(app_tool, "function_description", None))
        args_dict = _args_from_apptool(app_tool)
        return_info = {
            "description": getattr(app_tool, "return_description", "") or "",
            "type": _type_label(getattr(app_tool, "return_type", "Any")),
        }
        return description, args_dict, return_info
    description = _summarize_docstring(inspect.getdoc(method))
    args_dict = _args_from_callable(method)
    return_info = _return_info_from_callable(method)
    return description, args_dict, return_info


def _state_user_tool_specs(inst: object) -> list[tuple[str, str, Any]]:
    app_cls = inst.__class__
    if app_cls in _STATE_USER_TOOL_CACHE:
        return list(_STATE_USER_TOOL_CACHE[app_cls])
    module_name = getattr(app_cls, "__module__", "")
    if not module_name:
        _STATE_USER_TOOL_CACHE[app_cls] = []
        return []
    base_name = module_name.rsplit(".", 1)[0]
    states_module_name = f"{base_name}.states"
    try:
        states_module = import_module(states_module_name)
    except ModuleNotFoundError:
        _STATE_USER_TOOL_CACHE[app_cls] = []
        return []
    state_classes: list[type[AppState]] = []
    for _, cls in inspect.getmembers(states_module, inspect.isclass):
        if cls is AppState:
            continue
        if issubclass(cls, AppState):
            state_classes.append(cls)
    specs: list[tuple[str, str, Any]] = []
    for state_cls in state_classes:
        for name, func in inspect.getmembers(state_cls, predicate=inspect.isfunction):
            if getattr(func, "_is_user_tool", False):
                specs.append((state_cls.__name__, name, func))
    _STATE_USER_TOOL_CACHE[app_cls] = specs
    return list(specs)


def build_non_oracle_block(app_instances: dict[str, object], selected_apps: list[str]) -> str:
    """Describe non-oracle notification methods per selected app."""
    lines = []
    for app_name in selected_apps:
        inst = app_instances.get(app_name)
        scoped_methods: dict[str, set[str]] = {}
        descriptions: dict[str, str] = {}
        for scope in ("user", "agent"):
            scope_methods = NOTIFICATION_TEMPLATES.get(scope, {}).get(app_name, {})
            for method_name, template in scope_methods.items():
                scoped_methods.setdefault(method_name, set()).add(scope)
                if method_name not in descriptions:
                    descriptions[method_name] = template
        if not scoped_methods:
            continue
        entries = []
        for method_name in sorted(scoped_methods):
            method_obj = getattr(inst, method_name, None) if inst else None
            fallback_description = descriptions.get(method_name, "")
            raw_doc = getattr(method_obj, "__doc__", None) if method_obj else None
            description = _summarize_docstring(raw_doc or fallback_description)
            signature = _signature_from_callable(method_name, method_obj)
            args_dict = _args_from_callable(method_obj)
            return_info = (
                _return_info_from_callable(method_obj) if method_obj is not None else {"description": "", "type": "Any"}
            )
            scopes = ", ".join(sorted(scoped_methods[method_name]))
            note = f"notification scopes: {scopes}"
            entries.append(
                _format_tool_entry(
                    signature,
                    description=description,
                    args_dict=args_dict,
                    return_info=return_info,
                    note=note,
                )
            )
        if entries:
            formatted_entries = "\n".join(f"  - {entry}" for entry in entries)
            lines.append(f"{app_name}:\n{formatted_entries}")
    return "\n\n".join(lines) if lines else "(none)"


def _gather_oracle_entries(inst: object) -> list[str]:
    entries: list[str] = []
    seen: set[str] = set()
    registry_specs = [
        (ToolAttributeName.USER, ToolType.USER, "user tool"),
        (ToolAttributeName.APP, ToolType.APP, "app tool"),
    ]
    for attr, tool_type, label in registry_specs:
        try:
            tools = inst.get_tools_with_attribute(attr, tool_type)  # type: ignore[attr-defined]  # naq
        except Exception as exc:
            logging.debug("Skipping tools for %s due to error: %s", inst, exc)
            continue
        for tool in tools:
            func_name = getattr(tool, "func_name", None)
            if not func_name:
                continue
            cache_key = func_name
            if cache_key in seen:
                continue
            seen.add(cache_key)
            method = getattr(inst, func_name, None)
            if method is not None:
                description, args_dict, return_info = _describe_callable(method)
                signature = _signature_from_callable(func_name, method)
            else:
                description = _summarize_docstring(getattr(tool, "function_description", None))
                arg_names = [arg.name for arg in getattr(tool, "args", []) if getattr(arg, "name", None)]
                signature = _format_signature(func_name, arg_names)
                args_dict = _args_from_apptool(tool)
                return_info = {
                    "description": getattr(tool, "return_description", "") or "",
                    "type": _type_label(getattr(tool, "return_type", "Any")),
                }
            entries.append(
                _format_tool_entry(
                    signature,
                    description=description,
                    args_dict=args_dict,
                    return_info=return_info,
                    note=label,
                )
            )
    for state_name, func_name, func in _state_user_tool_specs(inst):
        cache_key = f"{state_name}.{func_name}"
        if cache_key in seen:
            continue
        seen.add(cache_key)
        description, args_dict, return_info = _describe_callable(func)
        signature = _signature_from_callable(func_name, func)
        note = f"state user tool ({state_name})"
        entries.append(
            _format_tool_entry(
                signature,
                description=description,
                args_dict=args_dict,
                return_info=return_info,
                note=note,
            )
        )
    return sorted(entries)


def build_oracle_block(app_instances: dict[str, object], selected_apps: list[str]) -> str:
    """Describe oracle-style app tools that can be invoked during events."""
    lines = []
    for app_name in selected_apps:
        inst = app_instances.get(app_name)
        if inst is None:
            continue
        entries = _gather_oracle_entries(inst)
        if entries:
            formatted_entries = "\n".join(f"  - {entry}" for entry in entries)
            lines.append(f"{app_name}:\n{formatted_entries}")
    return "\n\n".join(lines) if lines else "(none)"


def _gather_event_registered_entries(inst: object) -> list[str]:
    entries: list[str] = []
    seen: set[str] = set()
    for name, member in inspect.getmembers(inst, predicate=callable):
        if name.startswith("_"):
            continue
        method = member
        if not getattr(method, "__event_registered__", False):
            continue
        if name in seen:
            continue
        seen.add(name)
        description, args_dict, return_info = _describe_callable(method)
        signature = _signature_from_callable(name, method)
        op_label = _operation_label(getattr(method, "__operation_type__", None))
        entries.append(
            _format_tool_entry(
                signature,
                description=description,
                args_dict=args_dict,
                return_info=return_info,
                note=op_label,
            )
        )
    for state_name, func_name, func in _state_user_tool_specs(inst):
        cache_key = f"{state_name}.{func_name}"
        if cache_key in seen:
            continue
        seen.add(cache_key)
        description, args_dict, return_info = _describe_callable(func)
        signature = _signature_from_callable(func_name, func)
        op_label = _operation_label(getattr(func, "__operation_type__", None))
        note_parts = [op_label, f"state: {state_name}"]
        note = ", ".join(part for part in note_parts if part)
        entries.append(
            _format_tool_entry(
                signature,
                description=description,
                args_dict=args_dict,
                return_info=return_info,
                note=note or None,
            )
        )
    return sorted(entries)


def _format_brief_tool_entry(signature: str, *, description: str) -> str:
    """Return a single-line, narrative-friendly summary for a tool."""
    desc = description.strip() if description else "No description provided."
    if not desc:
        desc = "No description provided."
    return f"{signature}: {desc}"


def _gather_event_registered_brief_entries(inst: object) -> list[str]:
    """Gather concise entries for event-registered tools, omitting args/returns/notes."""
    entries: list[str] = []
    seen: set[str] = set()
    registry_specs = [
        (ToolAttributeName.USER, ToolType.USER),
        (ToolAttributeName.APP, ToolType.APP),
    ]
    for attr, tool_type in registry_specs:
        try:
            tools = inst.get_tools_with_attribute(attr, tool_type)  # type: ignore[attr-defined]  # naq
        except Exception as exc:
            logging.debug("Skipping tools for %s due to error: %s", inst, exc)
            continue
        for tool in tools:
            func_name = getattr(tool, "func_name", None)
            if not func_name:
                continue
            if func_name in seen:
                continue
            seen.add(func_name)
            method = getattr(inst, func_name, None)
            if method is not None:
                description, _, _ = _describe_callable(method)
                signature = _signature_from_callable(func_name, method)
            else:
                description = _summarize_docstring(getattr(tool, "function_description", None))
                arg_names = [arg.name for arg in getattr(tool, "args", []) if getattr(arg, "name", None)]
                signature = _format_signature(func_name, arg_names)
            entries.append(_format_brief_tool_entry(signature, description=description))

    for state_name, func_name, func in _state_user_tool_specs(inst):
        cache_key = f"{state_name}.{func_name}"
        if cache_key in seen:
            continue
        seen.add(cache_key)
        description, _, _ = _describe_callable(func)
        signature = _signature_from_callable(func_name, func)
        entries.append(_format_brief_tool_entry(signature, description=description))

    return sorted(entries)


def build_all_tools_block(app_instances: dict[str, object], target_apps: list[str]) -> str:
    """Describe all event-registered tools for the selected apps."""
    lines = []
    for app_name in target_apps:
        inst = app_instances.get(app_name)
        if inst is None:
            continue
        entries = _gather_event_registered_entries(inst)
        if entries:
            formatted_entries = "\n".join(f"  - {entry}" for entry in entries)
            lines.append(f"{app_name}:\n{formatted_entries}")
    return "\n\n".join(lines) if lines else "(none)"


def build_selected_tools_block(app_instances: dict[str, object], target_apps: list[str]) -> str:
    """Describe event-registered tools for the selected apps in a brief, narrative-oriented format."""
    lines = []
    for app_name in target_apps:
        inst = app_instances.get(app_name)
        if inst is None:
            continue
        entries = _gather_event_registered_brief_entries(inst)
        if entries:
            formatted_entries = "\n".join(f"  - {entry}" for entry in entries)
            lines.append(f"{app_name}:\n{formatted_entries}")
    return "\n\n".join(lines) if lines else "(none)"


def prepare_prompt_context_data(app_def_scenario: object, selected_apps: list[str]) -> dict[str, str]:
    """Assemble all dynamic prompt blocks used by the multi-step generator."""
    app_instances = {app.__class__.__name__: app for app in getattr(app_def_scenario, "apps", [])}
    selected_plus_system = selected_apps + [name for name in SYSTEM_APPS if name in app_instances]
    import_instructions = build_import_instructions_block(selected_plus_system)
    tool_descriptions = build_tool_descriptions(app_def_scenario, selected_plus_system)
    allowed_non_oracle = build_non_oracle_block(app_instances, selected_apps)
    allowed_oracle = build_oracle_block(app_instances, selected_apps)
    allowed_all_tools = build_all_tools_block(app_instances, selected_plus_system)
    selected_tools_description = build_selected_tools_block(app_instances, selected_apps)
    app_init_block = build_app_initialization_block(selected_plus_system)
    selected_display = ", ".join(selected_plus_system) if selected_plus_system else "(none)"
    return {
        "selected_apps": selected_display,
        "import_instructions": import_instructions,
        "tool_descriptions": tool_descriptions,
        "allowed_non_oracle_block": allowed_non_oracle,
        "allowed_oracle_block": allowed_oracle,
        "allowed_all_tools_block": allowed_all_tools,
        "app_initialization_block": app_init_block,
        "selected_tools_description": selected_tools_description,
    }


# from pas.scenarios.registry import registry as pas_registry


def main() -> None:
    """CLI entry point for the multi-step scenario generator."""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser("multi-steps-scenario-generator")
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        type=Path,
        default=None,
        help="Directory where intermediate step files should be written.",
    )
    parser.add_argument(
        "--model",
        dest="model",
        default="gpt-5-chat-latest",
        help="LLM model identifier supported by the configured provider.",
    )
    parser.add_argument(
        "--provider",
        dest="provider",
        default="openai",
        help="LLM provider name (e.g., openai, azure, anthropic).",
    )
    parser.add_argument(
        "--endpoint",
        dest="endpoint",
        default=None,
        help="Optional custom endpoint for the provider.",
    )
    parser.add_argument(
        "--max-iterations",
        dest="max_iterations",
        type=int,
        default=2,
        help="Maximum number of attempts per step.",
    )
    parser.add_argument(
        "--resume-from-step2",
        dest="resume_from_step2",
        action="store_true",
        default=True,
        help=(
            "Reuse an existing Step 1 description from the output directory and "
            "start the pipeline at Step 2 (apps & data)."
        ),
    )
    parser.add_argument(
        "--debug-prompts",
        dest="debug_prompts",
        action="store_true",
        default=False,
        help="If set, skip LLM calls and print the prompts for all agents instead.",
    )
    parser.add_argument(
        "--apps",
        dest="selected_apps",
        nargs="*",
        default=["StatefulMessagingApp", "StatefulContactsApp", "StatefulCalendarApp", "StatefulEmailApp"],
        help=(
            "Explicit list of app class names to include (PASAgentUserInterface and "
            "HomeScreenSystemApp are always available). Defaults to all apps in the app definition scenario."
        ),
    )
    args = parser.parse_args()

    app_def_scenario = ScenarioWithAllPASApps()
    app_def_scenario.initialize()
    app_instances = {app.__class__.__name__: app for app in getattr(app_def_scenario, "apps", [])}
    selected_apps = determine_selected_apps(app_instances, args.selected_apps)
    if not selected_apps:
        logging.warning("No selectable apps found; continuing with system apps only.")
    prompt_context = prepare_prompt_context_data(app_def_scenario, selected_apps)

    engine = build_engine(args.model, args.provider, args.endpoint)
    agent = MultiStepScenarioGeneratingAgentsOrchestrator(
        llm_engine=engine,
        output_dir=args.output_dir,
        max_iterations=args.max_iterations,
        prompt_context=prompt_context,
        debug_prompts=args.debug_prompts,
        resume_from_step2=args.resume_from_step2,
    )

    result = agent.run()
    print(json.dumps(result, default=_json_serializer, indent=2))


def _json_serializer(obj: object) -> object:
    if isinstance(obj, Path):
        return str(obj)
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


if __name__ == "__main__":
    main()
