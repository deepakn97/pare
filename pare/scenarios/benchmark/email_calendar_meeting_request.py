"""Proactive calendar event creation from meeting request email with availability check."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.contacts import Contact
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulCalendarApp,
    StatefulContactsApp,
    StatefulEmailApp,
)
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("email_calendar_meeting_request")
class EmailCalendarMeetingRequest(PAREScenario):
    """Agent reads meeting request email, checks calendar availability, and offers to create event.

    User receives a meeting request email from colleague with date/time/location details.
    Proactive agent detects the meeting request, checks calendar for conflicts, and either:
    (1) creates the event if user is free, or (2) suggests alternative times if there's a conflict.
    """

    # Scenario starts on 2025-11-11 at 9:00 AM UTC (ecologically valid timestamp)
    # This ensures notification timestamps align with calendar event dates
    start_time = datetime(2025, 11, 11, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        # Initialize apps
        self.email = StatefulEmailApp(name="Emails")
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.contacts = StatefulContactsApp(name="Contacts")
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Populate contacts - Add Sarah Johnson (meeting requester)
        self.contacts.add_contact(
            Contact(
                first_name="Sarah",
                last_name="Johnson",
                contact_id="contact-sarah-johnson",
                email="sarah.johnson@company.com",
                phone="555-123-4567",
            )
        )

        # Populate calendar - Add existing events on Nov 19 (no conflict with 2-3 PM slot)
        # Event 1: Morning standup (9-10 AM)
        self.calendar.add_calendar_event(
            title="Team Standup",
            start_datetime="2025-11-19 09:00:00",
            end_datetime="2025-11-19 10:00:00",
            attendees=["Development Team"],
            location="Virtual",
        )

        # Event 2: Late afternoon client call (4-5 PM)
        self.calendar.add_calendar_event(
            title="Client Status Update",
            start_datetime="2025-11-19 16:00:00",
            end_datetime="2025-11-19 17:00:00",
            attendees=["John Smith", "Client Team"],
            location="Conference Room B",
        )

        # Email app starts empty (meeting request arrives as event in build_events_flow)

        # Register all apps
        self.apps = [self.email, self.calendar, self.contacts, self.agent_ui, self.system_app]

    def build_events_flow(self) -> None:
        """Build event flow - incoming email triggers proactive calendar check and event creation."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        email = self.get_typed_app(StatefulEmailApp, "Emails")
        calendar = self.get_typed_app(StatefulCalendarApp, "Calendar")

        with EventRegisterer.capture_mode():
            # Event 1: Incoming meeting request email from Sarah (environment event)
            email_event = email.send_email_to_user_only(
                sender="sarah.johnson@company.com",
                subject="Project Planning Meeting - Next Tuesday",
                content="Hi! I'd like to schedule a project planning meeting next Tuesday, November 19th at 2:00 PM. The meeting will be 1 hour long and we'll meet at Downtown Office - Conference Room A. Let me know if this works for you without any calendar conflicts!",
            ).delayed(20)

            # Event 2: Agent proactively proposes to check calendar and add meeting (oracle)
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed you received a meeting request from Sarah Johnson for next Tuesday, November 19th at 2:00 PM. Would you like me to check your calendar and add this meeting?"
                )
                .oracle()
                .depends_on(email_event, delay_seconds=2)
            )

            # Event 3: User accepts the proposal (oracle)
            acceptance_event = (
                aui.accept_proposal(content="Yes, please check my calendar and add it.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Event 4: Agent checks calendar availability for 2-3 PM slot (oracle)
            check_event = (
                calendar.get_calendar_events_from_to(
                    start_datetime="2025-11-19 14:00:00",
                    end_datetime="2025-11-19 15:00:00",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Event 5: Agent creates calendar event (oracle)
            create_event = (
                calendar.add_calendar_event(
                    title="Project Planning Meeting with Sarah",
                    start_datetime="2025-11-19 14:00:00",
                    end_datetime="2025-11-19 15:00:00",
                    location="Downtown Office - Conference Room A",
                    attendees=["Sarah Johnson"],
                )
                .oracle()
                .depends_on(check_event, delay_seconds=1)
            )

            # Event 6: Agent confirms successful completion (oracle)
            confirmation_event = (
                aui.send_message_to_user(
                    content="I've added the meeting to your calendar for Tuesday, November 19th at 2:00 PM. You're free at that time - you have Team Standup in the morning and Client Status Update later at 4 PM."
                )
                .oracle()
                .depends_on(create_event, delay_seconds=1)
            )

        # Register all events
        self.events = [
            email_event,
            proposal_event,
            acceptance_event,
            check_event,
            create_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent checked calendar and created event or suggested alternatives."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1: Agent sent proposal mentioning Sarah Johnson and calendar/meeting
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PAREAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "Sarah Johnson" in e.action.args.get("content", "")
                and any(
                    keyword in e.action.args.get("content", "")
                    for keyword in ["November 19", "next Tuesday", "calendar"]
                )
                for e in log_entries
            )

            # Check 2: Agent checked calendar using get_calendar_events_from_to
            calendar_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "get_calendar_events_from_to"
                for e in log_entries
            )

            # Check 3: Agent created calendar event with correct details
            event_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and e.action.args.get("start_datetime") == "2025-11-19 14:00:00"
                and e.action.args.get("end_datetime") == "2025-11-19 15:00:00"
                and (
                    "Downtown Office" in e.action.args.get("location", "")
                    or "Conference Room A" in e.action.args.get("location", "")
                )
                and "Sarah Johnson" in e.action.args.get("attendees", [])
                for e in log_entries
            )

            success = proposal_found and calendar_check_found and event_created
            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
