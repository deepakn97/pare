"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.contacts import Contact
from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
from are.simulation.apps.shopping import Item, Product
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulContactsApp,
    StatefulMessagingApp,
)
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("group_purchase_coordinator")
class GroupPurchaseCoordinator(PASScenario):
    """Agent coordinates a group purchase by collecting participant commitments and placing a bulk order.

    The user receives a message from a contact, Lisa Park, asking if the user wants to join a group order for discounted office chairs (ProductName: "ErgoMax Office Chair"). Lisa explains that they need at least 3 people total to qualify for a bulk discount code "BULK3FOR20" (20% off when buying 3+ chairs). The agent must:
    1. Parse the group purchase invitation from the incoming message
    2. Search the shopping app to verify the product exists and retrieve its product_id
    3. Check if the discount code BULK3FOR20 is valid for the ErgoMax Office Chair
    4. After user confirms interest, send messages to other contacts (Mark Stevens and Jennifer Wu) to gauge their interest in joining the group purchase
    5. After receiving confirmations from participants via messages, add 3 ErgoMax chairs to the cart
    6. Apply the BULK3FOR20 discount code and checkout the order
    7. Send a confirmation message to all participants with order details

    This scenario exercises multi-party coordination via messaging, discount validation across shopping tools, conditional cart assembly based on participant confirmments, and group notification after transaction completion..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Contacts app with participants
        self.contacts = StatefulContactsApp(name="Contacts")

        # Add user contact (is_user=True)
        user_contact = Contact(
            first_name="Alex",
            last_name="Johnson",
            contact_id="user_001",
            is_user=True,
            phone="+1-555-0100",
            email="alex.johnson@example.com",
        )
        self.contacts.add_contact(user_contact)

        # Add Lisa Park (initiator of group purchase)
        lisa_contact = Contact(
            first_name="Lisa",
            last_name="Park",
            contact_id="lisa_001",
            phone="+1-555-0201",
            email="lisa.park@example.com",
        )
        self.contacts.add_contact(lisa_contact)

        # Add Mark Stevens (potential participant)
        mark_contact = Contact(
            first_name="Mark",
            last_name="Stevens",
            contact_id="mark_001",
            phone="+1-555-0202",
            email="mark.stevens@example.com",
        )
        self.contacts.add_contact(mark_contact)

        # Add Jennifer Wu (potential participant)
        jennifer_contact = Contact(
            first_name="Jennifer",
            last_name="Wu",
            contact_id="jennifer_001",
            phone="+1-555-0203",
            email="jennifer.wu@example.com",
        )
        self.contacts.add_contact(jennifer_contact)

        # Initialize Messaging app
        self.messaging = StatefulMessagingApp(name="Messages")
        self.messaging.current_user_id = "user_001"
        self.messaging.current_user_name = "Alex Johnson"

        # Register contacts in messaging app
        self.messaging.add_contacts([
            ("Lisa Park", "+1-555-0201"),
            ("Mark Stevens", "+1-555-0202"),
            ("Jennifer Wu", "+1-555-0203"),
        ])

        # Seed baseline conversation history with Lisa (earlier context)
        lisa_conversation = ConversationV2(
            conversation_id="conv_lisa_001",
            participant_ids=["user_001", "+1-555-0201"],
            title="Lisa Park",
            messages=[
                MessageV2(
                    sender_id="+1-555-0201",
                    content="Hi Alex! How have you been?",
                    timestamp=datetime(2025, 11, 15, 14, 30, 0, tzinfo=UTC).timestamp(),
                ),
                MessageV2(
                    sender_id="user_001",
                    content="Great, thanks! How about you?",
                    timestamp=datetime(2025, 11, 15, 14, 35, 0, tzinfo=UTC).timestamp(),
                ),
            ],
            last_updated=datetime(2025, 11, 15, 14, 35, 0, tzinfo=UTC).timestamp(),
        )
        self.messaging.add_conversation(lisa_conversation)

        # Initialize Shopping app with ErgoMax Office Chair product
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Create ErgoMax Office Chair product
        ergomax_product = Product(name="ErgoMax Office Chair", product_id="prod_ergomax_001")

        # Add a single variant (no color/size options for simplicity)
        ergomax_item = Item(item_id="item_ergomax_001", price=299.99, available=True, options={})
        ergomax_product.variants["item_ergomax_001"] = ergomax_item
        self.shopping.products["prod_ergomax_001"] = ergomax_product

        # Add bulk discount code BULK3FOR20 for the ErgoMax chair item
        self.shopping.discount_codes["item_ergomax_001"] = {"BULK3FOR20": 0.20}

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.messaging, self.shopping]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Lisa sends message about group purchase invitation
            lisa_invitation = messaging_app.create_and_add_message(
                conversation_id="conv_lisa_001",
                sender_id="+1-555-0201",
                content="Hey Alex! I'm organizing a group purchase for ErgoMax Office Chairs. They're running a bulk discount - if we get 3+ people, we can use code BULK3FOR20 for 20% off! Each chair is normally $299.99. Are you interested in joining? Or if you have enough people to buy that together can you help me buy one with your group as well?",
            ).delayed(10)

            # Agent reads the conversation to see Lisa's invitation
            # Motivated by: Lisa's message about group purchase just arrived
            read_lisa_conv = (
                messaging_app.read_conversation(conversation_id="conv_lisa_001", offset=0, limit=10)
                .oracle()
                .depends_on(lisa_invitation, delay_seconds=2)
            )

            # Agent searches shopping to verify the ErgoMax Office Chair product exists
            # Motivated by: Lisa mentioned "ErgoMax Office Chair" in her message
            search_product = (
                shopping_app.search_product(product_name="ErgoMax Office Chair", offset=0, limit=10)
                .oracle()
                .depends_on(read_lisa_conv, delay_seconds=1)
            )

            # Agent checks the discount code BULK3FOR20 for the ErgoMax chair
            # Motivated by: Lisa mentioned discount code "BULK3FOR20" in her message
            check_discount = (
                shopping_app.get_discount_code_info(discount_code="BULK3FOR20")
                .oracle()
                .depends_on(search_product, delay_seconds=1)
            )

            # Agent proposes to user: join the group purchase and coordinate with other contacts
            # Motivated by: verified product exists and discount code is valid
            proposal_event = (
                aui.send_message_to_user(
                    content="Lisa invited you to join a group purchase for ErgoMax Office Chairs. The product costs $299.99 and there's a valid 20% bulk discount (BULK3FOR20) for orders of 3+. Would you like me to coordinate with Mark Stevens and Jennifer Wu to see if they're interested in joining?"
                )
                .oracle()
                .depends_on(check_discount, delay_seconds=2)
            )

            # User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please reach out to Mark and Jennifer! And if they are all interested then buy 3 in total for Mark, Jennifer and Lisa together."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Agent sends message to Mark Stevens to gauge interest
            # Motivated by: user accepted the proposal to coordinate with Mark and Jennifer
            message_mark = (
                messaging_app.send_message(
                    user_id="+1-555-0202",
                    content="Hi Mark! I'm coordinating a group purchase for ErgoMax Office Chairs with Lisa and Alex. We can get 20% off if we order 3+. Are you interested?",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Agent sends message to Jennifer Wu to gauge interest
            # Motivated by: user accepted the proposal to coordinate with Mark and Jennifer
            message_jennifer = (
                messaging_app.send_message(
                    user_id="+1-555-0203",
                    content="Hi Jennifer! I'm coordinating a group purchase for ErgoMax Office Chairs with Lisa and Alex. We can get 20% off if we order 3+. Are you interested?",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Environment Event 2: Mark responds with interest
            mark_response = messaging_app.create_and_add_message(
                conversation_id="conv_mark_001",
                sender_id="+1-555-0202",
                content="Yes, I'm in! Count me in for one chair.",
            ).delayed(45)

            # Environment Event 3: Jennifer responds with interest
            jennifer_response = messaging_app.create_and_add_message(
                conversation_id="conv_jennifer_001",
                sender_id="+1-555-0203",
                content="Sounds great! I'd love to join. Put me down for one.",
            ).delayed(50)

            # Agent reads Mark's response
            # Motivated by: Mark's confirmation message just arrived
            read_mark_response = (
                messaging_app.read_conversation(conversation_id="conv_mark_001", offset=0, limit=10)
                .oracle()
                .depends_on([mark_response], delay_seconds=2)
            )

            # Agent reads Jennifer's response
            # Motivated by: Jennifer's confirmation message just arrived
            read_jennifer_response = (
                messaging_app.read_conversation(conversation_id="conv_jennifer_001", offset=0, limit=10)
                .oracle()
                .depends_on([jennifer_response], delay_seconds=2)
            )

            # Agent searches for the product details to get product_id
            # Motivated by: have commitments from 3 people (Lisa, Mark, Jennifer implied by user acceptance), need to place order
            get_product = (
                shopping_app.search_product(product_name="ErgoMax Office Chair", offset=0, limit=10)
                .oracle()
                .depends_on([read_mark_response, read_jennifer_response], delay_seconds=2)
            )

            # Agent adds 3 ErgoMax chairs to cart (one for user/Lisa coordination, one for Mark, one for Jennifer)
            # Motivated by: confirmed 3 participants, need item_id from product search
            add_to_cart = (
                shopping_app.add_to_cart(item_id="item_ergomax_001", quantity=3)
                .oracle()
                .depends_on(get_product, delay_seconds=1)
            )

            # Agent checks out with the BULK3FOR20 discount code
            # Motivated by: cart has 3+ items, can now apply bulk discount
            checkout_event = (
                shopping_app.checkout(discount_code="BULK3FOR20").oracle().depends_on(add_to_cart, delay_seconds=1)
            )

            # Agent sends confirmation to Lisa
            # Motivated by: order placed successfully, need to notify all participants
            confirm_lisa = (
                messaging_app.send_message(
                    user_id="+1-555-0201",
                    content="Great news! The group purchase is complete. I've placed the order for 3 ErgoMax Office Chairs with the 20% BULK3FOR20 discount applied. Total savings achieved!",
                )
                .oracle()
                .depends_on(checkout_event, delay_seconds=2)
            )

            # Agent sends confirmation to Mark
            # Motivated by: order placed successfully, need to notify all participants
            confirm_mark = (
                messaging_app.send_message(
                    user_id="+1-555-0202",
                    content="Good news Mark! The group purchase is complete. I've placed the order for 3 ErgoMax Office Chairs with 20% off.",
                )
                .oracle()
                .depends_on(checkout_event, delay_seconds=2)
            )

            # Agent sends confirmation to Jennifer
            # Motivated by: order placed successfully, need to notify all participants
            confirm_jennifer = (
                messaging_app.send_message(
                    user_id="+1-555-0203",
                    content="Good news Jennifer! The group purchase is complete. I've placed the order for 3 ErgoMax Office Chairs with 20% off.",
                )
                .oracle()
                .depends_on(checkout_event, delay_seconds=2)
            )

        # Register ALL events here in self.events
        self.events = [
            lisa_invitation,
            read_lisa_conv,
            search_product,
            check_discount,
            proposal_event,
            acceptance_event,
            message_mark,
            message_jennifer,
            mark_response,
            jennifer_response,
            read_mark_response,
            read_jennifer_response,
            get_product,
            add_to_cart,
            checkout_event,
            confirm_lisa,
            confirm_mark,
            confirm_jennifer,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()
            agent_entries = [e for e in log_entries if e.event_type == EventType.AGENT]

            # Check 1 (STRICT): Agent sent proposal to user about coordinating the group purchase
            proposal_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_entries
            )

            # Check 2 (STRICT): Agent verified product exists by searching for ErgoMax Office Chair
            product_search_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "search_product"
                and "ergomax" in e.action.args.get("product_name", "").lower()
                for e in agent_entries
            )

            # Check 3 (STRICT): Agent checked discount code validity
            discount_check_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_discount_code_info"
                and e.action.args.get("discount_code", "") == "BULK3FOR20"
                for e in agent_entries
            )

            # Check 4 (STRICT): Agent sent messages to Mark and Jennifer (equivalence class: send_message)
            # Accept send_message to either Mark's or Jennifer's contact identifiers
            mark_message_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id", "") == "+1-555-0202"
                for e in agent_entries
            )

            jennifer_message_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id", "") == "+1-555-0203"
                for e in agent_entries
            )

            # Check 5 (STRICT): Agent added 3 ErgoMax chairs to cart
            add_to_cart_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
                and e.action.args.get("item_id", "") == "item_ergomax_001"
                and e.action.args.get("quantity", 0) == 3
                for e in agent_entries
            )

            # Check 6 (STRICT): Agent checked out with BULK3FOR20 discount code
            checkout_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                and e.action.args.get("discount_code", "") == "BULK3FOR20"
                for e in agent_entries
            )

            # Aggregate all checks
            success = (
                proposal_found
                and product_search_found
                and discount_check_found
                and mark_message_found
                and jennifer_message_found
                and add_to_cart_found
                and checkout_found
            )

            # Build rationale if failed
            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal to user")
                if not product_search_found:
                    missing_checks.append("product search for ErgoMax")
                if not discount_check_found:
                    missing_checks.append("discount code check for BULK3FOR20")
                if not mark_message_found:
                    missing_checks.append("message to Mark Stevens")
                if not jennifer_message_found:
                    missing_checks.append("message to Jennifer Wu")
                if not add_to_cart_found:
                    missing_checks.append("add 3 chairs to cart")
                if not checkout_found:
                    missing_checks.append("checkout with BULK3FOR20")
                rationale = f"Missing critical checks: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
