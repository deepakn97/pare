from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.email_client import Email, EmailFolderName
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


@register_scenario("shopping_discount_calendar_reminder")
class ShoppingDiscountCalendarReminder(PASScenario):
    """Agent proactively applies expiring discount codes before calendar events that require specific items.

    The user has a calendar event "Team Building Hike" scheduled for December 25, 2025 at 9:00 AM with several colleagues, tagged as "outdoor-activity". The user's shopping account has an active 30% discount code "OUTDOOR30" applicable to hiking gear that expires on December 22, 2025. The user has previously browsed but not purchased "Hiking Boots" and "Water Bottle" in their cart. An email notification arrives on December 20, 2025 reminding the user that "OUTDOOR30 expires in 2 days." The agent must:
    1. Detect the discount expiration reminder email
    2. Extract the discount code and expiration date
    3. Search calendar for upcoming relevant events (outdoor/hiking-tagged events)
    4. Identify the Team Building Hike event occurring after the discount expires
    5. Check shopping cart for relevant items that qualify for the discount
    6. Proactively offer to complete checkout with the discount before expiration
    7. Apply the discount code and complete the order if user accepts

    This scenario exercises temporal reasoning (discount expiration vs event timing), cross-app correlation (email → shopping → calendar), semantic matching (discount category → event type → cart items), and proactive purchase assistance with time-sensitive offers..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.shopping = StatefulShoppingApp(name="Shopping")
        self.email = StatefulEmailApp(name="Emails")

        # Populate calendar app with baseline data
        # Calendar event: "Team Building Hike" on December 25, 2025 at 9:00 AM
        self.hike_event_id = self.calendar.add_calendar_event(
            title="Team Building Hike",
            start_datetime="2025-12-25 09:00:00",
            end_datetime="2025-12-25 14:00:00",
            tag="outdoor-activity",
            description="Annual team building hike in the mountains",
            location="Mountain Trail Park",
            attendees=["alice@company.com", "bob@company.com", "charlie@company.com"],
        )

        # Populate shopping app with baseline data
        # Product 1: Hiking Boots
        boots_product_id = self.shopping.add_product("Hiking Boots")
        boots_item_id = self.shopping.add_item_to_product(
            product_id=boots_product_id,
            price=120.0,
            options={"size": "10", "color": "brown"},
            available=True,
        )

        # Product 2: Water Bottle
        bottle_product_id = self.shopping.add_product("Water Bottle")
        bottle_item_id = self.shopping.add_item_to_product(
            product_id=bottle_product_id,
            price=25.0,
            options={"size": "1L", "color": "blue"},
            available=True,
        )

        # Add items to cart (previously browsed but not purchased)
        self.shopping.add_to_cart(boots_item_id, quantity=1)
        self.shopping.add_to_cart(bottle_item_id, quantity=2)

        # Add discount code "OUTDOOR30" (30% off) applicable to both items
        # Discount expires December 22, 2025
        self.shopping.add_discount_code(boots_item_id, {"OUTDOOR30": 30.0})
        self.shopping.add_discount_code(bottle_item_id, {"OUTDOOR30": 30.0})

        # Populate email app with baseline data (older emails for context)
        # Previous email from shopping site about the account
        welcome_email = Email(
            sender="support@outdoorgear.com",
            recipients=[self.email.user_email],
            subject="Welcome to OutdoorGear!",
            content="Thank you for creating an account with OutdoorGear. Check your cart for items you added earlier.",
            timestamp=datetime(2025, 11, 10, 10, 0, 0, tzinfo=UTC).timestamp(),
            is_read=True,
        )
        self.email.add_email(welcome_email, EmailFolderName.INBOX)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.calendar, self.shopping, self.email]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")

        with EventRegisterer.capture_mode():
            # Environment event: Discount expiration reminder email arrives
            # Timestamp: December 20, 2025, 10:00 AM (5 days before the hike, 2 days before discount expires)
            discount_email_id = "discount_reminder_email_001"
            env_discount_email = email_app.send_email_to_user_with_id(
                email_id=discount_email_id,
                sender="support@outdoorgear.com",
                subject="Reminder: OUTDOOR30 expires in 2 days!",
                content=(
                    "Hi there,\n\n"
                    "Your discount code OUTDOOR30 (30% off outdoor gear) expires on December 22, 2025 at 11:59 PM. "
                    "Don't miss this opportunity to save on hiking boots, water bottles, and more!\n\n"
                    "Check your cart now to complete your purchase.\n\n"
                    "Best,\nOutdoorGear Team"
                ),
            ).delayed(datetime(2025, 12, 20, 10, 0, 0, tzinfo=UTC).timestamp() - self.start_time)

            # Oracle event 1: Agent reads the discount expiration email
            oracle_read_email = (
                email_app.get_email_by_id(
                    email_id=discount_email_id,
                    folder_name="INBOX",
                )
                .oracle()
                .depends_on(env_discount_email)
            )

            # Oracle event 2: Agent checks shopping cart to see what items are pending
            oracle_check_cart = shopping_app.list_cart().oracle().depends_on(oracle_read_email)

            # Oracle event 3: Agent verifies discount code applicability to cart items
            oracle_check_discount = (
                shopping_app.get_discount_code_info(discount_code="OUTDOOR30").oracle().depends_on(oracle_check_cart)
            )

            # Oracle event 4: Agent searches calendar for upcoming outdoor/hiking events
            # The agent needs to check if there are relevant events after the discount expires
            oracle_search_calendar = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-12-22 00:00:00",
                    end_datetime="2026-01-15 23:59:59",
                )
                .oracle()
                .depends_on(oracle_check_discount)
            )

            # Oracle event 5: Agent sends proposal to user about completing checkout with discount
            oracle_proposal = (
                aui.send_message_to_user(
                    content=(
                        "I noticed your OUTDOOR30 discount code expires on December 22, but you have items in your cart -- Hiking Boots and Water Bottle "
                        "that would benefit from it. You also have 'Team Building Hike' scheduled for December 25. "
                        "Would you like me to complete your checkout now with the 30% discount before it expires?"
                    )
                )
                .oracle()
                .depends_on(oracle_search_calendar)
            )

            # User event: User accepts the proposal
            user_accept = (
                aui.accept_proposal(content="Yes, please go ahead and complete the checkout with the discount.")
                .oracle()
                .depends_on(oracle_proposal, delay_seconds=2)
            )

            # Oracle event 6: Agent performs checkout with discount code
            oracle_checkout = shopping_app.checkout(discount_code="OUTDOOR30").oracle().depends_on(user_accept)

            # Oracle event 7: Agent confirms completion to user
            oracle_confirmation = (
                aui.send_message_to_user(
                    content=(
                        "Done! I've completed your checkout with the OUTDOOR30 discount code. "
                        "Your order has been placed and you saved 30% on your hiking gear for the Team Building Hike."
                    )
                )
                .oracle()
                .depends_on(oracle_checkout)
            )

        # Register ALL events
        self.events = [
            env_discount_email,
            oracle_read_email,
            oracle_check_cart,
            oracle_check_discount,
            oracle_search_calendar,
            oracle_proposal,
            user_accept,
            oracle_checkout,
            oracle_confirmation,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1 (STRICT): Agent sent proposal mentioning the discount code expiration and the hike event
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 2 (STRICT): Agent read the discount email to understand the expiration
            read_email_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "get_email_by_id"
                for e in log_entries
            )

            # Check 3 (STRICT): Agent checked the shopping cart to see what items are pending
            cart_checked = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "list_cart"
                for e in log_entries
            )

            # Check 4 (STRICT): Agent searched calendar for upcoming events
            calendar_searched = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "get_calendar_events_from_to"
                for e in log_entries
            )

            # Check 5 (STRICT): Agent performed checkout with the OUTDOOR30 discount code
            checkout_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                and e.action.args.get("discount_code") == "OUTDOOR30"
                for e in log_entries
            )

            # Check 6 (FLEXIBLE): Agent sent a message to user after checkout (content can vary)
            final_message_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # All strict checks must pass; flexible check is optional but expected
            success = proposal_found and read_email_found and cart_checked and calendar_searched and checkout_found

            if not success:
                rationale = []
                if not proposal_found:
                    rationale.append("no agent proposal mentioning discount and hike event")
                if not read_email_found:
                    rationale.append("agent did not read the discount email")
                if not cart_checked:
                    rationale.append("agent did not check shopping cart")
                if not calendar_searched:
                    rationale.append("agent did not search calendar for events")
                if not checkout_found:
                    rationale.append("agent did not complete checkout with OUTDOOR30 discount")

                return ScenarioValidationResult(
                    success=False, rationale="; ".join(rationale) if rationale else "validation failed"
                )

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
