from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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
    """Agent notifies a meeting host by email when an already-booked ride becomes delayed.

    The user receives an email from their client, Sarah Martinez, proposing an in-person meeting at a specific address
    tomorrow afternoon. The email mentions that punctuality is important due to Sarah's tight schedule and asks that if the
    user is delayed, they should email Sarah in advance. Separately, the Cab app sends a delay notification for an
    already-booked ride to the meeting. The agent must:
    1. Read the meeting invitation email to capture the meeting time/location and the request to email if delayed
    2. Detect the ride delay notification
    3. Propose emailing Sarah with the delay and an updated ETA
    4. After user acceptance, reply to Sarah's email with the delay update

    This scenario exercises user-gated communication to a third party, grounding the action in an explicit email request,
    and delay-triggered coordination across email and cab.
    """

    start_time = datetime(2025, 11, 19, 13, 0, 0, tzinfo=UTC).timestamp()
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

        # Seed a pre-existing ride (booked outside the scenario) so a delay notification is meaningful.
        # The agent will NOT book a ride in this scenario; only react to the delay.
        self.cab.order_ride(
            start_location="123 Main Street, San Francisco, CA 94102",
            end_location="456 Market Street, San Francisco, CA 94105",
            service_type="Default",
            ride_time="2025-11-19 13:30:00",
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.cab]

    def build_events_flow(self) -> None:
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
                content=(
                    "Hi! I'd like to meet at 2:00 PM to discuss the product roadmap. The meeting will be at our office: "
                    "456 Market Street, San Francisco, CA 94105. Please be on time as I have back-to-back meetings.\n\n"
                    "If you're delayed for any reason, please email me about the ETA in advance so I can adjust.\n\n"
                    "Looking forward to seeing you!"
                ),
            ).delayed(15)

            # Agent reads the email to extract meeting details
            # Motivated by: incoming email notification about meeting
            read_email_event = (
                email_app.get_email_by_id(email_id="meeting-invitation-sarah")
                .oracle()
                .depends_on(meeting_email_event, delay_seconds=3)
            )

            # Environment Event 2: Ride status update - delay notification
            delay_notification_event = cab_app.update_ride_status(
                status="delayed", message="Driver is running 15 minutes behind schedule due to traffic."
            ).delayed(25)

            # Agent asks user whether to email Sarah about the delay
            # Motivated by: meeting email explicitly requested emailing in advance if delayed.
            notify_user_event = (
                aui.send_message_to_user(
                    content="Your ride to Sarah's meeting is delayed by 15 minutes. Sarah asked in her email to be notified in advance if you're delayed. Should I reply to her email with an updated ETA?"
                )
                .oracle()
                .depends_on([delay_notification_event, read_email_event], delay_seconds=2)
            )

            # User confirms to notify Sarah
            confirm_notify_event = (
                aui.accept_proposal(content="Yes, please proceed.")
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
            delay_notification_event,
            notify_user_event,
            confirm_notify_event,
            reply_sarah_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to agent/oracle events only
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent asked the user whether to email Sarah about the delay
            # Content-flexible: verify at least one send_message_to_user occurred.
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 2: Agent replied to Sarah's email about the delay
            reply_to_sarah_found = any(
                e.action.class_name == "StatefulEmailApp"
                and e.action.function_name in ["reply_to_email", "send_email"]
                and e.action.args.get("email_id") == "meeting-invitation-sarah"
                and "15" in e.action.args.get("content", "")
                for e in agent_events
            )

            # Aggregate all strict checks
            all_checks_passed = proposal_found and reply_to_sarah_found

            if not all_checks_passed:
                # Build failure rationale
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent did not send any messages to user")
                if not reply_to_sarah_found:
                    missing_checks.append("agent did not reply to Sarah's email about delay")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
