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


@register_scenario("schedule_meeting")
class ScenarioTutorialScheduleMeeting(Scenario):
    """Agent proactively proposes scheduling a meeting after user receives email invitations."""

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate the necessary apps."""
        agui = AgentUserInterface()
        calendar = CalendarApp()
        email_client = EmailClientApp()
        contacts = ContactsApp()
        fs = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))
        messaging = MessagingApp()
        system = SystemApp()

        default_fs_folders(fs)

        contacts.add_contact(
            Contact(
                first_name="Alice",
                last_name="Foster",
                phone="+33 456 987 1234",
                email="alicefoster@example.com",
                gender=Gender.FEMALE,
                status=Status.EMPLOYED,
                age=31,
            )
        )

        contacts.add_contact(
            Contact(
                first_name="Bob",
                last_name="King",
                phone="+33 456 234 9988",
                email="bobking@example.com",
                gender=Gender.MALE,
                status=Status.EMPLOYED,
                age=29,
            )
        )

        self.apps = [agui, calendar, email_client, contacts, fs, messaging, system]

    def build_events_flow(self) -> None:
        """Construct the event flow for scheduling a meeting scenario."""
        aui = self.get_typed_app(AgentUserInterface)
        email_client = self.get_typed_app(EmailClientApp)
        calendar = self.get_typed_app(CalendarApp)

        with EventRegisterer.capture_mode():
            # User requests help
            start_msg = aui.send_message_to_agent(
                content="Assistant, please keep an eye on my inbox for any meeting invitations."
            ).depends_on(None, delay_seconds=1)

            # Alice sends an email about a meeting
            alice_email = email_client.send_email_to_user(
                email=Email(
                    sender="alicefoster@example.com",
                    recipients=[email_client.user_email],
                    subject="Project Update Meeting",
                    content="Hi, can we arrange a project update meeting with Bob this week?",
                    attachments={},
                    email_id="alice_email",
                )
            ).depends_on(start_msg, delay_seconds=1)

            # Agent proactively proposes a response to organize the meeting
            agent_propose = aui.send_message_to_user(
                content=(
                    "You received an email from Alice asking to set up a meeting with Bob. "
                    "Shall I check your calendar and suggest times?"
                )
            ).depends_on(alice_email, delay_seconds=1)

            # User confirms the proposal
            user_confirm = aui.send_message_to_agent(
                content="Yes, please check and propose a time that works for us."
            ).depends_on(agent_propose, delay_seconds=1)

            # Oracle event: agent schedules a meeting in the calendar app
            oracle_schedule = (
                calendar.add_calendar_event(
                    title="Project Update Meeting",
                    start_datetime="1970-01-01 00:00:03",
                    end_datetime="1970-01-01 00:00:04",
                    attendees=["Alice Foster", "Bob King"],
                    description="Discuss project updates and next steps.",
                )
                .oracle()
                .depends_on(user_confirm, delay_seconds=1)
            )

        self.events = [start_msg, alice_email, agent_propose, user_confirm, oracle_schedule]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate whether the agent scheduled the meeting correctly."""
        try:
            events = env.event_log.list_view()
            meeting_created = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "CalendarApp"
                and event.action.function_name == "add_calendar_event"
                and "Project Update Meeting" in event.action.args.get("title", "")
                for event in events
            )

            proactive_message = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "AgentUserInterface"
                and "meeting" in event.action.args.get("content", "").lower()
                for event in events
            )

            return ScenarioValidationResult(success=(meeting_created and proactive_message))
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
