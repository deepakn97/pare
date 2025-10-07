"""Helpers to assemble a contacts follow-up scenario stack."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from are.simulation.apps.contacts import Contact, ContactsApp, Gender, Status
from are.simulation.apps.email_client import Email, EmailFolderName
from are.simulation.notification_system import VerbosityLevel
from are.simulation.types import EventType, disable_events

from pas.apps.contacts.app import StatefulContactsApp
from pas.apps.email.app import StatefulEmailApp
from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.system import HomeScreenSystemApp
from pas.scenarios.base import build_proactive_stack
from pas.scenarios.types import OracleAction, ScenarioSetup
from pas.tasks.types import TaskContext, TaskDefinition

__all__ = ["build_contacts_followup_components", "build_pas_contacts_meta_components"]

if TYPE_CHECKING:
    from pas.proactive import LLMClientProtocol


def build_contacts_followup_components(
    *,
    llm: LLMClientProtocol,
    user_llm: LLMClientProtocol,
    max_user_turns: int,
    log_mode: Literal["overwrite", "append"],
    primary_app: str | None = None,
) -> ScenarioSetup:
    """Construct the environment, user proxy, and proactive agent for contacts flows."""
    contacts = StatefulContactsApp(name="contacts")
    email = StatefulEmailApp(name="email")
    messaging = StatefulMessagingApp(name="messaging")
    messaging.name = "messaging"

    system_app = HomeScreenSystemApp(name="system")
    _seed_contacts_app(contacts)
    email_id = _seed_email_app(email)
    messaging_context = _seed_messaging_app(messaging)

    oracle_actions = [
        OracleAction(
            app="email",
            function="forward_email",
            args={"email_id": email_id, "recipients": ["jordan.lee@example.com"], "folder_name": "INBOX"},
            description="Forward the manager's update email to Jordan Lee so they stay in sync before the meeting.",
            expected_event_type=EventType.AGENT,
        )
    ]

    setup = build_proactive_stack(
        apps=[contacts, email, messaging, system_app],
        llm=llm,
        user_llm=user_llm,
        max_user_turns=max_user_turns,
        log_mode=log_mode,
        primary_app=primary_app,
        oracle_actions=oracle_actions,
        notification_verbosity=VerbosityLevel.MEDIUM,
    )

    if messaging_context is not None:
        _emit_initial_messages(messaging, **messaging_context)

    return setup


def build_pas_contacts_meta_components(
    *,
    llm: LLMClientProtocol,
    user_llm: LLMClientProtocol,
    max_user_turns: int,
    log_mode: Literal["overwrite", "append"],
    primary_app: str | None = None,
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
    existing_pairs = {(contact.first_name, contact.last_name) for contact in app.contacts.values()}
    if ("Alex", "Smith") not in existing_pairs:
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
    if ("Jordan", "Lee") not in existing_pairs:
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
    has_user_contact = any(contact.is_user for contact in app.contacts.values())
    if not has_user_contact:
        app.add_contact(
            Contact(
                first_name="Taylor",
                last_name="Brooks",
                phone="+1-202-555-0150",
                email="taylor.brooks@example.com",
                gender=Gender.OTHER,
                status=Status.EMPLOYED,
                is_user=True,
            )
        )


def _seed_email_app(app: StatefulEmailApp) -> str:
    inbox = app.folders.get(EmailFolderName.INBOX)
    if inbox is None:
        raise RuntimeError("Email inbox missing")

    existing = next((email for email in inbox.emails if email.subject == "Client sync prep notes"), None)
    if existing is not None:
        return existing.email_id

    email = Email(
        sender="morgan.rivera@example.com",
        recipients=["user@meta.com"],
        subject="Client sync prep notes",
        content=(
            "Just jotting these down so they're easy to forward:\n\n"
            "- Let Jordan know the deck needs the latest dates\n"
            "- Have them remind engineering about the mobile build freeze\n"
            "- Share the call-in info if they can't join onsite\n\n"
            "Appreciate it!"
        ),
        email_id="client-sync-prep-notes",
    )
    app.add_email(email, folder_name=EmailFolderName.INBOX)
    return email.email_id


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


def _emit_initial_messages(app: StatefulMessagingApp, *, conversation_id: str, sender_id: str) -> None:
    content = (
        "Morning! I just emailed you the client sync prep notes. Please forward that exact email to Jordan Lee "
        "(no need to rewrite anything) so they're ready for the call later today."
    )
    app.create_and_add_message(conversation_id=conversation_id, sender_id=sender_id, content=content)
