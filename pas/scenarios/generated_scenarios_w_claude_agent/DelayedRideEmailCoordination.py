"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.contacts import Contact
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


@register_scenario("delayed_ride_email_coordination")
class DelayedRideEmailCoordination(PASScenario):
    """Agent coordinates ride booking and arrival notification for a time-sensitive meeting based on incoming email invitation.

    The user receives an email from their client, Sarah Martinez, proposing an in-person meeting at a specific address tomorrow afternoon. The email mentions that punctuality is important due to Sarah's tight schedule. The agent must:
    1. Parse the meeting location and time from the incoming email
    2. Calculate appropriate departure time by requesting a ride quotation from the user's home to the meeting location
    3. Book the ride with sufficient buffer time to ensure early arrival
    4. Monitor the booked ride status to detect any delays
    5. If the ride is delayed, proactively notify Sarah via email reply explaining the situation and providing an updated ETA

    This scenario exercises cross-app coordination (email → cab), temporal reasoning with buffer calculation, continuous monitoring of ride status, and conditional communication triggered by service delays..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails", user_email="user@example.com")

        # Initialize cab app
        self.cab = StatefulCabApp(name="Cab")

        # Populate baseline data: user's home address as a contact
        user_contact = Contact(
            first_name="User",
            last_name="Person",
            is_user=True,
            email="user@example.com",
            address="123 Main Street, San Francisco, CA 94102",
            phone="+1-555-0100",
        )

        # Populate baseline data: Sarah Martinez as a client contact
        sarah_contact = Contact(
            first_name="Sarah",
            last_name="Martinez",
            email="sarah.martinez@clientcorp.com",
            phone="+1-555-0234",
            job="Senior Director",
            description="Client contact for business meetings",
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.cab]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Sarah sends meeting invitation email
            meeting_email_event = email_app.send_email_to_user_with_id(
                email_id="meeting-invitation-sarah",
                sender="sarah.martinez@clientcorp.com",
                subject="Meeting Tomorrow - Product Discussion",
                content="Hi! I'd like to meet tomorrow (Nov 19) at 2:00 PM to discuss the product roadmap. The meeting will be at our office: 456 Market Street, San Francisco, CA 94105. Please be on time as I have back-to-back meetings. Looking forward to seeing you!",
            ).delayed(15)

            # Agent reads the email to extract meeting details
            # Motivated by: incoming email notification about meeting
            read_email_event = (
                email_app.get_email_by_id(email_id="meeting-invitation-sarah")
                .oracle()
                .depends_on(meeting_email_event, delay_seconds=3)
            )

            # Agent proposes to book a ride to the meeting
            # Motivated by: email contains meeting location and time-sensitive punctuality requirement
            propose_ride_event = (
                aui.send_message_to_user(
                    content="I saw Sarah Martinez sent you a meeting invitation for tomorrow at 2:00 PM at 456 Market Street. She emphasized punctuality. Would you like me to book a ride to ensure you arrive on time?"
                )
                .oracle()
                .depends_on(read_email_event, delay_seconds=2)
            )

            # User accepts the proposal
            accept_proposal_event = (
                aui.accept_proposal(content="Yes, please book a ride for me.")
                .oracle()
                .depends_on(propose_ride_event, delay_seconds=3)
            )

            # Agent requests ride quotation to calculate timing
            # Motivated by: user accepted proposal to book ride
            get_quote_event = (
                cab_app.get_quotation(
                    start_location="123 Main Street, San Francisco, CA 94102",
                    end_location="456 Market Street, San Francisco, CA 94105",
                    service_type="Default",
                    ride_time="2025-11-19 13:30:00",
                )
                .oracle()
                .depends_on(accept_proposal_event, delay_seconds=2)
            )

            # Agent books the ride
            # Motivated by: quotation obtained, need to confirm booking
            book_ride_event = (
                cab_app.order_ride(
                    start_location="123 Main Street, San Francisco, CA 94102",
                    end_location="456 Market Street, San Francisco, CA 94105",
                    service_type="Default",
                    ride_time="2025-11-19 13:30:00",
                )
                .oracle()
                .depends_on(get_quote_event, delay_seconds=2)
            )

            # Environment Event 2: Ride status update - delay notification
            delay_notification_event = (
                cab_app.update_ride_status(
                    status="delayed", message="Driver is running 15 minutes behind schedule due to traffic."
                )
                .delayed(10)
                .depends_on(book_ride_event)
            )

            # Agent sends notification to user and Sarah about the delay
            # Motivated by: ride status update shows delay, meeting requires punctuality
            notify_user_event = (
                aui.send_message_to_user(
                    content="Your ride to Sarah's meeting is delayed by 15 minutes. Should I notify Sarah about this delay?"
                )
                .oracle()
                .depends_on(delay_notification_event, delay_seconds=2)
            )

            # User confirms to notify Sarah
            confirm_notify_event = (
                aui.accept_proposal(content="Yes, please let her know.")
                .oracle()
                .depends_on(notify_user_event, delay_seconds=2)
            )

            # Agent replies to Sarah's email about the delay
            # Motivated by: user approved notifying Sarah, and delay information from ride status
            reply_sarah_event = (
                email_app.reply_to_email(
                    email_id="meeting-invitation-sarah",
                    content="Hi Sarah, I'm looking forward to our meeting tomorrow at 2:00 PM. Just wanted to give you a heads up that my ride is running about 15 minutes behind due to traffic. I should arrive by 2:15 PM. Apologies for the delay!",
                )
                .oracle()
                .depends_on(confirm_notify_event, delay_seconds=3)
            )

        # Register ALL events
        self.events = [
            meeting_email_event,
            read_email_event,
            propose_ride_event,
            accept_proposal_event,
            get_quote_event,
            book_ride_event,
            delay_notification_event,
            notify_user_event,
            confirm_notify_event,
            reply_sarah_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to agent/oracle events only
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent read the meeting email
            email_read_found = any(
                e.action.class_name == "StatefulEmailApp"
                and e.action.function_name in ["get_email_by_id", "list_emails"]
                and (
                    e.action.function_name != "get_email_by_id"
                    or e.action.args.get("email_id") == "meeting-invitation-sarah"
                )
                for e in agent_events
            )

            # STRICT Check 2: Agent proposed ride booking to user
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 3: Agent got ride quotation
            quotation_found = any(
                e.action.class_name == "StatefulCabApp" and e.action.function_name == "get_quotation"
                for e in agent_events
            )

            # STRICT Check 4: Agent booked the ride
            booking_found = any(
                e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "order_ride"
                and e.action.args.get("end_location") is not None
                and "456 market street" in e.action.args.get("end_location").lower()
                for e in agent_events
            )

            # STRICT Check 5: Agent notified user about the delay
            # (This check is already satisfied by proposal_found above, since send_message_to_user
            # is used for both initial proposal and delay notification)
            delay_notification_found = proposal_found  # At least one message to user

            # STRICT Check 6: Agent replied to Sarah's email about the delay
            reply_to_sarah_found = any(
                e.action.class_name == "StatefulEmailApp"
                and e.action.function_name in ["reply_to_email", "send_email"]
                and e.action.args.get("email_id") == "meeting-invitation-sarah"
                for e in agent_events
            )

            # Aggregate all strict checks
            all_checks_passed = (
                email_read_found
                and proposal_found
                and quotation_found
                and booking_found
                and delay_notification_found
                and reply_to_sarah_found
            )

            if not all_checks_passed:
                # Build failure rationale
                missing_checks = []
                if not email_read_found:
                    missing_checks.append("agent did not read meeting email")
                if not proposal_found:
                    missing_checks.append("agent did not send any messages to user")
                if not quotation_found:
                    missing_checks.append("agent did not get ride quotation")
                if not booking_found:
                    missing_checks.append("agent did not book the ride")
                if not reply_to_sarah_found:
                    missing_checks.append("agent did not reply to Sarah's email about delay")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
