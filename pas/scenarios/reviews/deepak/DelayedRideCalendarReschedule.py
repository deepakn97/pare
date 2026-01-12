"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.calendar import CalendarEvent
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCabApp,
    StatefulCalendarApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("delayed_ride_calendar_reschedule")
class DelayedRideCalendarReschedule(PASScenario):
    """Agent proactively reschedules a calendar meeting when the user's cab ride is significantly delayed.

    The user has ordered a cab to reach a client meeting scheduled at 2:00 PM today. The cab was expected to pick up at 1:15 PM, providing sufficient buffer time. However, at 1:10 PM, the user receives a cab status notification indicating the driver is delayed by 45 minutes due to traffic. Given the original 30-minute ride duration and the delay, the user cannot make the 2:00 PM meeting on time. The agent must:
    1. Detect the cab delay notification from the ride status update
    2. Read current ride details to determine the delay magnitude and destination
    3. Search the calendar for meetings around the expected arrival time
    4. Calculate that the user will now arrive at approximately 2:30 PM instead of 1:45 PM
    5. Propose rescheduling the 2:00 PM calendar event to accommodate the delay
    6. After user acceptance, edit the calendar event to a later time slot (e.g., 2:45 PM)
    7. Monitor the updated ride status to confirm the user is en route

    This scenario exercises real-time travel disruption handling, cross-app coordination between transportation and scheduling, time-based inference (delay propagation to meeting arrival), calendar event modification under time pressure, and reactive rescheduling triggered by external service updates..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.cab = StatefulCabApp(name="Cab")
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Populate apps with scenario specific data
        # Calendar: Add the 2:00 PM client meeting at Downtown Office
        # Meeting time: 2025-11-18 14:00:00 (2:00 PM)
        meeting_start = datetime(2025, 11, 18, 14, 0, 0, tzinfo=UTC).timestamp()
        meeting_end = datetime(2025, 11, 18, 15, 0, 0, tzinfo=UTC).timestamp()
        client_meeting = CalendarEvent(
            title="Client Meeting - Q4 Review",
            start_datetime=meeting_start,
            end_datetime=meeting_end,
            location="Downtown Office, 456 Business Blvd",
            description="Quarterly review meeting with key client",
            attendees=["John Smith", "Sarah Johnson"],
            tag="work",
        )
        self.client_meeting_event_id = self.calendar.set_calendar_event(client_meeting)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.cab, self.calendar]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")

        # Extract the event_id from the calendar (seeded in Step 2)
        # The calendar has one event with title "Client Meeting - Q4 Review"
        client_meeting_event_id = None
        for event in self.calendar.events.values():
            if "Client Meeting" in event.title:
                client_meeting_event_id = event.event_id
                break

        with EventRegisterer.capture_mode():
            # Environment Event 1: User orders a cab ride to the meeting location
            # This happens at 12:45 PM (1 hour 15 min before meeting)
            order_ride_event = cab_app.order_ride(
                start_location="User Home, 123 Main St",
                end_location="Downtown Office, 456 Business Blvd",
                service_type="Default",
                ride_time="2025-11-18 12:45:00",
            ).delayed(5)

            # Environment Event 2: Cab status update - driver is delayed by 45 minutes
            # This happens at 1:10 PM (13:10), 25 minutes after booking
            # The user expected pickup at 1:15 PM but now it's delayed to 2:00 PM
            delay_notification_event = cab_app.update_ride_status(
                status="DELAYED",
                message="Heavy traffic on Route 5. Estimated delay: 45 minutes. Apologies for the inconvenience.",
            ).depends_on(order_ride_event, delay_seconds=10)

            # Oracle Event 1: Agent checks current ride status to understand the delay
            # Motivated by: delay_notification_event showing "DELAYED" status with 45-min delay message
            check_ride_event = (
                cab_app.get_current_ride_status().oracle().depends_on(delay_notification_event, delay_seconds=2)
            )

            # Oracle Event 2: Agent checks calendar for meetings around the expected arrival time
            # Motivated by: ride delay will impact arrival time; need to check if meetings are affected
            check_calendar_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-18 13:00:00", end_datetime="2025-11-18 15:00:00"
                )
                .oracle()
                .depends_on(check_ride_event, delay_seconds=1)
            )

            # Oracle Event 3: Agent sends proposal to user about rescheduling the meeting
            # Motivated by: delay_notification_event showed 45-min delay which will make user late for 2PM meeting
            proposal_event = (
                aui.send_message_to_user(
                    content="I saw your cab is delayed by 45 minutes due to heavy traffic. You have a Client Meeting - Q4 Review scheduled at 2:00 PM, but with the delay you'll arrive around 2:30 PM. Would you like me to reschedule the meeting to 2:45 PM to accommodate the delay?"
                )
                .oracle()
                .depends_on(check_calendar_event, delay_seconds=2)
            )

            # Oracle Event 4: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please reschedule to 2:45 PM.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event 5: Agent edits the calendar event to new time
            # Motivated by: user accepted the reschedule proposal in acceptance_event
            edit_meeting_event = (
                calendar_app.edit_calendar_event(
                    event_id=client_meeting_event_id,
                    start_datetime="2025-11-18 14:45:00",
                    end_datetime="2025-11-18 15:45:00",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            order_ride_event,
            delay_notification_event,
            check_ride_event,
            check_calendar_event,
            proposal_event,
            acceptance_event,
            edit_meeting_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent checked ride status to understand the delay
            # The agent MUST observe the delayed ride status to understand the 45-minute delay
            ride_status_checked = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "get_current_ride_status"
                for e in log_entries
            )

            # STRICT Check 2: Agent queried calendar to find affected meetings
            # The agent MUST check the calendar for meetings around the expected arrival time
            calendar_queried = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "get_calendar_events_from_to"
                for e in log_entries
            )

            # STRICT Check 3: Agent sent proposal mentioning the cab delay and meeting reschedule
            # The agent MUST reference the delay and propose rescheduling the Client Meeting
            # Content is flexible but must mention key concepts: delay/traffic and the meeting
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 4: Agent edited the calendar event to accommodate the delay
            # The agent MUST call edit_calendar_event with the event_id
            # Start time should be later than the original 2:00 PM (14:00:00) to accommodate delay
            # Accept any reasonable reschedule time (not checking exact time for flexibility)
            meeting_rescheduled = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "edit_calendar_event"
                and e.action.args.get("event_id") is not None
                and e.action.args.get("start_datetime") is not None
                # Verify it's rescheduled to a later time (after original 14:00:00)
                and e.action.args.get("start_datetime", "") > "2025-11-18 14:00:00"
                for e in log_entries
            )

            # All checks must pass for success
            success = ride_status_checked and calendar_queried and proposal_found and meeting_rescheduled

            if not success:
                # Build rationale for failure
                missing_checks = []
                if not ride_status_checked:
                    missing_checks.append("agent did not check ride status")
                if not calendar_queried:
                    missing_checks.append("agent did not query calendar for meetings")
                if not proposal_found:
                    missing_checks.append("agent did not send reschedule proposal mentioning delay and meeting")
                if not meeting_rescheduled:
                    missing_checks.append("agent did not edit calendar event to reschedule meeting")

                rationale = "Validation failed: " + "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
