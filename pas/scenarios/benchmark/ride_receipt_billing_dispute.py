"""Scenario: Agent detects billing discrepancy in ride receipt and files dispute."""

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


@register_scenario("ride_receipt_billing_dispute")
class RideReceiptBillingDispute(PASScenario):
    """Agent detects billing discrepancy in ride receipt and files dispute with supporting evidence from ride history.

    The user receives an email receipt from the cab service for a ride taken yesterday from "Central Station" to "450 Oak Avenue" showing a charge of $45.00 with surge pricing applied. The agent must: 1. Parse the receipt details (ride ID, route, charge amount, surge pricing flag) from the incoming email, 2. Search the user's cab ride history to locate the corresponding ride record, 3. Compare the receipt's claimed route and pricing against the actual ride details stored in the ride history, 4. Identify the billing error (e.g., surge pricing was incorrectly applied during non-peak hours, or distance was overestimated), 5. Draft and send a dispute email to the cab company's billing department citing the specific discrepancy with evidence from the ride record (actual pickup time, service type, base fare).

    This scenario exercises cross-app data reconciliation (email → cab history verification), financial discrepancy detection through systematic comparison, evidence-based dispute composition, and proactive consumer advocacy without requiring user investigation..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.email = StatefulEmailApp(name="Emails")
        self.cab = StatefulCabApp(name="Cab")

        # Seed completed ride in cab history from yesterday at 2:00 PM
        # This is the actual ride that was taken - it was a Default service, NOT Premium
        # Actual charge should be around $15-18 for a 15km ride at $1.00/km base rate
        yesterday_ride_time = datetime(2025, 11, 17, 14, 0, 0, tzinfo=UTC).timestamp()
        self.ride_id = self.cab.add_new_ride(
            service_type="Default",
            start_location="Central Station",
            end_location="450 Oak Avenue",
            price=16.50,
            duration=18.0,
            time_stamp=yesterday_ride_time,
            distance_km=15.0,
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.cab]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # Environment Event 1: User receives fraudulent billing receipt email
            # This is the trigger - a billing email claiming Premium/surge pricing for the Default ride
            receipt_email_event = email_app.send_email_to_user_with_id(
                email_id="receipt_email_001",
                sender="billing@quickride.com",
                subject="Your Ride Receipt - $45.00",
                content=f"""Dear Alex Chen,

Thank you for riding with QuickRide!

Ride Details:
- Ride ID: {self.ride_id}
- Date: November 17, 2025 at 2:00 PM
- Route: Central Station → 450 Oak Avenue
- Service Type: Premium (Surge Pricing Applied)
- Distance: 15.0 km
- Total Charge: $45.00

This charge has been processed to your payment method.

If you have any questions, contact billing@quickride.com.

Best regards,
QuickRide Billing Team""",
            ).delayed(10)

            # Oracle Event 1: Agent retrieves ride history to cross-reference the receipt
            # Motivation: the receipt email arrived claiming Premium service with $45 charge,
            # but the agent needs to check ride history to verify what service was actually used
            get_history_event = (
                cab_app.get_ride_history(offset=0, limit=10).oracle().depends_on(receipt_email_event, delay_seconds=5)
            )

            # Oracle Event 2: Agent proposes to file a billing dispute
            # Motivation: the receipt email claims Premium service ($45) but ride history reveals
            # it was actually Default service ($16.50), so agent proposes dispute with evidence
            proposal_event = (
                aui.send_message_to_user(
                    content="I received a billing receipt from QuickRide claiming $45.00 for your ride yesterday (Central Station → 450 Oak Avenue), with Premium surge pricing. However, your ride history shows this was a Default service ride that cost $16.50. This appears to be a billing error of $28.50. Would you like me to send a dispute email to QuickRide's billing department with the correct ride details?"
                )
                .oracle()
                .depends_on(get_history_event, delay_seconds=3)
            )

            # Oracle Event 3: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please file the dispute with the correct information.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent sends dispute email with evidence from ride history
            # Motivation: user accepted the proposal, so agent now sends the dispute email
            # citing the specific discrepancy (Premium claimed vs Default actual)
            dispute_email_event = (
                email_app.send_email(
                    recipients=["billing@quickride.com"],
                    subject=f"Billing Dispute - Ride ID {self.ride_id}",
                    content=f"""Dear QuickRide Billing Team,

I am writing to dispute the charge on the receipt I received for ride ID {self.ride_id}.

Receipt Claims:
- Service Type: Premium (Surge Pricing Applied)
- Total Charge: $45.00

Actual Ride Details (from my ride history):
- Service Type: Default
- Actual Charge: $16.50
- Route: Central Station → 450 Oak Avenue (15.0 km)
- Date/Time: November 17, 2025 at 2:00 PM

The receipt incorrectly claims Premium surge pricing was applied, but my ride history confirms this was a standard Default service ride. The overcharge is $28.50.

Please review and correct this billing error. I request a refund of the $28.50 overcharge.

Thank you,
Alex Chen""",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=5)
            )

        # Register ALL events here in self.events
        self.events = [
            receipt_email_event,
            get_history_event,
            proposal_event,
            acceptance_event,
            dispute_email_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check Step 1: Agent retrieved ride history to verify the receipt
            # This is the core reasoning step where agent cross-references receipt against ride records
            ride_history_check = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "get_ride_history"
                for e in log_entries
            )

            # STRICT Check Step 2: Agent sent a proposal message to the user about the billing discrepancy
            # The agent must inform the user about the detected billing error
            # FLEXIBLE: wording details do not matter, only that the proposal was sent
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check Step 3: Agent sent a dispute email to the billing department
            # This is the key action - filing the dispute with the cab company
            # The agent must use send_email (the only available email-sending function for agent-initiated emails)
            # FLEXIBLE: exact email content/wording does not matter, only that the email was sent to billing
            dispute_email_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "send_email"
                and "billing@quickride.com" in e.action.args.get("recipients", [])
                for e in log_entries
            )

            # All three strict checks must pass for success
            success = ride_history_check and proposal_found and dispute_email_sent

            if not success:
                # Build rationale explaining which checks failed
                failed_checks = []
                if not ride_history_check:
                    failed_checks.append("agent did not retrieve ride history to verify receipt")
                if not proposal_found:
                    failed_checks.append("agent did not send proposal message to user about discrepancy")
                if not dispute_email_sent:
                    failed_checks.append("agent did not send dispute email to billing@quickride.com")
                rationale = "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
