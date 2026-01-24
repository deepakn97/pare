from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import HomeScreenSystemApp, PASAgentUserInterface, StatefulCabApp, StatefulEmailApp
from pas.apps.reminder import StatefulReminderApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("cab_issue_followup_with_details")
class CabIssueFollowupWithDetails(PASScenario):
    """Agent handles a cab company follow-up request by retrieving ride history and creating a reminder.

    The user receives an email from Urban Rides Support (support@urbanrides.com) stating: "We received your feedback about ride quality issues on your recent trip from Downtown Office to Airport Terminal on December 15th around 3:00 PM. To process your refund request, please reply with: (1) the exact pickup time, (2) driver's service type, and (3) final fare amount. We will process refunds within 48 hours of receiving complete information."

    The agent must: 1. Parse the ride description (route and approximate time) from the email. 2. Search ride history using get_ride_history to find rides around December 15th 3:00 PM. 3. Identify the matching ride from Downtown Office to Airport Terminal. 4. Extract the required details (exact pickup time, service type, fare) using get_ride. 5. Reply to the support email with the three requested pieces of information formatted clearly. 6. Create a reminder for 48 hours later to check if the refund was processed.

    This scenario exercises ride history search and retrieval without hardcoded ride IDs, cross-app information synthesis from cab data into email responses, parsing structured information requests from external parties, and temporal reminder coordination tied to external service-level agreements.

    ---.
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
        self.reminder = StatefulReminderApp(name="Reminders")

        # Populate apps with baseline data
        # Email: User's email address
        self.email.user_email = "user@example.com"

        # Cab: Seed ride history with the problematic ride from December 15th
        # December 15th, 2025 at 3:00 PM UTC corresponds to timestamp
        ride_timestamp = datetime(2025, 12, 15, 15, 0, 0, tzinfo=UTC).timestamp()

        # Add the ride that matches the email description
        self.cab.add_new_ride(
            service_type="Premium",
            start_location="Downtown Office",
            end_location="Airport Terminal",
            price=45.50,
            duration=35.0,
            time_stamp=ride_timestamp,
            distance_km=18.5,
        )

        # Add a couple of other rides to make history more realistic
        # Earlier ride on December 10th
        earlier_ride_timestamp = datetime(2025, 12, 10, 8, 30, 0, tzinfo=UTC).timestamp()
        self.cab.add_new_ride(
            service_type="Default",
            start_location="Home",
            end_location="Downtown Office",
            price=22.00,
            duration=25.0,
            time_stamp=earlier_ride_timestamp,
            distance_km=12.0,
        )

        # Later ride on December 18th
        later_ride_timestamp = datetime(2025, 12, 18, 17, 45, 0, tzinfo=UTC).timestamp()
        self.cab.add_new_ride(
            service_type="Default",
            start_location="Shopping Mall",
            end_location="Home",
            price=18.50,
            duration=20.0,
            time_stamp=later_ride_timestamp,
            distance_km=10.5,
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.cab, self.reminder]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")

        with EventRegisterer.capture_mode():
            # Environment event: Cab company sends refund request email
            email_id = "refund_request_001"
            env_email = email_app.send_email_to_user_with_id(
                email_id=email_id,
                sender="support@urbanrides.com",
                subject="Refund Request - Additional Information Required",
                content="""Dear valued customer,

We received your feedback about ride quality issues on your recent trip from Downtown Office to Airport Terminal on December 15th around 3:00 PM.

To process your refund request, please reply with the following information:
1. The exact pickup time
2. Driver's service type (Default, Premium, or Van)
3. Final fare amount

We will process refunds within 48 hours of receiving complete information. You can create a reminder to check the refund status in 48 hours.

Best regards,
Urban Rides Support Team""",
            )

            # Agent observes email and retrieves ride history to find matching ride
            # Motivation: email explicitly requests ride details for Dec 15 ~3PM from Downtown Office to Airport Terminal
            get_history = cab_app.get_ride_history(offset=0, limit=10).oracle().depends_on(env_email, delay_seconds=2)

            # Agent identifies the matching ride from history and retrieves detailed info
            # Motivation: history revealed rides; need specific ride details to extract exact pickup time, service type, and fare
            get_ride_details = cab_app.get_ride(idx=2).oracle().depends_on(get_history, delay_seconds=1)

            # Agent proposes to reply with the requested information
            # Motivation: email from support@urbanrides.com explicitly requested ride details for refund processing
            proposal = (
                aui.send_message_to_user(
                    content="""I noticed you received a refund request from Urban Rides Support asking for details about your December 15th ride from Downtown Office to Airport Terminal.

I found the ride in your history and can reply with the requested information:
- Exact pickup time: December 15, 2025 at 15:00 (3:00 PM UTC)
- Service type: Premium
- Final fare: $45.50

Would you like me to send this information to Urban Rides Support? And also create a reminder to check the refund status in 48 hours."""
                )
                .oracle()
                .depends_on([env_email, get_ride_details], delay_seconds=3)
            )

            # User accepts the proposal
            acceptance = (
                aui.accept_proposal(content="Yes, please do that.").oracle().depends_on(proposal, delay_seconds=2)
            )

            # Agent replies to the email with the requested details
            # Motivation: user accepted proposal; ride details extracted from get_ride(idx=2) showing Premium service at $45.50 on Dec 15 at 15:00
            reply_email = (
                email_app.reply_to_email(
                    email_id=email_id,
                    folder_name="INBOX",
                    content="""Hello,

Thank you for reaching out regarding my refund request. Here is the requested information for my ride on December 15th:

1. Exact pickup time: December 15, 2025 at 15:00 UTC (3:00 PM)
2. Driver's service type: Premium
3. Final fare amount: $45.50

Please let me know if you need any additional information.

Best regards""",
                )
                .oracle()
                .depends_on(acceptance, delay_seconds=2)
            )

            # Agent creates reminder to check refund status in 48 hours
            # Motivation: email stated "We will process refunds within 48 hours"; need follow-up reminder
            from datetime import UTC, datetime, timedelta

            reminder_time = datetime.fromtimestamp(self.start_time, tz=UTC) + timedelta(hours=48)
            reminder_time_str = reminder_time.strftime("%Y-%m-%d %H:%M:%S")

            add_reminder = (
                reminder_app.add_reminder(
                    title="Check Urban Rides refund status",
                    due_datetime=reminder_time_str,
                    description="Follow up on the refund request for the December 15th Premium ride ($45.50). Urban Rides Support should have processed it within 48 hours.",
                )
                .oracle()
                .depends_on(reply_email, delay_seconds=3)
            )

            # Agent confirms completion to user
            # Motivation: all requested actions completed (email reply sent, reminder created); user should be notified
            confirmation = (
                aui.send_message_to_user(
                    content="""Done! I've replied to Urban Rides Support with the ride details and created a reminder for 48 hours from now to check on your refund status."""
                )
                .oracle()
                .depends_on(add_reminder, delay_seconds=2)
            )

        # Register ALL events here in self.events
        self.events = [
            env_email,
            get_history,
            get_ride_details,
            proposal,
            acceptance,
            reply_email,
            add_reminder,
            confirmation,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent sent proposal mentioning the refund request and key ride details
            # The proposal should reference Urban Rides Support and the December 15th ride
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 2: Agent replied to the refund request email
            # The reply should be to the correct email_id and contain ride details
            # Content validation is FLEXIBLE (wording may vary), but structural data must be present
            email_reply_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == "refund_request_001"
                # Check that reply contains the required information types (flexible exact wording)
                and any(keyword in e.action.args.get("content", "") for keyword in ["Premium", "premium"])
                and "45.50" in e.action.args.get("content", "")
                for e in log_entries
            )

            # STRICT Check 3: Agent created a reminder for the 48-hour follow-up
            # Title/description wording is FLEXIBLE, but the reminder must reference refund and timing
            reminder_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulReminderApp"
                and e.action.function_name == "add_reminder"
                # Verify due_datetime is present and non-empty (exact time may vary slightly)
                and e.action.args.get("due_datetime") is not None
                and len(e.action.args.get("due_datetime", "")) > 0
                for e in log_entries
            )

            # Calculate success: all strict checks must pass
            success = proposal_found and email_reply_sent and reminder_created

            if not success:
                # Build rationale for failure
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal mentioning refund request")
                if not email_reply_sent:
                    missing_checks.append("email reply with ride details to Urban Rides Support")
                if not reminder_created:
                    missing_checks.append("48-hour refund follow-up reminder")

                rationale = "Missing critical checks: " + ", ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
