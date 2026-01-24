from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.email_client import Email, EmailFolderName
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

    The user has an active order for "Standing Desk" placed five days ago with expected delivery in 2-3 business days. A shipping notification email arrives stating "Your order has been processed and will ship within 5-7 business days" - contradicting the original promise. The agent must:
    1. Detect the shipping delay notification
    2. Retrieve the original order details to confirm the items and original delivery estimate
    3. Calculate that the new timeline exceeds the promised window by 4+ days
    4. Compose a polite but firm inquiry email to the merchant's support address (extracted from the notification email)
    5. Include the order ID, item names, original promise, and new timeline in the draft
    6. Present the draft to the user for review and sending

    This scenario exercises shipping notification parsing, order-email cross-referencing, timeline discrepancy detection, automated complaint drafting with factual details extracted from multiple sources, and email composition using data from both shopping order state and notification content..
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

        # Initialize shopping app with baseline products and existing order
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Create product: Standing Desk
        desk_product_id = self.shopping.add_product("Standing Desk - Adjustable Height")
        desk_item_id = self.shopping.add_item_to_product(
            product_id=desk_product_id,
            price=299.99,
            options={"color": "oak", "size": "60x30 inches"},
            available=True,
        )

        # Create an order placed 5 days ago (November 13, 2025 at 9 AM UTC)
        # Current time is November 18, 2025 at 9 AM UTC
        order_date = datetime(2025, 11, 13, 9, 0, 0, tzinfo=UTC)
        self.order_id = "ORD20251113-4829"

        # Create order with Standing Desk - status is "processed" (not yet shipped)
        # Using add_order() method to comply with Guidelines #1 (Manual Data Setup)
        self.shopping.add_order(
            order_id=self.order_id,
            order_status="processed",
            order_date=order_date.timestamp(),
            order_total=299.99,
            item_id=desk_item_id,
            quantity=1,
        )

        # Seed: Order confirmation email sent 5 days ago (November 13, 2025 at 9:30 AM UTC)
        # This email contains the original delivery promise (2-3 business days) that the agent will need to reference.
        self.order_confirmation_email_id = "email_order_confirmation_001"
        order_confirmation_email = Email(
            email_id=self.order_confirmation_email_id,
            sender="support@officefurnituredirect.com",
            recipients=[self.email.user_email],
            subject=f"Order Confirmation - {self.order_id}",
            content=f"Thank you for your order!\n\nOrder Details:\n- Order ID: {self.order_id}\n- Items: Standing Desk - Adjustable Height\n- Order Date: November 13, 2025\n- Expected Delivery: 2-3 business days\n\nYour order is being processed and you will receive a shipping notification once it ships.\n\nFor questions, contact us at support@officefurnituredirect.com.",
            timestamp=datetime(2025, 11, 13, 9, 30, 0, tzinfo=UTC).timestamp(),
            is_read=True,
        )
        self.email.add_email(order_confirmation_email, EmailFolderName.INBOX)

        # Store shipping notification email ID for use in build_events_flow
        self.shipping_notification_email_id = "email_shipping_delay_001"

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.shopping]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Shipping notification email arrives with new delayed timeline
            # NOTE: This email only contains the new timeline (5-7 days). The agent must reference
            # the earlier order confirmation email (seeded in init_and_populate_apps) to get the
            # original promise (2-3 days) and detect the discrepancy.
            shipping_notification_event = email_app.send_email_to_user_with_id(
                email_id=self.shipping_notification_email_id,
                sender="support@officefurnituredirect.com",
                subject=f"Shipping Update - Order {self.order_id}",
                content=f"Thank you for your order! Your order {self.order_id} for Standing Desk - Adjustable Height has been processed and will ship within 5-7 business days. You will receive a tracking number once your order ships. For questions, contact us at support@officefurnituredirect.com.",
            ).delayed(15)

            # Oracle Event 1: Agent reads the shipping notification email to extract order ID and new timeline
            # Motivated by: the shipping notification email provides the new timeline (5-7 days) and order ID
            read_notification_event = (
                email_app.get_email_by_id(
                    email_id=self.shipping_notification_email_id,
                    folder_name="INBOX",
                )
                .oracle()
                .depends_on(shipping_notification_event, delay_seconds=2)
            )

            # Oracle Event 2: Agent reads the order confirmation email to get original delivery promise
            # Motivated by: need to find the original promise (2-3 days) to compare with new timeline (5-7 days)
            # The order confirmation email was sent 5 days ago and contains "Expected Delivery: 2-3 business days"
            read_confirmation_event = (
                email_app.get_email_by_id(
                    email_id=self.order_confirmation_email_id,
                    folder_name="INBOX",
                )
                .oracle()
                .depends_on(read_notification_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent retrieves order details to confirm items and order status
            # Motivated by: need to verify the order exists and get item details for the inquiry email
            get_order_event = (
                shopping_app.get_order_details(
                    order_id=self.order_id,
                )
                .oracle()
                .depends_on(read_confirmation_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent proposes drafting an inquiry email
            # Motivated by: detected discrepancy between original promise (2-3 days, now 5 days overdue) and new timeline (5-7 more days)
            proposal_event = (
                aui.send_message_to_user(
                    content=f"I noticed your order {self.order_id} (Standing Desk) was placed 5 days ago with 2-3 day delivery, but just received a notification saying it will ship in 5-7 more days. Would you like me to draft an inquiry email to the merchant about this delay?",
                )
                .oracle()
                .depends_on(get_order_event, delay_seconds=2)
            )

            # Oracle Event 5: User accepts the proposal
            # Motivated by: user wants the agent to proceed with drafting
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please draft an inquiry email about the delay.",
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent composes the inquiry email with order details
            # Motivated by: user accepted proposal, agent now has all information (order ID, items, timelines, support email) from prior events
            compose_email_event = (
                email_app.send_email(
                    recipients=["support@officefurnituredirect.com"],
                    subject=f"Inquiry About Delayed Order {self.order_id}",
                    content=f"Hello,\n\nI am writing regarding order {self.order_id} placed on November 13, 2025, for a Standing Desk - Adjustable Height.\n\nAt the time of purchase, the expected delivery was 2-3 business days. However, I just received a shipping notification stating the order will ship within 5-7 business days, which significantly exceeds the original timeline.\n\nCould you please clarify the reason for this delay and provide an updated delivery estimate?\n\nThank you.",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=3)
            )

        # Register ALL events
        self.events = [
            shipping_notification_event,
            read_notification_event,
            read_confirmation_event,
            get_order_event,
            proposal_event,
            acceptance_event,
            compose_email_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent composed/sent inquiry email to merchant support
            # Core final outcome: composing the inquiry email with extracted details
            # Accept send_email (sends immediately) or save_draft (saves to drafts for review)
            # Note: send_composed_email internally calls send_email, so checking send_email covers both cases
            # Be flexible on exact wording but strict on structural requirements
            inquiry_email_found = False
            email_content = ""
            email_subject = ""

            for e in agent_events:
                if not isinstance(e.action, Action) or e.action.class_name != "StatefulEmailApp":
                    continue

                function_name = e.action.function_name
                args = e.action.resolved_args if e.action.resolved_args else e.action.args

                # Check send_email (direct method or called from send_composed_email)
                if function_name == "send_email" or function_name == "save_draft":
                    recipients = args.get("recipients", [])
                    if "support@officefurnituredirect.com" in recipients:
                        inquiry_email_found = True
                        email_content = args.get("content", "")
                        email_subject = args.get("subject", "")
                        break

            # STRICT Check 2: Email must reference the order ID (structural requirement)
            # Be flexible on exact wording but must contain the order ID
            order_id_in_content = self.order_id in email_content or self.order_id in email_subject

            # All strict checks must pass for success
            success = inquiry_email_found and order_id_in_content

            if not success:
                missing_checks = []
                if not inquiry_email_found:
                    missing_checks.append("inquiry email to merchant support not composed/sent")
                if not order_id_in_content:
                    missing_checks.append("order ID not found in email content or subject")

                rationale = "Missing critical checks: " + "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
