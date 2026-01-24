from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulEmailApp,
)
from pas.apps.cab import StatefulCabApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("cab_expense_reimbursement_workflow")
class CabExpenseReimbursementWorkflow(PASScenario):
    """Agent processes corporate cab expense reimbursement request triggered by policy change email.

    The user receives an email from the company's finance department (Sarah Chen, sarah.chen@company-finance.com) on Monday, December 23rd at 9:00 AM stating: "Our corporate cab reimbursement policy has changed. All cab rides taken in the last 7 days for business purposes must be submitted by Friday Dec 27th with ride details (dates, routes, amounts). Please forward your ride history to accounting@company.com with subject 'Cab Reimbursement - [Your Name] - Dec 2024'." The agent must:
    1. Parse the email to extract the reimbursement deadline (Dec 27th), time window (last 7 days = Dec 16-23), and submission instructions (send to accounting@company.com)
    2. Use the cab app to retrieve ride history for the specified 7-day period
    3. Extract ride details (dates, start/end locations, service types, fare amounts) from each ride record
    4. Compose a new email to accounting@company.com with subject line following the specified format, listing all rides with dates, routes, and amounts in the body

    This scenario exercises email-triggered administrative workflows, cab ride history retrieval (not booking), multi-ride data aggregation, and structured email composition with specific formatting requirements.
    """

    start_time = datetime(2024, 12, 23, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.email = StatefulEmailApp(name="Emails")
        self.cab = StatefulCabApp(name="Cab")

        # Populate baseline data
        # Cab: Seed ride history for the past 7 days (Dec 16-23)
        # These rides will be retrieved by the agent when processing the reimbursement request.

        # Ride 1: Dec 17, 2024 - Airport ride
        self.cab.add_new_ride(
            service_type="Premium",
            start_location="Home",
            end_location="Airport",
            price=45.50,
            duration=35.0,
            time_stamp=datetime(2024, 12, 17, 8, 30, 0, tzinfo=UTC).timestamp(),
            distance_km=25.0,
        )

        # Ride 2: Dec 19, 2024 - Client meeting
        self.cab.add_new_ride(
            service_type="Default",
            start_location="Office",
            end_location="Client Site Downtown",
            price=18.75,
            duration=20.0,
            time_stamp=datetime(2024, 12, 19, 14, 0, 0, tzinfo=UTC).timestamp(),
            distance_km=12.0,
        )

        # Ride 3: Dec 20, 2024 - Return from client meeting
        self.cab.add_new_ride(
            service_type="Default",
            start_location="Client Site Downtown",
            end_location="Office",
            price=19.25,
            duration=22.0,
            time_stamp=datetime(2024, 12, 20, 17, 30, 0, tzinfo=UTC).timestamp(),
            distance_km=12.0,
        )

        # Ride 4: Dec 22, 2024 - Conference venue
        self.cab.add_new_ride(
            service_type="Van",
            start_location="Hotel",
            end_location="Conference Center",
            price=32.00,
            duration=25.0,
            time_stamp=datetime(2024, 12, 22, 9, 0, 0, tzinfo=UTC).timestamp(),
            distance_km=15.0,
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
            # Environment Event 1: Policy change email from finance department
            # Trigger contains explicit instructions: 7-day window, deadline (Dec 27), submission format, recipient
            policy_email_event = email_app.send_email_to_user_with_id(
                email_id="policy_email_dec2024",
                sender="sarah.chen@company-finance.com",
                subject="URGENT: Updated Cab Reimbursement Policy - Action Required by Dec 27",
                content="Hi,\n\nOur corporate cab reimbursement policy has changed effective immediately. All business cab rides taken in the last 7 days (Dec 16-23) must be submitted by Friday December 27th, 2024.\n\nPlease compile your ride history and send the following details to accounting@company.com:\n- Date of each ride\n- Start and end locations\n- Service type\n- Fare amount\n\nUse subject line: 'Cab Reimbursement - [Your Name] - Dec 2024'\n\nThis is mandatory for all employees. Missing the deadline will delay your reimbursement.\n\nBest regards,\nSarah Chen\nFinance Department",
            ).delayed(5)

            # Oracle Event 1: Agent retrieves ride history for the 7-day window mentioned in policy email
            # Motivation: policy email explicitly requests "rides taken in the last 7 days (Dec 16-23)"
            retrieve_rides_event = (
                cab_app.get_ride_history(offset=0, limit=10).oracle().depends_on(policy_email_event, delay_seconds=3)
            )

            # Oracle Event 2: Agent sends proposal to user
            # Motivation: policy email content requests action ("must be submitted"), deadline ("by Dec 27"), and format requirements
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed an urgent reimbursement request from Finance (Sarah Chen). The email asks you to submit cab ride details from Dec 16-23 to accounting@company.com by Dec 27th. I found 4 business rides in that period. Would you like me to compile the ride details and send the reimbursement email?"
                )
                .oracle()
                .depends_on(retrieve_rides_event, delay_seconds=2)
            )

            # Oracle Event 3: User accepts proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please prepare and send the reimbursement email.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent composes and sends reimbursement email with ride details
            # Motivation: user accepted proposal; ride details were retrieved in retrieve_rides_event
            send_reimbursement_event = (
                email_app.send_email(
                    recipients=["accounting@company.com"],
                    subject="Cab Reimbursement - User - Dec 2024",
                    content="Dear Accounting Team,\n\nPlease find my business cab ride details for the period Dec 16-23, 2024:\n\n1. December 17, 2024\n   Route: Home to Airport\n   Service: Premium\n   Fare: $45.50\n\n2. December 19, 2024\n   Route: Office to Client Site Downtown\n   Service: Default\n   Fare: $18.75\n\n3. December 20, 2024\n   Route: Client Site Downtown to Office\n   Service: Default\n   Fare: $19.25\n\n4. December 22, 2024\n   Route: Hotel to Conference Center\n   Service: Van\n   Fare: $32.00\n\nTotal reimbursement amount: $115.50\n\nPlease process at your earliest convenience.\n\nBest regards",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=4)
            )

        # Register ALL events
        self.events = [
            policy_email_event,
            retrieve_rides_event,
            proposal_event,
            acceptance_event,
            send_reimbursement_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to agent events only
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent sent proposal to user about the reimbursement request
            # The proposal should reference the finance email and deadline mentioned in the policy email
            proposal_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(keyword in e.action.args.get("content", "").lower() for keyword in ["reimbursement", "finance"])
                for e in agent_events
            )

            # STRICT Check 2: Agent retrieved ride history (demonstrates observing cab app state)
            # Accepts either get_ride_history or equivalent methods for retrieving ride data
            ride_history_retrieved = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name in ["get_ride_history", "get_ride"]
                for e in agent_events
            )

            # STRICT Check 3: Agent sent email to accounting@company.com with reimbursement details
            # Must include the required recipient, but wording is flexible
            reimbursement_email_sent = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "send_email"
                and "accounting@company.com" in e.action.args.get("recipients", [])
                for e in agent_events
            )

            # Build success and rationale
            success = proposal_found and ride_history_retrieved and reimbursement_email_sent

            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal about reimbursement request")
                if not ride_history_retrieved:
                    missing_checks.append("ride history retrieval from cab app")
                if not reimbursement_email_sent:
                    missing_checks.append("reimbursement email sent to accounting@company.com")

                rationale = f"Missing critical checks: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
