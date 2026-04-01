from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.calendar import CalendarEvent
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulCabApp,
    StatefulCalendarApp,
)
from pare.apps.reminder import StatefulReminderApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("ride_booking_for_calendar_event")
class RideBookingForCalendarEvent(PAREScenario):
    """Agent proactively books a cab ride based on an upcoming calendar event with location details.

    The user has a calendar event titled "Client Meeting at Downtown Office" scheduled later today with location
    "450 Market Street, San Francisco". A reminder notification arrives shortly after the scenario starts, reminding
    the user they have 90 minutes until the meeting and providing the user's current location. The agent must:
    1. Detect the reminder notification (time-driven; emitted automatically when the reminder is due)
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
        """Initialize apps with test data."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.reminder = StatefulReminderApp(name="Reminders")
        self.cab = StatefulCabApp(name="Cab")

        # Populate calendar with the upcoming client meeting event
        # Event is scheduled for later today at 10:30 AM UTC (90 minutes after the reminder notification).
        meeting_event = CalendarEvent(
            title="Client Meeting at Downtown Office",
            start_datetime=datetime(2025, 11, 18, 10, 30, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 11, 18, 12, 0, 0, tzinfo=UTC).timestamp(),
            location="450 Market Street, San Francisco",
            description="Quarterly business review with key client",
            tag="work",
            attendees=["User", "Sarah Chen"],
        )
        self.calendar.set_calendar_event(meeting_event)

        # Seed a time-driven reminder that will automatically notify user+agent when due.
        # The scenario runner advances simulated time; we set this reminder a few seconds after start_time so it fires.
        self.reminder.add_reminder(
            title="Reminder: book a cab for the Client Meeting at Downtown Office",
            due_datetime="2025-11-18 09:01:00",
            description=(
                "The meeting starts in 90 minutes at 450 Market Street, San Francisco. "
                "Current location is 123 Main Street, San Francisco. Please schedule a cab to the meeting location now in advance."
            ),
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.calendar, self.reminder, self.cab]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PAREAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # NOTE: Reminder notifications are time-driven in the Reminders app.
            # The reminder seeded in init will automatically notify the user+agent when it reaches `due_datetime`.
            # The agent does NOT need to call get_all_reminders(); we model reaction time by delaying the first oracle.

            # Agent detects the reminder notification and reads the calendar event details
            # to understand the meeting location and time
            agent_get_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-18 08:00:00", end_datetime="2025-11-18 12:30:00"
                )
                .oracle()
                # Reminder is due shortly after start_time; wait until after it would have fired.
                .delayed(70)
            )

            # Agent requests cab quotation for the route from a default pickup location to the meeting location
            # The agent infers the user needs transportation based on the meeting location in the calendar
            agent_quotation = (
                cab_app.get_quotation(
                    start_location="123 Main Street, San Francisco",
                    end_location="450 Market Street, San Francisco",
                    service_type="Default",
                    ride_time="2025-11-18 10:00:00",
                )
                .oracle()
                .depends_on(agent_get_event, delay_seconds=3)
            )

            # Agent proposes booking a cab to the user, citing the calendar reminder as the trigger
            # The proposal explicitly references the environment cue (reminder notification)
            agent_proposal = (
                aui.send_message_to_user(
                    content="I noticed your Client Meeting at Downtown Office starts at 10:30 AM at 450 Market Street, San Francisco. Would you like me to book a cab for you? I found a Default service ride departing at 10:00 AM, giving you time to arrive before the meeting starts."
                )
                .oracle()
                .depends_on([agent_quotation], delay_seconds=2)
            )

            # User accepts the agent's proposal
            user_accept = (
                aui.accept_proposal(content="Yes, please proceed.").oracle().depends_on(agent_proposal, delay_seconds=5)
            )

            # Agent orders the ride after user acceptance
            agent_order_ride = (
                cab_app.order_ride(
                    start_location="123 Main Street, San Francisco",
                    end_location="450 Market Street, San Francisco",
                    service_type="Default",
                    ride_time="2025-11-18 10:00:00",
                )
                .oracle()
                .depends_on(user_accept, delay_seconds=2)
            )

        # Register ALL events
        self.events = [
            agent_get_event,
            agent_quotation,
            agent_proposal,
            user_accept,
            agent_order_ride,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only agent/oracle events (EventType.AGENT)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent proposed the ride booking to the user (FLEXIBLE on content)
            proposal_found = any(
                e.action.class_name == "PAREAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 2: Agent ordered the ride after user acceptance
            order_ride_found = any(
                e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "order_ride"
                and e.action.args.get("end_location") is not None
                and "450 market street" in e.action.args.get("end_location").lower()
                for e in agent_events
            )

            # Determine success based on strict checks
            success = proposal_found and order_ride_found

            # Build rationale for failures
            rationale_parts = []
            if not proposal_found:
                rationale_parts.append("agent did not propose ride booking to user")
            if not order_ride_found:
                rationale_parts.append("agent did not order the ride to correct location")

            rationale = "; ".join(rationale_parts) if rationale_parts else None

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
