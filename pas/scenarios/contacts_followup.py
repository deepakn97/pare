"""Helpers to assemble a contacts follow-up scenario stack."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from are.simulation.apps.contacts import Contact, ContactsApp, Gender, Status
from are.simulation.apps.system import SystemApp
from are.simulation.notification_system import VerbosityLevel
from are.simulation.types import disable_events
from are.simulation.validation.constants import APP_ALIAS

from pas.apps.calendar.app import StatefulCalendarApp
from pas.apps.contacts.app import StatefulContactsApp
from pas.apps.email.app import StatefulEmailApp
from pas.apps.messaging.app import StatefulMessagingApp
from pas.logging_utils import get_pas_file_logger
from pas.proactive import LLMBasedProactiveAgent, LLMClientProtocol, ProactiveAgentProtocol
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
    from pas.environment import StateAwareEnvironmentWrapper

__all__ = ["build_contacts_followup_components"]


def _ensure_stateful_messaging_alias() -> None:
    if "MessagingAppV2" not in APP_ALIAS:
        APP_ALIAS["MessagingAppV2"] = ["StatefulMessagingApp"]
        return
    aliases = APP_ALIAS["MessagingAppV2"]
    if "StatefulMessagingApp" not in aliases:
        aliases.append("StatefulMessagingApp")


def build_contacts_followup_components(
    *,
    llm: LLMClientProtocol,
    user_llm: LLMClientProtocol,
    max_user_turns: int,
    log_mode: Literal["overwrite", "append"],
    primary_app: str,
) -> tuple[StateAwareEnvironmentWrapper, StatefulUserProxy, ProactiveAgentProtocol, LLMDecisionMaker]:
    """Construct the environment, user proxy, and proactive agent for contacts flows."""
    log_dir = Path("logs") / "pas"
    user_log = log_dir / "user_proxy.log"
    proactive_log = log_dir / "proactive_agent.log"
    events_log = log_dir / "events.log"

    initialise_runtime(log_paths=[user_log, proactive_log, events_log], clear_existing=log_mode == "overwrite")
    _ensure_stateful_messaging_alias()

    notification_system = create_notification_system(verbosity=VerbosityLevel.MEDIUM)

    env = create_environment(notification_system)
    contacts = StatefulContactsApp(name="contacts")
    calendar = StatefulCalendarApp(name="calendar")
    email = StatefulEmailApp(name="email")
    messaging = StatefulMessagingApp(name="messaging")
    messaging.name = "messaging"

    system_app = SystemApp(name="system")
    env.register_apps([contacts, calendar, email, messaging, system_app])

    _seed_contacts_app(contacts)
    messaging_context = _seed_messaging_app(messaging)

    app_sequence = [contacts.name, calendar.name, email.name, messaging.name]
    if primary_app not in app_sequence:
        raise ValueError(f"Unknown primary_app '{primary_app}'")

    user_logger = get_pas_file_logger("pas.user_proxy", user_log, level=logging.DEBUG)
    planner_logger = get_pas_file_logger("pas.user_proxy.planner", user_log, level=logging.DEBUG)
    decision_logger = get_pas_file_logger("pas.user_proxy.decisions", user_log, level=logging.DEBUG)
    orchestrator_logger = get_pas_file_logger("pas.proactive.orchestrator", proactive_log, level=logging.DEBUG)
    agent_logger = get_pas_file_logger("pas.proactive.agent", proactive_log, level=logging.DEBUG)

    planner_cb = build_stateful_user_planner(
        user_llm,
        [contacts, calendar, email, messaging, system_app],
        initial_app_name=primary_app,
        include_system_tools=True,
        logger=planner_logger,
    )
    decision_maker = LLMDecisionMaker(user_llm, logger=decision_logger)
    plan_executor_cb = build_plan_executor(
        llm,
        (),
        system_prompt=(
            "You plan proactive interventions as a mobile assistant. "
            "Reason about the goal, identify missing context, and pick the next tool that advances progress. "
            "Gather supporting information before committing to final actions. One response represents a single step in a multi-step plan."
        ),
        logger=orchestrator_logger,
    )

    user_proxy = StatefulUserProxy(
        env, env.notification_system, max_user_turns=max_user_turns, logger=user_logger, planner=planner_cb
    )

    agent = LLMBasedProactiveAgent(
        llm,
        system_prompt="You summarise recent completed events and suggest helpful follow-ups.",
        max_context_events=200,
        plan_executor=plan_executor_cb,
        summary_builder=lambda result: result.notes,
        logger=agent_logger,
    )

    env.subscribe_to_completed_events(agent.observe)
    attach_event_logging(env, events_log)

    if messaging_context is not None:
        _emit_initial_message(messaging, **messaging_context)

    return env, user_proxy, agent, decision_maker


def _seed_contacts_app(app: ContactsApp) -> None:
    if app.get_contacts()["contacts"]:
        return
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


def _seed_messaging_app(app: StatefulMessagingApp) -> dict[str, str] | None:
    if app.conversations:
        return None

    previous_id = app.current_user_id
    app.current_user_id = "user-you"
    app.current_user_name = "You"

    app.conversation_view_limit = 25
    app.messages_view_limit = 40

    if isinstance(previous_id, str) and previous_id != app.current_user_id and previous_id in app.id_to_name:
        app.id_to_name.pop(previous_id)

    app.id_to_name[app.current_user_id] = app.current_user_name
    app.name_to_id[app.current_user_name] = app.current_user_id

    app.add_users(["Jordan Lee", "Morgan Rivera"])
    jordan_id = app.get_user_id("Jordan Lee")
    manager_id = app.get_user_id("Morgan Rivera")
    if jordan_id is None or manager_id is None:
        raise RuntimeError("Failed to initialise messaging contacts")

    with disable_events():
        conversation_id = app.create_group_conversation(user_ids=[jordan_id, manager_id], title="Team Follow-up")

    return {"conversation_id": conversation_id, "sender_id": manager_id}


def _emit_initial_message(app: StatefulMessagingApp, *, conversation_id: str, sender_id: str) -> None:
    message = (
        "Jordan missed the standup. Please email Jordan Lee a quick summary of the revised launch timeline "
        "so they can catch up before the client call."
    )
    app.create_and_add_message(conversation_id=conversation_id, sender_id=sender_id, content=message)
