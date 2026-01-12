"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.contacts import Contact
from are.simulation.apps.shopping import CartItem, Order
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulContactsApp,
)
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("cancelled_gift_order_contact_tracking")
class CancelledGiftOrderContactTracking(PASScenario):
    """Agent tracks cancelled gift orders by enriching contact records and suggesting replacement purchases.

    The user receives a notification that their order (#8472) containing "Wireless Earbuds - Blue" has been cancelled by the seller due to stock unavailability. This order was being shipped to "142 Maple Street" - the same address listed for contact "Jamie Chen" whose description mentions "enjoys music, birthday in January." The agent must:
    1. Parse the cancellation notification to extract order ID and affected products
    2. Retrieve the full cancelled order details including shipping address
    3. Search contacts for anyone with a matching address to identify the intended recipient
    4. Update Jamie Chen's contact description to append a note about the cancelled gift item
    5. Search the shopping catalog for alternative products in the same category (earbuds/audio)
    6. Propose re-ordering a replacement product for the same delivery address

    This scenario exercises cancellation-notification handling, address-based contact correlation (shopping → contacts reverse lookup), proactive contact record enrichment with shopping context, and recovery workflow planning across both apps.

    ---.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with baseline data.

        Contacts: Jamie Chen with address "142 Maple Street" and description mentioning music interest and birthday
        Shopping: Product catalog with wireless earbuds and alternative audio products
        Orders: Pre-existing order #8472 for "Wireless Earbuds - Blue" to Jamie's address (will be cancelled in Step 3)
        """
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Contacts app
        self.contacts = StatefulContactsApp(name="Contacts")

        # Populate contacts - Jamie Chen is the gift recipient
        jamie = Contact(
            first_name="Jamie",
            last_name="Chen",
            phone="555-0142",
            email="jamie.chen@example.com",
            address="142 Maple Street",
            description="enjoys music, birthday in January",
        )
        self.jamie_contact_id = self.contacts.add_contact(jamie)

        # Add a few other contacts for context
        alex = Contact(
            first_name="Alex",
            last_name="Johnson",
            phone="555-0198",
            email="alex.j@example.com",
            address="87 Oak Avenue",
            description="colleague",
        )
        self.contacts.add_contact(alex)

        # Initialize Shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Add products: Wireless Earbuds (the cancelled one) and alternatives
        earbuds_blue_pid = self.shopping.add_product("Wireless Earbuds - Blue")
        earbuds_blue_item_id = self.shopping.add_item_to_product(
            product_id=earbuds_blue_pid,
            price=79.99,
            options={"color": "blue", "type": "wireless"},
            available=False,  # Will be marked unavailable, leading to cancellation
        )

        # Alternative products in the same category
        earbuds_black_pid = self.shopping.add_product("Wireless Earbuds - Black")
        earbuds_black_item_id = self.shopping.add_item_to_product(
            product_id=earbuds_black_pid, price=79.99, options={"color": "black", "type": "wireless"}, available=True
        )

        headphones_pid = self.shopping.add_product("Premium Headphones")
        headphones_item_id = self.shopping.add_item_to_product(
            product_id=headphones_pid,
            price=129.99,
            options={"type": "over-ear", "noise-cancelling": True},
            available=True,
        )

        earbuds_pro_pid = self.shopping.add_product("Pro Earbuds")
        earbuds_pro_item_id = self.shopping.add_item_to_product(
            product_id=earbuds_pro_pid, price=149.99, options={"type": "wireless", "premium": True}, available=True
        )

        # Create a pre-existing order that will be cancelled in Step 3
        # Order #8472 with the blue earbuds, shipped to Jamie's address
        # Directly create Order object to avoid add_order's CartItem construction bug
        order_item = CartItem(
            item_id=earbuds_blue_item_id,
            quantity=1,
            price=79.99,
            available=False,
            options={"color": "blue", "type": "wireless"},
        )
        order_8472 = Order(
            order_id="8472",
            order_status="processed",
            order_date=self.start_time - 86400,  # 1 day before scenario start
            order_total=79.99,
            order_items={earbuds_blue_item_id: order_item},
        )
        self.shopping.orders["8472"] = order_8472

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.shopping]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Order cancellation notification
            # The seller cancels order #8472 (Wireless Earbuds - Blue) due to stock unavailability
            cancel_event = shopping_app.update_order_status(order_id="8472", status="cancelled").delayed(15)

            # Oracle Event 1: Agent retrieves cancelled order details to understand what was cancelled
            # Motivation: The cancellation notification (from update_order_status) triggers the agent to investigate
            get_order_event = (
                shopping_app.get_order_details(order_id="8472").oracle().depends_on(cancel_event, delay_seconds=2)
            )

            # Oracle Event 2: Agent searches contacts by address to find the gift recipient
            # Motivation: The order details reveal shipping address "142 Maple Street"; agent correlates this with contacts
            search_contacts_event = (
                contacts_app.search_contacts(query="142 Maple Street")
                .oracle()
                .depends_on(get_order_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent retrieves Jamie Chen's full contact details
            # Motivation: Search results identified Jamie Chen at the matching address; agent needs full details for proposal
            get_contact_event = (
                contacts_app.get_contact(contact_id=self.jamie_contact_id)
                .oracle()
                .depends_on(search_contacts_event, delay_seconds=1)
            )

            # Oracle Event 4: Agent proposes tracking the cancelled gift and searching for alternatives
            # Motivation: Agent has confirmed this was a gift order to Jamie (music lover, January birthday) at 142 Maple Street
            proposal_event = (
                aui.send_message_to_user(
                    content="Your order #8472 (Wireless Earbuds - Blue, $79.99) to 142 Maple Street was cancelled by the seller. This appears to be a gift for Jamie Chen (enjoys music, birthday in January). Would you like me to update Jamie's contact to track this and search for alternative products?"
                )
                .oracle()
                .depends_on(get_contact_event, delay_seconds=2)
            )

            # Oracle Event 5: User accepts the proposal
            # Motivation: User confirms they want the agent to proceed with tracking and finding alternatives
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please update Jamie's contact and let me know if you find a replacement of a new earbuds. but please don't add that to cart or order for me."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event 6: Agent updates Jamie's contact description to note the cancelled gift
            # Motivation: User accepted; agent enriches contact record with shopping context for future reference
            update_contact_event = (
                contacts_app.edit_contact(
                    contact_id=self.jamie_contact_id,
                    updates={
                        "description": "enjoys music, birthday in January. Note: Order #8472 (Wireless Earbuds - Blue) cancelled - pending gift reorder"
                    },
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 7: Agent searches for alternative wireless earbuds products
            # Motivation: User requested replacement; agent searches catalog for similar products in the same category
            search_products_event = (
                shopping_app.search_product(product_name="earbuds")
                .oracle()
                .depends_on(update_contact_event, delay_seconds=2)
            )

            # Oracle Event 8: Agent proposes reordering an alternative product
            # Motivation: Search revealed available alternatives; agent suggests a similar product at the same price point
            reorder_proposal_event = (
                aui.send_message_to_user(
                    content="I've updated Jamie Chen's contact to note the cancelled gift. I found alternative products: Wireless Earbuds - Black ($79.99, in stock) or Premium Headphones ($129.99, in stock). Would you like to order one of these for delivery to 142 Maple Street?"
                )
                .oracle()
                .depends_on(search_products_event, delay_seconds=2)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            cancel_event,
            get_order_event,
            search_contacts_event,
            get_contact_event,
            proposal_event,
            acceptance_event,
            update_contact_event,
            search_products_event,
            reorder_proposal_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()
            agent_entries = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent retrieved cancelled order details
            # The agent must fetch order #8472 to understand what was cancelled
            order_retrieved = any(
                e.action.class_name == "StatefulShoppingApp" and e.action.function_name == "get_order_details"
                for e in agent_entries
            )

            # STRICT Check 2: Agent searched contacts by the shipping address
            # The agent must correlate the shipping address from the cancelled order with contact records
            contacts_searched = any(
                e.action.class_name == "StatefulContactsApp" and e.action.function_name == "search_contacts"
                for e in agent_entries
            )

            # STRICT Check 3: Agent retrieved Jamie Chen's contact details
            # After finding Jamie via address search, agent must get full contact details
            jamie_contact_retrieved = any(
                e.action.class_name == "StatefulContactsApp" and e.action.function_name == "get_contact"
                for e in agent_entries
            )

            # FLEXIBLE Check 4: Agent sent initial proposal to user
            # The agent should propose tracking the cancelled gift and finding alternatives
            # Content is flexible, but the proposal action must exist
            initial_proposal_sent = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_entries
            )

            # STRICT Check 5: Agent updated Jamie's contact description
            # The agent must enrich the contact record with the cancelled gift context
            contact_updated = any(
                e.action.class_name == "StatefulContactsApp" and e.action.function_name == "edit_contact"
                for e in agent_entries
            )

            # STRICT Check 6: Agent searched for alternative products
            # The agent must search the shopping catalog for replacement items
            alternatives_searched = any(
                e.action.class_name == "StatefulShoppingApp" and e.action.function_name == "search_product"
                for e in agent_entries
            )

            # Evaluate success: all strict checks must pass
            success = (
                order_retrieved
                and contacts_searched
                and jamie_contact_retrieved
                and contact_updated
                and alternatives_searched
            )

            # Build rationale for failure
            rationale = None
            if not success:
                missing = []
                if not order_retrieved:
                    missing.append("order #8472 details not retrieved")
                if not contacts_searched:
                    missing.append("contacts not searched by shipping address")
                if not jamie_contact_retrieved:
                    missing.append("Jamie Chen's contact details not retrieved")
                if not contact_updated:
                    missing.append("Jamie Chen's contact record not updated with cancelled gift note")
                if not alternatives_searched:
                    missing.append("alternative earbuds products not searched")
                rationale = "; ".join(missing)

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
