from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.calendar import CalendarEvent
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
)
from pas.apps.reminder import StatefulReminderApp
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("calendar_product_search_suggestion")
class CalendarProductSearchSuggestion(PASScenario):
    """Agent proactively suggests shopping for items when detecting upcoming calendar events that typically require specific products.

    The user has a calendar event "Camping Trip at Yosemite" scheduled for next weekend with three attendees. A user-created reminder notification fires prompting them to prepare for the trip and explicitly calls out key missing items (tent, sleeping bags), suggesting searches in the shopping app. The agent must:
    1. Detect the reminder notification (time-driven; emitted automatically when the reminder is due)
    2. Read the full event information using `get_calendar_event()` to understand the activity type and timing
    3. Extract the explicit packing checklist items (e.g., "tent", "sleeping bag") from the reminder
    4. Search the shopping catalog for those specific items using `search_product()`
    5. Proactively offer to help the user browse camping supplies before the trip
    6. Upon user acceptance, add suggested essential items to cart for review

    This scenario exercises calendar-to-shopping grounding (explicit reminder checklist → product searches), proactive search assistance triggered by calendar reminders, context-aware product discovery without prior cart state, time-based urgency reasoning (trip approaching), and cross-app workflow initiation where calendar context drives shopping exploration.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize calendar app
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Initialize reminder app (time-driven notifications)
        self.reminder = StatefulReminderApp(name="Reminders")

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
        # Seed products via public APIs (avoid mutating internal dicts directly).
        self.tent_product_id = self.shopping.add_product("4-Person Camping Tent")
        self.tent_item_green_id = self.shopping.add_item_to_product(
            product_id=self.tent_product_id,
            price=149.99,
            options={"color": "Green", "capacity": "4 person"},
            available=True,
        )
        self.shopping.add_item_to_product(
            product_id=self.tent_product_id,
            price=149.99,
            options={"color": "Blue", "capacity": "4 person"},
            available=True,
        )

        self.sleeping_bag_product_id = self.shopping.add_product("All-Season Sleeping Bag")
        self.sleeping_bag_item_red_id = self.shopping.add_item_to_product(
            product_id=self.sleeping_bag_product_id,
            price=79.99,
            options={"color": "Red", "temperature_rating": "20F"},
            available=True,
        )
        self.shopping.add_item_to_product(
            product_id=self.sleeping_bag_product_id,
            price=79.99,
            options={"color": "Black", "temperature_rating": "20F"},
            available=True,
        )

        stove_product_id = self.shopping.add_product("Portable Camp Stove")
        self.shopping.add_item_to_product(
            product_id=stove_product_id,
            price=45.99,
            options={"size": "Compact", "fuel_type": "Propane"},
            available=True,
        )

        headlamp_product_id = self.shopping.add_product("LED Headlamp")
        self.shopping.add_item_to_product(
            product_id=headlamp_product_id,
            price=24.99,
            options={"brightness": "300 lumens", "battery": "Rechargeable"},
            available=True,
        )

        chair_product_id = self.shopping.add_product("Folding Camping Chair")
        self.shopping.add_item_to_product(
            product_id=chair_product_id,
            price=34.99,
            options={"weight_capacity": "300 lbs", "color": "Gray"},
            available=True,
        )

        cooler_product_id = self.shopping.add_product("Insulated Cooler")
        self.shopping.add_item_to_product(
            product_id=cooler_product_id,
            price=89.99,
            options={"capacity": "50 quarts", "ice_retention": "5 days"},
            available=True,
        )

        # Seed a time-driven reminder that will automatically notify the user+agent when due.
        # Following benchmark convention, set it shortly after start_time so it fires once the runner advances time.
        self.reminder.add_reminder(
            title="Yosemite trip prep — buy tent + sleeping bags",
            due_datetime="2025-11-18 09:01:00",
            description=(
                "Yosemite camping trip is coming up.\n\n"
                "We still need several big items: a tent and 3 sleeping bags. Buy these today.\n"
                'Search in Shopping: "tent" and "sleeping bag" and add options to cart so we can review before checkout.'
            ),
        )

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.calendar, self.reminder, self.shopping]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # NOTE: Reminder notifications are time-driven in the Reminders app.
            # The reminder seeded in init (`due_datetime="2025-11-18 09:01:00"`) will automatically notify user+agent.
            # The agent does NOT need to poll reminders; we model reaction time by delaying the first oracle action.

            # Oracle Event 1: Agent checks calendar to understand upcoming events context
            check_calendar_events = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-22 00:00:00",
                    end_datetime="2025-11-24 00:00:00",
                )
                .oracle()
                .delayed(70)
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
                    content="I noticed your Yosemite trip is coming up, and your reminder called out a tent and sleeping bags as missing items. Would you like me to search for those and add a few good options to your cart for review (no checkout unless you tell me to)?"
                )
                .oracle()
                .depends_on(search_sleeping_bag, delay_seconds=2)
            )

            # User Event: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please proceed.").oracle().depends_on(proposal_event, delay_seconds=5)
            )

            # Oracle Event 5: Agent gets details for tent product
            get_tent_details = (
                shopping_app.get_product_details(product_id=self.tent_product_id)
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 6: Agent adds tent to cart
            add_tent_to_cart = (
                shopping_app.add_to_cart(item_id=self.tent_item_green_id, quantity=1)
                .oracle()
                .depends_on(get_tent_details, delay_seconds=1)
            )

            # Oracle Event 7: Agent gets details for sleeping bag product
            get_bag_details = (
                shopping_app.get_product_details(product_id=self.sleeping_bag_product_id)
                .oracle()
                .depends_on(add_tent_to_cart, delay_seconds=1)
            )

            # Oracle Event 8: Agent adds sleeping bags to cart (3 attendees need sleeping bags)
            add_bags_to_cart = (
                shopping_app.add_to_cart(item_id=self.sleeping_bag_item_red_id, quantity=3)
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

        self.events = [
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

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to AGENT events only
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent sent proposal about camping supplies
            # (content-flexible: just verify the message was sent, don't check exact wording)
            proposal_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 2: Agent added tent to cart
            tent_added_to_cart = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
                and e.action.args.get("item_id") == self.tent_item_green_id
                and e.action.args.get("quantity") == 1
                for e in agent_events
            )

            # STRICT Check 3: Agent added sleeping bags to cart
            bags_added_to_cart = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
                and e.action.args.get("item_id") == self.sleeping_bag_item_red_id
                and e.action.args.get("quantity") == 3
                for e in agent_events
            )

            # Combine all strict checks
            success = proposal_found and tent_added_to_cart and bags_added_to_cart

            if not success:
                # Build rationale for failure
                failed_checks = []
                if not proposal_found:
                    failed_checks.append("proposal message not found")
                if not tent_added_to_cart:
                    failed_checks.append("tent not added to cart")
                if not bags_added_to_cart:
                    failed_checks.append("sleeping bags not added to cart")

                rationale = "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
