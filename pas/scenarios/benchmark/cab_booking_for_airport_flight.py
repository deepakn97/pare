"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.calendar import CalendarEvent
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


@register_scenario("cab_booking_for_airport_flight")
class CabBookingForAirportFlight(PASScenario):
    """Agent proactively books a cab ride to the airport for an upcoming flight based on calendar and email information.

    The user has a flight departing on Friday, December 20th at 3:00 PM from San Francisco International Airport (SFO). The calendar contains a "Flight to Seattle" event scheduled from 3:00 PM to 4:00 PM on that date. An email arrives from the airline confirming the flight details and suggesting passengers arrive 2 hours early for domestic flights. The agent must:
    1. Parse the incoming flight confirmation email to extract departure time and airport arrival recommendation
    2. Search the calendar for the flight event on December 20th to verify timing
    3. Calculate appropriate departure time (2 hours before flight = 1:00 PM, suggest cab pickup at 12:00 PM for travel buffer)
    4. Use cab app to get quotation for ride from user's home to SFO at 12:00 PM on December 20th
    5. Propose booking the ride to the user
    6. Upon acceptance, confirm the order and add a "Cab to Airport" calendar event at the pickup time

    This scenario exercises cross-app coordination (email → calendar → cab), time-based reasoning with safety buffers, quotation-to-order workflow in the cab app, and proactive trip logistics assistance..
    """

    start_time = datetime(2024, 12, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.email = StatefulEmailApp(name="Emails")
        self.email.user_email = "user@example.com"

        self.calendar = StatefulCalendarApp(name="Calendar")

        self.cab = StatefulCabApp(name="Cab")

        # Populate calendar with the flight event
        # Flight on December 20, 2024 at 3:00 PM (15:00)
        flight_event = CalendarEvent(
            title="Flight to Seattle",
            start_datetime=datetime(2024, 12, 20, 15, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2024, 12, 20, 16, 0, 0, tzinfo=UTC).timestamp(),
            location="San Francisco International Airport (SFO)",
            description="Flight AA1234 to Seattle",
            tag="Travel",
        )
        self.calendar.set_calendar_event(flight_event)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.calendar, self.cab]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Incoming flight confirmation email from airline
            # This triggers the entire workflow
            flight_email_event = email_app.send_email_to_user_with_id(
                email_id="flight_confirmation_001",
                sender="noreply@airline.com",
                subject="Flight Confirmation - AA1234 to Seattle",
                content="Dear Passenger,\n\nYour flight AA1234 to Seattle has been confirmed.\n\nDeparture: Friday, December 20, 2024 at 3:00 PM\nAirport: San Francisco International Airport (SFO)\nGate: To be announced 2 hours before departure\n\nImportant: Please arrive at the airport at least 2 hours before your scheduled departure time for domestic flights.\n\nThank you for flying with us!\n\nBest regards,\nAirline Customer Service",
            ).delayed(30)

            # Oracle Event 2: Agent proposes booking a cab to the airport
            # Motivated by: flight confirmation email recommends arriving 2 hours early (1:00 PM),
            # so cab pickup at 12:00 PM allows travel buffer
            proposal_event = (
                aui.send_message_to_user(
                    content="I saw your flight confirmation email for AA1234 to Seattle on December 20th at 3:00 PM. The airline recommends arriving 2 hours early (1:00 PM). Would you like me to book a cab from your home to SFO departing at 12:00 PM to ensure you arrive on time?"
                )
                .oracle()
                .depends_on(flight_email_event, delay_seconds=2)
            )

            # Oracle Event 3: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please book the cab and add a calendar event for the cab pickup. Use the Default service."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event 4: Agent gets quotation for the cab ride
            # Motivated by: user accepted and specified "Default service"
            quotation_event = (
                cab_app.get_quotation(
                    start_location="123 Home Street",
                    end_location="San Francisco International Airport (SFO)",
                    service_type="Default",
                    ride_time="2024-12-20 12:00:00",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent books the cab ride
            # Motivated by: quotation obtained, now confirming the order
            order_event = (
                cab_app.order_ride(
                    start_location="123 Home Street",
                    end_location="San Francisco International Airport (SFO)",
                    service_type="Default",
                    ride_time="2024-12-20 12:00:00",
                )
                .oracle()
                .depends_on(quotation_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent adds "Cab to Airport" calendar event
            # Motivated by: cab booking confirmed, now adding it to calendar for user visibility
            add_cab_event = (
                calendar_app.add_calendar_event(
                    title="Cab to Airport",
                    start_datetime="2024-12-20 12:00:00",
                    end_datetime="2024-12-20 13:00:00",
                    location="123 Home Street to SFO",
                    description="Cab ride to airport for Flight AA1234",
                    tag="Travel",
                )
                .oracle()
                .depends_on(order_event, delay_seconds=2)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            flight_email_event,
            proposal_event,
            acceptance_event,
            quotation_event,
            order_event,
            add_cab_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT type events
            agent_entries = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent sent proposal mentioning the flight, date, and cab booking
            # The agent must reference December 20th and propose booking a cab to the airport
            proposal_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_entries
            )

            # STRICT Check 2: Agent obtained cab quotation before booking
            # This demonstrates proper quotation-to-order workflow
            quotation_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "get_quotation"
                and "san francisco international airport" in e.action.args.get("end_location", "").lower()
                and "12:00:00" in e.action.args.get("ride_time", "")
                for e in agent_entries
            )

            # STRICT Check 3: Agent booked the cab ride
            # The booking must be for the correct destination and pickup time
            cab_ordered = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "order_ride"
                and "san francisco international airport" in e.action.args.get("end_location", "").lower()
                and "12:00:00" in e.action.args.get("ride_time", "")
                for e in agent_entries
            )

            # STRICT Check 4: Agent added cab event to calendar
            # This ensures visibility of the cab pickup in the user's schedule
            calendar_event_added = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                for e in agent_entries
            )

            # Build rationale for failure
            if not (proposal_found and quotation_found and cab_ordered and calendar_event_added):
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal to user")
                if not quotation_found:
                    missing_checks.append("cab quotation for airport ride")
                if not cab_ordered:
                    missing_checks.append("cab order confirmation")
                if not calendar_event_added:
                    missing_checks.append("calendar event for cab pickup")

                rationale = f"Missing required actions: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            success = proposal_found and quotation_found and cab_ordered and calendar_event_added
            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
