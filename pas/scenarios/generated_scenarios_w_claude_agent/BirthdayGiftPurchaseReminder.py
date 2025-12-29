"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.calendar import CalendarEvent
from are.simulation.apps.contacts import Contact, Gender, Status
from are.simulation.apps.shopping import Item, Product
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
    StatefulContactsApp,
)
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("birthday_gift_purchase_reminder")
class BirthdayGiftPurchaseReminder(PASScenario):
    """Agent coordinates birthday gift purchase based on calendar event and contact information.

    The user has a calendar event for "Sarah Martinez's Birthday Party" scheduled for next Saturday at 6:00 PM. The user receives a shopping app notification about a flash sale on electronics including laptops. The agent must:
    1. Detect the flash sale notification and identify relevant products
    2. Check the calendar for upcoming birthdays within the next week
    3. Search contacts to retrieve details about Sarah Martinez
    4. Infer that Sarah (who works in graphic design per contact description) might appreciate a laptop as a birthday gift
    5. Propose purchasing a specific laptop from the sale before it ends
    6. Add the laptop to cart with appropriate quantity
    7. Complete checkout with any applicable discount code from the sale notification

    This scenario exercises temporal reasoning (birthday proximity), cross-app information synthesis (calendar event → contact lookup → product search), proactive shopping assistance, and deadline-sensitive task completion (flash sale expiration)..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.contacts = StatefulContactsApp(name="Contacts")
        self.shopping = StatefulShoppingApp(name="Shopping")
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Populate Contacts app with baseline data
        # Add contact: Sarah Martinez (birthday person, graphic designer)
        sarah = Contact(
            first_name="Sarah",
            last_name="Martinez",
            gender=Gender.FEMALE,
            age=28,
            status=Status.EMPLOYED,
            job="Graphic Designer",
            description="Professional graphic designer specializing in digital media and visual communications",
            phone="+1-555-0123",
            email="sarah.martinez@example.com",
        )
        self.contacts.add_contact(sarah)

        # Add current user contact
        user = Contact(
            first_name="Alex",
            last_name="Johnson",
            is_user=True,
            phone="+1-555-9999",
            email="alex.johnson@example.com",
        )
        self.contacts.add_contact(user)

        # Populate Calendar app with baseline data
        # Birthday party event on Saturday, November 22, 2025 at 6:00 PM (4 days from start_time)
        birthday_event = CalendarEvent(
            title="Sarah Martinez's Birthday Party",
            start_datetime=datetime(2025, 11, 22, 18, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 11, 22, 21, 0, 0, tzinfo=UTC).timestamp(),
            tag="personal",
            description="Birthday celebration for Sarah Martinez",
            location="The Garden Restaurant",
            attendees=["Sarah Martinez", "Alex Johnson"],
        )
        self.calendar.set_calendar_event(birthday_event)

        # Populate Shopping app with baseline product catalog
        # Create laptop products for the flash sale
        laptop_product = Product(
            name="ProBook Elite 15 Laptop",
        )
        laptop_item = Item(
            price=899.99,
            available=True,
            options={
                "brand": "TechPro",
                "screen_size": "15.6 inch",
                "processor": "Intel Core i7",
                "ram": "16GB",
                "storage": "512GB SSD",
                "color": "Silver",
            },
        )
        laptop_product.variants["default"] = laptop_item
        self.shopping.products[laptop_product.product_id] = laptop_product

        # Add another laptop option
        creative_laptop_product = Product(
            name="Creative Studio Pro Laptop",
        )
        creative_item = Item(
            price=1299.99,
            available=True,
            options={
                "brand": "DesignTech",
                "screen_size": "16 inch",
                "processor": "Intel Core i9",
                "ram": "32GB",
                "storage": "1TB SSD",
                "color": "Space Gray",
                "features": "High color accuracy display, perfect for graphic design",
            },
        )
        creative_laptop_product.variants["default"] = creative_item
        self.shopping.products[creative_laptop_product.product_id] = creative_laptop_product

        # Add discount code for the flash sale
        self.shopping.discount_codes[laptop_item.item_id] = {"FLASHSALE20": 0.20}
        self.shopping.discount_codes[creative_item.item_id] = {"FLASHSALE20": 0.20}

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.shopping, self.calendar]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")

        with EventRegisterer.capture_mode():
            # Environment event: Shopping app notifies about flash sale with discount code
            # This provides the exogenous trigger that motivates the agent to act
            flash_sale_notification = shopping_app.add_discount_code(
                item_id=next(iter(shopping_app.products.values())).variants["default"].item_id,
                discount_code={"FLASHSALE20": 20.0},
            )

            # Agent checks calendar for upcoming events within the next week
            # Motivated by: flash sale notification suggests limited-time opportunity, prompting agent to check for relevant upcoming occasions
            calendar_check = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-18 00:00:00", end_datetime="2025-11-25 23:59:59"
                )
                .oracle()
                .delayed(5)
            )

            # Agent searches contacts for Sarah Martinez details
            # Motivated by: calendar check revealed "Sarah Martinez's Birthday Party" event, so agent needs contact info to understand who Sarah is
            contact_search = (
                contacts_app.search_contacts(query="Sarah Martinez")
                .oracle()
                .depends_on(calendar_check, delay_seconds=3)
            )

            # Agent retrieves full contact details for Sarah
            # Motivated by: search returned Sarah's contact_id, now agent needs full profile (including job: Graphic Designer) to infer gift preferences
            contact_details = (
                contacts_app.get_contact(contact_id=next(iter(contacts_app.contacts.values())).contact_id)
                .oracle()
                .depends_on(contact_search, delay_seconds=2)
            )

            # Agent searches shopping catalog for laptops
            # Motivated by: contact details revealed Sarah is a Graphic Designer, and flash sale is on electronics including laptops suitable for design work
            product_search = (
                shopping_app.search_product(product_name="Laptop").oracle().depends_on(contact_details, delay_seconds=4)
            )

            # Agent gets details of the Creative Studio Pro Laptop
            # Motivated by: product search returned laptops; agent examines the one with "graphic design" features mentioned in options
            product_details = (
                shopping_app.get_product_details(product_id=list(shopping_app.products.values())[1].product_id)
                .oracle()
                .depends_on(product_search, delay_seconds=3)
            )

            # Agent proposes purchasing the laptop as a birthday gift for Sarah
            # Motivated by: synthesized evidence shows (1) Sarah's birthday in 4 days, (2) she's a graphic designer, (3) suitable laptop on sale with discount
            proposal = (
                aui.send_message_to_user(
                    content="I noticed Sarah Martinez's birthday party is coming up on Saturday (Nov 22). I also see there's a flash sale on electronics with a 20% discount code (FLASHSALE20). Since Sarah is a graphic designer, the Creative Studio Pro Laptop would make an excellent gift - it features a high color accuracy display perfect for design work. Would you like me to add it to your cart and complete the purchase?"
                )
                .oracle()
                .depends_on(product_details, delay_seconds=5)
            )

            # User accepts the proposal
            acceptance = (
                aui.accept_proposal(
                    content="Yes, that's a great idea! Please go ahead and purchase it with the discount code."
                )
                .oracle()
                .depends_on(proposal, delay_seconds=10)
            )

            # Agent adds the laptop to cart
            # Motivated by: user accepted the proposal to purchase the laptop
            add_to_cart = (
                shopping_app.add_to_cart(
                    item_id=list(shopping_app.products.values())[1].variants["default"].item_id, quantity=1
                )
                .oracle()
                .depends_on(acceptance, delay_seconds=3)
            )

            # Agent completes checkout with discount code
            # Motivated by: item is now in cart and user requested purchase with the discount code
            checkout = (
                shopping_app.checkout(discount_code="FLASHSALE20").oracle().depends_on(add_to_cart, delay_seconds=4)
            )

            # Agent confirms successful purchase to user
            # Motivated by: checkout completed successfully, user should be informed of the order completion
            confirmation = (
                aui.send_message_to_user(
                    content="Purchase completed! I've ordered the Creative Studio Pro Laptop with the FLASHSALE20 discount code. The order has been placed and you saved 20% on this birthday gift for Sarah."
                )
                .oracle()
                .depends_on(checkout, delay_seconds=2)
            )

        # Register ALL events here in self.events
        self.events = [
            flash_sale_notification,
            calendar_check,
            contact_search,
            contact_details,
            product_search,
            product_details,
            proposal,
            acceptance,
            add_to_cart,
            checkout,
            confirmation,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT type events for all checks
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent checked calendar for upcoming events
            # This is a critical reasoning step - agent must examine the calendar to discover the birthday party
            calendar_check_found = any(
                e.action.class_name == "StatefulCalendarApp" and e.action.function_name == "get_calendar_events_from_to"
                for e in agent_events
            )

            # STRICT Check 2: Agent searched or retrieved contact information for Sarah Martinez
            # Agent must access contact data to learn Sarah's profession (Graphic Designer)
            # Accept either search_contacts OR get_contact as both achieve the goal
            contact_lookup_found = any(
                e.action.class_name == "StatefulContactsApp"
                and e.action.function_name in ["search_contacts", "get_contact"]
                for e in agent_events
            )

            # STRICT Check 3: Agent searched for products (laptops)
            # Agent must explore the shopping catalog to find suitable gift options
            # Accept either search_product OR get_product_details as both achieve product discovery
            product_search_found = any(
                e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name in ["search_product", "get_product_details"]
                for e in agent_events
            )

            # STRICT Check 4: Agent proposed the purchase to the user
            # This is critical - agent must explicitly communicate the gift suggestion to the user
            # We check for send_message_to_user but are flexible on the exact content
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 5: Agent added item to cart
            # After user acceptance, agent must actually add the laptop to the shopping cart
            add_to_cart_found = any(
                e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
                and e.action.args.get("quantity", 0) >= 1
                for e in agent_events
            )

            # STRICT Check 6: Agent completed checkout
            # Final critical action - agent must execute the purchase transaction
            # We verify the discount code was used but are flexible on its exact format
            checkout_found = any(
                e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                and "discount_code" in e.action.args
                and e.action.args["discount_code"]  # Verify discount_code is non-empty
                for e in agent_events
            )

            # Combine all strict checks
            success = (
                calendar_check_found
                and contact_lookup_found
                and product_search_found
                and proposal_found
                and add_to_cart_found
                and checkout_found
            )

            # Build rationale for failure cases
            if not success:
                missing = []
                if not calendar_check_found:
                    missing.append("calendar check for upcoming events")
                if not contact_lookup_found:
                    missing.append("contact lookup for Sarah Martinez")
                if not product_search_found:
                    missing.append("product search/discovery in shopping catalog")
                if not proposal_found:
                    missing.append("proposal message to user about gift purchase")
                if not add_to_cart_found:
                    missing.append("add laptop to cart action")
                if not checkout_found:
                    missing.append("checkout with discount code")

                rationale = f"Missing critical agent actions: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
