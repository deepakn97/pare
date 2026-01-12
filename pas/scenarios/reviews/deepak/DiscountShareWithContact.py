"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.contacts import Contact
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


@register_scenario("discount_share_with_contact")
class DiscountShareWithContact(PASScenario):
    """Agent shares applicable discount code with a contact based on shopping notification and contact interests.

    The user receives a notification about a new 30% discount code for electronics items in the shopping app. The user has a contact, Sarah Martinez, whose contact description indicates she is interested in electronics and gadgets. The agent must:
    1. Parse the discount notification to identify the discount code and applicable product category
    2. Search contacts to identify relevant recipients based on interest matching
    3. Retrieve the specific discount code details from the shopping app
    4. Compose and send a message to Sarah via messaging informing her about the discount
    5. Confirm the action with the user

    This scenario exercises notification-triggered reasoning, cross-app correlation (shopping → contacts), interest-based filtering from contact metadata, and proactive sharing of personalized information..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize contacts app
        self.contacts = StatefulContactsApp(name="Contacts")

        # Initialize messaging app (used to deliver the exogenous discount alert and to message Sarah).
        self.messaging = StatefulMessagingApp(name="Messages")

        # Create the user contact
        user_contact = Contact(
            first_name="John",
            last_name="Doe",
            contact_id="user_001",
            is_user=True,
            phone="+1-555-0100",
            email="john.doe@email.com",
        )
        self.contacts.add_contact(user_contact)

        # Create Sarah Martinez - interested in electronics and gadgets
        sarah_contact = Contact(
            first_name="Sarah",
            last_name="Martinez",
            contact_id="sarah_001",
            phone="+1-555-0201",
            email="sarah.martinez@email.com",
            description="Tech enthusiast interested in electronics and gadgets. Always looking for deals on new tech products.",
        )
        self.contacts.add_contact(sarah_contact)

        # Create additional contacts without electronics interest
        mike_contact = Contact(
            first_name="Mike",
            last_name="Johnson",
            contact_id="mike_001",
            phone="+1-555-0202",
            email="mike.johnson@email.com",
            description="Fitness enthusiast and outdoor sports lover.",
        )
        self.contacts.add_contact(mike_contact)

        # Initialize shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Add electronics products
        laptop_product = Product(name="UltraBook Pro Laptop", product_id="prod_laptop_001")
        laptop_item = Item(
            item_id="item_laptop_001",
            price=1299.99,
            available=True,
            options={"color": "silver", "storage": "512GB", "category": "electronics"},
        )
        laptop_product.variants["item_laptop_001"] = laptop_item
        self.shopping.products["prod_laptop_001"] = laptop_product

        headphones_product = Product(name="Wireless Noise-Cancelling Headphones", product_id="prod_headphones_001")
        headphones_item = Item(
            item_id="item_headphones_001",
            price=299.99,
            available=True,
            options={"color": "black", "category": "electronics"},
        )
        headphones_product.variants["item_headphones_001"] = headphones_item
        self.shopping.products["prod_headphones_001"] = headphones_product

        smartwatch_product = Product(name="Smart Fitness Watch", product_id="prod_watch_001")
        smartwatch_item = Item(
            item_id="item_watch_001",
            price=399.99,
            available=True,
            options={"color": "black", "category": "electronics"},
        )
        smartwatch_product.variants["item_watch_001"] = smartwatch_item
        self.shopping.products["prod_watch_001"] = smartwatch_product

        # Add non-electronics product for contrast
        shoes_product = Product(name="Running Shoes", product_id="prod_shoes_001")
        shoes_item = Item(
            item_id="item_shoes_001",
            price=129.99,
            available=True,
            options={"size": "10", "color": "blue", "category": "sports"},
        )
        shoes_product.variants["item_shoes_001"] = shoes_item
        self.shopping.products["prod_shoes_001"] = shoes_product

        # Add discount code TECH30 that applies to electronics items only
        self.shopping.discount_codes["item_laptop_001"] = {"TECH30": 30.0}
        self.shopping.discount_codes["item_headphones_001"] = {"TECH30": 30.0}
        self.shopping.discount_codes["item_watch_001"] = {"TECH30": 30.0}

        # Seed messaging users + a "Shopping Alerts" group so the discount details are observable (code + category).
        self.messaging.add_users(["Acme Shop", "Shop Bot"])
        self.messaging.add_contacts([("Sarah Martinez", sarah_contact.phone)])
        self.sarah_user_id = self.messaging.name_to_id["Sarah Martinez"]
        shop_id = self.messaging.name_to_id["Acme Shop"]
        bot_id = self.messaging.name_to_id["Shop Bot"]
        self.shop_alerts_conversation_id = self.messaging.create_group_conversation(
            user_ids=[shop_id, bot_id],
            title="Shopping Alerts",
        )
        self.shop_sender_id = shop_id

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.shopping, self.messaging]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Shopping alert arrives mentioning the discount code + electronics category.
            # NOTE: ShoppingApp discount APIs don't encode category; category must come from observable text.
            discount_alert_event = messaging_app.create_and_add_message(
                conversation_id=self.shop_alerts_conversation_id,
                sender_id=self.shop_sender_id,
                content="New promo: TECH30 gives 30% off electronics items today. Use code TECH30 at checkout. Share it with your contacts today!",
            ).delayed(10)

            # Oracle Event 1: Agent reads the alert to extract code + category ("electronics").
            # Motivation: incoming shopping alert notification.
            read_alert_event = (
                messaging_app.read_conversation(
                    conversation_id=self.shop_alerts_conversation_id,
                    offset=0,
                    limit=10,
                )
                .oracle()
                .depends_on([discount_alert_event], delay_seconds=2)
            )

            # Oracle Event 1: Agent searches contacts for potential recipients
            # Motivation: The agent observed a discount notification for electronics items and searches contacts
            # to find anyone with "electronics" interest mentioned in their description.
            search_contacts_event = (
                contacts_app.search_contacts(query="electronics")
                .oracle()
                .depends_on([read_alert_event], delay_seconds=2)
            )

            # Oracle Event 2: Agent retrieves Sarah's contact details
            # Motivation: The search returned Sarah; the agent retrieves her full contact record to verify
            # her description mentions electronics/gadgets and to get her email for the proposal.
            get_contact_event = (
                contacts_app.get_contact(contact_id="sarah_001")
                .oracle()
                .depends_on([search_contacts_event], delay_seconds=1)
            )

            # Oracle Event 3: Agent retrieves discount code applicability from the shopping app.
            # Motivation: confirm TECH30 exists and see which items it applies to.
            get_discount_info_event = (
                shopping_app.get_discount_code_info(discount_code="TECH30")
                .oracle()
                .depends_on([read_alert_event], delay_seconds=1)
            )

            # Oracle Event 4: Agent proposes sharing the discount with Sarah
            # Motivation: Having confirmed Sarah's electronics interest from her contact description,
            # the agent proposes informing Sarah about the TECH30 discount code.
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed a new 30% discount code (TECH30) for electronics items. Your contact Sarah Martinez is interested in electronics and gadgets. Would you like me to help you share this discount with her?"
                )
                .oracle()
                .depends_on([get_contact_event, get_discount_info_event], delay_seconds=2)
            )

            # Oracle Event 5: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please help me share the discount with Sarah.")
                .oracle()
                .depends_on([proposal_event], delay_seconds=2)
            )

            # Oracle Event 6: Agent sends the discount code to Sarah via messaging.
            # Motivation: user approved sharing; Sarah is a reachable messaging contact in the environment.
            send_to_sarah_event = (
                messaging_app.send_message(
                    user_id=self.sarah_user_id,
                    content="Hey Sarah — I saw a promo for electronics: code TECH30 gives 30% off eligible electronics items. Thought you might like it!",
                )
                .oracle()
                .depends_on([acceptance_event], delay_seconds=2)
            )

            # Oracle Event 7: Agent confirms completion to the user.
            confirmation_event = (
                aui.send_message_to_user(
                    content="Done — I messaged Sarah Martinez with the TECH30 electronics discount code."
                )
                .oracle()
                .depends_on([send_to_sarah_event], delay_seconds=1)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            discount_alert_event,
            read_alert_event,
            search_contacts_event,
            get_contact_event,
            proposal_event,
            acceptance_event,
            send_to_sarah_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1 (STRICT): Agent searched for contacts interested in electronics
            # The agent must have searched contacts with query related to "electronics" to find Sarah
            search_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "search_contacts"
                for e in log_entries
            )

            # Check Step 2 (STRICT): Agent retrieved Sarah's contact details
            # The agent must have fetched Sarah's contact by ID to verify her interest
            get_contact_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "get_contact"
                for e in log_entries
            )

            # Check Step 3 (STRICT): Agent proposed sharing discount with Sarah
            # The agent must have sent a proposal mentioning the discount code and Sarah's name
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check Step 4 (STRICT): Agent provided Sarah's contact information after acceptance
            # The agent must have sent a message to Sarah with TECH30 after the user accepted.
            send_to_sarah_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name in ["send_message", "send_message_to_group_conversation"]
                for e in log_entries
            )

            # All checks must pass for success
            success = search_found and get_contact_found and proposal_found and send_to_sarah_found

            if not success:
                # Build rationale for failure
                missing_checks = []
                if not search_found:
                    missing_checks.append("contact search for electronics")
                if not get_contact_found:
                    missing_checks.append("get_contact for sarah_001")
                if not proposal_found:
                    missing_checks.append("proposal to share discount with Sarah")
                if not send_to_sarah_found:
                    missing_checks.append("send_message to Sarah with TECH30")

                rationale = f"Missing required agent actions: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
