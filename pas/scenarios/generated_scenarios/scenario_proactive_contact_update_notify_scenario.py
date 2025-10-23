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


@register_scenario("scenario_proactive_contact_update_notify")
class ScenarioProactiveContactUpdateNotify(Scenario):
    """Agent proactively detects outdated contact info and proposes update based on new email."""

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate required applications."""
        agui = AgentUserInterface()
        contacts = ContactsApp()
        email_client = EmailClientApp()
        messaging = MessagingApp()
        system = SystemApp()
        calendar = CalendarApp()
        fs = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))

        default_fs_folders(fs)

        # Populate contacts with an initial entry for a friend
        contacts.add_contact(
            Contact(
                first_name="Emily",
                last_name="Park",
                phone="+1 202 333 8932",
                email="emily.park@oldcompany.com",
                gender=Gender.FEMALE,
                status=Status.EMPLOYED,
                job="Marketing Manager",
                city_living="New York",
                country="USA",
                age=35,
            )
        )

        contacts.add_contact(
            Contact(
                first_name="Lucas",
                last_name="Hughes",
                phone="+1 707 555 9921",
                email="lucas.h@example.com",
                gender=Gender.MALE,
                status=Status.EMPLOYED,
                job="Engineer",
                city_living="Boston",
                country="USA",
                age=31,
            )
        )

        self.apps = [agui, contacts, email_client, messaging, system, calendar, fs]

    def build_events_flow(self) -> None:
        """Define the sequence of scenario events."""
        aui = self.get_typed_app(AgentUserInterface)
        email_app = self.get_typed_app(EmailClientApp)
        messaging = self.get_typed_app(MessagingApp)

        emily_conversation = messaging.create_conversation(participants=["Emily Park"], title="Reunion with Emily")

        with EventRegisterer.capture_mode():
            # Event 0: User asks assistant to monitor important updates in contact communications
            intro_evt = aui.send_message_to_agent(
                content="Assistant, please track any contact updates in new messages or emails."
            ).depends_on(None, delay_seconds=1)

            # Event 1: Emily sends an email from a new domain indicating change
            incoming_email = email_app.send_email_to_user(
                email=Email(
                    sender="emily.park@newcompany.com",
                    recipients=[email_app.user_email],
                    subject="New Work Email Update",
                    content=(
                        "Hey, just a quick note to let you know I have a new company address now! "
                        "Please update your records from oldcompany.com to newcompany.com."
                    ),
                    email_id="emily_update_1",
                )
            ).depends_on(intro_evt, delay_seconds=2)

            # Event 2: Agent notifies the user of possible outdated contact data
            notify_user = aui.send_message_to_user(
                content="I noticed Emily Park emailed from a new address. Would you like me to update her contact info?"
            ).depends_on(incoming_email, delay_seconds=2)

            # Event 3: User confirms update
            confirm_update = aui.send_message_to_agent(
                content="Yes, please update Emily's contact to her new email address."
            ).depends_on(notify_user, delay_seconds=2)

            # Event 4: Oracle action: assistant updates contact information in contacts app
            apply_update = (
                self.get_typed_app(ContactsApp)
                .edit_contact(contact_id="1", updates={"email": "emily.park@newcompany.com"})
                .oracle()
                .depends_on(confirm_update, delay_seconds=1)
            )

            # Event 5: Follow-up message logged after update confirmation
            final_message = messaging.send_message(
                conversation_id=emily_conversation,
                content="Hi Emily, I've updated your contact info in my address book!",
            ).depends_on(apply_update, delay_seconds=2)

        self.events = [intro_evt, incoming_email, notify_user, confirm_update, apply_update, final_message]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Check if the contact was updated as expected and user was informed."""
        try:
            log = env.event_log.list_view()
            contact_updated = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "ContactsApp"
                and ev.action.function_name == "edit_contact"
                and ev.action.args.get("updates", {}).get("email") == "emily.park@newcompany.com"
                for ev in log
            )
            user_alerted = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "AgentUserInterface"
                and ev.action.function_name == "send_message_to_user"
                and "emily" in ev.action.args["content"].lower()
                and "update" in ev.action.args["content"].lower()
                for ev in log
            )
            message_sent = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "MessagingApp"
                and ev.action.function_name == "send_message"
                and "updated your contact" in ev.action.args["content"].lower()
                for ev in log
            )
            return ScenarioValidationResult(success=contact_updated and user_alerted and message_sent)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
