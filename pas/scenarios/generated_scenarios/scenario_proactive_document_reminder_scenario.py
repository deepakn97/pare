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


@register_scenario("scenario_proactive_document_reminder")
class ScenarioProactiveDocumentReminder(Scenario):
    """Proactive scenario: assistant receives report email, proposes to set a reminder, user confirms, agent creates calendar reminder."""

    start_time: float | None = 0
    duration: float | None = 30

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate applications with data and environment context."""
        aui = AgentUserInterface()
        calendar = CalendarApp()
        email_client = EmailClientApp()
        contacts = ContactsApp()
        fs = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))
        messaging = MessagingApp()
        system = SystemApp()

        default_fs_folders(fs)

        contacts.add_contact(
            Contact(
                first_name="Clara",
                last_name="Williams",
                phone="+44 202 999 1837",
                email="clara.williams@corp.com",
                gender=Gender.FEMALE,
                status=Status.EMPLOYED,
                age=31,
            )
        )
        contacts.add_contact(
            Contact(
                first_name="Daniel",
                last_name="Evans",
                phone="+44 913 222 5581",
                email="daniel.evans@corp.com",
                gender=Gender.MALE,
                status=Status.EMPLOYED,
                age=38,
            )
        )

        self.apps = [aui, calendar, email_client, contacts, fs, messaging, system]

    def build_events_flow(self) -> None:
        """Define the series of events that constitute the scenario."""
        email_client = self.get_typed_app(EmailClientApp)
        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(CalendarApp)

        with EventRegisterer.capture_mode():
            # Event 0: user instructs assistant to monitor incoming project emails
            event0 = aui.send_message_to_agent(
                content="Please monitor my inbox for project-related reports and suggest reminders if anything important arrives."
            ).depends_on(None, delay_seconds=1)

            # Event 1: Clara sends a project status report email
            event1 = email_client.send_email_to_user(
                email=Email(
                    sender="clara.williams@corp.com",
                    recipients=[email_client.user_email],
                    subject="Quarterly Project Update Report",
                    content="Hello, please find attached the quarterly status update for review before Thursday meeting.",
                    attachments={"project_report_Q1.pdf": base64.b64encode(b"Quarterly Project Report Content")},
                    email_id="email_clara_report",
                )
            ).depends_on(event0, delay_seconds=4)

            # Event 2: Agent proposes setting up a reminder to review the report
            event2 = aui.send_message_to_user(
                content="I noticed an email from Clara with a quarterly project report. Would you like me to set a reminder to review it before the Thursday meeting?"
            ).depends_on(event1, delay_seconds=2)

            # Event 3: user confirms they want the reminder
            event3 = aui.send_message_to_agent(
                content="Yes, please set a reminder to review the report tomorrow morning."
            ).depends_on(event2, delay_seconds=3)

            # Event 4: agent acts and sets a reminder in the calendar (oracle)
            event4 = (
                calendar.add_calendar_event(
                    title="Review Clara's Project Report",
                    start_datetime="1970-01-02 09:00:00",
                    end_datetime="1970-01-02 09:30:00",
                    tag="reminder",
                    description="Review the quarterly project report from Clara before Thursday meeting.",
                )
                .oracle()
                .depends_on(event3, delay_seconds=1)
            )

        self.events = [event0, event1, event2, event3, event4]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate successful behavior based on actions taken by the simulated agent."""
        try:
            events = env.event_log.list_view()

            reminder_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Review Clara" in e.action.args.get("title", "")
                for e in events
            )

            proposal_made = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "reminder" in e.action.args.get("content", "").lower()
                for e in events
            )

            return ScenarioValidationResult(success=(proposal_made and reminder_created))
        except Exception as ex:
            return ScenarioValidationResult(success=False, exception=ex)
