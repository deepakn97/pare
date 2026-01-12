"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.calendar import CalendarEvent
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
    StatefulEmailApp,
)
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("email_attachment_cart_suggestion")
class EmailAttachmentCartSuggestion(PASScenario):
    """Agent proactively suggests adding shopping items based on product recommendations received via email attachment.

    The user receives an email on December 20, 2025 at 10:00 AM from a colleague "Sarah Johnson" (sarah.johnson@company.com) with subject "Holiday Gift Ideas for Tech Enthusiasts" containing a text attachment listing recommended products: "Wireless Headphones", "Portable Charger", and "USB-C Cable Organizer". The email content says "Hey! I compiled this list of great tech gifts. Check out the attached file - these are all available on your favorite shopping site." The agent must:
    1. Detect the incoming email with product recommendation attachment
    2. Download and parse the attachment to extract product names
    3. Search the shopping catalog to verify which recommended products are actually available
    4. Identify that the user has an upcoming calendar event "Secret Santa Exchange" on December 24, 2025 requiring gift purchases
    5. Proactively offer to add the available recommended products to the shopping cart for the upcoming gift exchange
    6. Add the products to cart if the user accepts the suggestion

    This scenario exercises email attachment processing, cross-app temporal reasoning (email arrival → calendar event deadline), product search and availability checking, and proactive shopping assistance based on external recommendations correlated with calendar obligations..
    """

    start_time = datetime(2025, 12, 20, 10, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps here
        self.email = StatefulEmailApp(name="Emails")
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Populate apps with scenario specific data here

        # Calendar: Add Secret Santa Exchange event on December 24, 2025
        secret_santa_start = datetime(2025, 12, 24, 18, 0, 0, tzinfo=UTC).timestamp()
        secret_santa_end = datetime(2025, 12, 24, 21, 0, 0, tzinfo=UTC).timestamp()
        secret_santa_event = CalendarEvent(
            title="Secret Santa Exchange",
            start_datetime=secret_santa_start,
            end_datetime=secret_santa_end,
            location="Office Party Room",
            description="Annual holiday gift exchange with the team",
            tag="Social",
        )
        self.calendar.add_event(secret_santa_event)

        # Shopping: Populate catalog with products matching the recommendations
        # Product 1: Wireless Headphones
        wireless_headphones_pid = self.shopping.add_product("Wireless Headphones")
        self.shopping.add_item_to_product(
            product_id=wireless_headphones_pid,
            price=79.99,
            options={"color": "black", "type": "over-ear"},
            available=True,
        )

        # Product 2: Portable Charger
        portable_charger_pid = self.shopping.add_product("Portable Charger")
        self.shopping.add_item_to_product(
            product_id=portable_charger_pid,
            price=29.99,
            options={"capacity": "10000mAh", "color": "silver"},
            available=True,
        )

        # Product 3: USB-C Cable Organizer
        cable_organizer_pid = self.shopping.add_product("USB-C Cable Organizer")
        self.shopping.add_item_to_product(
            product_id=cable_organizer_pid,
            price=14.99,
            options={"material": "leather", "color": "brown"},
            available=True,
        )

        # Add some unrelated products to make the catalog more realistic
        laptop_stand_pid = self.shopping.add_product("Laptop Stand")
        self.shopping.add_item_to_product(
            product_id=laptop_stand_pid,
            price=39.99,
            options={"material": "aluminum", "adjustable": True},
            available=True,
        )

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.calendar, self.shopping]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Environment event: Sarah sends email with product recommendations
            email_id = "gift_recommendations_email"
            env_email = email_app.send_email_to_user_with_id(
                email_id=email_id,
                sender="sarah.johnson@company.com",
                subject="Holiday Gift Ideas for Tech Enthusiasts",
                content=(
                    "Hey! I compiled this list of great tech gifts for your Secret Santa exchange.\n"
                    "I remember you mentioned the exchange is coming up soon (Dec 24) — hopefully this helps you pick something in time:\n\n"
                    "- Wireless Headphones\n"
                    "- Portable Charger\n"
                    "- USB-C Cable Organizer\n\n"
                    "All of these are available on your favorite shopping site. Hope this helps!"
                ),
            )

            # Oracle: Agent searches inbox for the just-arrived gift email (motivated by env_email).
            search_email = (
                email_app.search_emails(query="gift", folder_name="INBOX")
                .oracle()
                .depends_on(env_email, delay_seconds=2)
            )

            # Oracle: Agent opens the email to read recommendations
            open_email = (
                email_app.get_email_by_id(email_id=email_id, folder_name="INBOX").oracle().depends_on(search_email)
            )

            # Oracle: Agent checks calendar to confirm the Secret Santa exchange timing referenced in the email (deadline/urgency).
            calendar_start = "2025-12-20 00:00:00"
            calendar_end = "2025-12-31 23:59:59"
            check_calendar = (
                calendar_app.get_calendar_events_from_to(start_datetime=calendar_start, end_datetime=calendar_end)
                .oracle()
                .depends_on(open_email)
            )

            # Oracle: Agent searches for "Wireless Headphones" in shopping catalog
            search_headphones = (
                shopping_app.search_product(product_name="Wireless Headphones").oracle().depends_on(check_calendar)
            )

            # Oracle: Agent searches for "Portable Charger"
            search_charger = (
                shopping_app.search_product(product_name="Portable Charger").oracle().depends_on(search_headphones)
            )

            # Oracle: Agent searches for "USB-C Cable Organizer"
            search_organizer = (
                shopping_app.search_product(product_name="Cable Organizer").oracle().depends_on(search_charger)
            )

            # Oracle: Agent proposes adding recommended products to cart
            proposal = (
                aui.send_message_to_user(
                    content="I noticed Sarah sent you gift recommendations for tech enthusiasts, and you have a Secret Santa Exchange on December 24th. Would you like me to add these items to your cart?"
                )
                .oracle()
                .depends_on(search_organizer)
            )

            # User: Accept the proposal
            user_accept = aui.accept_proposal(content="Yes, please add them.").delayed(5.0).depends_on(proposal)

            # Oracle: Agent lists all products
            list_products = shopping_app.list_all_products(offset=0, limit=10).oracle().depends_on(user_accept)

            # Oracle: Agent confirms found items
            confirm = (
                aui.send_message_to_user(
                    content="I've verified all three recommended items are available in the catalog and match your Secret Santa event timeline. They're ready for your review."
                )
                .oracle()
                .depends_on(list_products)
            )

        # Register ALL events here in self.events
        self.events = [
            env_email,
            search_email,
            open_email,
            check_calendar,
            search_headphones,
            search_charger,
            search_organizer,
            proposal,
            user_accept,
            list_products,
            confirm,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1: Agent searched for gift-related emails (STRICT: action must occur)
            email_search_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "search_emails"
                for e in log_entries
            )

            # Check 2: Agent retrieved the specific email with recommendations (STRICT)
            email_read_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "get_email_by_id"
                and e.action.args.get("email_id") == "gift_recommendations_email"
                for e in log_entries
            )

            # Check 3: Agent checked calendar for upcoming events (STRICT: action must occur)
            calendar_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "get_calendar_events_from_to"
                for e in log_entries
            )

            # Check 4: Agent searched for at least two of the three recommended products (STRICT: coordination logic)
            product_searches = [
                e
                for e in log_entries
                if e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "search_product"
            ]
            product_search_found = len(product_searches) >= 2

            # Check 5: Agent sent proposal message to user (STRICT: action must occur, FLEXIBLE: exact wording)
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 6: Agent listed products after user acceptance (STRICT: shows agent verified catalog)
            list_products_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "list_all_products"
                for e in log_entries
            )

            # All strict checks must pass
            success = (
                email_search_found
                and email_read_found
                and calendar_check_found
                and product_search_found
                and proposal_found
                and list_products_found
            )

            if not success:
                rationale_parts = []
                if not email_search_found:
                    rationale_parts.append("no email search found")
                if not email_read_found:
                    rationale_parts.append("did not read gift recommendations email")
                if not calendar_check_found:
                    rationale_parts.append("no calendar check found")
                if not product_search_found:
                    rationale_parts.append("insufficient product searches (need at least 2)")
                if not proposal_found:
                    rationale_parts.append("no proposal message to user found")
                if not list_products_found:
                    rationale_parts.append("did not list products after acceptance")

                rationale = "; ".join(rationale_parts)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
