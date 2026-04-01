from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.email_client import Email, EmailClientApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("proactive_meeting_summary_share")
class ProactiveMeetingSummaryShare(Scenario):
    """Scenario: The agent receives a meeting summary email, proposes to share it and create a calendar event for follow-up."""

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all required applications with mock data."""
        aui = AgentUserInterface()
        calendar = CalendarApp()
        contacts = ContactsApp()
        email = EmailClientApp()
        system = SystemApp(name="system_main")

        # Populate some contacts
        contacts.add_new_contact(
            first_name="Jordan",
            last_name="Miller",
            gender=Gender.MALE,
            status=Status.EMPLOYED,
            job="Project Manager",
            phone="+1-222-555-0181",
            email="jordan.miller@example.com",
        )
        contacts.add_new_contact(
            first_name="Alex",
            last_name="Smith",
            gender=Gender.FEMALE,
            status=Status.EMPLOYED,
            job="Software Developer",
            phone="+1-222-555-0190",
            email="alex.smith@example.com",
        )

        self.apps = [aui, calendar, contacts, email, system]

    def build_events_flow(self) -> None:
        """Describe the chronological flow of events."""
        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(CalendarApp)
        email_app = self.get_typed_app(EmailClientApp)
        contacts = self.get_typed_app(ContactsApp)
        system_app = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # User sends a first message asking about unread emails for team updates
            user_init = aui.send_message_to_agent(
                content="Hey Assistant, check if there's any email from Alex about the project updates."
            ).depends_on(None, delay_seconds=1)

            # The agent would find one relevant email (oracle ground truth)
            incoming_email = email_app.send_email_to_user(
                email=Email(
                    email_id="email_001",
                    sender="alex.smith@example.com",
                    recipients=["user@example.com"],
                    subject="Project Alpha - Weekly Summary",
                    content="Here's the summary of the week's progress and next steps for the team discussion.",
                )
            ).depends_on(user_init, delay_seconds=2)

            # Agent proposes to share it with Jordan (proactive step)
            agent_proposal = aui.send_message_to_user(
                content="I found an email from Alex titled 'Project Alpha - Weekly Summary'. Would you like me to forward it to Jordan Miller and add a calendar session for next week to review it together?"
            ).depends_on(incoming_email, delay_seconds=1)

            # User approves with contextual confirmation
            user_confirmation = aui.send_message_to_agent(
                content="Yes, please share it with Jordan and set up that review session for next Wednesday morning."
            ).depends_on(agent_proposal, delay_seconds=1)

            # Agent forwards email after user confirmation (oracle truth)
            forward_mail = (
                email_app.forward_email(email_id="email_001", recipients=["jordan.miller@example.com"])
                .oracle()
                .depends_on(user_confirmation, delay_seconds=1)
            )

            # Agent gets current time from system to prepare proper scheduling
            current_time = system_app.get_current_time().depends_on(forward_mail, delay_seconds=1)

            # Agent then creates a follow-up meeting event into the calendar
            create_event = (
                calendar.add_calendar_event(
                    title="Project Alpha Review Meeting",
                    start_datetime="2024-06-12 10:00:00",
                    end_datetime="2024-06-12 11:00:00",
                    tag="Project Alpha",
                    description="Discuss Alex's weekly summary and define next week milestones.",
                    attendees=["Jordan Miller", "Alex Smith"],
                    location="Main Office - Meeting Room 2",
                )
                .oracle()
                .depends_on(current_time, delay_seconds=2)
            )

            # Wait for short delay notification (simulate background idle)
            system_wait = system_app.wait_for_notification(timeout=2).depends_on(create_event, delay_seconds=1)

        self.events = [
            user_init,
            incoming_email,
            agent_proposal,
            user_confirmation,
            forward_mail,
            current_time,
            create_event,
            system_wait,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Verify that email was forwarded and meeting added."""
        try:
            events = env.event_log.list_view()

            email_forwarded = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "EmailClientApp"
                and e.action.function_name == "forward_email"
                and "jordan.miller@example.com" in e.action.args["recipients"]
                for e in events
            )

            event_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Project Alpha Review Meeting" in e.action.args["title"]
                for e in events
            )

            proposal_to_user = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "forward" in e.action.args["content"].lower()
                and "calendar" in e.action.args["content"].lower()
                for e in events
            )

            return ScenarioValidationResult(success=(email_forwarded and event_created and proposal_to_user))
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
