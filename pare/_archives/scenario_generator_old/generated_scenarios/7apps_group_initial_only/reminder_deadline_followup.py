from __future__ import annotations

import base64
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


@register_scenario("reminder_deadline_followup")
class ScenarioReminderDeadlineFollowup(Scenario):
    """Scenario: The agent receives an urgent email, proposes to create a reminder, user confirms, reminder is created."""

    start_time: float | None = 0
    duration: float | None = 22

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and fill all apps with starting data."""
        aui = AgentUserInterface()
        calendar = CalendarApp()
        email_client = EmailClientApp()
        contacts = ContactsApp()
        messaging = MessagingApp()
        fs = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))
        system = SystemApp()
        default_fs_folders(fs)

        # Add two contacts — an HR Manager and an Employee
        contacts.add_contact(
            Contact(
                first_name="Linda",
                last_name="Briggs",
                phone="+44 556 102 987",
                email="linda.briggs@corp.com",
                status=Status.EMPLOYED,
                job="HR Manager",
                gender=Gender.FEMALE,
            )
        )
        contacts.add_contact(
            Contact(
                first_name="Peter",
                last_name="Young",
                phone="+44 492 883 774",
                email="peter.young@corp.com",
                status=Status.EMPLOYED,
                job="Analyst",
                gender=Gender.MALE,
            )
        )

        self.apps = [aui, calendar, email_client, contacts, messaging, fs, system]

    def build_events_flow(self) -> None:
        """Construct the event timeline for this scenario."""
        email_client = self.get_typed_app(EmailClientApp)
        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(CalendarApp)
        contacts = self.get_typed_app(ContactsApp)

        with EventRegisterer.capture_mode():
            # User triggers initial proactive assistant setup
            user_init = aui.send_message_to_agent(
                content="Hey Assistant, please check new emails for anything marked urgent and suggest if a reminder is needed."
            ).depends_on(None, delay_seconds=1)

            # HR manager sends an urgent email to the user
            urgent_email = email_client.send_email_to_user(
                email=Email(
                    sender="linda.briggs@corp.com",
                    recipients=[email_client.user_email],
                    subject="URGENT: Submit Timesheet by Tomorrow EOD",
                    content="Reminder: The monthly timesheet submission is due by tomorrow EOD. Please confirm receipt.",
                    attachments={"timesheet_guidelines.pdf": base64.b64encode(b"Timesheet rules and steps")},
                    email_id="linda_msg_urgent",
                )
            ).depends_on(user_init, delay_seconds=2)

            # Agent proposes creating a reminder
            agent_propose = aui.send_message_to_user(
                content="I noticed an urgent request from Linda Briggs about submitting your timesheet tomorrow. Shall I create a reminder for you?"
            ).depends_on(urgent_email, delay_seconds=1)

            # User agrees to create reminder
            user_confirm = aui.send_message_to_agent(
                content="Yes, please create a reminder for that tomorrow afternoon."
            ).depends_on(agent_propose, delay_seconds=1)

            # Oracle truth: agent creates the calendar reminder
            create_reminder = (
                calendar.add_calendar_event(
                    title="Submit Timesheet - HR Deadline",
                    start_datetime="1970-01-02 15:00:00",
                    end_datetime="1970-01-02 15:15:00",
                    tag="work",
                    description="Timesheet submission deadline (per Linda Briggs).",
                )
                .oracle()
                .depends_on(user_confirm, delay_seconds=1)
            )

        self.events = [user_init, urgent_email, agent_propose, user_confirm, create_reminder]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Check if a reminder event was properly created after confirmation."""
        try:
            logs = env.event_log.list_view()

            reminder_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Timesheet" in e.action.args.get("title", "")
                for e in logs
            )

            confirmation_request = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and ("reminder" in e.action.args.get("content", "").lower())
                and ("linda" in e.action.args.get("content", "").lower())
                for e in logs
            )

            user_approved = any(
                e.event_type == EventType.USER
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "create a reminder" in e.action.args.get("content", "").lower()
                for e in logs
            )

            success = reminder_created and confirmation_request and user_approved
            return ScenarioValidationResult(success=success)
        except Exception as ex:
            return ScenarioValidationResult(success=False, exception=ex)
