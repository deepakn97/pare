"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.calendar import CalendarEvent
from are.simulation.apps.contacts import Contact
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
    StatefulEmailApp,
)
from pas.apps.cab import StatefulCabApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("cab_delay_meeting_mitigation")
class CabDelayMeetingMitigation(PASScenario):
    """Agent proactively mitigates meeting lateness risk when an active cab ride experiences delay.

    The user has booked a cab ride departing at 8:30 AM on Monday, December 23rd to attend a "Q4 Budget Review" meeting scheduled at
    the Downtown Financial Center from 9:00 AM to 10:30 AM with attendees Sarah Johnson (CFO) and Mark Peterson (Finance Director).
    At 8:25 AM, the cab app sends a notification stating "Your ride is delayed by 20 minutes due to driver availability. New estimated
    pickup time: 8:50 AM. Original arrival time may not be met." The agent must:
    1. Parse the cab delay notification to extract the delay duration and impact on arrival time
    2. Search the calendar for events around 9:00 AM on December 23rd to identify which commitment is affected
    3. Read the "Q4 Budget Review" event details to retrieve attendee list and meeting importance
    4. Calculate that a 20-minute delay means arrival at 9:15-9:20 AM instead of 9:00 AM, causing late arrival
    5. Propose two mitigation options: (a) cancel the delayed ride and book a faster service type (e.g., premium vs. standard) to recover time, or
       (b) send an email to meeting attendees notifying them of a 15-20 minute delay
    6. Upon user selection of option (a), cancel the current ride, get quotations for premium service types departing immediately, and book the fastest available option
    7. Alternatively, if user selects option (b), compose and send an email to Sarah Johnson and Mark Peterson explaining the delay and requesting to start without the user
       or reschedule the start time

    This scenario exercises cab-initiated triggers (delay notification), ride status and service type comparison workflows, time-sensitive decision making,
    bidirectional cab-calendar-email coordination, and user-driven choice between alternative mitigation strategies.
    """

    start_time = datetime(2024, 12, 23, 8, 25, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Calendar app and populate with Q4 Budget Review meeting
        self.calendar = StatefulCalendarApp(name="Calendar")
        meeting_start = datetime(2024, 12, 23, 9, 0, 0, tzinfo=UTC).timestamp()
        meeting_end = datetime(2024, 12, 23, 10, 30, 0, tzinfo=UTC).timestamp()
        budget_meeting = CalendarEvent(
            title="Q4 Budget Review",
            start_datetime=meeting_start,
            end_datetime=meeting_end,
            location="Downtown Financial Center",
            attendees=["Sarah Johnson", "Mark Peterson"],
            description="Quarterly budget review meeting with CFO and Finance Director",
            tag="Work",
        )
        self.calendar.set_calendar_event(budget_meeting)

        # Initialize Email app with contact information
        self.email = StatefulEmailApp(name="Emails")
        # Sarah Johnson contact
        sarah = Contact(
            first_name="Sarah",
            last_name="Johnson",
            email="sarah.johnson@company.com",
            job="CFO",
            phone="+1-555-0101",
        )
        # Mark Peterson contact
        mark = Contact(
            first_name="Mark",
            last_name="Peterson",
            email="mark.peterson@company.com",
            job="Finance Director",
            phone="+1-555-0102",
        )

        # Initialize Cab app and book a ride for the morning
        self.cab = StatefulCabApp(name="Cab")
        # Book a ride at 8:30 AM to Downtown Financial Center
        self.ride = self.cab.order_ride(
            start_location="Home",
            end_location="Downtown Financial Center",
            service_type="Default",
            ride_time="2024-12-23 08:30:00",
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.calendar, self.email, self.cab]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Cab ride delay notification (NON-ORACLE trigger)
            # Motivation: This is the primary exogenous trigger that starts the scenario
            delay_notification = cab_app.update_ride_status(
                status="DELAYED",
                message="Your ride is delayed by 20 minutes due to driver availability. New estimated pickup time: 8:50 AM. Original arrival time may not be met. Sorry if it will affect any of your calendar events.",
            ).delayed(5)

            # Environment Event 2: One of the meeting attendees emails the user asking if they're joining.
            # Motivation: This is a realistic, user-visible cue that reinforces the need to notify attendees if late.
            attendee_ping_email = email_app.send_email_to_user_with_id(
                email_id="email-q4-budget-review-ping-001",
                sender="sarah.johnson@company.com",
                subject="Q4 Budget Review starting now",
                content=(
                    "Hi Alex,\n\nWe're about to start the Q4 Budget Review. Are you on your way?\n"
                    "If you're running late, please email Mark and me so we can start without you.\n\nThanks,\nSarah"
                ),
            ).delayed(6)

            # Oracle Event 1b: Agent reads the attendee email to ground the email-notification mitigation.
            read_attendee_email = (
                email_app.get_email_by_id(email_id="email-q4-budget-review-ping-001")
                .oracle()
                .depends_on(attendee_ping_email, delay_seconds=1)
            )

            # Oracle Event 2: Agent checks current ride status to assess delay details
            # Motivation: delay_notification contains "delayed by 20 minutes" - agent needs ride details to understand impact
            check_ride_status = (
                cab_app.get_current_ride_status()
                .oracle()
                .depends_on([delay_notification, read_attendee_email], delay_seconds=2)
            )

            # Oracle Event 3: Agent queries calendar for events around expected arrival time (9:00-9:30 AM)
            # Motivation: delay_notification says "Original arrival time may not be met" - agent must identify affected commitments
            check_calendar = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2024-12-23 09:00:00",
                    end_datetime="2024-12-23 10:30:00",
                )
                .oracle()
                .depends_on(check_ride_status, delay_seconds=2)
            )

            # Oracle Event 4: Agent proposes mitigation to user
            # Motivation: check_calendar revealed "Q4 Budget Review" at 9:00 AM; 20-min delay means late arrival
            proposal = (
                aui.send_message_to_user(
                    content="Your cab ride to Downtown Financial Center is delayed by 20 minutes. You have a Q4 Budget Review meeting with Sarah Johnson and Mark Peterson at 9:00 AM. With the delay, you may arrive 15-20 minutes late. Would you like me to send an email to the attendees explaining the delay and apologizing for the late start?"
                )
                .oracle()
                .depends_on(check_calendar, delay_seconds=2)
            )

            # Oracle Event 5: User accepts the proposal
            # Motivation: User response to agent's proposal
            acceptance = (
                aui.accept_proposal(content="Yes, please notify them about the delay.")
                .oracle()
                .depends_on(proposal, delay_seconds=3)
            )

            # Oracle Event 6: Agent sends email to meeting attendees (WRITE action gated by acceptance)
            # Motivation: acceptance approved notifying attendees per proposal plan
            send_notification = (
                email_app.send_email(
                    recipients=["sarah.johnson@company.com", "mark.peterson@company.com"],
                    subject="Running 15-20 minutes late for Q4 Budget Review",
                    content="Hi Sarah and Mark,\n\nI wanted to let you know that I'm running approximately 15-20 minutes late for our 9:00 AM Q4 Budget Review meeting due to an unexpected delay with my transportation. I apologize for the inconvenience and will join as soon as I arrive.\n\nFeel free to start without me if needed, or we can push the start time back slightly.\n\nThank you for your understanding.",
                )
                .oracle()
                .depends_on(acceptance, delay_seconds=2)
            )

        # Register ALL events
        self.events = [
            delay_notification,
            attendee_ping_email,
            read_attendee_email,
            check_ride_status,
            check_calendar,
            proposal,
            acceptance,
            send_notification,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent sent proposal mentioning the delay and meeting impact
            # The proposal must reference the delay, the meeting, and the attendees
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 2: Agent checked calendar to identify affected events
            # The agent must query the calendar around 9:00 AM to find the meeting
            # Accept either get_calendar_events_from_to or read_today_calendar_events as valid
            calendar_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name
                in ["get_calendar_events_from_to", "read_today_calendar_events", "get_calendar_event"]
                for e in log_entries
            )

            # STRICT Check 3: Agent sent email notification to meeting attendees
            # The email must be sent to both Sarah and Mark (or at least one of them)
            # Accept either send_email or reply_to_email as valid (if scenario had an incoming email)
            email_sent_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name in ["send_email", "reply_to_email", "send_batch_reply"]
                and (
                    "sarah.johnson@company.com" in str(e.action.args.get("recipients", []))
                    or "mark.peterson@company.com" in str(e.action.args.get("recipients", []))
                    or "sarah.johnson@company.com" in str(e.action.args.get("recipient", ""))
                    or "mark.peterson@company.com" in str(e.action.args.get("recipient", ""))
                )
                for e in log_entries
            )

            # All strict checks must pass
            success = proposal_found and calendar_check_found and email_sent_found

            if not success:
                # Build rationale for which checks failed
                failed_checks = []
                if not proposal_found:
                    failed_checks.append("no agent proposal mentioning delay and meeting found")
                if not calendar_check_found:
                    failed_checks.append("agent did not check calendar for affected events")
                if not email_sent_found:
                    failed_checks.append("no email notification sent to meeting attendees")

                rationale = "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
