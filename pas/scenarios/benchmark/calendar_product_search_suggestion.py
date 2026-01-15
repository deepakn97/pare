"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.calendar import CalendarEvent
from are.simulation.apps.shopping import Item, Product
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
)
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("calendar_product_search_suggestion")
class CalendarProductSearchSuggestion(PASScenario):
    """Agent proactively suggests shopping for items when detecting upcoming calendar events that typically require specific products.

    The user has a calendar event "Camping Trip at Yosemite" scheduled for next weekend with three attendees. A calendar notification fires reminding the user about the upcoming camping trip and explicitly calls out key missing items (tent, sleeping bags) and suggests searching the shopping app for those items. The agent must:
    1. Detect the calendar event notification and parse the event details
    2. Read the full event information using `get_calendar_event()` to understand the activity type and timing
    3. Extract the explicit packing checklist items (e.g., "tent", "sleeping bag") from the calendar reminder
    4. Search the shopping catalog for those specific items using `search_product()`
    5. Proactively offer to help the user browse camping supplies before the trip
    6. Upon user acceptance, add suggested essential items to cart for review

    This scenario exercises calendar-to-shopping grounding (explicit reminder checklist → product searches), proactive search assistance triggered by calendar reminders, context-aware product discovery without prior cart state, time-based urgency reasoning (trip approaching), and cross-app workflow initiation where calendar context drives shopping exploration.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize calendar app
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Initialize shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Populate calendar with camping trip event
        # Event scheduled 5 days from start_time (Nov 23, 2025)
        camping_start = datetime(2025, 11, 23, 10, 0, 0, tzinfo=UTC).timestamp()
        camping_end = datetime(2025, 11, 23, 18, 0, 0, tzinfo=UTC).timestamp()

        camping_event = CalendarEvent(
            title="Camping Trip at Yosemite",
            start_datetime=camping_start,
            end_datetime=camping_end,
            tag="Outdoor",
            description="Weekend camping trip with friends at Yosemite National Park",
            location="Yosemite National Park, CA",
            attendees=["Alice Johnson", "Bob Smith", "Current User"],
        )
        self.calendar.set_calendar_event(camping_event)

        # Populate shopping catalog with camping products
        # Tent product
        tent_product = Product(name="4-Person Camping Tent", product_id="prod_tent_001")
        tent_product.variants = {
            "item_tent_green": Item(
                item_id="item_tent_green",
                price=149.99,
                available=True,
                options={"color": "Green", "capacity": "4 person"},
            ),
            "item_tent_blue": Item(
                item_id="item_tent_blue",
                price=149.99,
                available=True,
                options={"color": "Blue", "capacity": "4 person"},
            ),
        }
        self.shopping.products["prod_tent_001"] = tent_product

        # Sleeping bag product
        sleeping_bag_product = Product(name="All-Season Sleeping Bag", product_id="prod_bag_001")
        sleeping_bag_product.variants = {
            "item_bag_red": Item(
                item_id="item_bag_red",
                price=79.99,
                available=True,
                options={"color": "Red", "temperature_rating": "20F"},
            ),
            "item_bag_black": Item(
                item_id="item_bag_black",
                price=79.99,
                available=True,
                options={"color": "Black", "temperature_rating": "20F"},
            ),
        }
        self.shopping.products["prod_bag_001"] = sleeping_bag_product

        # Camping stove product
        stove_product = Product(name="Portable Camp Stove", product_id="prod_stove_001")
        stove_product.variants = {
            "item_stove_compact": Item(
                item_id="item_stove_compact",
                price=45.99,
                available=True,
                options={"size": "Compact", "fuel_type": "Propane"},
            ),
        }
        self.shopping.products["prod_stove_001"] = stove_product

        # Headlamp product
        headlamp_product = Product(name="LED Headlamp", product_id="prod_lamp_001")
        headlamp_product.variants = {
            "item_lamp_basic": Item(
                item_id="item_lamp_basic",
                price=24.99,
                available=True,
                options={"brightness": "300 lumens", "battery": "Rechargeable"},
            ),
        }
        self.shopping.products["prod_lamp_001"] = headlamp_product

        # Camping chair product
        chair_product = Product(name="Folding Camping Chair", product_id="prod_chair_001")
        chair_product.variants = {
            "item_chair_standard": Item(
                item_id="item_chair_standard",
                price=34.99,
                available=True,
                options={"weight_capacity": "300 lbs", "color": "Gray"},
            ),
        }
        self.shopping.products["prod_chair_001"] = chair_product

        # Cooler product
        cooler_product = Product(name="Insulated Cooler", product_id="prod_cooler_001")
        cooler_product.variants = {
            "item_cooler_medium": Item(
                item_id="item_cooler_medium",
                price=89.99,
                available=True,
                options={"capacity": "50 quarts", "ice_retention": "5 days"},
            ),
        }
        self.shopping.products["prod_cooler_001"] = cooler_product

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.calendar, self.shopping]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Alice (attendee) adds a reminder event about packing for the camping trip
            # This serves as the trigger - an attendee creates a related event 5 days before the main camping trip
            packing_reminder_event = calendar_app.add_calendar_event_by_attendee(
                who_add="Alice Johnson",
                title="Pack camping gear",
                start_datetime="2025-11-22 18:00:00",  # Day before camping trip
                end_datetime="2025-11-22 20:00:00",
                description=(
                    "Hey! Quick reminder to pack for Yosemite tomorrow.\n\n"
                    "Also, it looks like we still haven't bought the big two items yet: a tent and sleeping bags. "
                    "Can you please buy those today?\n\n"
                    'If you\'re shopping in the app, try searching: "tent" and "sleeping bag", and add them to your cart so we can review before checkout.'
                ),
                attendees=["Alice Johnson", "Bob Smith"],
            ).delayed(10)

            # Oracle Event 1: Agent checks calendar to understand upcoming events context
            check_calendar_events = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-22 00:00:00",
                    end_datetime="2025-11-24 00:00:00",
                )
                .oracle()
                .depends_on(packing_reminder_event, delay_seconds=3)
            )

            # Oracle Event 2: Agent searches for tent products
            # Motivation: the calendar reminder explicitly listed "tent" and suggested searching the shopping app.
            search_tent = (
                shopping_app.search_product(product_name="tent")
                .oracle()
                .depends_on(check_calendar_events, delay_seconds=2)
            )

            # Oracle Event 3: Agent searches for sleeping bag products
            # Motivation: the calendar reminder explicitly listed "sleeping bags" and suggested searching the shopping app.
            search_sleeping_bag = (
                shopping_app.search_product(product_name="sleeping bag")
                .oracle()
                .depends_on(search_tent, delay_seconds=1)
            )

            # Oracle Event 4: Agent sends proposal to help shop for camping supplies
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed your Yosemite trip is coming up, and the calendar reminder checklist called out a tent and sleeping bags. Would you like me to search for those and add a few good options to your cart for review (no checkout unless you tell me to)?"
                )
                .oracle()
                .depends_on(search_sleeping_bag, delay_seconds=2)
            )

            # User Event: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please help me find the essentials.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=5)
            )

            # Oracle Event 5: Agent gets details for tent product
            get_tent_details = (
                shopping_app.get_product_details(product_id="prod_tent_001")
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 6: Agent adds tent to cart
            add_tent_to_cart = (
                shopping_app.add_to_cart(item_id="item_tent_green", quantity=1)
                .oracle()
                .depends_on(get_tent_details, delay_seconds=1)
            )

            # Oracle Event 7: Agent gets details for sleeping bag product
            get_bag_details = (
                shopping_app.get_product_details(product_id="prod_bag_001")
                .oracle()
                .depends_on(add_tent_to_cart, delay_seconds=1)
            )

            # Oracle Event 8: Agent adds sleeping bags to cart (3 attendees need sleeping bags)
            add_bags_to_cart = (
                shopping_app.add_to_cart(item_id="item_bag_red", quantity=3)
                .oracle()
                .depends_on(get_bag_details, delay_seconds=1)
            )

            # Oracle Event 9: Agent sends summary message with cart contents
            summary_event = (
                aui.send_message_to_user(
                    content="I've added camping essentials to your cart: 1 tent and 3 sleeping bags. You can review and checkout when ready."
                )
                .oracle()
                .depends_on(add_bags_to_cart, delay_seconds=2)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            packing_reminder_event,
            check_calendar_events,
            search_tent,
            search_sleeping_bag,
            proposal_event,
            acceptance_event,
            get_tent_details,
            add_tent_to_cart,
            get_bag_details,
            add_bags_to_cart,
            summary_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:  # noqa: C901
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to AGENT events only
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent checked calendar to understand upcoming events context
            calendar_check_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "get_calendar_events_from_to"
                for e in agent_events
            )

            # STRICT Check 2: Agent searched for camping-related products (tent)
            tent_search_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "search_product"
                and "tent" in str(e.action.args.get("product_name", "")).lower()
                for e in agent_events
            )

            # STRICT Check 3: Agent searched for camping-related products (sleeping bag)
            sleeping_bag_search_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "search_product"
                and "sleeping" in str(e.action.args.get("product_name", "")).lower()
                for e in agent_events
            )

            # STRICT Check 4: Agent sent proposal about camping supplies
            # (content-flexible: just verify the message was sent, don't check exact wording)
            proposal_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 5: Agent got tent product details after acceptance
            tent_details_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_product_details"
                and e.action.args.get("product_id") == "prod_tent_001"
                for e in agent_events
            )

            # STRICT Check 6: Agent added tent to cart
            tent_added_to_cart = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
                and e.action.args.get("item_id", "").startswith("item_tent_")
                and e.action.args.get("quantity") == 1
                for e in agent_events
            )

            # STRICT Check 7: Agent got sleeping bag product details
            bag_details_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_product_details"
                and e.action.args.get("product_id") == "prod_bag_001"
                for e in agent_events
            )

            # STRICT Check 8: Agent added sleeping bags to cart (quantity 3 for attendees)
            bags_added_to_cart = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
                and e.action.args.get("item_id", "").startswith("item_bag_")
                and e.action.args.get("quantity") == 3
                for e in agent_events
            )

            # Combine all strict checks
            success = (
                calendar_check_found
                and tent_search_found
                and sleeping_bag_search_found
                and proposal_found
                and tent_details_found
                and tent_added_to_cart
                and bag_details_found
                and bags_added_to_cart
            )

            if not success:
                # Build rationale for failure
                failed_checks = []
                if not calendar_check_found:
                    failed_checks.append("calendar check not found")
                if not tent_search_found:
                    failed_checks.append("tent search not found")
                if not sleeping_bag_search_found:
                    failed_checks.append("sleeping bag search not found")
                if not proposal_found:
                    failed_checks.append("proposal message not found")
                if not tent_details_found:
                    failed_checks.append("tent product details not retrieved")
                if not tent_added_to_cart:
                    failed_checks.append("tent not added to cart")
                if not bag_details_found:
                    failed_checks.append("sleeping bag product details not retrieved")
                if not bags_added_to_cart:
                    failed_checks.append("sleeping bags (quantity 3) not added to cart")

                rationale = "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
