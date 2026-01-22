"""Scenario: Agent proactively mitigates meeting lateness risk when cab ride experiences delay."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
    StatefulContactsApp,
    StatefulEmailApp,
)
from pas.apps.cab import StatefulCabApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("cab_delay_meeting_mitigation")
class CabDelayMeetingMitigation(PASScenario):
    """Agent proactively mitigates meeting lateness risk when an active cab ride experiences delay.

    The user has booked a cab ride departing at 8:30 AM on Monday, December 23rd to attend a "Q4 Budget Review" meeting
    scheduled at the Downtown Financial Center from 9:00 AM to 10:30 AM with attendees Sarah Johnson (CFO) and
    Mark Peterson (Finance Director). At 8:25 AM, the cab app sends a delay notification: "Your ride is delayed by
    10 minutes due to traffic. New estimated pickup time: 8:40 AM." The agent must:
    1. Parse the cab delay notification to extract the delay duration and impact on arrival time
    2. Check the calendar for events around the expected arrival time to identify affected commitments
    3. Retrieve the "Q4 Budget Review" event details including attendee list
    4. Look up attendee contact information in the contacts app
    5. Propose sending an email to meeting attendees notifying them of the delay
    6. Upon user acceptance, compose and send an email to Sarah Johnson and Mark Peterson explaining the delay

    This scenario exercises cab-initiated triggers (delay notification), time-sensitive decision making,
    cab-calendar-contacts-email coordination, and proactive meeting management.
    """

    start_time = datetime(2024, 12, 23, 8, 25, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Contacts app and add meeting attendees
        self.contacts = StatefulContactsApp(name="Contacts")
        self.sarah_contact_id = self.contacts.add_new_contact(
            first_name="Sarah",
            last_name="Johnson",
            email="sarah.johnson@company.com",
            job="CFO",
            phone="+1-555-0101",
        )
        self.mark_contact_id = self.contacts.add_new_contact(
            first_name="Mark",
            last_name="Peterson",
            email="mark.peterson@company.com",
            job="Finance Director",
            phone="+1-555-0102",
        )

        # Initialize Calendar app and populate with Q4 Budget Review meeting
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.calendar.add_calendar_event(
            title="Q4 Budget Review",
            start_datetime="2024-12-23 09:00:00",
            end_datetime="2024-12-23 10:30:00",
            location="Downtown Financial Center",
            attendees=["Sarah Johnson", "Mark Peterson"],
            description="Quarterly budget review meeting with CFO and Finance Director",
        )

        # Initialize Email app
        self.email = StatefulEmailApp(name="Emails")

        # Initialize Cab app and book a ride for the morning
        self.cab = StatefulCabApp(name="Cab")
        self.cab.order_ride(
            start_location="Home",
            end_location="Downtown Financial Center",
            service_type="Default",
            ride_time="2024-12-23 08:30:00",
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.calendar, self.email, self.cab]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")

        with EventRegisterer.capture_mode():
            # Environment Event: Cab ride delay notification
            delay_notification = cab_app.update_ride_status(
                status="DELAYED",
                message="Your ride is delayed by 10 minutes due to traffic. New estimated pickup time: 8:40 AM.",
            ).delayed(5)

            # Agent checks current ride status to assess delay details
            check_ride_status = (
                cab_app.get_current_ride_status().oracle().depends_on(delay_notification, delay_seconds=2)
            )

            # Agent queries calendar for events around expected arrival time
            check_calendar = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2024-12-23 09:00:00",
                    end_datetime="2024-12-23 10:30:00",
                )
                .oracle()
                .depends_on(check_ride_status, delay_seconds=2)
            )

            # Agent searches contacts for attendee information
            search_contacts = (
                contacts_app.search_contacts(query="Sarah Johnson").oracle().depends_on(check_calendar, delay_seconds=2)
            )

            # Agent proposes mitigation to user
            proposal = (
                aui.send_message_to_user(
                    content="Your cab ride to Downtown Financial Center is delayed by 10 minutes. You have a Q4 Budget Review meeting with Sarah Johnson and Mark Peterson at 9:00 AM. With the delay, you may arrive about 10 minutes late. Would you like me to send an email to the attendees explaining the delay?"
                )
                .oracle()
                .depends_on(search_contacts, delay_seconds=2)
            )

            # User accepts the proposal
            acceptance = (
                aui.accept_proposal(content="Yes, please notify them about the delay.")
                .oracle()
                .depends_on(proposal, delay_seconds=3)
            )

            # Agent sends email to meeting attendees
            send_notification = (
                email_app.send_email(
                    recipients=["sarah.johnson@company.com", "mark.peterson@company.com"],
                    subject="Running about 10 minutes late for Q4 Budget Review",
                    content="Hi Sarah and Mark,\n\nI wanted to let you know that I'm running approximately 10 minutes late for our 9:00 AM Q4 Budget Review meeting due to a delay with my cab. I apologize for the inconvenience and will join as soon as I arrive.\n\nFeel free to start without me if needed.\n\nThank you for your understanding.",
                )
                .oracle()
                .depends_on(acceptance, delay_seconds=2)
            )

        self.events = [
            delay_notification,
            check_ride_status,
            check_calendar,
            search_contacts,
            proposal,
            acceptance,
            send_notification,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent achieved the essential outcomes for this scenario.

        Essential outcomes (what we check):
        - Agent sent proposal to user about the delay
        - Agent sent email to meeting attendees (both Sarah and Mark)

        Not checked (intermediate steps the agent might do differently):
        - How agent checked calendar (get_calendar_events_from_to, list_events, etc.)
        - How agent looked up contacts (search_contacts, get_contact, etc.)
        """
        try:
            log_entries = env.event_log.list_view()

            # CHECK 1: Agent sent proposal to user
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # CHECK 2: Agent sent email to both meeting attendees
            email_sent_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "send_email"
                and "sarah.johnson@company.com" in str(e.action.args.get("recipients", []))
                and "mark.peterson@company.com" in str(e.action.args.get("recipients", []))
                for e in log_entries
            )

            success = proposal_found and email_sent_found

            if not success:
                failed_checks = []
                if not proposal_found:
                    failed_checks.append("agent did not send proposal to user about delay")
                if not email_sent_found:
                    failed_checks.append(
                        "agent did not send email to both attendees (sarah.johnson@company.com and mark.peterson@company.com)"
                    )
                rationale = "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
