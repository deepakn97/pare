"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCabApp,
    StatefulEmailApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("delayed_ride_incident_claim")
class DelayedRideIncidentClaim(PASScenario):
    """Agent mitigates a delayed cab ride by booking a replacement ride and submitting a compensation claim by email.

    The user receives an urgent email from CabApp Support stating that their current ride #R2847 (789 Pine Street → Medical Center, 456 Oak Avenue) is delayed by 45+ minutes, jeopardizing a 4:00 PM medical appointment. The email recommends canceling and booking an alternative ride immediately and instructs the user to reply to claims@cabapp.com with (1) new ride confirmation details, (2) a brief incident summary, and (3) original ride ID R2847 to receive a full refund plus a $15 credit. The agent must:
    1. Verify the delayed ride context via cab history/status tools
    2. Propose canceling the delayed ride, booking a replacement ride, and submitting the claim email
    3. After user acceptance, cancel the delayed ride and book the replacement ride for the same route
    4. Retrieve the new ride status to reference as confirmation details
    5. Reply to the support email with the required claim information

    This scenario exercises delay-triggered decision making, cab cancellation + rebooking, ride-status verification for claim details, and email-based claim submission.

    ---.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Email app with baseline data
        self.email = StatefulEmailApp(name="Emails", user_email="user@example.com")

        # Seed: Original booking confirmation email (sent earlier on Jan 10)
        # This email exists before the scenario trigger and contains the original ride details
        self.email.create_and_add_email_with_time(
            sender="bookings@cabapp.com",
            recipients=["user@example.com"],
            subject="Ride Confirmed - Pickup 3:30 PM - Ride #R2847",
            content="Your ride has been confirmed.\n\nRide Details:\n- Ride ID: R2847\n- Pickup: 789 Pine Street\n- Destination: Medical Center, 456 Oak Avenue\n- Service: Standard\n- Scheduled Time: January 10, 2025 at 3:30 PM\n- Estimated Fare: $28.00\n- Estimated Duration: 15 minutes\n\nThank you for choosing CabApp!",
            email_time="2025-01-10 14:00:00",
            folder_name="INBOX",
        )

        # Initialize Cab app with baseline ride history
        self.cab = StatefulCabApp(name="Cab")

        # Seed: The delayed ride R2847 that was booked earlier
        # This ride is currently ongoing but experiencing significant delay
        # Note: We use add_new_ride to seed historical data, then will set it as ongoing in events
        ride_timestamp = datetime(2025, 1, 10, 15, 30, 0, tzinfo=UTC).timestamp()
        self.cab.add_new_ride(
            service_type="Default",
            start_location="789 Pine Street",
            end_location="456 Oak Avenue",
            price=28.0,
            duration=15.0,
            time_stamp=ride_timestamp,
            distance_km=12.5,
        )

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.cab]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Urgent email from CabApp Support about ride delay requiring immediate action
            # This is the primary trigger - user receives notification about delayed ride and claim process
            delay_email_event = email_app.send_email_to_user_with_id(
                email_id="delay_notice_email",
                sender="support@cabapp.com",
                subject="Ride Delay Alert - Immediate Action Required",
                content="Your current ride (Ride #R2847) from 789 Pine Street to Medical Center, 456 Oak Avenue scheduled for 3:30 PM is delayed by 45+ minutes due to driver unavailability. For your urgent medical appointment at 4:00 PM, we recommend canceling and booking an alternative ride immediately from your current location (789 Pine Street) to Medical Center (456 Oak Avenue) with Standard service. We will process a full refund for the delayed ride plus a $15 credit. To claim your credit, reply to claims@cabapp.com with: (1) new ride confirmation details, (2) brief incident summary, and (3) original ride ID R2847.",
            ).delayed(5)

            # Oracle Event 2: Agent checks ride history to verify delayed ride details
            # Motivation: delay email references "Ride #R2847" - agent needs to confirm ride exists and details
            check_ride_history_event = (
                cab_app.get_ride_history(offset=0, limit=5).oracle().depends_on(delay_email_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent gets quotation for immediate replacement ride
            # Motivation: delay email explicitly requests "booking an alternative ride immediately" with specific locations
            get_quote_event = (
                cab_app.get_quotation(
                    start_location="789 Pine Street",
                    end_location="456 Oak Avenue",
                    service_type="Default",
                    ride_time=None,
                )
                .oracle()
                .depends_on(check_ride_history_event, delay_seconds=1)
            )

            # Oracle Event 4: Agent sends proposal to user with cancellation + rebooking + claims plan
            # Motivation: delay email requires immediate action and explicitly instructs replying to claims@cabapp.com for refund + credit.
            proposal_event = (
                aui.send_message_to_user(
                    content="I received an urgent email from CabApp Support: your ride R2847 (789 Pine Street → Medical Center, 456 Oak Avenue) is delayed by 45+ minutes and may cause you to miss your 4:00 PM appointment. They recommend canceling and booking a replacement ride immediately and replying to claims@cabapp.com with the new ride confirmation details + a brief incident summary to receive a full refund and $15 credit. Should I cancel the delayed ride, book the replacement ride, and submit the claim email?"
                )
                .oracle()
                .depends_on(get_quote_event, delay_seconds=2)
            )

            # Oracle Event 5: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please cancel and book the replacement ride immediately, then submit the claim email."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event 6: Agent cancels the delayed ride (WRITE - depends on acceptance)
            # Motivation: user accepted proposal in acceptance_event
            cancel_ride_event = cab_app.user_cancel_ride().oracle().depends_on(acceptance_event, delay_seconds=1)

            # Oracle Event 7: Agent books replacement ride (WRITE - depends on acceptance)
            # Motivation: user accepted proposal; delay email specified immediate booking with same locations/service
            book_replacement_event = (
                cab_app.order_ride(
                    start_location="789 Pine Street",
                    end_location="456 Oak Avenue",
                    service_type="Default",
                    ride_time=None,
                )
                .oracle()
                .depends_on(cancel_ride_event, delay_seconds=1)
            )

            # Oracle Event 8: Agent checks new ride status to confirm booking
            # Motivation: agent needs new ride details to include in claim reply (delay email requests "new ride confirmation details")
            check_new_ride_event = (
                cab_app.get_current_ride_status().oracle().depends_on(book_replacement_event, delay_seconds=1)
            )

            # Oracle Event 9: Agent replies to claims email with required details (WRITE - depends on acceptance)
            # Motivation: delay email requests reply to claims@cabapp.com with specific details; user accepted claim handling
            reply_claims_event = (
                email_app.reply_to_email(
                    email_id="delay_notice_email",
                    content="I am submitting a compensation claim for Ride R2847 as requested.\n\nOriginal Ride Details:\n- Ride ID: R2847\n- Scheduled: January 10, 2025 at 3:30 PM\n- Route: 789 Pine Street to Medical Center, 456 Oak Avenue\n- Service: Standard\n- Delay: 45+ minutes\n\nNew Ride Confirmation:\n- I canceled the delayed ride and booked an immediate replacement ride for the same route and service type.\n\nIncident Summary:\nThe 45+ minute delay jeopardized my time-sensitive 4:00 PM medical appointment at Medical Center. Per your email, I request a full refund for ride R2847 plus the $15 credit.\n\nPlease confirm receipt and processing timeline.",
                )
                .oracle()
                .depends_on(check_new_ride_event, delay_seconds=2)
            )

        # Register ALL events here in self.events
        self.events = [
            delay_email_event,
            check_ride_history_event,
            get_quote_event,
            proposal_event,
            acceptance_event,
            cancel_ride_event,
            book_replacement_event,
            check_new_ride_event,
            reply_claims_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent sent proposal referencing ride R2847 delay and replacement plan
            # This is the core reasoning - agent must recognize the urgent situation and propose a solution
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "R2847" in e.action.args.get("content", "")
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["delay", "cancel", "replacement", "medical"]
                )
                for e in log_entries
            )

            # FLEXIBLE Check 2: Agent observed ride history to verify delayed ride
            # This demonstrates the agent verified the ride details before taking action
            ride_history_check = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "get_ride_history"
                for e in log_entries
            )

            # STRICT Check 4: Agent cancelled the delayed ride
            # This is a critical action - the agent must cancel the problematic ride
            cancel_ride_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "user_cancel_ride"
                for e in log_entries
            )

            # STRICT Check 5: Agent booked replacement ride with correct route
            # This is the core action - agent must book the replacement with same locations
            replacement_ride_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "order_ride"
                and "789 pine street" in e.action.args.get("start_location", "").lower()
                and "456 oak avenue" in e.action.args.get("end_location", "").lower()
                for e in log_entries
            )

            # STRICT Check 6: Agent replied to claims email
            # This is the final critical action - submitting the claim
            # Flexible on exact message content but strict on the reply action with correct email_id
            claim_reply_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == "delay_notice_email"
                for e in log_entries
            )

            # Collect all strict checks
            strict_checks = [
                ("proposal with ride delay and replacement plan", proposal_found),
                ("cancelled delayed ride R2847", cancel_ride_found),
                ("booked replacement ride with correct route", replacement_ride_found),
                ("replied to claims email", claim_reply_sent),
            ]

            # Collect failed strict checks for rationale
            failed_checks = [name for name, passed in strict_checks if not passed]

            # Success requires all strict checks to pass
            success = all(passed for _, passed in strict_checks)

            # Build rationale for failure
            rationale = f"Missing critical actions: {', '.join(failed_checks)}" if not success else ""

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
