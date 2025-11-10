"""Utilities to bridge Meta ARE scenarios into PAS stateful environments."""

from __future__ import annotations

import logging
import typing as t
from typing import TYPE_CHECKING, Any, Literal

from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.contacts import ContactsApp
from are.simulation.apps.email_client import EmailClientApp
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.messaging_v2 import MessagingAppV2
from are.simulation.apps.system import SystemApp
from are.simulation.types import AbstractEvent, ActionDescription, EventType, OracleEvent

from pas.apps.calendar.app import StatefulCalendarApp
from pas.apps.contacts.app import StatefulContactsApp
from pas.apps.email.app import StatefulEmailApp
from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.system import HomeScreenSystemApp
from pas.scenarios.base import build_proactive_stack
from pas.scenarios.types import OracleAction, ScenarioSetup

LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from are.simulation.scenarios.scenario import Scenario

    from pas.environment import StateAwareEnvironmentWrapper
    from pas.proactive import LLMClientProtocol # type: ignore


APP_NAME_MAP = {
    "ContactsApp": "contacts",
    "CalendarApp": "calendar",
    "EmailClientApp": "email",
    "MessagingApp": "messaging",
    "MessagingAppV2": "messaging",
    "SystemApp": "system",
    "AgentUserInterface": "AgentUserInterface",
    "SandboxLocalFileSystem": "SandboxLocalFileSystem",
}


def _transform_messaging_args(kwargs: dict[str, object], app: object) -> dict[str, object]:
    if "sender" not in kwargs or "sender_id" in kwargs:
        return kwargs
    sender_name_obj = kwargs.pop("sender")
    if not isinstance(sender_name_obj, str):
        raise TypeError("Messaging sender must be provided as a string")
    mapping = getattr(app, "name_to_id", {})
    if sender_name_obj not in mapping:
        raise KeyError(f"Unknown sender '{sender_name_obj}' for messaging app")
    kwargs["sender_id"] = mapping[sender_name_obj]
    return kwargs


ARG_TRANSFORMERS: dict[str, dict[str, t.Callable[[dict[str, object], object], dict[str, object]]]] = {
    "messaging": {
        "add_message": _transform_messaging_args,
        "create_and_add_message": _transform_messaging_args,
        "*": _transform_messaging_args,
    }
}


def _resolve_limit(value: object, fallback: int) -> int:
    if isinstance(value, int | float):
        candidate = int(value)
        if candidate > 0:
            return max(candidate, fallback)
    return fallback


def _normalise_messaging_state(state: dict[str, t.Any]) -> dict[str, t.Any]:
    conversations = state.get("conversations", {})
    name_to_id: dict[str, str] = dict(state.get("name_to_id", {}))
    id_to_name: dict[str, str] = dict(state.get("id_to_name", {}))

    def ensure_user(name: str) -> str:
        if name not in name_to_id:
            identifier = f"user-{len(name_to_id) + 1}"
            name_to_id[name] = identifier
            id_to_name[identifier] = name
        return name_to_id[name]

    upgraded_conversations: dict[str, t.Any] = {}
    for conv_id, conv in conversations.items():
        participant_names = conv.get("participant_ids") or conv.get("participants") or []
        participant_ids = [ensure_user(name) for name in participant_names]
        upgraded_conversations[conv_id] = {
            "conversation_id": conv.get("conversation_id", conv_id),
            "title": conv.get("title"),
            "messages": conv.get("messages", []),
            "participant_ids": participant_ids,
            "last_updated": conv.get("last_updated", 0.0),
        }

    current_name = state.get("current_user_name")
    if isinstance(current_name, str) and current_name:
        current_id = ensure_user(current_name)
    else:
        default_name = "Me"
        current_id = ensure_user(default_name)
        current_name = default_name

    return {
        "conversations": upgraded_conversations,
        "messages_view_limit": _resolve_limit(state.get("messages_view_limit"), 40),
        "conversation_view_limit": _resolve_limit(state.get("conversation_view_limit"), 25),
        "mode": state.get("mode", "NAME"),
        "name_to_id": name_to_id,
        "id_to_name": id_to_name,
        "current_user_id": current_id,
        "current_user_name": current_name,
    }


def _initialise_stateful_app(
    meta_app: ContactsApp | CalendarApp | EmailClientApp | MessagingApp | MessagingAppV2,
    target_cls: type[StatefulCalendarApp | StatefulContactsApp | StatefulEmailApp | StatefulMessagingApp],
    *,
    name: str,
    transform: t.Callable[[dict[str, t.Any]], dict[str, t.Any]] | None = None,
) -> StatefulCalendarApp | StatefulContactsApp | StatefulEmailApp | StatefulMessagingApp:
    state = meta_app.get_state()
    if transform is not None:
        state = transform(state)
    stateful = target_cls(name=name)
    stateful.load_state(state)
    stateful.name = name
    return stateful


def _convert_meta_app(meta_app: object) -> object:
    if isinstance(meta_app, ContactsApp):
        return _initialise_stateful_app(meta_app, StatefulContactsApp, name="contacts")
    if isinstance(meta_app, CalendarApp):
        return _initialise_stateful_app(meta_app, StatefulCalendarApp, name="calendar")
    if isinstance(meta_app, EmailClientApp):
        return _initialise_stateful_app(meta_app, StatefulEmailApp, name="email")
    if isinstance(meta_app, MessagingApp | MessagingAppV2):
        return _initialise_stateful_app(
            meta_app, StatefulMessagingApp, name="messaging", transform=_normalise_messaging_state
        )
    if isinstance(meta_app, SystemApp):
        system = HomeScreenSystemApp(name="system")
        system.wait_for_notification_timeout = getattr(meta_app, "wait_for_notification_timeout", None)
        return system

    canonical = APP_NAME_MAP.get(meta_app.__class__.__name__, getattr(meta_app, "name", meta_app.__class__.__name__))
    if hasattr(meta_app, "name"):
        meta_app.name = canonical
    return meta_app


def _convert_meta_apps(meta_apps: t.Iterable[object]) -> list[object]:
    return [_convert_meta_app(app) for app in meta_apps]


def _extract_kwargs(app_name: str, function_name: str, app: object, raw_args: dict[str, object]) -> dict[str, object]:
    kwargs: dict[str, object] = {}
    for arg_name, details in raw_args.items():
        if arg_name == "self":
            continue
        value: object = details
        if isinstance(details, dict) and "value" in details:
            value = details["value"]
        kwargs[arg_name] = value
    transformers = ARG_TRANSFORMERS.get(app_name)
    if transformers is not None:
        transform = transformers.get(function_name) or transformers.get("*")
        if transform is not None:
            kwargs = transform(kwargs, app)
    return kwargs


def _apply_events(env: StateAwareEnvironmentWrapper, events: t.Sequence[AbstractEvent]) -> None:
    for event in events:
        if event.event_type not in {EventType.ENV, EventType.AGENT}:
            continue
        app_name = APP_NAME_MAP.get(event.app_name(), event.app_name().lower())
        if app_name not in env.apps:
            raise KeyError(f"App '{app_name}' missing while applying events")
        app = env.get_app(app_name)
        function_name = event.function_name()
        if function_name is None:
            continue
        method = getattr(app, function_name, None)
        if method is None:
            continue
        raw_args = event.action.args if event.action else {}
        kwargs = _extract_kwargs(app_name, function_name, app, raw_args)
        method(**kwargs)


def _map_app_name(app: str | None) -> str | None:
    if app is None:
        return None
    return APP_NAME_MAP.get(app, app.lower())


def _literal_eval(value: str, value_type: str | None) -> object:
    if value_type is None:
        return value
    lower = value_type.lower()
    if lower in {"str", "string"}:
        return value
    if lower in {"int", "integer"}:
        return int(value)
    if lower in {"float"}:
        return float(value)
    if lower == "list":
        body = value.strip()
        if body.startswith("[") and body.endswith("]"):
            inner = body[1:-1].strip()
            if not inner:
                return []
            return [item.strip().strip("'\"") for item in inner.split(",")]
        return [value]
    if lower == "bool":
        return value.lower() == "true"
    return value


def _convert_action_description(
    desc: ActionDescription | None, *, event_id: str | None, event_type: EventType | None
) -> OracleAction | None:
    if desc is None:
        return None

    normalised_args: dict[str, Any] = {}
    for arg in desc.args:
        name = arg.get("name")
        if not name:
            continue
        raw_value = arg.get("value")
        value_type = arg.get("value_type")
        if isinstance(raw_value, str):
            normalised_args[name] = _literal_eval(raw_value, value_type)
        else:
            normalised_args[name] = raw_value

    mapped_app = _map_app_name(desc.app)
    if mapped_app is None:
        return None

    return OracleAction(
        app=mapped_app,
        function=desc.function,
        args=normalised_args,
        description=f"Oracle expectation for {desc.app}.{desc.function}",
        source_event_id=event_id,
        expected_event_type=event_type,
    )


def _partition_events(events: t.Sequence[AbstractEvent]) -> tuple[list[AbstractEvent], list[OracleEvent]]:
    env_events: list[AbstractEvent] = []
    oracle_events: list[OracleEvent] = []
    for event in events:
        if isinstance(event, OracleEvent):
            oracle_events.append(event)
        else:
            env_events.append(event)
    return env_events, oracle_events


def _convert_oracles(events: t.Iterable[OracleEvent]) -> list[OracleAction]:
    converted: list[OracleAction] = []
    for event in events:
        oracle_action = _convert_action_description(
            event.action_desc, event_id=event.event_id, event_type=event.event_type
        )
        if oracle_action is not None:
            converted.append(oracle_action)
    return converted


def build_components_from_meta(
    *,
    meta_apps: t.Iterable[Any],
    meta_events: t.Sequence[AbstractEvent] | None,
    llm: LLMClientProtocol,
    user_llm: LLMClientProtocol,
    max_user_turns: int,
    log_mode: Literal["overwrite", "append"],
    primary_app: str | None,
    oracle_messages: t.Sequence[str] | None = None,
) -> ScenarioSetup:
    """Create PAS components from meta-style app definitions."""
    stateful_apps = _convert_meta_apps(meta_apps)
    if not any(isinstance(app, HomeScreenSystemApp) for app in stateful_apps):
        stateful_apps.append(HomeScreenSystemApp(name="system"))

    setup = build_proactive_stack(
        apps=list(stateful_apps),
        llm=llm,
        user_llm=user_llm,
        max_user_turns=max_user_turns,
        log_mode=log_mode,
        primary_app=primary_app,
        goal_prompt=None,
    )
    env = setup.env

    extracted_oracles: list[OracleEvent] = []
    if meta_events:
        env_events, oracle_events = _partition_events(meta_events)
        _apply_events(env, env_events)
        extracted_oracles.extend(oracle_events)

    if oracle_messages and "AgentUserInterface" in env.apps:
        agent_ui = env.get_app("AgentUserInterface")
        for content in oracle_messages:
            agent_ui.send_message_to_user(content=content)

    converted_oracles = _convert_oracles(extracted_oracles)
    if converted_oracles:
        setup.oracle_actions = converted_oracles

    return setup


def build_meta_scenario_components(
    scenario: Scenario,
    *,
    llm: LLMClientProtocol,
    user_llm: LLMClientProtocol,
    max_user_turns: int,
    log_mode: Literal["overwrite", "append"],
    primary_app: str | None = None,
) -> ScenarioSetup:
    """Construct components from an instantiated Meta ARE scenario class."""
    scenario.initialize()
    meta_apps = scenario.apps or []
    meta_events = scenario.events or []
    oracle_messages: list[str] | None = None
    aui_events = [
        event
        for event in meta_events
        if not isinstance(event, OracleEvent)
        and event.app_name() == "AgentUserInterface"
        and event.function_name() == "send_message_to_agent"
    ]
    if aui_events:
        raw_args = aui_events[0].action.args if aui_events[0].action else {}
        content = raw_args.get("content") if isinstance(raw_args, dict) else None
        if isinstance(content, str):
            oracle_messages = ["Incoming request: " + content]

    return build_components_from_meta(
        meta_apps=meta_apps,
        meta_events=meta_events,
        llm=llm,
        user_llm=user_llm,
        max_user_turns=max_user_turns,
        log_mode=log_mode,
        primary_app=primary_app,
        oracle_messages=oracle_messages,
    )
