"""Utilities to bridge Meta ARE scenarios into PAS stateful environments."""

from __future__ import annotations

import logging
import typing as t
from typing import TYPE_CHECKING, Any, Literal

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.contacts import Contact, ContactsApp, Gender, Status
from are.simulation.apps.email_client import EmailClientApp
from are.simulation.apps.messaging_v2 import MessagingAppV2
from are.simulation.apps.system import SystemApp
from are.simulation.types import EventType

from pas.apps.calendar.app import StatefulCalendarApp
from pas.apps.contacts.app import StatefulContactsApp
from pas.apps.email.app import StatefulEmailApp
from pas.apps.messaging.app import StatefulMessagingApp
from pas.scenarios.contacts_followup import build_contacts_followup_components

LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from are.simulation.scenarios.scenario import Scenario
    from are.simulation.types import AbstractEvent

    from pas.environment import StateAwareEnvironmentWrapper
    from pas.proactive import LLMClientProtocol, ProactiveAgentProtocol
    from pas.user_proxy import StatefulUserProxy
    from pas.user_proxy.decision_maker import LLMDecisionMaker


APP_NAME_MAP = {
    "ContactsApp": "contacts",
    "CalendarApp": "calendar",
    "EmailClientApp": "email",
    "MessagingApp": "messaging",
    "MessagingAppV2": "messaging",
    "SystemApp": "system",
}


def _clone_contacts_app() -> ContactsApp:
    app = ContactsApp(name="contacts")
    app.add_contact(
        Contact(
            first_name="Alex",
            last_name="Smith",
            phone="+1-202-555-0110",
            email="alex.smith@example.com",
            gender=Gender.MALE,
            status=Status.EMPLOYED,
        )
    )
    app.add_contact(
        Contact(
            first_name="Jordan",
            last_name="Lee",
            phone="+1-202-555-0188",
            email="jordan.lee@example.com",
            gender=Gender.OTHER,
            status=Status.UNKNOWN,
        )
    )
    return app


def _clone_messaging_app_with_prompt() -> tuple[MessagingAppV2, str]:
    app = MessagingAppV2(name="messaging")
    previous_id = app.current_user_id
    app.current_user_id = "user-you"
    app.current_user_name = "You"
    if isinstance(previous_id, str) and previous_id in app.id_to_name:
        app.id_to_name.pop(previous_id)
    app.id_to_name[app.current_user_id] = app.current_user_name
    app.name_to_id[app.current_user_name] = app.current_user_id

    app.add_users(["Jordan Lee", "Morgan Rivera"])
    jordan_id = app.get_user_id("Jordan Lee")
    manager_id = app.get_user_id("Morgan Rivera")
    if jordan_id is None or manager_id is None:
        raise RuntimeError("Failed to seed messaging app")

    conversation_id = app.create_group_conversation(user_ids=[jordan_id, manager_id], title="Team Follow-up")

    message = (
        "Jordan missed the standup. Please email Jordan Lee a quick summary of the revised launch "
        "timeline so they can catch up before the client call."
    )
    app.create_and_add_message(conversation_id=conversation_id, sender_id=manager_id, content=message)
    return app, message


def _convert_contact_app(meta_app: ContactsApp) -> StatefulContactsApp:
    stateful = StatefulContactsApp(name="contacts")
    stateful.load_state(meta_app.get_state())
    stateful.name = "contacts"
    return stateful


def _convert_calendar_app(meta_app: CalendarApp) -> StatefulCalendarApp:
    stateful = StatefulCalendarApp(name="calendar")
    stateful.load_state(meta_app.get_state())
    stateful.name = "calendar"
    return stateful


def _convert_email_app(meta_app: EmailClientApp) -> StatefulEmailApp:
    stateful = StatefulEmailApp(name="email")
    stateful.load_state(meta_app.get_state())
    stateful.name = "email"
    return stateful


def _convert_messaging_app(meta_app: MessagingAppV2) -> StatefulMessagingApp:
    stateful = StatefulMessagingApp(name="messaging")
    stateful.load_state(meta_app.get_state())
    stateful.name = "messaging"
    return stateful


CONVERTERS: dict[type, t.Callable[[Any], Any]] = {
    ContactsApp: _convert_contact_app,
    CalendarApp: _convert_calendar_app,
    EmailClientApp: _convert_email_app,
    MessagingAppV2: _convert_messaging_app,
}


def _convert_meta_apps(meta_apps: t.Iterable[Any]) -> list[Any]:
    stateful_apps: list[Any] = []
    for app in meta_apps:
        converter = None
        for cls, conv in CONVERTERS.items():
            if isinstance(app, cls):
                converter = conv
                break
        if converter is not None:
            stateful_apps.append(converter(app))
        else:
            stateful_apps.append(app)
    return stateful_apps


def _apply_events(env: StateAwareEnvironmentWrapper, events: t.Sequence[AbstractEvent]) -> None:
    for event in events:
        if event.event_type is not EventType.ENV:
            continue
        app_name = APP_NAME_MAP.get(event.app_name(), event.app_name().lower())
        try:
            app = env.get_app(app_name)
        except KeyError:
            continue
        function_name = event.function_name()
        if function_name is None:
            continue
        method = getattr(app, function_name, None)
        if method is None:
            continue
        raw_args = event.action.args if event.action else {}
        kwargs: dict[str, Any] = {}
        for arg_name, details in raw_args.items():
            if arg_name == "self":
                continue
            value = details
            if isinstance(details, dict) and "value" in details:
                value = details["value"]
            kwargs[arg_name] = value
        try:
            method(**kwargs)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Failed to replay scenario event %s.%s: %s", app_name, function_name, exc)


def build_components_from_meta(
    *,
    meta_apps: t.Iterable[Any],
    meta_events: t.Sequence[AbstractEvent] | None,
    llm: LLMClientProtocol,
    user_llm: LLMClientProtocol,
    max_user_turns: int,
    log_mode: Literal["overwrite", "append"],
    primary_app: str,
) -> tuple[StateAwareEnvironmentWrapper, StatefulUserProxy, ProactiveAgentProtocol, LLMDecisionMaker]:
    """Create PAS components from meta-style app definitions."""
    stateful_apps = _convert_meta_apps(meta_apps)

    base_env, proxy, agent, decision_maker = build_contacts_followup_components(
        llm=llm, user_llm=user_llm, max_user_turns=max_user_turns, log_mode=log_mode, primary_app=primary_app
    )

    base_env.apps.clear()
    base_env.register_apps(list(stateful_apps))

    if meta_events:
        _apply_events(base_env, meta_events)

    return base_env, proxy, agent, decision_maker


def build_pas_contacts_meta_components(
    *,
    llm: LLMClientProtocol,
    user_llm: LLMClientProtocol,
    max_user_turns: int,
    log_mode: Literal["overwrite", "append"],
    primary_app: str,
) -> tuple[StateAwareEnvironmentWrapper, StatefulUserProxy, ProactiveAgentProtocol, LLMDecisionMaker]:
    """Construct components mirroring the demo scenario using meta-style apps."""
    contacts = _clone_contacts_app()
    messaging, _ = _clone_messaging_app_with_prompt()
    calendar = CalendarApp(name="calendar")
    email = EmailClientApp(name="email")
    system = SystemApp(name="system")
    agui = AgentUserInterface()

    meta_apps = [agui, calendar, email, contacts, messaging, system]
    return build_components_from_meta(
        meta_apps=meta_apps,
        meta_events=None,
        llm=llm,
        user_llm=user_llm,
        max_user_turns=max_user_turns,
        log_mode=log_mode,
        primary_app=primary_app,
    )


def build_meta_scenario_components(
    scenario: Scenario,
    *,
    llm: LLMClientProtocol,
    user_llm: LLMClientProtocol,
    max_user_turns: int,
    log_mode: Literal["overwrite", "append"],
    primary_app: str,
) -> tuple[StateAwareEnvironmentWrapper, StatefulUserProxy, ProactiveAgentProtocol, LLMDecisionMaker]:
    """Construct components from an instantiated Meta ARE scenario class."""
    scenario.initialize()
    meta_apps = scenario.apps or []
    meta_events = scenario.events or []
    return build_components_from_meta(
        meta_apps=meta_apps,
        meta_events=meta_events,
        llm=llm,
        user_llm=user_llm,
        max_user_turns=max_user_turns,
        log_mode=log_mode,
        primary_app=primary_app,
    )
