from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.contacts import Contact
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


@register_scenario("ride_cancellation_expense_reporting")
class RideCancellationExpenseReporting(PASScenario):
    """Agent monitors ride cancellation and proactively sends expense report via email.

    The user has an active cab ride ordered for a business trip. An email arrives from their colleague notifying them that the meeting has been cancelled. The agent must: 1. Detect the meeting cancellation email. 2. Check current active ride status. 3. Recognize the ride is no longer needed. 4. Cancel the active ride. 5. Retrieve the cancellation fee details from ride history. 6. Compose and send an expense report email to the finance department with the cancellation fee and reason.

    This scenario exercises cross-app coordination between email monitoring and ride management, proactive cost mitigation through ride cancellation, post-cancellation data retrieval from ride history, and automated expense reporting via email composition..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Cab app
        self.cab = StatefulCabApp(name="Cab")
        # Baseline: User has already ordered a ride to the office for a business meeting
        # The ride was ordered earlier and is currently active (on-going)
        self.cab.order_ride(
            start_location="User Home",
            end_location="Corporate Office Downtown",
            service_type="Premium",
            ride_time="2025-11-18 09:00:00",
        )

        # Initialize Email app
        self.email = StatefulEmailApp(name="Emails")
        # Seed baseline contacts who will be referenced in the scenario
        colleague_contact = Contact(
            first_name="Sarah",
            last_name="Chen",
            email="sarah.chen@company.com",
            phone="+1-555-0123",
        )
        finance_contact = Contact(
            first_name="Finance",
            last_name="Department",
            email="finance@company.com",
            phone="+1-555-0199",
        )
        # Note: We do not seed the cancellation email here; it will arrive as an
        # environment event in Step 3 to trigger the agent's response

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.cab, self.email]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Meeting cancellation email arrives from colleague
            # This is the exogenous trigger that starts the scenario
            cancellation_email_id = "email-meeting-cancelled-001"
            email_event = email_app.send_email_to_user_with_id(
                email_id=cancellation_email_id,
                sender="sarah.chen@company.com",
                subject="Meeting Cancelled Today",
                content="Hi, I'm sorry but I need to cancel our 10 AM meeting at the office today. An urgent matter came up. Let's reschedule for next week.",
            ).delayed(10)

            # Oracle Event 1: Agent detects the cancellation email and reads it to understand the situation
            # Motivation: The agent received a new email notification and needs to read its full content
            read_email_event = (
                email_app.get_email_by_id(email_id=cancellation_email_id, folder_name="INBOX")
                .oracle()
                .depends_on(email_event, delay_seconds=2)
            )

            # Oracle Event 2: Agent checks current ride status to see if there's an active ride
            # Motivation: The email mentioned a meeting cancellation; the agent needs to check if transport is arranged
            check_ride_event = cab_app.get_current_ride_status().oracle().depends_on(read_email_event, delay_seconds=1)

            # Oracle Event 3: Agent proposes canceling the ride and handling the expense report
            # Motivation: The agent found an active ride to the office, but the meeting was cancelled per the email
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed your meeting at the office was cancelled. You have an active Premium ride to Corporate Office Downtown. Would you like me to cancel the ride?"
                )
                .oracle()
                .depends_on(check_ride_event, delay_seconds=2)
            )

            # Oracle Event 4: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please cancel the ride and file the expense report.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event 5: Agent cancels the active ride
            # Motivation: The user accepted the proposal to cancel the ride
            cancel_ride_event = cab_app.user_cancel_ride().oracle().depends_on(acceptance_event, delay_seconds=1)

            # Oracle Event 6: Agent retrieves ride history to get cancellation fee details
            # Motivation: The user requested to file expense report; need to get cancellation fee from ride history
            get_history_event = (
                cab_app.get_ride_history(offset=0, limit=10).oracle().depends_on(cancel_ride_event, delay_seconds=2)
            )

            # Oracle Event 7: Agent composes and sends expense report email to finance department
            # Motivation: User accepted proposal to file expense report; ride was cancelled and history retrieved
            send_expense_email_event = (
                email_app.send_email(
                    recipients=["finance@company.com"],
                    subject="Expense Report - Ride Cancellation Fee",
                    content="Dear Finance Department,\n\nPlease find below the expense details for a cancelled business ride:\n\nReason: Business meeting at Corporate Office Downtown was cancelled by colleague\nRide Service: Premium\nOriginal Destination: Corporate Office Downtown\nCancellation Fee: [Amount from cancelled ride]\nDate: November 18, 2025\n\nPlease process this cancellation fee for reimbursement.\n\nBest regards",
                )
                .oracle()
                .depends_on(get_history_event, delay_seconds=2)
            )

        self.events = [
            email_event,
            read_email_event,
            check_ride_event,
            proposal_event,
            acceptance_event,
            cancel_ride_event,
            get_history_event,
            send_expense_email_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent sent proposal to the user (STRICT - core reasoning)
            # The proposal must reference the meeting cancellation and offer to cancel ride + file expense report
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check Step 2a: Agent read the cancellation email (STRICT - must detect the trigger)
            email_read_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "get_email_by_id"
                and e.action.args.get("email_id") == "email-meeting-cancelled-001"
                for e in log_entries
            )

            # Check Step 2b: Agent checked current ride status (STRICT - must verify ride exists)
            ride_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "get_current_ride_status"
                for e in log_entries
            )

            # Check Step 3a: Agent cancelled the ride (STRICT - core action)
            cancel_ride_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "user_cancel_ride"
                for e in log_entries
            )

            # Check Step 5: Agent retrieved ride history to get cancellation fee (STRICT - required for expense report)
            get_history_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "get_ride_history"
                for e in log_entries
            )

            # Check Step 6: Agent sent expense report email to finance department (STRICT - core requirement from scenario description)
            expense_email_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "send_email"
                and "finance@company.com" in e.action.args.get("recipients", [])
                for e in log_entries
            )

            # All checks must pass for success
            success = (
                proposal_found
                and email_read_found
                and ride_check_found
                and cancel_ride_found
                and get_history_found
                and expense_email_found
            )

            if not success:
                # Build rationale for failure
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("no agent proposal to user found in log")
                if not email_read_found:
                    missing_checks.append("agent did not read the meeting cancellation email")
                if not ride_check_found:
                    missing_checks.append("agent did not check current ride status")
                if not cancel_ride_found:
                    missing_checks.append("agent did not cancel the ride")
                if not get_history_found:
                    missing_checks.append("agent did not retrieve ride history to get cancellation fee")
                if not expense_email_found:
                    missing_checks.append("agent did not send expense report email to finance department")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
