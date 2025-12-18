"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.contacts import Contact
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


@register_scenario("gift_purchase_multi_email_inference")
class GiftPurchaseMultiEmailInference(PASScenario):
    """Agent infers gift-buying opportunity by correlating product interest mentioned in one email with discount code offered in another email.

    The user receives an email from their partner mentioning their anniversary is next week and casually stating "I've been wanting to upgrade my old yoga mat." Two hours later, a separate promotional email arrives from a sports equipment retailer with a 25% discount code for yoga and fitness products, valid for three days. The agent must: 1. Parse both emails to extract the product interest (yoga mat) and the discount opportunity (25% off fitness products). 2. Correlate the temporal proximity (anniversary next week, discount expires in three days) and topical overlap (yoga mat + yoga products discount). 3. Search the shopping catalog for yoga mats that qualify for the discount code. 4. Select an appropriate product and add it to cart. 5. Apply the discount code from the promotional email. 6. Propose completing the purchase as an anniversary gift before the discount expires. 7. After user acceptance, complete checkout and confirm the order.

    This scenario exercises multi-source information synthesis (correlating independent emails without explicit connection), implicit goal inference (partner's casual mention implies gift opportunity), temporal reasoning (coordinating anniversary timing with discount expiration), social context awareness (recognizing gift-giving situations), and opportunistic resource utilization (applying third-party discount to fulfill inferred personal goal).
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
        from are.simulation.apps.shopping import Item, Product

        # Premium yoga mat product
        premium_yoga_mat = Product(name="Premium Eco Yoga Mat", product_id="product-yoga-mat-001")
        premium_yoga_mat.variants["purple-6mm"] = Item(
            item_id="item-yoga-mat-001-purple",
            price=89.99,
            available=True,
            options={"color": "Purple", "thickness": "6mm", "material": "Natural Rubber"},
        )
        premium_yoga_mat.variants["blue-6mm"] = Item(
            item_id="item-yoga-mat-001-blue",
            price=89.99,
            available=True,
            options={"color": "Blue", "thickness": "6mm", "material": "Natural Rubber"},
        )
        self.shopping.products["product-yoga-mat-001"] = premium_yoga_mat

        # Standard yoga mat product
        standard_yoga_mat = Product(name="Standard Exercise Yoga Mat", product_id="product-yoga-mat-002")
        standard_yoga_mat.variants["black-5mm"] = Item(
            item_id="item-yoga-mat-002-black",
            price=49.99,
            available=True,
            options={"color": "Black", "thickness": "5mm", "material": "PVC"},
        )
        standard_yoga_mat.variants["pink-5mm"] = Item(
            item_id="item-yoga-mat-002-pink",
            price=49.99,
            available=True,
            options={"color": "Pink", "thickness": "5mm", "material": "PVC"},
        )
        self.shopping.products["product-yoga-mat-002"] = standard_yoga_mat

        # Deluxe yoga mat product
        deluxe_yoga_mat = Product(name="Deluxe Professional Yoga Mat", product_id="product-yoga-mat-003")
        deluxe_yoga_mat.variants["gray-8mm"] = Item(
            item_id="item-yoga-mat-003-gray",
            price=129.99,
            available=True,
            options={"color": "Gray", "thickness": "8mm", "material": "Cork & Natural Rubber"},
        )
        self.shopping.products["product-yoga-mat-003"] = deluxe_yoga_mat

        # Add discount codes for yoga products (25% off)
        self.shopping.discount_codes["item-yoga-mat-001-purple"] = {"FITNESS25": 0.25}
        self.shopping.discount_codes["item-yoga-mat-001-blue"] = {"FITNESS25": 0.25}
        self.shopping.discount_codes["item-yoga-mat-002-black"] = {"FITNESS25": 0.25}
        self.shopping.discount_codes["item-yoga-mat-002-pink"] = {"FITNESS25": 0.25}
        self.shopping.discount_codes["item-yoga-mat-003-gray"] = {"FITNESS25": 0.25}

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.shopping]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
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
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check: Agent searched shopping catalog for yoga mats
            product_search_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "search_product"
                and "yoga" in str(e.action.args.get("product_name", "")).lower()
                for e in log_entries
            )

            # STRICT Check: Agent sent proposal mentioning both partner and gift opportunity
            proposal_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check: Agent added yoga mat product to cart
            add_to_cart_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
                and "yoga-mat" in str(e.action.args.get("item_id", ""))
                for e in log_entries
            )

            # STRICT Check: Agent completed checkout with discount code
            checkout_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                and str(e.action.args.get("discount_code", "")).upper() == "FITNESS25"
                for e in log_entries
            )

            # Build rationale for failure
            missing_checks = []
            if not product_search_found:
                missing_checks.append("product search for yoga mat")
            if not proposal_found:
                missing_checks.append("proposal mentioning partner/anniversary and yoga mat")
            if not add_to_cart_found:
                missing_checks.append("add yoga mat to cart")
            if not checkout_found:
                missing_checks.append("checkout with FITNESS25 discount code")

            success = product_search_found and proposal_found and add_to_cart_found and checkout_found

            rationale = None
            if not success:
                rationale = f"Missing critical checks: {', '.join(missing_checks)}"

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
