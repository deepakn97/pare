from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.contacts import Contact, ContactsApp, Gender, Status
from are.simulation.apps.email_client import Email, EmailClientApp
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.sandbox_file_system import SandboxLocalFileSystem
from are.simulation.apps.system import SystemApp
from are.simulation.data.population_scripts.sandbox_file_system_population import default_fs_folders
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("followup_contact_update")
class ScenarioFollowUpContactUpdate(Scenario):
    """Proactive behavior: agent identifies new email containing contact details.

    Proposes to update contact record, user confirms, agent updates contacts database.
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate required applications."""
        agui = AgentUserInterface()
        email_client = EmailClientApp()
        contacts = ContactsApp()
        system = SystemApp()
        fs = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))
        messaging = MessagingApp()
        calendar = CalendarApp()

        default_fs_folders(fs)

        # populate contacts
        contacts.add_contact(
            Contact(
                first_name="Amanda",
                last_name="Lake",
                phone="+44 7012 345678",
                email="amanda.lake@creativeworks.com",
                gender=Gender.FEMALE,
                status=Status.EMPLOYED,
                job="Marketing Lead",
                country="UK",
            )
        )
        contacts.add_contact(
            Contact(
                first_name="Brian",
                last_name="Stone",
                phone="+44 7770 223344",
                email="brianstone@designhub.io",
                gender=Gender.MALE,
                status=Status.EMPLOYED,
                job="Graphic Designer",
                country="UK",
            )
        )

        self.apps = [agui, email_client, contacts, fs, messaging, calendar, system]

    def build_events_flow(self) -> None:
        """Define the sequence of scenario events."""
        aui = self.get_typed_app(AgentUserInterface)
        email_client = self.get_typed_app(EmailClientApp)
        contacts = self.get_typed_app(ContactsApp)

        with EventRegisterer.capture_mode():
            # initial user setup
            e0 = aui.send_message_to_agent(
                content="Assistant, please help me keep my contacts up-to-date based on my emails."
            ).depends_on(None, delay_seconds=1)

            # New email arrives with updated contact details
            e1 = email_client.send_email_to_user(
                email=Email(
                    sender="amanda.lake@creativeworks.com",
                    recipients=[email_client.user_email],
                    subject="Updated Contact Info",
                    content=(
                        "Hi there, just letting you know I've got a new phone number: +44 7900 556677 "
                        "and I've moved offices to the Edinburgh branch."
                    ),
                    email_id="msg2847",
                )
            ).depends_on(e0, delay_seconds=1)

            # Agent proactively suggests updating Amanda's contact info
            e2 = aui.send_message_to_user(
                content=(
                    "I noticed Amanda Lake sent you an email mentioning a new phone number and office. "
                    "Should I update her contact record with these details?"
                )
            ).depends_on(e1, delay_seconds=2)

            # User confirms that agent should proceed
            e3 = aui.send_message_to_agent(content="Yes, please update Amanda's information accordingly.").depends_on(
                e2, delay_seconds=1
            )

            # Agent performs the edit in ContactsApp (oracle)
            e4 = (
                contacts.edit_contact(
                    contact_id="amanda.lake@creativeworks.com",
                    updates={"phone": "+44 7900 556677", "city_living": "Edinburgh"},
                )
                .oracle()
                .depends_on(e3, delay_seconds=2)
            )

            # Optionally, agent confirms completion
            e5 = aui.send_message_to_user(
                content="Done. Amanda's contact details have been updated in your contacts."
            ).depends_on(e4, delay_seconds=1)

        self.events = [e0, e1, e2, e3, e4, e5]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Check if the contact was updated as expected and user was informed."""
        try:
            events = env.event_log.list_view()

            contact_update_done = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "ContactsApp"
                and event.action.function_name == "edit_contact"
                and "amanda.lake@creativeworks.com" in event.action.args.get("contact_id", "")
                and "Edinburgh" in str(event.action.args.get("updates", ""))
                for event in events
            )

            confirmation_sent = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "AgentUserInterface"
                and event.action.function_name == "send_message_to_user"
                and "updated" in event.action.args.get("content", "").lower()
                and "amanda" in event.action.args.get("content", "").lower()
                for event in events
            )

            return ScenarioValidationResult(success=(contact_update_done and confirmation_sent))
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
