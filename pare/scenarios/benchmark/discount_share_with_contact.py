from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.contacts import Contact
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulContactsApp,
    StatefulMessagingApp,
)
from pare.apps.shopping import StatefulShoppingApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("discount_share_with_contact")
class DiscountShareWithContact(PAREScenario):
    """Agent shares applicable discount code with a contact based on shopping notification and contact interests.

    The user receives a notification about a new 30% discount code for electronics items in the
    shopping app. The user has a contact, Sarah Martinez, whose contact description indicates she
    is interested in electronics and gadgets.

    The agent must:
    1. Parse the discount notification to identify the discount code and applicable product category
    2. Search contacts to identify relevant recipients based on interest matching
    3. Propose sharing the discount with Sarah
    4. After user approval, send a message to Sarah via messaging informing her about the discount

    This scenario exercises notification-triggered reasoning, cross-app correlation (shopping to
    contacts), interest-based filtering from contact metadata, and proactive sharing of
    personalized information.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize contacts app
        self.contacts = StatefulContactsApp(name="Contacts")

        # Initialize messaging app (used to deliver discount alert and message Sarah)
        self.messaging = StatefulMessagingApp(name="Messages")

        # Create Sarah Martinez - interested in electronics and gadgets
        sarah_contact = Contact(
            first_name="Sarah",
            last_name="Martinez",
            phone="+1-555-0201",
            email="sarah.martinez@email.com",
            description="Tech enthusiast interested in electronics and gadgets. Always looking for deals on new tech products.",
        )
        self.contacts.add_contact(sarah_contact)
        self.sarah_contact_id = sarah_contact.contact_id

        # Create additional contact without electronics interest
        mike_contact = Contact(
            first_name="Mike",
            last_name="Johnson",
            phone="+1-555-0202",
            email="mike.johnson@email.com",
            description="Fitness enthusiast and outdoor sports lover.",
        )
        self.contacts.add_contact(mike_contact)

        # Initialize shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Add electronics products using proper API methods
        laptop_prod_id = self.shopping.add_product(name="UltraBook Pro Laptop")
        laptop_item_id = self.shopping.add_item_to_product(
            product_id=laptop_prod_id,
            price=1299.99,
            options={"color": "silver", "storage": "512GB", "category": "electronics"},
            available=True,
        )

        headphones_prod_id = self.shopping.add_product(name="Wireless Noise-Cancelling Headphones")
        headphones_item_id = self.shopping.add_item_to_product(
            product_id=headphones_prod_id,
            price=299.99,
            options={"color": "black", "category": "electronics"},
            available=True,
        )

        watch_prod_id = self.shopping.add_product(name="Smart Fitness Watch")
        watch_item_id = self.shopping.add_item_to_product(
            product_id=watch_prod_id,
            price=399.99,
            options={"color": "black", "category": "electronics"},
            available=True,
        )

        # Add non-electronics product for contrast
        shoes_prod_id = self.shopping.add_product(name="Running Shoes")
        self.shopping.add_item_to_product(
            product_id=shoes_prod_id,
            price=129.99,
            options={"size": "10", "color": "blue", "category": "sports"},
            available=True,
        )

        # Add discount code TECH30 that applies to electronics items only
        self.shopping.add_discount_code(item_id=laptop_item_id, discount_code={"TECH30": 30.0})
        self.shopping.add_discount_code(item_id=headphones_item_id, discount_code={"TECH30": 30.0})
        self.shopping.add_discount_code(item_id=watch_item_id, discount_code={"TECH30": 30.0})

        # Seed messaging users + a "Shopping Alerts" group for discount notification
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
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")

        with EventRegisterer.capture_mode():
            # Environment Event: Shopping alert arrives mentioning the discount code + electronics category
            discount_alert_event = messaging_app.create_and_add_message(
                conversation_id=self.shop_alerts_conversation_id,
                sender_id=self.shop_sender_id,
                content="New promo: TECH30 gives 30% off electronics items today. Use code TECH30 at checkout. Share it with your contacts today!",
            ).delayed(10)

            # Oracle Event 1: Agent reads the alert to extract code + category
            read_alert_event = (
                messaging_app.read_conversation(
                    conversation_id=self.shop_alerts_conversation_id,
                    offset=0,
                    limit=10,
                )
                .oracle()
                .depends_on([discount_alert_event], delay_seconds=2)
            )

            # Oracle Event 2: Agent searches contacts for electronics interest
            search_contacts_event = (
                contacts_app.search_contacts(query="electronics")
                .oracle()
                .depends_on([read_alert_event], delay_seconds=2)
            )

            # Oracle Event 3: Agent retrieves Sarah's contact details
            get_contact_event = (
                contacts_app.get_contact(contact_id=self.sarah_contact_id)
                .oracle()
                .depends_on([search_contacts_event], delay_seconds=1)
            )

            # Oracle Event 4: Agent retrieves discount code info
            get_discount_info_event = (
                shopping_app.get_discount_code_info(discount_code="TECH30")
                .oracle()
                .depends_on([read_alert_event], delay_seconds=1)
            )

            # Oracle Event 5: Agent proposes sharing the discount with Sarah
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed a new 30% discount code (TECH30) for electronics items. Your contact Sarah Martinez is interested in electronics and gadgets. Would you like me to share this discount with her?"
                )
                .oracle()
                .depends_on([get_contact_event, get_discount_info_event], delay_seconds=2)
            )

            # Oracle Event 6: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please share the discount with Sarah.")
                .oracle()
                .depends_on([proposal_event], delay_seconds=2)
            )

            # Oracle Event 7: Agent sends the discount code to Sarah via messaging
            send_to_sarah_event = (
                messaging_app.send_message(
                    user_id=self.sarah_user_id,
                    content="Hey Sarah - I saw a promo for electronics: code TECH30 gives 30% off eligible electronics items. Thought you might like it!",
                )
                .oracle()
                .depends_on([acceptance_event], delay_seconds=2)
            )

            # Oracle Event 8: Agent confirms completion to the user
            confirmation_event = (
                aui.send_message_to_user(
                    content="Done - I messaged Sarah Martinez with the TECH30 electronics discount code."
                )
                .oracle()
                .depends_on([send_to_sarah_event], delay_seconds=1)
            )

        self.events = [
            discount_alert_event,
            read_alert_event,
            search_contacts_event,
            get_contact_event,
            get_discount_info_event,
            proposal_event,
            acceptance_event,
            send_to_sarah_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate essential outcomes: proposal sent and message sent to Sarah."""
        try:
            log_entries = env.event_log.list_view()
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # Essential outcome 1: Agent proposed sharing discount with Sarah
            proposal_sent = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PAREAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # Essential outcome 2: Agent sent message to Sarah with the discount code
            message_sent_to_sarah = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and "TECH30" in e.action.args.get("content", "")
                for e in agent_events
            )

            success = proposal_sent and message_sent_to_sarah

            if not success:
                missing = []
                if not proposal_sent:
                    missing.append("proposal to share discount")
                if not message_sent_to_sarah:
                    missing.append("message to Sarah with TECH30")

                rationale = f"Validation failed: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
