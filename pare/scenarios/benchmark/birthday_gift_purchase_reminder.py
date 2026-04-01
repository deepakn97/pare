"""Scenario: Agent coordinates birthday gift purchase based on calendar event and contact information."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulCalendarApp,
    StatefulContactsApp,
)
from pare.apps.shopping import StatefulShoppingApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("birthday_gift_purchase_reminder")
class BirthdayGiftPurchaseReminder(PAREScenario):
    """Agent coordinates birthday gift purchase based on calendar event and contact information.

    The user has a calendar event for "Sarah Martinez's Birthday Party" scheduled for next Saturday at 6:00 PM. The user receives a shopping app notification about a flash sale on electronics including laptops. The agent must:
    1. Detect the flash sale notification and identify relevant products
    2. Check the calendar for upcoming birthdays within the next week
    3. Search contacts to retrieve details about Sarah Martinez
    4. Infer that Sarah (who works in graphic design per contact description) might appreciate a laptop as a birthday gift
    5. Propose purchasing a specific laptop from the sale before it ends
    6. Add the laptop to cart with appropriate quantity
    7. Complete checkout with any applicable discount code from the sale notification

    This scenario exercises temporal reasoning (birthday proximity), cross-app information synthesis (calendar event → contact lookup → product search), proactive shopping assistance, and deadline-sensitive task completion (flash sale expiration).
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    additional_system_prompt = """You are looking to buy a birthday gift for Sarah Martinez, who is a graphic designer.
Only accept gift suggestions that specifically mention the Creative Studio Pro Laptop, as it has features ideal for graphic design work (high color accuracy display, powerful processor).
Do not accept suggestions for other laptops like the ProBook Elite 15."""

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.contacts = StatefulContactsApp(name="Contacts")
        self.shopping = StatefulShoppingApp(name="Shopping")
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Add contact: Sarah Martinez (birthday person, graphic designer)
        self.sarah_contact_id = self.contacts.add_new_contact(
            first_name="Sarah",
            last_name="Martinez",
            gender="Female",
            age=28,
            status="Employed",
            job="Graphic Designer",
            description="Professional graphic designer specializing in digital media and visual communications",
            phone="+1-555-0123",
            email="sarah.martinez@example.com",
        )

        # Add birthday party event (4 days from start_time)
        self.calendar.add_calendar_event(
            title="Sarah Martinez's Birthday Party",
            start_datetime="2025-11-22 18:00:00",
            end_datetime="2025-11-22 21:00:00",
            description="Birthday celebration for Sarah Martinez",
            location="The Garden Restaurant",
            attendees=["Sarah Martinez"],
        )

        # Create laptop products using proper app methods
        # Product 1: ProBook Elite 15 Laptop
        probook_product_id = self.shopping.add_product(name="ProBook Elite 15 Laptop")
        self.probook_item_id = self.shopping.add_item_to_product(
            product_id=probook_product_id,
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

        # Product 2: Creative Studio Pro Laptop (ideal for graphic designers)
        creative_product_id = self.shopping.add_product(name="Creative Studio Pro Laptop")
        self.creative_item_id = self.shopping.add_item_to_product(
            product_id=creative_product_id,
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
        self.creative_product_id = creative_product_id

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.shopping, self.calendar]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")

        with EventRegisterer.capture_mode():
            # Environment event: Flash sale notification - adds discount codes for laptops
            flash_sale_notification = shopping_app.add_discount_code(
                item_id=self.creative_item_id,
                discount_code={"FLASHSALE20": 20.0},
            ).delayed(5)

            # Also add discount to the other laptop (second env event, concurrent)
            flash_sale_notification_2 = shopping_app.add_discount_code(
                item_id=self.probook_item_id,
                discount_code={"FLASHSALE20": 20.0},
            ).delayed(5)

            # Agent checks calendar for upcoming events within the next week
            calendar_check = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-18 00:00:00", end_datetime="2025-11-25 23:59:59"
                )
                .oracle()
                .depends_on(flash_sale_notification, delay_seconds=3)
            )

            # Agent searches contacts for Sarah Martinez details
            contact_search = (
                contacts_app.search_contacts(query="Sarah Martinez")
                .oracle()
                .depends_on(calendar_check, delay_seconds=3)
            )

            # Agent retrieves full contact details for Sarah
            contact_details = (
                contacts_app.get_contact(contact_id=self.sarah_contact_id)
                .oracle()
                .depends_on(contact_search, delay_seconds=2)
            )

            # Agent searches shopping catalog for laptops
            product_search = (
                shopping_app.search_product(product_name="Laptop").oracle().depends_on(contact_details, delay_seconds=4)
            )

            # Agent gets details of the Creative Studio Pro Laptop
            product_details = (
                shopping_app.get_product_details(product_id=self.creative_product_id)
                .oracle()
                .depends_on(product_search, delay_seconds=3)
            )

            # Agent proposes purchasing the laptop as a birthday gift for Sarah
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
            add_to_cart = (
                shopping_app.add_to_cart(item_id=self.creative_item_id, quantity=1)
                .oracle()
                .depends_on(acceptance, delay_seconds=3)
            )

            # Agent completes checkout with discount code
            checkout = (
                shopping_app.checkout(discount_code="FLASHSALE20").oracle().depends_on(add_to_cart, delay_seconds=4)
            )

            # Agent confirms successful purchase to user
            confirmation = (
                aui.send_message_to_user(
                    content="Purchase completed! I've ordered the Creative Studio Pro Laptop with the FLASHSALE20 discount code. The order has been placed and you saved 20% on this birthday gift for Sarah."
                )
                .oracle()
                .depends_on(checkout, delay_seconds=2)
            )

        self.events = [
            flash_sale_notification,
            flash_sale_notification_2,
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
        """Validate that agent achieved the essential outcomes for this scenario.

        Essential outcomes (what we check):
        - Agent sent proposal to user about purchasing a gift
        - Agent completed checkout with discount code

        Not checked (intermediate steps the agent might do differently):
        - How agent discovered the birthday event (calendar search method)
        - How agent looked up contact info (search vs get)
        - How agent found products (search vs browse)
        - Whether agent added to cart (implied by successful checkout)
        """
        try:
            log_entries = env.event_log.list_view()

            # CHECK 1: Agent sent proposal to user
            proposal_found = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "PAREAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # CHECK 2: Agent completed checkout with discount code
            checkout_found = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                and e.action.args.get("discount_code") == "FLASHSALE20"
                for e in log_entries
            )

            success = proposal_found and checkout_found

            if not success:
                failed_checks = []
                if not proposal_found:
                    failed_checks.append("agent did not send proposal to user")
                if not checkout_found:
                    failed_checks.append("agent did not complete checkout with FLASHSALE20 discount")
                rationale = "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
