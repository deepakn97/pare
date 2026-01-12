"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.shopping import CartItem, Item, Order, Product
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import HomeScreenSystemApp, PASAgentUserInterface, StatefulEmailApp, StatefulShoppingApp
from pas.apps.reminder import StatefulReminderApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("warranty_claim_order_lookup")
class WarrantyClaimOrderLookup(PASScenario):
    """Agent processes a warranty claim request email by retrieving order details and coordinating reminder-based follow-up tracking.

    The user receives an email from TechSupport@electromart.com with subject "Re: Your warranty claim inquiry - Action Required" stating: "We received your warranty inquiry about the defective Wireless Headphones Pro you mentioned. To process your claim, please reply with: (1) your original order ID or purchase date, (2) description of the defect (e.g., left speaker crackling), and (3) preferred replacement delivery timeframe. Claims must be filed within 90 days of purchase." The agent must:
    1. Parse the warranty claim email identifying the required information fields (order ID/date, defect description, delivery preference) and the product name (Wireless Headphones Pro)
    2. Search past orders using `search_product()` and `list_orders()` to locate the Wireless Headphones Pro purchase
    3. Retrieve complete order details via `get_order_details()` to extract the order ID and purchase date
    4. Propose replying to the warranty email with the retrieved order information, including a user-specified defect description (e.g., "Left speaker has intermittent crackling noise") and delivery preference (e.g., "2-day shipping preferred")
    5. After user acceptance, send the warranty claim response via `reply_to_email()` with all required details
    6. Create a follow-up reminder via `add_reminder()` titled "Check warranty claim status for Wireless Headphones Pro" due 7 days from now with description including the order ID and claim submission date
    7. Search emails via `search_emails()` to verify the warranty response was sent successfully

    This scenario exercises email-driven information retrieval workflows, historical order lookup and correlation with support requests, structured email response composition with user-specified details, reminder creation for follow-up tracking, and post-action email verification.

    ---.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize shopping app and populate with product catalog and past order
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Add Wireless Headphones Pro product to catalog
        headphones_product = Product(name="Wireless Headphones Pro", product_id="prod_headphones_001")
        headphones_item = Item(
            item_id="item_headphones_black",
            price=129.99,
            available=True,
            options={"color": "black", "warranty": "1 year"},
        )
        headphones_product.variants["item_headphones_black"] = headphones_item
        self.shopping.products["prod_headphones_001"] = headphones_product

        # Add a past order for the Wireless Headphones Pro (purchased 45 days ago)
        past_order_date = datetime(2025, 10, 4, 14, 30, 0, tzinfo=UTC)
        past_order = Order(
            order_id="order_hdphn_20251004",
            order_status="delivered",
            order_date=past_order_date,
            order_total=129.99,
            order_items={
                "item_headphones_black": CartItem(
                    item_id="item_headphones_black",
                    quantity=1,
                    price=129.99,
                    available=True,
                    options={"color": "black", "warranty": "1 year"},
                )
            },
        )
        self.shopping.orders["order_hdphn_20251004"] = past_order

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails")

        # Initialize reminder app (no baseline reminders needed)
        self.reminder = StatefulReminderApp(name="Reminders")

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.shopping, self.email, self.reminder]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")

        with EventRegisterer.capture_mode():
            # Environment event: warranty claim email arrives requesting specific information (order ID/date, defect description, delivery preference)
            warranty_email_event = email_app.send_email_to_user_with_id(
                email_id="warranty_claim_email_001",
                sender="TechSupport@electromart.com",
                subject="Re: Your warranty claim inquiry - Action Required",
                content="We received your warranty inquiry about the defective Wireless Headphones Pro you mentioned. To process your claim, please reply with: (1) your original order ID or purchase date, (2) description of the defect (e.g., left speaker crackling), and (3) preferred replacement delivery timeframe. Claims must be filed within 90 days of purchase. It's always good to setup a reminder to check the status of the claim after 7 days from your submission.",
            )

            # Motivation: Warranty email (warranty_email_event) mentions "Wireless Headphones Pro" and requests order information
            # Agent reads the warranty email to understand what is being requested
            read_warranty_email_event = (
                email_app.get_email_by_id(email_id="warranty_claim_email_001", folder_name="INBOX")
                .oracle()
                .depends_on(warranty_email_event, delay_seconds=2)
            )

            # Agent lists all orders to locate the Wireless Headphones Pro purchase
            list_orders_event = (
                shopping_app.list_orders().oracle().depends_on(read_warranty_email_event, delay_seconds=1)
            )

            # Motivation: list_orders_event output should contain order_hdphn_20251004; need full details (order date) per warranty email requirement "(1) order ID or purchase date"
            # Agent retrieves complete order details for the Wireless Headphones Pro order
            get_order_details_event = (
                shopping_app.get_order_details(order_id="order_hdphn_20251004")
                .oracle()
                .depends_on(list_orders_event, delay_seconds=1)
            )

            # Motivation: Warranty email (warranty_email_event content: "please reply with...") requests specific fields; get_order_details_event provides order ID + date
            # Agent proposes replying to warranty email with retrieved order information, asking user for defect description and delivery preference
            proposal_event = (
                aui.send_message_to_user(
                    content="I found your Wireless Headphones Pro order from the warranty claim email. The email from TechSupport@electromart.com requests: (1) order ID/date, (2) defect description, and (3) delivery preference. I found your order (ID: order_hdphn_20251004, purchased Oct 4, 2025). Would you like me to reply with this information and set up a reminder to check the status of the claim after 7 days from your submission? Please provide the defect description and your preferred delivery timeframe."
                )
                .oracle()
                .depends_on([warranty_email_event, get_order_details_event], delay_seconds=2)
            )

            # User accepts proposal and provides defect description and delivery preference
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please reply and set up a reminder. Defect: Left speaker has intermittent crackling noise. Delivery: 2-day shipping preferred."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Motivation: acceptance_event content provides user-specified "Left speaker has intermittent crackling noise" and "2-day shipping preferred"; warranty_email_event requires reply with order info + these details
            # Agent replies to warranty email with order details and user-provided defect description and delivery preference
            reply_email_event = (
                email_app.reply_to_email(
                    email_id="warranty_claim_email_001",
                    folder_name="INBOX",
                    content="Thank you for your warranty inquiry. Here is the requested information:\n\n(1) Order ID: order_hdphn_20251004, Purchase Date: October 4, 2025\n(2) Defect Description: Left speaker has intermittent crackling noise\n(3) Preferred Delivery Timeframe: 2-day shipping preferred\n\nPlease let me know if you need any additional information.",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Motivation: reply_email_event completed warranty response; need follow-up tracking per scenario requirement "Create a follow-up reminder...due 7 days from now"
            # Agent creates reminder to check warranty claim status in 7 days
            reminder_due = datetime(2025, 11, 25, 9, 0, 0, tzinfo=UTC)
            add_reminder_event = (
                reminder_app.add_reminder(
                    title="Check warranty claim status for Wireless Headphones Pro",
                    due_datetime=reminder_due.strftime("%Y-%m-%d %H:%M:%S"),
                    description="Follow up on warranty claim for order order_hdphn_20251004 submitted on November 18, 2025 to TechSupport@electromart.com regarding left speaker crackling defect.",
                )
                .oracle()
                .depends_on(reply_email_event, delay_seconds=2)
            )

        # Register ALL events here in self.events
        self.events = [
            warranty_email_event,
            read_warranty_email_event,
            list_orders_event,
            get_order_details_event,
            proposal_event,
            acceptance_event,
            reply_email_event,
            add_reminder_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT events (oracle events)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent read the warranty email
            read_email_found = any(
                e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "get_email_by_id"
                and e.action.args.get("email_id") == "warranty_claim_email_001"
                for e in agent_events
            )

            # STRICT Check 2: Agent searched for product or listed orders (equivalence class - both are valid ways to find orders)
            search_orders_found = any(
                (e.action.class_name == "StatefulShoppingApp" and e.action.function_name == "list_orders")
                for e in agent_events
            )

            # STRICT Check 3: Agent retrieved order details
            get_order_details_found = any(
                e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_order_details"
                and e.action.args.get("order_id") == "order_hdphn_20251004"
                for e in agent_events
            )

            # STRICT Check 4: Agent sent proposal to user (content flexible, just check the tool was called)
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 5: Agent replied to warranty email (content flexible, just verify the reply action)
            reply_email_found = any(
                e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == "warranty_claim_email_001"
                for e in agent_events
            )

            # STRICT Check 6: Agent created a follow-up reminder (title/description content flexible, verify action happened)
            add_reminder_found = any(
                e.action.class_name == "StatefulReminderApp"
                and e.action.function_name == "add_reminder"
                and e.action.args.get("title") is not None
                and len(e.action.args.get("title", "")) > 0
                for e in agent_events
            )

            # Combine all strict checks
            all_checks_passed = (
                read_email_found
                and search_orders_found
                and get_order_details_found
                and proposal_found
                and reply_email_found
                and add_reminder_found
            )

            # Build rationale if validation fails
            if not all_checks_passed:
                failed_checks = []
                if not read_email_found:
                    failed_checks.append("agent did not read warranty email")
                if not search_orders_found:
                    failed_checks.append("agent did not search for product/orders")
                if not get_order_details_found:
                    failed_checks.append("agent did not retrieve order details for order_hdphn_20251004")
                if not proposal_found:
                    failed_checks.append("agent did not send proposal to user")
                if not reply_email_found:
                    failed_checks.append("agent did not reply to warranty email")
                if not add_reminder_found:
                    failed_checks.append("agent did not create follow-up reminder")

                rationale = "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
