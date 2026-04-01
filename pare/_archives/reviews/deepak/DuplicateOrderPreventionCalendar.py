"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.calendar import CalendarEvent
from are.simulation.apps.shopping import Item, Product
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, Event, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
)
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("duplicate_order_prevention_calendar")
class DuplicateOrderPreventionCalendar(PASScenario):
    """Agent prevents duplicate product orders by correlating shopping history with calendar event notes.

    The user has placed a shopping order for "Office Desk Lamp" two weeks ago. Today, the user browses products and adds another "Office Desk Lamp" to their cart. Meanwhile, the user has a calendar event scheduled for tomorrow titled "Office Setup Day" with a note stating "desk lamp arriving tomorrow - remember to set up." The agent must:
    1. Detect the user adding a product to their cart
    2. Search order history for recent purchases of the same product
    3. Check calendar events for any mentions of the product or delivery
    4. Correlate the existing order with the calendar delivery note
    5. Proactively warn the user about the duplicate purchase
    6. Offer to remove the duplicate item from the cart

    This scenario exercises shopping history analysis, calendar content search, cross-app information synthesis (orders → calendar notes), duplicate detection logic, and proactive purchase prevention assistance..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Create "Office Desk Lamp" product with a single variant
        desk_lamp_product = Product(
            name="Office Desk Lamp",
            product_id="prod_desk_lamp_001",
        )
        desk_lamp_item = Item(
            item_id="item_desk_lamp_white",
            price=45.99,
            available=True,
            options={"color": "white", "brightness": "adjustable"},
        )
        desk_lamp_product.variants["item_desk_lamp_white"] = desk_lamp_item
        self.shopping.products["prod_desk_lamp_001"] = desk_lamp_product

        # NOTE: Past order history cannot be seeded directly in init_and_populate_apps.
        # The past order from two weeks ago will need to be created via an early
        # checkout event in build_events_flow() with a backdated timestamp, or
        # the agent will need to check order history that gets populated during the flow.

        # Initialize calendar app
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Add calendar event for tomorrow with delivery note
        tomorrow = self.start_time + (24 * 60 * 60)  # 1 day in seconds
        tomorrow_end = tomorrow + (2 * 60 * 60)  # 2-hour event
        office_setup_event = CalendarEvent(
            event_id="event_office_setup",
            title="Office Setup Day",
            start_datetime=tomorrow,
            end_datetime=tomorrow_end,
            description="desk lamp arriving tomorrow - remember to set up",
            tag="personal",
            location="Home Office",
        )
        self.calendar.events["event_office_setup"] = office_setup_event

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.shopping, self.calendar]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")

        # Seed a past order directly (workaround for add_order bug with CartItem name field)
        # This represents baseline data: a delivered order from two weeks ago
        from are.simulation.apps.shopping import CartItem, Order

        two_weeks_ago = self.start_time - (14 * 24 * 60 * 60)
        past_cart_item = CartItem(
            item_id="item_desk_lamp_white",
            quantity=1,
            price=45.99,
            available=True,
            options={"color": "white", "brightness": "adjustable"},
        )
        past_order = Order(
            order_id="order_past_desk_lamp",
            order_status="delivered",
            order_date=two_weeks_ago,
            order_total=45.99,
            order_items={"item_desk_lamp_white": past_cart_item},
        )
        shopping_app.orders["order_past_desk_lamp"] = past_order

        with EventRegisterer.capture_mode():
            # Event 2: User browses products (environment event)
            # This triggers the agent's awareness that the user is shopping
            browse_event = shopping_app.list_all_products(
                offset=0,
                limit=10,
            ).delayed(10)

            # Event 3: User views the desk lamp product (environment event)
            view_product_event = shopping_app.get_product_details(
                product_id="prod_desk_lamp_001",
            ).delayed(15)

            # Event 4: User adds desk lamp to cart (environment event)
            # This is the critical moment that should trigger agent investigation
            add_to_cart_event = shopping_app.add_to_cart(
                item_id="item_desk_lamp_white",
                quantity=1,
            ).delayed(20)

            # Event 5: Agent checks order history for recent purchases (oracle)
            check_orders_event = shopping_app.list_orders().oracle().depends_on(add_to_cart_event, delay_seconds=2)

            # Event 6: Agent searches calendar for mentions of "desk lamp" or "lamp" (oracle)
            # This allows the agent to discover the delivery note in the calendar event
            search_calendar_event = (
                calendar_app.search_events(
                    query="lamp",
                )
                .oracle()
                .depends_on(check_orders_event, delay_seconds=1)
            )

            # Event 7: Agent sends proposal to user about duplicate purchase (oracle)
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed you just added an Office Desk Lamp to your cart. You already ordered this same item two weeks ago (order_past_desk_lamp, delivered). Your calendar also shows a note for tomorrow's 'Office Setup Day' mentioning the desk lamp arrival. Would you like me to remove the duplicate item from your cart?"
                )
                .oracle()
                .depends_on(search_calendar_event, delay_seconds=2)
            )

            # Event 8: User accepts the proposal (oracle)
            acceptance_event = (
                aui.accept_proposal(content="Oh yes, you're right! Please remove it from my cart.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Event 9: Agent removes the duplicate item from cart (oracle)
            remove_from_cart_event = (
                shopping_app.remove_from_cart(
                    item_id="item_desk_lamp_white",
                    quantity=1,
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Event 10: Agent sends confirmation summary (oracle)
            summary_event = (
                aui.send_message_to_user(
                    content="Done! I've removed the Office Desk Lamp from your cart. Your original order is already on its way and should arrive tomorrow for your office setup."
                )
                .oracle()
                .depends_on(remove_from_cart_event, delay_seconds=1)
            )

        # TODO: Register ALL events here in self.events
        self.events: list[Event] = [
            browse_event,
            view_product_event,
            add_to_cart_event,
            check_orders_event,
            search_calendar_event,
            proposal_event,
            acceptance_event,
            remove_from_cart_event,
            summary_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent checked order history for recent purchases
            orders_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "list_orders"
                for e in log_entries
            )

            # STRICT Check 2: Agent searched calendar for product mentions
            calendar_search_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "search_events"
                and "lamp" in e.action.args.get("query", "").lower()
                for e in log_entries
            )

            # FLEXIBLE Check 3: Agent sent proposal to user about duplicate (content flexible)
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 4: Agent removed duplicate item from cart
            remove_from_cart_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "remove_from_cart"
                and e.action.args.get("item_id") == "item_desk_lamp_white"
                for e in log_entries
            )

            # All checks must pass for success
            success = orders_check_found and calendar_search_found and proposal_found and remove_from_cart_found

            if not success:
                missing_checks = []
                if not orders_check_found:
                    missing_checks.append("order history check")
                if not calendar_search_found:
                    missing_checks.append("calendar search for product mentions")
                if not proposal_found:
                    missing_checks.append("proposal message to user")
                if not remove_from_cart_found:
                    missing_checks.append("remove duplicate item from cart")

                rationale = f"Missing critical checks: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
