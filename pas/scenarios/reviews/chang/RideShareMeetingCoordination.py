"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.email_client import Email, EmailFolderName
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCabApp,
    StatefulCalendarApp,
    StatefulEmailApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("ride_share_meeting_coordination")
class RideShareMeetingCoordination(PASScenario):
    """Agent coordinates cab ride-sharing for a multi-attendee meeting based on email invitation and calendar details.

    The user receives an email invitation from their colleague Sarah Mitchell for a client presentation at WeWork Downtown on Friday, December 20th at 10:00 AM. The email mentions that Sarah and two other team members (Tom Brady and Lisa Wang) will also be attending from the same office location, and suggests carpooling to reduce costs. The calendar event is created with all attendees listed. The agent must:
    1. Parse the incoming meeting invitation email to extract location, time, and carpooling suggestion
    2. Read the calendar event to confirm attendee list and meeting details
    3. Calculate appropriate departure time (meeting at 10:00 AM, suggest 9:15 AM departure for 30-minute travel + 15-minute buffer)
    4. Use cab app to get quotation for a ride accommodating multiple passengers (4 people total) from the office to WeWork Downtown at 9:15 AM
    5. Compare service types to find the most cost-effective option for group travel
    6. Propose booking a shared ride to the user, mentioning cost savings and coordination with other attendees
    7. Upon acceptance, confirm the ride order and send a reply email to all meeting attendees informing them of the arranged transportation

    This scenario exercises email-triggered coordination, calendar attendee analysis, multi-passenger cab quotation workflows, cost optimization reasoning, and proactive group logistics with email-based confirmation to stakeholders.
    """

    start_time = datetime(2024, 12, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.email = StatefulEmailApp(name="Emails")
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.cab = StatefulCabApp(name="Cab")

        # Populate apps with scenario specific data
        # Email: Seed older emails for context (not the triggering invitation)
        self.email.add_email(
            Email(
                sender="sarah.mitchell@company.com",
                recipients=[self.email.user_email],
                subject="Client presentation prep",
                content="Hi! Just a reminder that we have our client presentation coming up on Friday. Looking forward to working with you on this!",
                timestamp=datetime(2024, 12, 15, 14, 30, 0, tzinfo=UTC).timestamp(),
                is_read=True,
            ),
            folder_name=EmailFolderName.INBOX,
        )

        # Calendar: Seed the meeting event (already exists in calendar before the scenario starts)
        meeting_event_id = self.calendar.add_calendar_event(
            title="Client Presentation - WeWork Downtown",
            start_datetime="2024-12-20 10:00:00",
            end_datetime="2024-12-20 11:30:00",
            location="WeWork Downtown, 123 Business Ave",
            description="Important client presentation for Q1 strategy review",
            attendees=["Sarah Mitchell", "Tom Brady", "Lisa Wang", "User"],
            tag="meeting",
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.calendar, self.cab]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Incoming meeting invitation email with carpooling suggestion
            # This is the triggering environment event that motivates all subsequent agent actions
            invitation_email_id = "meeting-invite-2024-12-20"
            invitation_email_event = email_app.send_email_to_user_with_id(
                email_id=invitation_email_id,
                sender="sarah.mitchell@company.com",
                subject="Meeting Invitation: Client Presentation - Friday Dec 20",
                content="Hi Team,\n\nI've scheduled our client presentation for Friday, December 20th at 10:00 AM at WeWork Downtown (123 Business Ave).\n\nAttendees: You, Tom Brady, Lisa Wang, and me (Sarah Mitchell).\n\nSince we're all coming from the same office location (456 Main St), I suggest we carpool to save costs. If you can arrange transportation for all 4 of us, that would be great!\n\nLooking forward to a successful presentation.\n\nBest,\nSarah",
            ).delayed(10)

            # Agent observes the email invitation and decides to check calendar details for attendees
            # Motivation: The email references a meeting; agent checks calendar to confirm attendee list and timing
            check_calendar_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2024-12-20 09:00:00",
                    end_datetime="2024-12-20 12:00:00",
                )
                .oracle()
                .depends_on(invitation_email_event, delay_seconds=3)
            )

            # Agent compares cab service types for 4-person group travel
            # Motivation: Email explicitly suggests carpooling for 4 people; agent needs quotations to find best option
            list_rides_event = (
                cab_app.list_rides(
                    start_location="456 Main St",
                    end_location="WeWork Downtown, 123 Business Ave",
                    ride_time="2024-12-20 09:15:00",
                )
                .oracle()
                .depends_on(check_calendar_event, delay_seconds=5)
            )

            # Agent proposes the ride-sharing arrangement to the user
            # Motivation: Based on email request for carpooling and cab quotations showing cost-effective Van option
            proposal_event = (
                aui.send_message_to_user(
                    content="I saw Sarah Mitchell's email about the client presentation on Friday, December 20th at 10:00 AM at WeWork Downtown. She suggested carpooling for all 4 attendees (you, Sarah, Tom, and Lisa) from the office.\n\nI checked available cab options for a 9:15 AM departure (allowing 30 min travel + 15 min buffer). The Van service accommodates all 4 people and is the most cost-effective at approximately $25-30 for the group.\n\nShall I book the Van ride for 9:15 AM on December 20th?",
                )
                .oracle()
                .depends_on(list_rides_event, delay_seconds=3)
            )

            # User accepts the proposal
            user_acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please book the Van and let everyone know.",
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=15)
            )

            # Agent books the Van ride for 4 passengers
            # Motivation: User explicitly accepted the proposal to book the Van
            book_ride_event = (
                cab_app.order_ride(
                    start_location="456 Main St",
                    end_location="WeWork Downtown, 123 Business Ave",
                    service_type="Van",
                    ride_time="2024-12-20 09:15:00",
                )
                .oracle()
                .depends_on(user_acceptance_event, delay_seconds=2)
            )

            # Agent replies to the invitation email to inform all attendees about the arranged transportation
            # Motivation: User asked to "let everyone know"; agent replies-all to meeting invitation email
            reply_email_event = (
                email_app.reply_to_email(
                    email_id=invitation_email_id,
                    folder_name="INBOX",
                    content="Hi Sarah and team,\n\nI've arranged a Van ride for all 4 of us on Friday, December 20th. Pickup is at 9:15 AM from our office (456 Main St) to WeWork Downtown.\n\nThis gives us plenty of time to arrive before the 10:00 AM presentation.\n\nSee you all Friday!\n\nBest",
                )
                .oracle()
                .depends_on(book_ride_event, delay_seconds=3)
            )

        # Register ALL events
        self.events = [
            invitation_email_event,
            check_calendar_event,
            list_rides_event,
            proposal_event,
            user_acceptance_event,
            book_ride_event,
            reply_email_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:  # noqa: C901
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only agent/oracle events (exclude ENV events)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent checked calendar for meeting details
            # The agent should query the calendar to understand attendee list and timing
            check_calendar_found = any(
                e.action.class_name == "StatefulCalendarApp" and e.action.function_name == "get_calendar_events_from_to"
                for e in agent_events
            )

            # STRICT Check 2: Agent queried cab services for group transportation
            # The agent must list available rides to compare options for 4 people
            list_rides_found = any(
                e.action.class_name == "StatefulCabApp" and e.action.function_name == "list_rides" for e in agent_events
            )

            # STRICT Check 3: Agent proposed the ride-sharing plan to user
            # The agent must communicate the proposal via the user interface
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 4: Agent booked the Van ride after user acceptance
            # This is the core action - booking transportation for the group
            book_ride_found = False
            for e in agent_events:
                if e.action.class_name == "StatefulCabApp" and e.action.function_name == "order_ride":
                    args = e.action.args if e.action.args else e.action.resolved_args
                    # Verify it's for the Van service (group transportation)
                    if args.get("service_type") == "Van":
                        book_ride_found = True
                        break

            # STRICT Check 5: Agent informed attendees via email reply
            # The agent must reply to the invitation email to coordinate with all participants
            reply_email_found = any(
                e.action.class_name == "StatefulEmailApp" and e.action.function_name == "reply_to_email"
                for e in agent_events
            )

            # Determine overall success
            success = (
                check_calendar_found and list_rides_found and proposal_found and book_ride_found and reply_email_found
            )

            # Build failure rationale if needed
            rationale = None
            if not success:
                missing = []
                if not check_calendar_found:
                    missing.append("calendar check for meeting details")
                if not list_rides_found:
                    missing.append("cab services query")
                if not proposal_found:
                    missing.append("proposal to user")
                if not book_ride_found:
                    missing.append("Van ride booking")
                if not reply_email_found:
                    missing.append("email reply to attendees")
                rationale = f"Missing critical actions: {', '.join(missing)}"

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
