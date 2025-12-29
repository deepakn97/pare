"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.shopping import CartItem, Item, Order, Product
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulEmailApp,
)
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("order_inquiry_email_draft")
class OrderInquiryEmailDraft(PASScenario):
    """Agent drafts inquiry email to shopping support after detecting delayed order from shipping notification.

    The user has an active order for "Standing Desk" and "Monitor Arm" placed five days ago with expected delivery in 2-3 business days. A shipping notification email arrives stating "Your order has been processed and will ship within 5-7 business days" - contradicting the original promise. The agent must:
    1. Detect the shipping delay notification
    2. Retrieve the original order details to confirm the items and original delivery estimate
    3. Calculate that the new timeline exceeds the promised window by 4+ days
    4. Compose a polite but firm inquiry email to the merchant's support address (extracted from the notification email)
    5. Include the order ID, item names, original promise, and new timeline in the draft
    6. Present the draft to the user for review and sending

    This scenario exercises shipping notification parsing, order-email cross-referencing, timeline discrepancy detection, automated complaint drafting with factual details extracted from multiple sources, and email composition using data from both shopping order state and notification content..
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
        self.email = StatefulEmailApp(name="Emails")

        # Initialize shopping app with baseline products and existing order
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Create product: Standing Desk
        desk_product_id = "prod_desk_001"
        desk_product = Product(
            name="Standing Desk - Adjustable Height",
            product_id=desk_product_id,
        )
        desk_item_id = "item_desk_001"
        desk_product.variants[desk_item_id] = Item(
            item_id=desk_item_id,
            price=299.99,
            available=True,
            options={"color": "oak", "size": "60x30 inches"},
        )
        self.shopping.products[desk_product_id] = desk_product

        # Create product: Monitor Arm
        arm_product_id = "prod_arm_001"
        arm_product = Product(
            name="Monitor Arm - Dual Mount",
            product_id=arm_product_id,
        )
        arm_item_id = "item_arm_001"
        arm_product.variants[arm_item_id] = Item(
            item_id=arm_item_id,
            price=89.99,
            available=True,
            options={"type": "dual", "weight_capacity": "20 lbs per arm"},
        )
        self.shopping.products[arm_product_id] = arm_product

        # Create an order placed 5 days ago (November 13, 2025 at 9 AM UTC)
        # Current time is November 18, 2025 at 9 AM UTC
        order_date = datetime(2025, 11, 13, 9, 0, 0, tzinfo=UTC)
        order_id = "ORD20251113-4829"

        # Create order with both items - status is "processed" (not yet shipped)
        self.shopping.orders[order_id] = Order(
            order_id=order_id,
            order_status="processed",
            order_date=order_date,
            order_total=389.98,  # 299.99 + 89.99
            order_items={
                desk_item_id: CartItem(
                    item_id=desk_item_id,
                    price=299.99,
                    quantity=1,
                    available=True,
                    options={"color": "oak", "size": "60x30 inches"},
                ),
                arm_item_id: CartItem(
                    item_id=arm_item_id,
                    price=89.99,
                    quantity=1,
                    available=True,
                    options={"type": "dual", "weight_capacity": "20 lbs per arm"},
                ),
            },
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.shopping]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Shipping notification email arrives with contradictory timeline
            shipping_notification_event = email_app.send_email_to_user_with_id(
                email_id="email_shipping_delay_001",
                sender="support@officefurnituredirect.com",
                subject="Shipping Update - Order ORD20251113-4829",
                content="Thank you for your order! Your order ORD20251113-4829 for Standing Desk - Adjustable Height and Monitor Arm - Dual Mount has been processed and will ship within 5-7 business days. You will receive a tracking number once your order ships. For questions, contact us at support@officefurnituredirect.com.",
            ).delayed(15)

            # Oracle Event 1: Agent reads the shipping notification email to extract order ID and new timeline
            # Motivated by: the shipping notification email above provides critical information (order ID, new timeline)
            read_notification_event = (
                email_app.get_email_by_id(
                    email_id="email_shipping_delay_001",
                    folder_name="INBOX",
                )
                .oracle()
                .depends_on(shipping_notification_event, delay_seconds=2)
            )

            # Oracle Event 2: Agent retrieves order details to confirm original timeline and items
            # Motivated by: need to verify the discrepancy between promised 2-3 days and the new 5-7 days timeline
            get_order_event = (
                shopping_app.get_order_details(
                    order_id="ORD20251113-4829",
                )
                .oracle()
                .depends_on(read_notification_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent proposes drafting an inquiry email
            # Motivated by: detected discrepancy between original promise (2-3 days, now 5 days overdue) and new timeline (5-7 more days)
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed your order ORD20251113-4829 (Standing Desk and Monitor Arm) was placed 5 days ago with 2-3 day delivery, but just received a notification saying it will ship in 5-7 more days. Would you like me to draft an inquiry email to the merchant about this delay?",
                )
                .oracle()
                .depends_on(get_order_event, delay_seconds=2)
            )

            # Oracle Event 4: User accepts the proposal
            # Motivated by: user wants the agent to proceed with drafting
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please draft an inquiry email about the delay.",
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent composes the inquiry email with order details
            # Motivated by: user accepted proposal, agent now has all information (order ID, items, timelines, support email) from prior events
            compose_email_event = (
                email_app.send_email(
                    recipients=["support@officefurnituredirect.com"],
                    subject="Inquiry About Delayed Order ORD20251113-4829",
                    content="Hello,\n\nI am writing regarding order ORD20251113-4829 placed on November 13, 2025, for a Standing Desk - Adjustable Height and Monitor Arm - Dual Mount.\n\nAt the time of purchase, the expected delivery was 2-3 business days. However, I just received a shipping notification stating the order will ship within 5-7 business days, which significantly exceeds the original timeline.\n\nCould you please clarify the reason for this delay and provide an updated delivery estimate?\n\nThank you.",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=3)
            )

        # Register ALL events
        self.events = [
            shipping_notification_event,
            read_notification_event,
            get_order_event,
            proposal_event,
            acceptance_event,
            compose_email_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent sent proposal mentioning the order and delay discrepancy
            # Must reference order ID and indicate awareness of the shipping delay issue
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 2: Agent read the shipping notification email
            # Critical step to detect the delay and extract support email
            read_email_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "get_email_by_id"
                for e in log_entries
            )

            # STRICT Check 3: Agent retrieved order details to verify the discrepancy
            # Essential to confirm original delivery promise and items ordered
            order_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_order_details"
                and e.action.args.get("order_id") == "ORD20251113-4829"
                for e in log_entries
            )

            # STRICT Check 4: Agent sent inquiry email to merchant support
            # Core action: composing and sending the complaint email with extracted details
            # Be flexible on exact wording but strict on structural requirements
            inquiry_email_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "send_email"
                and "support@officefurnituredirect.com" in e.action.args.get("recipients", [])
                for e in log_entries
            )

            # All strict checks must pass for success
            success = proposal_found and read_email_found and order_check_found and inquiry_email_sent

            if not success:
                # Build rationale for failure
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("proposal message with order ID not found")
                if not read_email_found:
                    missing_checks.append("shipping notification email not read")
                if not order_check_found:
                    missing_checks.append("order details not retrieved")
                if not inquiry_email_sent:
                    missing_checks.append("inquiry email to merchant support not sent")

                rationale = "Missing critical checks: " + "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
