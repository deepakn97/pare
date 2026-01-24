from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.contacts import Contact
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCabApp,
    StatefulCalendarApp,
    StatefulEmailApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("event_cancel_cab_cleanup")
class EventCancelCabCleanup(PASScenario):
    """Agent cancels an existing cab booking when a calendar event is cancelled by the organizer.

    The user has a "Client Presentation" meeting scheduled with Jessica Martinez on Friday, December 20th from 10:00 AM to 11:30 AM at WeWork Downtown. The user previously booked a cab ride departing at 9:15 AM to arrive on time. An email arrives from Jessica stating she needs to cancel the presentation due to an unexpected conflict. The agent must:
    1. Parse the incoming cancellation email to identify which event is being cancelled
    2. Search the calendar to find the "Client Presentation" event on December 20th
    3. Check the cab ride history to find the active booking for 9:15 AM on that date
    4. Propose cancelling the cab ride since the meeting is no longer happening
    5. Upon user acceptance, cancel the cab order using the cab app
    6. Verify the cancellation by checking the current ride status
    7. Reply to Jessica's email acknowledging the cancellation
    8. Delete the cancelled calendar event

    This scenario exercises email-triggered cancellation workflows, cross-app state cleanup (email → calendar → cab), ride history queries, cancellation verification via status checks, and coordinated multi-app deletions rather than creations..
    """

    start_time = datetime(2024, 12, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.email = StatefulEmailApp(name="Emails")
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.cab = StatefulCabApp(name="Cab")

        # Populate baseline data

        # Contact: Jessica Martinez (meeting organizer)
        jessica = Contact(
            first_name="Jessica",
            last_name="Martinez",
            email="jessica.martinez@clientcorp.com",
            phone="+1-555-0142",
        )

        # Calendar: Pre-existing "Client Presentation" event on December 20, 2024
        # Event time: 10:00 AM - 11:30 AM at WeWork Downtown
        event_start = datetime(2024, 12, 20, 10, 0, 0, tzinfo=UTC)
        event_end = datetime(2024, 12, 20, 11, 30, 0, tzinfo=UTC)

        self.calendar.add_calendar_event(
            title="Client Presentation",
            start_datetime=event_start.strftime("%Y-%m-%d %H:%M:%S"),
            end_datetime=event_end.strftime("%Y-%m-%d %H:%M:%S"),
            location="WeWork Downtown",
            attendees=["Jessica Martinez"],
            description="Quarterly review presentation for ClientCorp",
        )

        # Cab: Pre-existing booked ride departing at 9:15 AM on December 20, 2024
        # This ride was booked to arrive at the meeting on time
        ride_time = datetime(2024, 12, 20, 9, 15, 0, tzinfo=UTC)

        self.cab.order_ride(
            start_location="Home",
            end_location="WeWork Downtown",
            service_type="Default",
            ride_time=ride_time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.calendar, self.cab]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Jessica sends cancellation email
            # This is the exogenous trigger that starts the scenario
            cancellation_email = email_app.send_email_to_user_with_id(
                email_id="email-cancellation-001",
                sender="jessica.martinez@clientcorp.com",
                subject="Need to Cancel Client Presentation",
                content="Hi! I'm sorry for the short notice, but I need to cancel our Client Presentation scheduled for Friday, December 20th at 10:00 AM. An unexpected conflict has come up that I can't reschedule. Can we look at alternative dates next week? Again, my apologies for the inconvenience.",
            ).delayed(10)

            # Oracle Event 1: Agent searches calendar to find the mentioned event
            # Motivation: The cancellation email mentioned "Client Presentation" on "December 20th at 10:00 AM"
            search_calendar = (
                calendar_app.search_events(query="Client Presentation")
                .oracle()
                .depends_on(cancellation_email, delay_seconds=2)
            )

            # Oracle Event 2: Agent checks ride history to find associated cab booking
            # Motivation: Agent found the calendar event and needs to check if there's a related cab booking for that day
            check_ride_history = (
                cab_app.get_ride_history(offset=0, limit=10).oracle().depends_on(search_calendar, delay_seconds=2)
            )

            # Oracle Event 3: Agent proposes cancelling the cab and acknowledging the cancellation
            # Motivation: Email from Jessica triggered cancellation; agent found both calendar event and cab booking
            proposal = (
                aui.send_message_to_user(
                    content="I received a cancellation email from Jessica Martinez about the Client Presentation on December 20th at 10:00 AM. I found that you have a cab booked for 9:15 AM to WeWork Downtown for this meeting. Would you like me to cancel the cab ride and confirm the cancellation with Jessica?"
                )
                .oracle()
                .depends_on(check_ride_history, delay_seconds=3)
            )

            # User Event 1: User accepts the proposal
            user_acceptance = aui.accept_proposal(
                content="Yes, please cancel the cab and let Jessica know. Also you need to cleanup the calendar event for the Client Presentation."
            ).depends_on(proposal, delay_seconds=5)

            # Oracle Event 4: Agent cancels the cab ride
            # Motivation: User accepted the proposal to cancel the cab
            cancel_cab = cab_app.user_cancel_ride().oracle().depends_on(user_acceptance, delay_seconds=2)

            # Oracle Event 5: Agent verifies the cancellation by checking ride status
            # Motivation: Agent needs to confirm the cab cancellation was successful
            verify_cancellation = (
                cab_app.get_ride_history(offset=0, limit=10).oracle().depends_on(cancel_cab, delay_seconds=2)
            )

            # Oracle Event 6: Agent replies to Jessica's email acknowledging the cancellation
            # Motivation: User requested agent to "let Jessica know"; replying to the cancellation email received earlier
            reply_to_jessica = (
                email_app.reply_to_email(
                    email_id="email-cancellation-001",
                    folder_name="INBOX",
                    content="Hi Jessica,\n\nNo problem at all, I understand these things happen. I've cancelled my cab booking and updated my calendar. Let's definitely find a time next week that works for both of us.\n\nBest regards",
                )
                .oracle()
                .depends_on(verify_cancellation, delay_seconds=3)
            )

            # Oracle Event 7: Agent searches for the calendar event to get its ID for deletion
            # Motivation: Agent needs the event_id to delete the calendar event
            get_event_for_deletion = (
                calendar_app.search_events(query="Client Presentation")
                .oracle()
                .depends_on(reply_to_jessica, delay_seconds=2)
            )

            # Oracle Event 8: Agent deletes the cancelled calendar event
            # Motivation: Meeting is cancelled, so the calendar event should be removed to keep the calendar clean
            delete_event = (
                calendar_app.delete_calendar_event(event_id="PLACEHOLDER_EVENT_ID")
                .oracle()
                .depends_on(get_event_for_deletion, delay_seconds=2)
            )

        # Register ALL events here in self.events
        self.events = [
            cancellation_email,
            search_calendar,
            check_ride_history,
            proposal,
            user_acceptance,
            cancel_cab,
            verify_cancellation,
            reply_to_jessica,
            get_event_for_deletion,
            delete_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent cancelled the cab ride
            cab_cancelled = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "user_cancel_ride"
                for e in log_entries
            )

            # STRICT Check 2: Agent replied to Jessica's cancellation email
            # Accept reply_to_email with the correct email_id
            email_reply_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == "email-cancellation-001"
                for e in log_entries
            )

            # STRICT Check 3: Agent deleted the calendar event
            calendar_event_deleted = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "delete_calendar_event"
                for e in log_entries
            )

            # All strict checks must pass for success
            success = cab_cancelled and email_reply_found and calendar_event_deleted

            # Build rationale for failure
            if not success:
                missing = []
                if not cab_cancelled:
                    missing.append("cab cancellation")
                if not email_reply_found:
                    missing.append("email reply to Jessica")
                if not calendar_event_deleted:
                    missing.append("calendar event deletion")
                rationale = f"Missing critical actions: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
