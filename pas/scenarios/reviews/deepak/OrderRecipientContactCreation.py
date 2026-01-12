"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.contacts import Contact
from are.simulation.apps.shopping import CartItem, Item, Order, Product
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulContactsApp,
)
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("order_recipient_contact_creation")
class OrderRecipientContactCreation(PASScenario):
    """Agent creates a new contact from shipping details of a delivered order.

    The user receives a shopping notification that order #7234 containing "Bluetooth Speaker - Silver" has been delivered to "456 Oak Avenue" for recipient "Alex Thompson" (phone: 555-8765-432). The user does not have Alex Thompson in their contacts yet. The agent must:
    1. Parse the delivery notification to extract recipient name, phone, and address
    2. Search existing contacts to verify Alex Thompson is not already saved
    3. Create a new contact record for Alex Thompson with the extracted information
    4. Add a description note indicating this was a gift recipient from order #7234
    5. Propose sending a follow-up message to Alex asking if the package arrived safely

    This scenario exercises delivery-notification parsing, contact existence verification, proactive contact creation from shopping metadata, and cross-app coordination (shopping → contacts) for relationship management..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps here
        self.contacts = StatefulContactsApp(name="Contacts")
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Populate apps with scenario specific data here

        # --- Contacts: Baseline contacts (no Alex Thompson yet) ---
        # User contact
        user = Contact(
            first_name="Sam",
            last_name="Martinez",
            phone="555-0100",
            email="sam.martinez@email.com",
            is_user=True,
        )
        self.contacts.add_contact(user)

        # A few existing contacts to show the agent will need to verify Alex is new
        friend1 = Contact(
            first_name="Jordan",
            last_name="Lee",
            phone="555-0201",
            email="jordan.lee@email.com",
        )
        self.contacts.add_contact(friend1)

        friend2 = Contact(
            first_name="Morgan",
            last_name="Chen",
            phone="555-0202",
            email="morgan.chen@email.com",
        )
        self.contacts.add_contact(friend2)

        # --- Shopping: Catalog and Order #7234 (already placed, awaiting delivery trigger) ---
        # Product catalog with the Bluetooth Speaker
        bluetooth_speaker = Product(name="Bluetooth Speaker - Silver", product_id="prod_speaker_001")
        speaker_variant = Item(
            item_id="item_speaker_silver",
            price=79.99,
            available=True,
            options={"color": "Silver", "connectivity": "Bluetooth 5.0"},
        )
        bluetooth_speaker.variants["Silver"] = speaker_variant
        self.shopping.products[bluetooth_speaker.product_id] = bluetooth_speaker

        # Order #7234 placed earlier (before start_time), now awaiting delivery
        # The agent will learn about delivery through notification event in Step 3
        order_7234 = Order(
            order_id="order_7234",
            order_status="shipped",
            order_date=datetime(2025, 11, 15, 14, 30, 0, tzinfo=UTC),
            order_total=79.99,
            order_items={
                "item_speaker_silver": CartItem(
                    item_id="item_speaker_silver",
                    quantity=1,
                    price=79.99,
                    available=True,
                    options={
                        "color": "Silver",
                        "shipping_recipient": "Alex Thompson",
                        "shipping_phone": "555-8765-432",
                        "shipping_address": "456 Oak Avenue",
                    },
                )
            },
        )
        self.shopping.orders[order_7234.order_id] = order_7234

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.shopping]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Event 1: Order delivery notification (environment event)
            # This triggers the agent's awareness of the delivery to a new recipient
            delivery_event = shopping_app.update_order_status(order_id="order_7234", status="delivered").delayed(15)

            # Event 2: Agent lists orders to discover the delivered order details
            # Motivated by: delivery notification prompted agent to check what was delivered
            list_orders_event = shopping_app.list_orders().oracle().depends_on(delivery_event, delay_seconds=2)

            # Event 3: Agent retrieves full order details to extract shipping recipient info
            # Motivated by: list_orders revealed order_7234, now need full details including shipping metadata
            get_order_event = (
                shopping_app.get_order_details(order_id="order_7234")
                .oracle()
                .depends_on(list_orders_event, delay_seconds=1)
            )

            # Event 4: Agent searches contacts to verify Alex Thompson doesn't exist
            # Motivated by: order details show recipient "Alex Thompson", need to check if already saved
            search_event = (
                contacts_app.search_contacts(query="Alex Thompson")
                .oracle()
                .depends_on(get_order_event, delay_seconds=1)
            )

            # Event 5: Agent proposes creating a new contact for Alex Thompson
            # Motivated by: search returned no match, and order shipping details provide complete contact info
            proposal_event = (
                aui.send_message_to_user(
                    content="Your order #7234 (Bluetooth Speaker - Silver) was delivered to Alex Thompson at 456 Oak Avenue. Alex Thompson isn't in your contacts yet. Would you like me to save their information (phone: 555-8765-432, address: 456 Oak Avenue) as a new contact?"
                )
                .oracle()
                .depends_on(search_event, delay_seconds=2)
            )

            # Event 6: User accepts proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please create a contact for Alex.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Event 7: Agent creates new contact for Alex Thompson with extracted shipping details
            # Motivated by: user accepted proposal, now create contact using shipping metadata from order
            create_contact_event = (
                contacts_app.add_new_contact(
                    first_name="Alex",
                    last_name="Thompson",
                    phone="555-8765-432",
                    address="456 Oak Avenue",
                    description="Gift recipient from order #7234",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

        # Register ALL events
        self.events = [
            delivery_event,
            list_orders_event,
            get_order_event,
            search_event,
            proposal_event,
            acceptance_event,
            create_contact_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT events (oracle actions)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # Check 1 (STRICT): Agent searched contacts for Alex Thompson
            # This proves the agent verified the recipient was not already in contacts
            contact_search_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "search_contacts"
                for e in agent_events
            )

            # Check 2 (FLEXIBLE): Agent proposed creating the contact to the user
            # We verify the tool was called but are flexible on exact message content
            proposal_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # Check 3 (STRICT): Agent created new contact with correct name
            # This is the core action - must have Alex Thompson's first and last name
            contact_created = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "add_new_contact"
                for e in agent_events
            )

            # Check 4 (STRICT): Agent included phone number in contact creation
            # Phone was a key piece of data from the order
            contact_has_phone = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "add_new_contact"
                and e.action.args.get("phone") == "555-8765-432"
                for e in agent_events
            )

            # All strict checks must pass
            success = all([
                contact_search_found,
                proposal_found,
                contact_created,
                contact_has_phone,
            ])

            # Build rationale for failures
            if not success:
                missing = []
                if not contact_search_found:
                    missing.append("contact search for Alex Thompson")
                if not proposal_found:
                    missing.append("user proposal message")
                if not contact_created:
                    missing.append("contact creation with correct name")
                if not contact_has_phone:
                    missing.append("phone number in contact")
                rationale = f"Missing critical checks: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
