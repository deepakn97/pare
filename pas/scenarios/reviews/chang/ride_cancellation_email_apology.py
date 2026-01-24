from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.email_client import Email, EmailFolderName
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCabApp,
    StatefulEmailApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("ride_cancellation_email_apology")
class RideCancellationEmailApology(PASScenario):
    """Agent sends apologetic email with updated arrival time after detecting ride cancellation and rebooking.

    The user has a booked cab ride scheduled to pick them up at 2:00 PM to arrive at a business lunch with client Rachel Thompson at "Bistro Meridian" at 2:45 PM. The user previously sent Rachel an email confirming their attendance. A ride cancellation notification arrives from the cab service due to driver unavailability. The agent must:
    1. Detect the incoming ride cancellation notification through the cab app
    2. Retrieve ride history to identify the cancelled ride details (pickup location, destination, original time)
    3. Immediately book an alternative ride with the same route and service type
    4. Search the user's sent emails to locate the lunch confirmation thread with Rachel Thompson
    5. Reply to Rachel's email proactively, informing her about the cancellation and rebooking, and confirming the arrival time

    This scenario exercises real-time service disruption handling, cross-app coordination (cab → email), email thread retrieval by recipient/subject search, and proactive stakeholder communication without user prompting.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails")

        # Initialize cab app
        self.cab = StatefulCabApp(name="Cab")

        # Seed a sent email confirming lunch with Rachel
        # Email timestamp: 2025-11-17 16:00:00 UTC (previous day at 4 PM)
        lunch_confirmation_email = Email(
            sender="user@meta.com",
            recipients=["rachel.thompson@clientcorp.com"],
            subject="Lunch Meeting Tomorrow - Bistro Meridian",
            content="Hi Rachel,\n\nLooking forward to our lunch meeting tomorrow at 2:45 PM at Bistro Meridian. I'll be there on time.\n\nBest regards,\nAlex",
            timestamp=datetime(2025, 11, 17, 16, 0, 0, tzinfo=UTC).timestamp(),
            is_read=True,
        )
        self.email.add_email(lunch_confirmation_email, EmailFolderName.SENT)
        # Store email_id for use in Step 3
        self.lunch_confirmation_email_id = lunch_confirmation_email.email_id
        # ID for an incoming confirmation email from Rachel (emitted as an env event in build_events_flow).
        self.rachel_confirmation_email_id = "email-rachel-lunch-confirmation-001"

        # Seed a booked cab ride to Bistro Meridian
        # Pickup time: 2025-11-18 14:00:00 UTC (2:00 PM today)
        # Duration: 30 minutes (~0.5 hour = 1800 seconds)
        # This ride will be cancelled in Step 3
        ride_timestamp = datetime(2025, 11, 18, 14, 0, 0, tzinfo=UTC).timestamp()
        self.cab.add_new_ride(
            service_type="Default",
            start_location="123 Main St",
            end_location="Bistro Meridian",
            price=15.50,
            duration=1800.0,  # 30 minutes in seconds
            time_stamp=ride_timestamp,
            distance_km=12.5,
        )
        # Get the ride that was just added and modify it
        booked_ride = self.cab.ride_history[-1]
        booked_ride.status = "BOOKED"
        booked_ride.delay = 300.0  # 5 minutes delay in seconds
        # Note: Setting on_going_ride is required for scenario setup to simulate a booked ride
        self.cab.on_going_ride = booked_ride

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.cab]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")

        with EventRegisterer.capture_mode():
            # Environment event: Rachel confirms the lunch by email (grounds "Rachel" in the agent proposal).
            rachel_confirmation_event = email_app.send_email_to_user_with_id(
                email_id=self.rachel_confirmation_email_id,
                sender="rachel.thompson@clientcorp.com",
                subject="Re: Lunch Meeting Tomorrow - Bistro Meridian",
                content="Hi Alex,\n\nConfirmed for 2:45 PM at Bistro Meridian tomorrow. See you then.\n\nBest,\nRachel",
            ).delayed(5)

            # Agent checks inbox to pick up the meeting context (so referencing Rachel is justified).
            agent_check_inbox_event = (
                email_app.search_emails(query="Bistro Meridian", folder_name="INBOX")
                .oracle()
                .depends_on(rachel_confirmation_event, delay_seconds=1)
            )

            # Environment event: Ride cancellation by driver
            cancel_event = cab_app.cancel_ride(
                who_cancel="driver",
                message="Driver unavailable. Please book another ride. Sorry for the inconvenience.",
            ).depends_on(agent_check_inbox_event, delay_seconds=10)

            # Agent detects the cancellation notification and checks ride history to understand what was cancelled
            history_check_event = (
                cab_app.get_ride_history(offset=0, limit=5).oracle().depends_on(cancel_event, delay_seconds=2)
            )

            # Agent proposes to book a new ride and update Rachel about the delay
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed your ride to Bistro Meridian was cancelled. Would you like me to book an alternative ride and notify Rachel about a potential delay?"
                )
                .oracle()
                .depends_on([history_check_event, agent_check_inbox_event], delay_seconds=1)
            )

            # User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please rebook and let Rachel know.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Agent books a new ride with the same route
            rebook_event = (
                cab_app.order_ride(
                    start_location="123 Main St",
                    end_location="Bistro Meridian",
                    service_type="Default",
                    ride_time="2025-11-18 14:00:00",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Agent searches sent emails to find the confirmation thread with Rachel
            search_event = (
                email_app.search_emails(query="Bistro Meridian", folder_name="SENT")
                .oracle()
                .depends_on(rebook_event, delay_seconds=1)
            )

            # Agent replies to Rachel's email thread with updated arrival info
            reply_event = (
                email_app.reply_to_email(
                    email_id=self.lunch_confirmation_email_id,
                    folder_name="SENT",
                    content="Hi Rachel,\n\nI wanted to give you a quick heads up - my original ride was cancelled, but I've booked a replacement ride for the same time (2:00 PM pickup). I should still be able to make our 2:45 PM lunch on time. See you soon!\n\nBest,\nAlex",
                )
                .oracle()
                .depends_on(search_event, delay_seconds=2)
            )

            # Agent confirms completion
            confirmation_event = (
                aui.send_message_to_user(
                    content="I've booked a new ride to Bistro Meridian and sent Rachel an update about the situation. Your new ride is confirmed for 2:00 PM."
                )
                .oracle()
                .depends_on(reply_event, delay_seconds=1)
            )

        # Register ALL events here in self.events
        self.events = [
            rachel_confirmation_event,
            agent_check_inbox_event,
            cancel_event,
            history_check_event,
            proposal_event,
            acceptance_event,
            rebook_event,
            search_event,
            reply_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only agent/oracle events (EventType.AGENT)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent checked ride history to understand the cancellation
            # Accepts: get_ride_history
            history_check_found = any(
                e.action.class_name == "StatefulCabApp" and e.action.function_name == "get_ride_history"
                for e in agent_events
            )

            # STRICT Check 2: Agent proposed help to user (via PASAgentUserInterface.send_message_to_user)
            # This check is FLEXIBLE on content - we just verify the proposal happened
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 3: Agent booked a new ride after the cancellation
            # Accepts: order_ride with same destination (Bistro Meridian)
            rebook_found = any(
                e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "order_ride"
                and e.action.args.get("end_location") == "Bistro Meridian"
                for e in agent_events
            )

            # STRICT Check 4: Agent searched sent emails for Rachel's thread
            # Accepts: search_emails in SENT folder
            search_found = any(
                e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "search_emails"
                and e.action.args.get("folder_name") == "SENT"
                for e in agent_events
            )

            # STRICT Check 5: Agent replied to Rachel's email thread
            # Accepts: reply_to_email (must reply to the thread, not send a new email)
            # This check is FLEXIBLE on the content of the reply - we only verify the action occurred
            reply_found = any(
                e.action.class_name == "StatefulEmailApp" and e.action.function_name == "reply_to_email"
                for e in agent_events
            )

            # Collect failed checks for rationale
            failed_checks = []
            if not history_check_found:
                failed_checks.append("no ride history check found")
            if not proposal_found:
                failed_checks.append("no proposal to user found")
            if not rebook_found:
                failed_checks.append("no ride rebooking to Bistro Meridian found")
            if not search_found:
                failed_checks.append("no sent email search found")
            if not reply_found:
                failed_checks.append("no reply to Rachel's email found")

            success = all([
                history_check_found,
                proposal_found,
                rebook_found,
                search_found,
                reply_found,
            ])

            rationale = None
            if not success:
                rationale = f"Validation failed: {'; '.join(failed_checks)}"

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
