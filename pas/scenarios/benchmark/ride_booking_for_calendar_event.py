"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.calendar import CalendarEvent
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCabApp,
    StatefulCalendarApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("ride_booking_for_calendar_event")
class RideBookingForCalendarEvent(PASScenario):
    """Agent proactively books a cab ride based on an upcoming calendar event with location details.

    The user has a calendar event titled "Client Meeting at Downtown Office" scheduled for tomorrow at 10:00 AM with location "450 Market Street, San Francisco". The user receives a notification 90 minutes before the event reminding them about the meeting. The agent must:
    1. Detect the calendar event reminder notification
    2. Read the event details including location and start time
    3. Infer the user needs transportation to reach the location
    4. Calculate departure time allowing buffer for travel
    5. Request cab quotations for the route
    6. Propose booking a cab with service type and estimated cost
    7. After user acceptance, order the ride

    This scenario exercises calendar event monitoring, location-based reasoning, multi-step cab booking workflow (quotation → order), time-based scheduling coordination, and cross-app inference from calendar data to transportation needs..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.cab = StatefulCabApp(name="Cab")

        # Populate calendar with the upcoming client meeting event
        # Event is scheduled for tomorrow (2025-11-19) at 10:00 AM UTC
        # start_time is 2025-11-18 09:00:00 UTC, so event is ~25 hours away
        meeting_event = CalendarEvent(
            title="Client Meeting at Downtown Office",
            start_datetime=datetime(2025, 11, 19, 10, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 11, 19, 11, 30, 0, tzinfo=UTC).timestamp(),
            location="450 Market Street, San Francisco",
            description="Quarterly business review with key client",
            tag="work",
            attendees=["User", "Sarah Chen"],
        )
        self.calendar.set_calendar_event(meeting_event)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.calendar, self.cab]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # Environment event: Calendar reminder notification 90 minutes before the meeting
            # The meeting is at 2025-11-19 10:00:00 UTC, so the reminder arrives at 2025-11-19 08:30:00 UTC
            # start_time is 2025-11-18 09:00:00 UTC, so the reminder is 23.5 hours after start
            # Using a short delay of 5 seconds to model the notification arrival
            env_reminder = calendar_app.add_calendar_event_by_attendee(
                who_add="System",
                title="Reminder: Client Meeting at Downtown Office",
                start_datetime="2025-11-19 08:30:00",
                end_datetime="2025-11-19 08:31:00",
                # Include pickup context in the reminder so the agent doesn't need to guess start_location.
                description="Your meeting starts in 90 minutes at 450 Market Street, San Francisco. Your current location is 123 Main Street, San Francisco.",
                location="450 Market Street, San Francisco",
                attendees=["User"],
            ).delayed(5)

            # Agent detects the reminder notification and reads the calendar event details
            # to understand the meeting location and time
            agent_get_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-19 08:00:00", end_datetime="2025-11-19 12:00:00"
                )
                .oracle()
                .depends_on(env_reminder, delay_seconds=2)
            )

            # Agent requests cab quotation for the route from a default pickup location to the meeting location
            # The agent infers the user needs transportation based on the meeting location in the calendar
            agent_quotation = (
                cab_app.get_quotation(
                    start_location="123 Main Street, San Francisco",
                    end_location="450 Market Street, San Francisco",
                    service_type="Default",
                    ride_time="2025-11-19 09:30:00",
                )
                .oracle()
                .depends_on(agent_get_event, delay_seconds=3)
            )

            # Agent proposes booking a cab to the user, citing the calendar reminder as the trigger
            # The proposal explicitly references the environment cue (reminder notification)
            agent_proposal = (
                aui.send_message_to_user(
                    content="I noticed you have a Client Meeting at Downtown Office starting at 10:00 AM at 450 Market Street, San Francisco. Would you like me to book a cab for you? I found a Default service ride departing at 9:30 AM for approximately the estimated cost, giving you time to arrive before the meeting starts."
                )
                .oracle()
                .depends_on([env_reminder, agent_quotation], delay_seconds=2)
            )

            # User accepts the agent's proposal
            user_accept = (
                aui.accept_proposal(content="Yes, please book the Default ride for 9:30 AM.")
                .oracle()
                .depends_on(agent_proposal, delay_seconds=5)
            )

            # Agent orders the ride after user acceptance
            agent_order_ride = (
                cab_app.order_ride(
                    start_location="123 Main Street, San Francisco",
                    end_location="450 Market Street, San Francisco",
                    service_type="Default",
                    ride_time="2025-11-19 09:30:00",
                )
                .oracle()
                .depends_on(user_accept, delay_seconds=2)
            )

        # Register ALL events
        self.events = [
            env_reminder,
            agent_get_event,
            agent_quotation,
            agent_order_ride,
            user_accept,
            agent_order_ride,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only agent/oracle events (EventType.AGENT)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent queried calendar events to discover meeting details
            calendar_query_found = any(
                e.action.class_name == "StatefulCalendarApp" and e.action.function_name == "get_calendar_events_from_to"
                for e in agent_events
            )

            # STRICT Check 2: Agent requested cab quotation before proposing
            quotation_found = any(
                e.action.class_name == "StatefulCabApp" and e.action.function_name == "get_quotation"
                for e in agent_events
            )

            # STRICT Check 3: Agent proposed the ride booking to the user (FLEXIBLE on content)
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 4: Agent ordered the ride after user acceptance
            order_ride_found = any(
                e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "order_ride"
                and e.action.args.get("end_location") is not None
                and "450 market street" in e.action.args.get("end_location").lower()
                for e in agent_events
            )

            # Determine success based on strict checks
            success = calendar_query_found and quotation_found and proposal_found and order_ride_found

            # Build rationale for failures
            rationale_parts = []
            if not calendar_query_found:
                rationale_parts.append("agent did not query calendar events")
            if not quotation_found:
                rationale_parts.append("agent did not request cab quotation")
            if not proposal_found:
                rationale_parts.append("agent did not propose ride booking to user")
            if not order_ride_found:
                rationale_parts.append("agent did not order the ride to correct location")

            rationale = "; ".join(rationale_parts) if rationale_parts else None

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
