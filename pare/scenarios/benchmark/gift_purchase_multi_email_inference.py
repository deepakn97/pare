from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.contacts import Contact
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulEmailApp,
)
from pare.apps.shopping import StatefulShoppingApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("gift_purchase_multi_email_inference")
class GiftPurchaseMultiEmailInference(PAREScenario):
    """Agent infers gift-buying opportunity by correlating product interest mentioned in one email with discount code offered in another email.

    The user receives an email from their partner mentioning their anniversary is next week and casually stating "I've been wanting to upgrade my old yoga mat." Two hours later, a separate promotional email arrives from a sports equipment retailer with a 25% discount code for yoga and fitness products, valid for three days. The agent must: 1. Parse both emails to extract the product interest (yoga mat) and the discount opportunity (25% off fitness products). 2. Correlate the temporal proximity (anniversary next week, discount expires in three days) and topical overlap (yoga mat + yoga products discount). 3. Search the shopping catalog for yoga mats that qualify for the discount code. 4. Select an appropriate product and add it to cart. 5. Apply the discount code from the promotional email. 6. Propose completing the purchase as an anniversary gift before the discount expires. 7. After user acceptance, complete checkout and confirm the order.

    This scenario exercises multi-source information synthesis (correlating independent emails without explicit connection), implicit goal inference (partner's casual mention implies gift opportunity), temporal reasoning (coordinating anniversary timing with discount expiration), social context awareness (recognizing gift-giving situations), and opportunistic resource utilization (applying third-party discount to fulfill inferred personal goal).
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails")

        # Initialize shopping app with yoga mat products
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Seed contact for the partner
        from are.simulation.apps.contacts import Gender

        self.partner_contact = Contact(
            first_name="Sarah",
            last_name="Johnson",
            contact_id="contact-sarah",
            email="sarah.johnson@example.com",
            phone="555-123-4567",
            gender=Gender.FEMALE,
        )

        # Seed shopping catalog with yoga mats
        # Premium yoga mat product
        premium_yoga_mat_product_id = self.shopping.add_product("Premium Eco Yoga Mat")
        item_yoga_mat_001_purple = self.shopping.add_item_to_product(
            product_id=premium_yoga_mat_product_id,
            price=89.99,
            options={"color": "Purple", "thickness": "6mm", "material": "Natural Rubber"},
            available=True,
        )
        item_yoga_mat_001_blue = self.shopping.add_item_to_product(
            product_id=premium_yoga_mat_product_id,
            price=89.99,
            options={"color": "Blue", "thickness": "6mm", "material": "Natural Rubber"},
            available=True,
        )

        # Standard yoga mat product
        standard_yoga_mat_product_id = self.shopping.add_product("Standard Exercise Yoga Mat")
        item_yoga_mat_002_black = self.shopping.add_item_to_product(
            product_id=standard_yoga_mat_product_id,
            price=49.99,
            options={"color": "Black", "thickness": "5mm", "material": "PVC"},
            available=True,
        )
        item_yoga_mat_002_pink = self.shopping.add_item_to_product(
            product_id=standard_yoga_mat_product_id,
            price=49.99,
            options={"color": "Pink", "thickness": "5mm", "material": "PVC"},
            available=True,
        )

        # Deluxe yoga mat product
        deluxe_yoga_mat_product_id = self.shopping.add_product("Deluxe Professional Yoga Mat")
        item_yoga_mat_003_gray = self.shopping.add_item_to_product(
            product_id=deluxe_yoga_mat_product_id,
            price=129.99,
            options={"color": "Gray", "thickness": "8mm", "material": "Cork & Natural Rubber"},
            available=True,
        )

        # Add discount codes for yoga products (25% off)
        self.shopping.add_discount_code(item_yoga_mat_001_purple, {"FITNESS25": 0.25})
        self.shopping.add_discount_code(item_yoga_mat_001_blue, {"FITNESS25": 0.25})
        self.shopping.add_discount_code(item_yoga_mat_002_black, {"FITNESS25": 0.25})
        self.shopping.add_discount_code(item_yoga_mat_002_pink, {"FITNESS25": 0.25})
        self.shopping.add_discount_code(item_yoga_mat_003_gray, {"FITNESS25": 0.25})

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.shopping]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PAREAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Event 1: Email from partner mentioning anniversary and yoga mat interest (environment event)
            partner_email_event = email_app.send_email_to_user_with_id(
                email_id="email-partner-anniversary",
                sender="sarah.johnson@example.com",
                subject="Can't believe it's almost our anniversary!",
                content="Hi! I can't believe our anniversary is next week already (Nov 25th). Time flies! I've been wanting to upgrade my old yoga mat - it's getting worn out. Looking forward to celebrating with you!",
            ).delayed(10)

            # Event 2: Promotional email with discount code arrives 2 hours later (environment event)
            promo_email_event = email_app.send_email_to_user_only(
                sender="promotions@fitnessgear.com",
                subject="48-Hour Flash Sale: 25% Off All Yoga & Fitness Gear!",
                content="Exclusive offer for our valued customers! Get 25% off all yoga mats, fitness equipment, and accessories. Use code FITNESS25 at checkout. Sale ends in 3 days (Nov 21st). Don't miss out on premium yoga mats, resistance bands, and more!",
            ).delayed(15)

            # Event 3: Agent searches emails to correlate information (oracle)
            search_emails_event = (
                email_app.search_emails(
                    query="yoga mat",
                    folder_name="INBOX",
                )
                .oracle()
                .depends_on(promo_email_event, delay_seconds=3)
            )

            # Event 4: Agent searches shopping catalog for yoga mats (oracle)
            search_products_event = (
                shopping_app.search_product(
                    product_name="yoga mat",
                )
                .oracle()
                .depends_on(search_emails_event, delay_seconds=2)
            )

            # Event 5: Agent checks discount code validity (oracle)
            check_discount_event = (
                shopping_app.get_discount_code_info(
                    discount_code="FITNESS25",
                )
                .oracle()
                .depends_on(search_products_event, delay_seconds=1)
            )

            # Event 6: Agent proposes gift purchase with discount (oracle)
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed Sarah mentioned wanting a new yoga mat in her email about your anniversary next week. There's a timely 25% off sale on yoga mats (code FITNESS25) that expires in 3 days. Would you like me to help you purchase one as an anniversary gift?",
                )
                .oracle()
                .depends_on(check_discount_event, delay_seconds=2)
            )

            # Event 7: User accepts the proposal (oracle)
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, that's a great idea! Please find a good quality yoga mat.",
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Event 8: Agent gets details on a specific product (oracle)
            get_product_event = (
                shopping_app.get_product_details(
                    product_id="product-yoga-mat-001",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Event 9: Agent adds selected yoga mat to cart (oracle)
            add_to_cart_event = (
                shopping_app.add_to_cart(
                    item_id="item-yoga-mat-001-purple",
                    quantity=1,
                )
                .oracle()
                .depends_on(get_product_event, delay_seconds=1)
            )

            # Event 10: Agent completes checkout with discount code (oracle)
            checkout_event = (
                shopping_app.checkout(
                    discount_code="FITNESS25",
                )
                .oracle()
                .depends_on(add_to_cart_event, delay_seconds=1)
            )

            # Event 11: Agent confirms order completion to user (oracle)
            confirmation_event = (
                aui.send_message_to_user(
                    content="I've purchased the Premium Eco Yoga Mat in purple for Sarah's anniversary gift. With the 25% discount (code FITNESS25), the total came to $67.49. The order has been placed successfully.",
                )
                .oracle()
                .depends_on(checkout_event, delay_seconds=2)
            )

        # Register ALL events here in self.events
        self.events = [
            partner_email_event,
            promo_email_event,
            search_emails_event,
            search_products_event,
            check_discount_event,
            proposal_event,
            acceptance_event,
            get_product_event,
            add_to_cart_event,
            checkout_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent inferred gift opportunity from multiple emails and completed purchase."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1: Agent sent proposal (demonstrates multi-email inference)
            proposal_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "PAREAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 2: Agent completed checkout with discount code
            checkout_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                and str(e.action.args.get("discount_code", "")).upper() == "FITNESS25"
                for e in log_entries
            )

            success = proposal_found and checkout_found

            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent did not send proposal")
                if not checkout_found:
                    missing_checks.append("agent did not complete checkout with FITNESS25 discount")
                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
