"""Scenario: Agent calculates and reports business cab expenses from ride history."""

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


@register_scenario("ride_receipt_expense_note_organization")
class RideReceiptExpenseNoteOrganization(PASScenario):
    """Agent calculates business cab expenses and replies to finance with accurate totals.

    The user attended a 3-day business conference in Portland, Oregon. They have multiple cab
    rides in their history - some between the hotel and convention center (business-related)
    and some personal trips (restaurants, bookstores). The finance administrator sends an
    email requesting expense documentation, specifying that ONLY trips between the convention
    center and hotel are reimbursable. The agent must identify the relevant business trips,
    calculate the correct total, and reply to finance with accurate expense details.

    This scenario tests:
    - Filtering ride history based on business criteria (location matching)
    - Accurate expense calculation from multiple rides
    - Cross-app coordination between Cab and Email apps
    - Correctly excluding non-business expenses from reimbursement requests
    """

    start_time = datetime(2025, 11, 22, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    # Business ride prices for validation

    additional_system_prompt = """You attended a business conference in Portland, Oregon from Nov 18-20.
Your cab rides include both business trips (hotel ↔ convention center) and personal trips.

ACCEPT proposals that:
- Correctly identify that only hotel ↔ convention center trips are reimbursable
- Calculate the total from ONLY the business-related rides
- Offer to reply to the finance email with accurate expense details

REJECT proposals that:
- Include personal trips (to restaurants, bookstores, etc.) in the expense total
- Calculate an incorrect total amount
- Do not distinguish between business and personal rides"""

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails")

        # Initialize cab app with ride history
        self.cab = StatefulCabApp(name="Cab")

        # Add company email about the business trip (sent before the trip)
        self.email.create_and_add_email(
            sender="travel@company.com",
            subject="Business Trip Details - Portland Tech Conference",
            content="""Hi,

Your business trip to the Portland Tech Conference has been approved for November 18-20, 2025.

Conference Location:
Oregon Convention Center
777 NE Martin Luther King Jr Blvd, Portland, OR 97232

Hotel Accommodation:
Downtown Portland Hotel
500 SW Broadway, Portland, OR 97205

Please keep all transportation receipts for expense reimbursement.

Best regards,
Travel Coordination Team""",
        )

        # Business rides: Hotel ↔ Convention Center (6 rides over 3 days)
        # Day 1 (Nov 18)
        self.cab.add_new_ride(
            service_type="Default",
            start_location="Downtown Portland Hotel, 500 SW Broadway",
            end_location="Oregon Convention Center, 777 NE MLK Jr Blvd",
            price=18.50,
            duration=15.0 * 60,
            time_stamp=datetime(2025, 11, 18, 8, 30, 0, tzinfo=UTC).timestamp(),
            distance_km=4.2,
        )
        self.cab.add_new_ride(
            service_type="Default",
            start_location="Oregon Convention Center, 777 NE MLK Jr Blvd",
            end_location="Downtown Portland Hotel, 500 SW Broadway",
            price=19.25,
            duration=18.0 * 60,
            time_stamp=datetime(2025, 11, 18, 18, 15, 0, tzinfo=UTC).timestamp(),
            distance_km=4.5,
        )

        # Day 2 (Nov 19)
        self.cab.add_new_ride(
            service_type="Default",
            start_location="Downtown Portland Hotel, 500 SW Broadway",
            end_location="Oregon Convention Center, 777 NE MLK Jr Blvd",
            price=17.75,
            duration=14.0 * 60,
            time_stamp=datetime(2025, 11, 19, 8, 45, 0, tzinfo=UTC).timestamp(),
            distance_km=4.1,
        )
        self.cab.add_new_ride(
            service_type="Default",
            start_location="Oregon Convention Center, 777 NE MLK Jr Blvd",
            end_location="Downtown Portland Hotel, 500 SW Broadway",
            price=20.00,
            duration=20.0 * 60,
            time_stamp=datetime(2025, 11, 19, 17, 30, 0, tzinfo=UTC).timestamp(),
            distance_km=4.8,
        )

        # Day 3 (Nov 20)
        self.cab.add_new_ride(
            service_type="Default",
            start_location="Downtown Portland Hotel, 500 SW Broadway",
            end_location="Oregon Convention Center, 777 NE MLK Jr Blvd",
            price=18.50,
            duration=16.0 * 60,
            time_stamp=datetime(2025, 11, 20, 9, 0, 0, tzinfo=UTC).timestamp(),
            distance_km=4.3,
        )
        self.cab.add_new_ride(
            service_type="Default",
            start_location="Oregon Convention Center, 777 NE MLK Jr Blvd",
            end_location="Downtown Portland Hotel, 500 SW Broadway",
            price=19.00,
            duration=17.0 * 60,
            time_stamp=datetime(2025, 11, 20, 16, 45, 0, tzinfo=UTC).timestamp(),
            distance_km=4.4,
        )

        # Personal rides (NOT reimbursable)
        self.cab.add_new_ride(
            service_type="Default",
            start_location="Downtown Portland Hotel, 500 SW Broadway",
            end_location="Jake's Famous Crawfish Restaurant, 401 SW 12th Ave",
            price=12.50,
            duration=8.0 * 60,
            time_stamp=datetime(2025, 11, 18, 19, 30, 0, tzinfo=UTC).timestamp(),
            distance_km=1.8,
        )
        self.cab.add_new_ride(
            service_type="Default",
            start_location="Jake's Famous Crawfish Restaurant, 401 SW 12th Ave",
            end_location="Downtown Portland Hotel, 500 SW Broadway",
            price=13.25,
            duration=10.0 * 60,
            time_stamp=datetime(2025, 11, 18, 21, 45, 0, tzinfo=UTC).timestamp(),
            distance_km=2.0,
        )
        self.cab.add_new_ride(
            service_type="Default",
            start_location="Downtown Portland Hotel, 500 SW Broadway",
            end_location="Powell's City of Books, 1005 W Burnside St",
            price=14.75,
            duration=12.0 * 60,
            time_stamp=datetime(2025, 11, 19, 19, 0, 0, tzinfo=UTC).timestamp(),
            distance_km=2.5,
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.cab]

    def build_events_flow(self) -> None:
        """Build event flow - finance email triggers expense reporting."""
        aui = self.get_typed_app(PASAgentUserInterface)
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # ENV Event: Finance email requesting expense report
            finance_email_event = email_app.send_email_to_user_with_id(
                email_id="finance-expense-request",
                sender="finance@company.com",
                subject="Expense Report Required - Portland Business Trip",
                content="""Hi,

Please submit your transportation expense report for the Portland Tech Conference (Nov 18-20).

IMPORTANT: Only cab rides between the Downtown Portland Hotel and Oregon Convention Center
are eligible for reimbursement. Personal trips are not covered.

Please provide:
- List of eligible rides with dates and amounts
- Total reimbursable amount

Reply to this email with the details.

Thanks,
Finance Department""",
            ).delayed(10)

            # Oracle: Agent gets ride history
            get_rides_event = (
                cab_app.get_ride_history(offset=0, limit=20).oracle().depends_on(finance_email_event, delay_seconds=3)
            )

            # Oracle: Agent proposes to reply with expense details
            proposal_event = (
                aui.send_message_to_user(
                    content="I received an expense report request from Finance for your Portland trip. I've reviewed your cab history and identified 6 business rides between the hotel and convention center totaling $113.00. There are also 3 personal rides that are not eligible for reimbursement. Would you like me to reply to Finance with the expense details?"
                )
                .oracle()
                .depends_on(get_rides_event, delay_seconds=2)
            )

            # Oracle: User accepts
            acceptance_event = (
                aui.accept_proposal(content="Yes, please send the expense report to Finance.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle: Agent replies to finance email with expense details
            reply_event = (
                email_app.reply_to_email(
                    email_id="finance-expense-request",
                    folder_name="INBOX",
                    content="""Hi,

Here are my transportation expenses for the Portland Tech Conference (Nov 18-20):

Eligible Rides (Hotel ↔ Convention Center):
1. Nov 18 - Hotel to Convention Center: $18.50
2. Nov 18 - Convention Center to Hotel: $19.25
3. Nov 19 - Hotel to Convention Center: $17.75
4. Nov 19 - Convention Center to Hotel: $20.00
5. Nov 20 - Hotel to Convention Center: $18.50
6. Nov 20 - Convention Center to Hotel: $19.00

Total Reimbursable Amount: $113.00

Please let me know if you need any additional information.

Best regards""",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

        self.events = [
            finance_email_event,
            get_rides_event,
            proposal_event,
            acceptance_event,
            reply_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent correctly calculates and reports business expenses."""
        try:
            log_entries = env.event_log.list_view()

            # Essential outcome 1: Agent sent proposal to user
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Essential outcome 2: Agent replied to finance email
            reply_found = False
            reply_content = ""
            for e in log_entries:
                if (
                    e.event_type == EventType.AGENT
                    and isinstance(e.action, Action)
                    and e.action.class_name == "StatefulEmailApp"
                    and e.action.function_name == "reply_to_email"
                    and e.action.args.get("email_id") == "finance-expense-request"
                ):
                    reply_found = True
                    reply_content = e.action.args.get("content", "")
                    break

            # Essential outcome 3: Reply contains correct total amount ($113.00)
            correct_total = False
            if reply_content:
                # Check for correct total (allowing for format variations like $113, $113.00, 113.00)
                correct_total = "113.00" in reply_content or "113.0" in reply_content or "$113" in reply_content

            # Essential outcome 4: Reply mentions hotel and convention center
            mentions_locations = False
            if reply_content:
                content_lower = reply_content.lower()
                mentions_locations = ("hotel" in content_lower or "broadway" in content_lower) and (
                    "convention" in content_lower or "mlk" in content_lower
                )

            success = proposal_found and reply_found and correct_total and mentions_locations

            if not success:
                missing = self._build_validation_issues(proposal_found, reply_found, correct_total, mentions_locations)
                return ScenarioValidationResult(success=False, rationale=f"Missing: {', '.join(missing)}")

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)

    def _build_validation_issues(
        self, proposal_found: bool, reply_found: bool, correct_total: bool, mentions_locations: bool
    ) -> list[str]:
        """Build list of validation issues for failure reporting."""
        missing: list[str] = []
        if not proposal_found:
            missing.append("proposal to user")
        if not reply_found:
            missing.append("reply to finance email")
        if not correct_total:
            missing.append("correct total amount ($113.00)")
        if not mentions_locations:
            missing.append("mention of hotel/convention center locations")
        return missing
