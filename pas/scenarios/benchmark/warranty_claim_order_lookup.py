"""Scenario: Agent retrieves order details to help user respond to warranty claim email."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import HomeScreenSystemApp, PASAgentUserInterface, StatefulEmailApp, StatefulShoppingApp
from pas.apps.reminder import StatefulReminderApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("warranty_claim_order_lookup")
class WarrantyClaimOrderLookup(PASScenario):
    """Agent retrieves order details to help user respond to a warranty claim email.

    The user receives a warranty claim email from tech support asking for their order ID,
    defect description, and preferred delivery timeframe. The email mentions a 7-day
    turnaround time. The user has a past order for Wireless Headphones Pro. The agent
    locates the order, proposes to reply with the details, and proactively sets up a
    reminder to follow up on the claim status based on the turnaround time.

    This scenario tests:
    - Email-triggered information retrieval
    - Order history lookup and correlation
    - Structured email response composition
    - Proactive reminder creation based on inferred timing
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    additional_system_prompt = """You purchased Wireless Headphones Pro about 6 weeks ago and recently contacted
tech support about a defect (the left speaker has intermittent crackling noise). They've replied asking for your order details.

BEFORE the warranty email arrives:
- Check your email inbox or shopping orders

AFTER the warranty email arrives:

ACCEPT proposals that:
- Offer to look up your order details for the headphones
- Offer to reply to the warranty email with the required information
- Offer to set a reminder to follow up on the claim (based on the 7-day turnaround)

REJECT proposals that:
- Reply without finding the actual order details first"""

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize shopping app with product and past order
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Add product and item using proper API
        product_id = self.shopping.add_product(name="Wireless Headphones Pro")
        self.item_id = self.shopping.add_item_to_product(
            product_id=product_id,
            price=129.99,
            options={"color": "black", "warranty": "1 year"},
            available=True,
        )

        # Add past order (purchased 45 days ago)
        past_order_date = datetime(2025, 10, 4, 14, 30, 0, tzinfo=UTC)
        self.shopping.add_order(
            order_id="order_hdphn_20251004",
            order_status="delivered",
            order_date=past_order_date.timestamp(),
            order_total=129.99,
            item_id=self.item_id,
            quantity=1,
        )

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails")

        # Initialize reminder app
        self.reminder = StatefulReminderApp(name="Reminders")

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.shopping, self.email, self.reminder]

    def build_events_flow(self) -> None:
        """Build event flow - warranty email triggers order lookup and reply."""
        aui = self.get_typed_app(PASAgentUserInterface)
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")

        with EventRegisterer.capture_mode():
            # ENV Event: Warranty claim email arrives
            warranty_email_event = email_app.send_email_to_user_with_id(
                email_id="warranty_claim_email",
                sender="TechSupport@electromart.com",
                subject="Re: Your warranty claim inquiry - Action Required",
                content="""We received your warranty inquiry about the defective Wireless Headphones Pro you mentioned.

To process your claim, please reply with:
1. Your original order ID or purchase date
2. Description of the defect
3. Preferred replacement delivery timeframe

Claims must be filed within 90 days of purchase. Once we receive the required details, the typical turnaround time for processing is around 7 days.

Best regards,
ElectroMart Support Team""",
            ).delayed(5)

            # Oracle: Agent lists orders to find the headphones purchase
            list_orders_event = shopping_app.list_orders().oracle().depends_on(warranty_email_event, delay_seconds=3)

            # Oracle: Agent proposes to reply with order details
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "I found your Wireless Headphones Pro order (ID: order_hdphn_20251004, "
                        "purchased Oct 4, 2025) from the warranty email. The support team needs "
                        "your order details, defect description, and delivery preference. "
                        "They mentioned a 7-day turnaround. Would you like me to reply with "
                        "the order info and set a reminder to follow up in a week?"
                    )
                )
                .oracle()
                .depends_on(list_orders_event, delay_seconds=2)
            )

            # Oracle: User accepts and provides defect details
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes please. The defect is left speaker crackling. I'd prefer 2-day shipping."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle: Agent replies to warranty email
            reply_event = (
                email_app.reply_to_email(
                    email_id="warranty_claim_email",
                    folder_name="INBOX",
                    content="""Thank you for following up on my warranty claim.

Here is the requested information:
1. Order ID: order_hdphn_20251004, Purchase Date: October 4, 2025
2. Defect: Left speaker has intermittent crackling noise
3. Delivery Preference: 2-day shipping

Please let me know if you need anything else.

Best regards""",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle: Agent creates follow-up reminder based on 7-day turnaround
            add_reminder_event = (
                reminder_app.add_reminder(
                    title="Follow up on headphones warranty claim",
                    due_datetime="2025-11-25 09:00:00",
                    description="Check status of warranty claim for Wireless Headphones Pro (order_hdphn_20251004)",
                )
                .oracle()
                .depends_on(reply_event, delay_seconds=2)
            )

        self.events = [
            warranty_email_event,
            list_orders_event,
            proposal_event,
            acceptance_event,
            reply_event,
            add_reminder_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent replies to warranty email and creates reminder."""
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

            # Essential outcome 2: Agent replied to warranty email with order info
            reply_found = False
            for e in log_entries:
                if (
                    e.event_type == EventType.AGENT
                    and isinstance(e.action, Action)
                    and e.action.class_name == "StatefulEmailApp"
                    and e.action.function_name == "reply_to_email"
                    and e.action.args.get("email_id") == "warranty_claim_email"
                ):
                    content = e.action.args.get("content", "").lower()
                    # Check that reply contains order ID
                    if "order_hdphn_20251004" in content or "october 4" in content or "oct 4" in content:
                        reply_found = True
                        break

            # Essential outcome 3: Agent created follow-up reminder
            reminder_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulReminderApp"
                and e.action.function_name == "add_reminder"
                for e in log_entries
            )

            success = proposal_found and reply_found and reminder_found

            if not success:
                missing = []
                if not proposal_found:
                    missing.append("proposal to user")
                if not reply_found:
                    missing.append("reply to warranty email with order details")
                if not reminder_found:
                    missing.append("follow-up reminder")
                rationale = f"Missing: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
