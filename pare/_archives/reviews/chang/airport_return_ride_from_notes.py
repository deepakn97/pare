from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
)
from pas.apps.cab import StatefulCabApp
from pas.apps.note import StatefulNotesApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("airport_return_ride_from_notes")
class AirportReturnRideFromNotes(PASScenario):
    """Agent books return cab ride from airport based on travel notes and completed outbound ride.

    The user has a note titled "Seattle Trip" in their "Personal" folder containing travel details: destination "Seattle", departure date "January 15, 2025", and return date "January 18, 2025". When a cab ride completes with the dropoff location "San Francisco International Airport (SFO)", the agent must:
    1. Receive the ride completion notification
    2. Retrieve the completed ride details from ride history to identify the airport destination
    3. Search notes for travel plans to find the return date
    4. Calculate return pickup time (e.g., late afternoon on January 18)
    5. Get a ride quotation from the same airport back to the user's home address
    6. Propose booking the return cab ride
    7. After user acceptance, order the return ride with the selected service type

    This scenario exercises cross-app context correlation (cab completion → note search), temporal reasoning (extracting return dates and planning ahead), ride booking workflows, and proactive travel assistance based on inferred trip context..
    """

    start_time = datetime(2025, 1, 15, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Notes app
        self.note = StatefulNotesApp(name="Notes")

        # Seed travel note in Personal folder with trip details
        # Created a few days before departure (January 10, 2025)
        self.note.create_note_with_time(
            folder="Personal",
            title="Seattle Trip",
            content="Trip to Seattle\nDestination: Seattle, WA\nDeparture: January 15, 2025\nReturn: January 18, 2025\nFlight departs SFO at 10:30 AM",
            created_at="2025-01-10 14:30:00",
            updated_at="2025-01-10 14:30:00",
        )

        # Initialize Cab app
        self.cab = StatefulCabApp(name="Cab")

        # Seed an ongoing ride to SFO airport (will be completed by environment event)
        # This ride is in progress, started earlier this morning (departure day)
        # The ride will be completed via end_ride() environment event to trigger the agent
        departure_timestamp = datetime(2025, 1, 15, 8, 30, 0, tzinfo=UTC).timestamp()
        self.cab.add_new_ride(
            service_type="Premium",
            start_location="123 Main St, San Francisco",
            end_location="San Francisco International Airport (SFO)",
            price=45.50,
            duration=35.0,
            time_stamp=departure_timestamp,
            distance_km=22.5,
        )
        # Modify the ride to be ongoing and set it as on_going_ride for end_ride() to work
        ongoing_ride = self.cab.ride_history[-1]  # Get the ride just added
        ongoing_ride.status = "IN_PROGRESS"  # Change status from "BOOKED" to "IN_PROGRESS"
        ongoing_ride.delay = 0.0  # Set delay for ongoing ride
        # Note: Setting on_going_ride is required for scenario setup to simulate an ongoing ride
        # This is necessary because add_new_ride() doesn't automatically set on_going_ride
        self.cab.on_going_ride = ongoing_ride

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.note, self.cab]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")

        with EventRegisterer.capture_mode():
            # Environment event: Ride completion notification at SFO
            # This is the exogenous trigger that starts the agent's workflow
            env_ride_complete = cab_app.end_ride().delayed(5)

            # Agent observes the ride completion notification and retrieves ride history
            # to identify the destination (SFO airport)
            agent_check_history = (
                cab_app.get_ride_history(offset=0, limit=10).oracle().depends_on(env_ride_complete, delay_seconds=3)
            )

            # Agent searches notes for travel information based on the airport destination cue
            agent_search_notes = (
                note_app.search_notes(query="SFO").oracle().depends_on(agent_check_history, delay_seconds=2)
            )

            # Agent proposes booking return ride based on the trip note and completed outbound ride
            agent_proposal = (
                aui.send_message_to_user(
                    content="I noticed you just arrived at SFO for your Seattle trip (departing today, Jan 15). According to your travel note, you're returning on January 18, 2025. Would you like me to book a return cab ride from SFO back to 123 Main St on that date?"
                )
                .oracle()
                .depends_on([env_ride_complete, agent_search_notes], delay_seconds=3)
            )

            # User accepts the proposal
            user_acceptance = aui.accept_proposal(
                content="Yes, please book it for the afternoon around 3 PM on January 18."
            ).depends_on(agent_proposal, delay_seconds=5)

            # Agent gets quotation for the return ride from SFO to home
            agent_get_quote = (
                cab_app.get_quotation(
                    start_location="San Francisco International Airport (SFO)",
                    end_location="123 Main St, San Francisco",
                    service_type="Premium",
                    ride_time="2025-01-18 15:00:00",
                )
                .oracle()
                .depends_on(user_acceptance, delay_seconds=2)
            )

            # Agent books the return ride
            agent_book_ride = (
                cab_app.order_ride(
                    start_location="San Francisco International Airport (SFO)",
                    end_location="123 Main St, San Francisco",
                    service_type="Premium",
                    ride_time="2025-01-18 15:00:00",
                )
                .oracle()
                .depends_on(agent_get_quote, delay_seconds=2)
            )

            # Agent confirms completion to user
            agent_confirmation = (
                aui.send_message_to_user(
                    content="Done! I've booked a Premium cab from SFO to 123 Main St for January 18 at 3:00 PM."
                )
                .oracle()
                .depends_on(agent_book_ride, delay_seconds=2)
            )

        # Register ALL events
        self.events = [
            env_ride_complete,
            agent_check_history,
            agent_search_notes,
            agent_proposal,
            user_acceptance,
            agent_get_quote,
            agent_book_ride,
            agent_confirmation,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to agent events only (ignore ENV events)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent retrieved ride history to identify airport destination
            ride_history_check = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "get_ride_history"
                for e in agent_events
            )

            # STRICT Check 2: Agent searched notes for travel information
            notes_search_check = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "search_notes"
                for e in agent_events
            )

            # STRICT Check 3: Agent proposed booking return ride to user
            proposal_check = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 4: Agent booked the return ride with correct parameters
            booking_check = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "order_ride"
                and (
                    "san francisco" in e.action.args.get("start_location", "").lower()
                    or "sfo" in e.action.args.get("start_location", "").lower()
                )
                and "123 main" in e.action.args.get("end_location", "").lower()
                and "2025-01-18" in e.action.args.get("ride_time", "")
                for e in agent_events
            )

            # All STRICT checks must pass
            success = ride_history_check and notes_search_check and proposal_check and booking_check

            if not success:
                # Build rationale for failure
                missing_checks = []
                if not ride_history_check:
                    missing_checks.append("agent did not retrieve ride history")
                if not notes_search_check:
                    missing_checks.append("agent did not search notes for travel information")
                if not proposal_check:
                    missing_checks.append("agent did not propose booking return ride")
                if not booking_check:
                    missing_checks.append("agent did not book return ride on January 18 from SFO to home")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
