"""Helpers to assemble a contacts follow-up scenario stack."""

from __future__ import annotations

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
from pas.scenarios.base import build_proactive_stack
from pas.scenarios.types import OracleAction, ScenarioSetup
from pas.tasks.types import TaskContext, TaskDefinition

__all__ = ["build_contacts_followup_components", "build_pas_contacts_meta_components"]

if TYPE_CHECKING:
    from pas.proactive import LLMClientProtocol


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
) -> ScenarioSetup:
    """Construct the environment, user proxy, and proactive agent for contacts flows."""
    _ensure_stateful_messaging_alias()

    contacts = StatefulContactsApp(name="contacts")
    calendar = StatefulCalendarApp(name="calendar")
    email = StatefulEmailApp(name="email")
    messaging = StatefulMessagingApp(name="messaging")
    messaging.name = "messaging"

    system_app = SystemApp(name="system")
    _seed_contacts_app(contacts)
    messaging_context = _seed_messaging_app(messaging)

    oracle_actions = [
        OracleAction(
            app="email",
            function="send_email",
            args={
                "recipients": ["jordan.lee@example.com"],
                "subject": "Revised launch timeline summary",
                "content": (
                    "Provide Jordan with a concise rundown of the updated launch timeline, highlighting"
                    " key milestones, any delays, and next steps."
                ),
                "cc": [],
                "attachment_paths": [],
            },
            description=(
                "After gathering the revised launch timeline, email Jordan Lee with a clear summary so"
                " they can prepare before the client call."
            ),
        )
    ]

    setup = build_proactive_stack(
        apps=[contacts, calendar, email, messaging, system_app],
        llm=llm,
        user_llm=user_llm,
        max_user_turns=max_user_turns,
        log_mode=log_mode,
        primary_app=primary_app,
        oracle_actions=oracle_actions,
        notification_verbosity=VerbosityLevel.MEDIUM,
    )

    if messaging_context is not None:
        _emit_initial_message(messaging, **messaging_context)

    return setup


def build_pas_contacts_meta_components(
    *,
    llm: LLMClientProtocol,
    user_llm: LLMClientProtocol,
    max_user_turns: int,
    log_mode: Literal["overwrite", "append"],
    primary_app: str,
) -> ScenarioSetup:
    """Reuse the base contacts follow-up components for meta-style scaffolding."""
    return build_contacts_followup_components(
        llm=llm, user_llm=user_llm, max_user_turns=max_user_turns, log_mode=log_mode, primary_app=primary_app
    )


def build_contacts_followup_task(
    *,
    task_id: str = "contacts_followup",
    description: str = "Follow up with Jordan Lee via email after receiving a manager's ping.",
) -> TaskDefinition:
    """Return a task definition that recreates the contacts follow-up scenario."""

    def _builder(context: TaskContext) -> ScenarioSetup:
        return build_contacts_followup_components(
            llm=context.llm,
            user_llm=context.user_llm,
            max_user_turns=context.max_user_turns,
            log_mode=context.log_mode,
            primary_app=context.primary_app,
        )

    return TaskDefinition(task_id=task_id, description=description, scenario_builder=_builder)


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
