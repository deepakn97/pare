from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCabApp,
    StatefulEmailApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("colleague_ride_emergency_assist")
class ColleagueRideEmergencyAssist(PASScenario):
    """Agent books emergency ride for colleague and coordinates pickup via email communication.

    The user receives an urgent email from their colleague Lisa Park stating that her car broke down on the highway near "Oak Valley Rest Stop" and she needs a ride to the office at "450 Market Street" for an important 3:00 PM client presentation. The agent must:
    1. Parse the emergency pickup request, colleague's stranded location, and destination from the incoming email
    2. Request cab quotations from Oak Valley Rest Stop to 450 Market Street for immediate pickup
    3. Select an appropriate service type and book the ride on behalf of the user (who will pay for the colleague's ride)
    4. Reply to Lisa's email with ride confirmation details including service type, estimated pickup time, and instructions to wait for the cab
    5. Monitor the booked ride status to detect when the driver arrives at the pickup location
    6. Send a follow-up email to Lisa when the ride status changes to "arrived" or "in progress," confirming the cab has reached her location

    This scenario exercises cross-app coordination (email → cab → email), third-party ride booking where the user arranges transportation for another person, temporal reasoning with urgent time constraints (client meeting deadline), email thread continuation with actionable ride logistics, and proactive status monitoring with follow-up communication..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with baseline data.

        Baseline state (pre-existing before start_time):
        - Email: lisa.park@company.com (colleague contact exists)
        - No pre-existing emails, calendar events, or cab bookings
        - The triggering emergency email will arrive as an early environment event in Step 3
        """
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize email app with user's email address
        self.email = StatefulEmailApp(name="Emails")

        # Initialize cab app
        self.cab = StatefulCabApp(name="Cab")

        # No baseline data to seed - the colleague's emergency email will arrive
        # as a triggering environment event in Step 3

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.cab]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # ENVIRONMENT EVENT 1: Emergency email from colleague arrives
            emergency_email = email_app.send_email_to_user_with_id(
                email_id="emergency_lisa_email_001",
                sender="lisa.park@company.com",
                subject="URGENT: Car broke down - need ride to office!",
                content="Hi! My car just broke down on the highway near Oak Valley Rest Stop. I desperately need a ride to the office at 450 Market Street for my 3:00 PM client presentation. Can you help me book a cab? I'm stranded here and my phone battery is dying. Please use email to let me know if you've booked the ride!",
            )

            # ORACLE EVENT 1: Agent reads the emergency email (motivated by notification of new email)
            read_email = (
                email_app.get_email_by_id(
                    email_id="emergency_lisa_email_001",
                    folder_name="INBOX",
                )
                .oracle()
                .depends_on(emergency_email, delay_seconds=2)
            )

            # ORACLE EVENT 2: Agent gets cab quotation (motivated by emergency email requesting ride booking)
            get_quote = (
                cab_app.get_quotation(
                    start_location="Oak Valley Rest Stop",
                    end_location="450 Market Street",
                    service_type="Premium",
                    ride_time=None,
                )
                .oracle()
                .depends_on(read_email, delay_seconds=3)
            )

            # ORACLE EVENT 3: Agent asks for permission BEFORE booking (ride booking is a commit action).
            proposal_book = (
                aui.send_message_to_user(
                    content="I saw Lisa's emergency email about her car breakdown at Oak Valley Rest Stop. I can book a Premium cab for her to get to the office at 450 Market Street for her 3:00 PM meeting (you'll be charged). Should I book it now?"
                )
                .oracle()
                .depends_on(get_quote, delay_seconds=2)
            )

            # USER EVENT 1: User approves booking the ride
            user_accept_booking = (
                aui.accept_proposal(content="Yes, please proceed.").oracle().depends_on(proposal_book, delay_seconds=5)
            )

            # ORACLE EVENT 4: Agent books the ride (motivated by user approval + quotation showing availability)
            book_ride = (
                cab_app.order_ride(
                    start_location="Oak Valley Rest Stop",
                    end_location="450 Market Street",
                    service_type="Premium",
                    ride_time=None,
                )
                .oracle()
                .depends_on(user_accept_booking, delay_seconds=2)
            )

            # ORACLE EVENT 5: Agent checks ride status to get details for email (motivated by booking completion)
            check_status = cab_app.get_current_ride_status().oracle().depends_on(book_ride, delay_seconds=2)

            # ORACLE EVENT 6: Agent asks for permission to email Lisa the ride details
            proposal_send_details = (
                aui.send_message_to_user(
                    content="The Premium cab is booked. Should I email Lisa the pickup and confirmation details?"
                )
                .oracle()
                .depends_on(check_status, delay_seconds=2)
            )

            # USER EVENT 2: User approves sending details to Lisa
            user_accept_send_details = (
                aui.accept_proposal(content="Yes, please proceed.")
                .oracle()
                .depends_on(proposal_send_details, delay_seconds=5)
            )

            # ORACLE EVENT 7: Agent replies to Lisa's email with ride details (motivated by user approval)
            reply_email = (
                email_app.reply_to_email(
                    email_id="emergency_lisa_email_001",
                    folder_name="INBOX",
                    content="Hi Lisa! I've got you covered. I just booked a Premium cab for you.\n\nPickup Location: Oak Valley Rest Stop\nDestination: 450 Market Street\nService Type: Premium\nEstimated arrival: 5-8 minutes\n\nThe driver will arrive shortly. Please wait at your current location and look for the cab. You'll make it to your 3:00 PM presentation with time to spare. Good luck with the meeting!",
                )
                .oracle()
                .depends_on(user_accept_send_details, delay_seconds=3)
            )

        # Register ALL events here in self.events
        self.events = [
            emergency_email,
            read_email,
            get_quote,
            proposal_book,
            user_accept_booking,
            book_ride,
            check_status,
            proposal_send_details,
            user_accept_send_details,
            reply_email,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to agent events only (exclude environment events)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # Check 1: STRICT - Agent sent proposal mentioning Lisa and the emergency situation
            proposal_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # Check 2: STRICT - Agent booked the ride for the correct locations
            booking_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "order_ride"
                and "oak valley rest stop" in e.action.args.get("start_location", "").lower()
                and "450 market street" in e.action.args.get("end_location", "").lower()
                for e in agent_events
            )

            # Determine success based on strict checks (all must pass)
            success = proposal_found and booking_found

            # Build rationale for failure
            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("no proposal to user found")
                if not booking_found:
                    missing_checks.append("no ride booking for correct locations")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
