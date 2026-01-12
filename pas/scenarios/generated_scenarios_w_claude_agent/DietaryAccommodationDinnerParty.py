"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.calendar import CalendarEvent
from are.simulation.apps.shopping import CartItem, Item, Order, Product
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
)
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("dietary_accommodation_dinner_party")
class DietaryAccommodationDinnerParty(PASScenario):
    """Agent accommodates updated dietary restrictions for an upcoming dinner party guest.

    The user has a calendar event "Dinner Party at Home" scheduled for Saturday evening with several attendees including Rachel Foster. The user previously placed a shopping order for party supplies and ingredients that includes items containing gluten and dairy. The user receives a message from Rachel Foster (an existing contact) explaining that she recently developed lactose intolerance and celiac disease, and apologizing for the last-minute dietary update. The agent must:
    1. Parse the dietary restriction information from the incoming message using `search_contacts()` to locate Rachel's contact record
    2. Search the calendar via `search_events()` or `read_today_calendar_events()` to find upcoming events where Rachel is an attendee
    3. Identify the dinner party event and retrieve attendee list via `list_attendees()`
    4. Check recent shopping orders using `list_orders()` and examine order details via `get_order_details()` to identify items containing gluten or dairy
    5. Infer that the existing order may not accommodate Rachel's new dietary restrictions
    6. Propose canceling the current order and placing a new order with gluten-free and dairy-free alternatives
    7. After user acceptance, cancel the problematic order via `cancel_order()` and search for suitable replacement products using `search_product()`
    8. Add appropriate gluten-free and dairy-free items to cart via `add_to_cart()` and complete checkout with `checkout()`

    This scenario exercises cross-app information synthesis (messaging → contact lookup → calendar event correlation → shopping order modification), proactive dietary accommodation reasoning, and multi-step transactional workflow coordination..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with baseline data for dietary accommodation scenario."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize calendar app with upcoming dinner party event
        self.calendar = StatefulCalendarApp(name="Calendar")
        # Saturday evening dinner party (Nov 23, 2025 at 7:00 PM for 3 hours)
        dinner_party_start = datetime(2025, 11, 23, 19, 0, 0, tzinfo=UTC).timestamp()
        dinner_party_end = datetime(2025, 11, 23, 22, 0, 0, tzinfo=UTC).timestamp()
        dinner_event = CalendarEvent(
            title="Dinner Party at Home",
            start_datetime=dinner_party_start,
            end_datetime=dinner_party_end,
            description="Hosting dinner party for friends",
            location="Home",
            attendees=["Rachel Foster", "David Martinez", "Sarah Chen"],
        )
        self.calendar.set_calendar_event(dinner_event)

        # Initialize shopping app with product catalog and existing order
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Add products to catalog
        # Product 1: Lasagna (contains gluten and dairy)
        lasagna_product = Product(name="Classic Beef Lasagna", product_id="prod_lasagna_001")
        lasagna_item = Item(
            item_id="item_lasagna_001",
            price=18.99,
            available=True,
            options={"size": "family", "contains": "wheat, dairy"},
        )
        lasagna_product.variants["item_lasagna_001"] = lasagna_item
        self.shopping.products["prod_lasagna_001"] = lasagna_product

        # Product 2: Cheese platter (contains dairy)
        cheese_product = Product(name="Artisan Cheese Platter", product_id="prod_cheese_001")
        cheese_item = Item(
            item_id="item_cheese_001",
            price=24.50,
            available=True,
            options={"variety": "mixed", "contains": "dairy"},
        )
        cheese_product.variants["item_cheese_001"] = cheese_item
        self.shopping.products["prod_cheese_001"] = cheese_product

        # Product 3: Garlic bread (contains gluten and dairy)
        bread_product = Product(name="Garlic Bread", product_id="prod_bread_001")
        bread_item = Item(
            item_id="item_bread_001",
            price=6.99,
            available=True,
            options={"type": "sourdough", "contains": "wheat, dairy"},
        )
        bread_product.variants["item_bread_001"] = bread_item
        self.shopping.products["prod_bread_001"] = bread_product

        # Product 4: Tiramisu (contains gluten and dairy)
        tiramisu_product = Product(name="Tiramisu Dessert", product_id="prod_tiramisu_001")
        tiramisu_item = Item(
            item_id="item_tiramisu_001",
            price=12.99,
            available=True,
            options={"size": "large", "contains": "wheat, dairy, eggs"},
        )
        tiramisu_product.variants["item_tiramisu_001"] = tiramisu_item
        self.shopping.products["prod_tiramisu_001"] = tiramisu_product

        # Add gluten-free and dairy-free alternatives to catalog
        # Alternative 1: Gluten-free pasta
        gf_pasta_product = Product(name="Gluten-Free Pasta Bake", product_id="prod_gf_pasta_001")
        gf_pasta_item = Item(
            item_id="item_gf_pasta_001",
            price=19.99,
            available=True,
            options={"size": "family", "gluten_free": True, "dairy_free": True},
        )
        gf_pasta_product.variants["item_gf_pasta_001"] = gf_pasta_item
        self.shopping.products["prod_gf_pasta_001"] = gf_pasta_product

        # Alternative 2: Vegan cheese board
        vegan_cheese_product = Product(name="Vegan Cheese Board", product_id="prod_vegan_cheese_001")
        vegan_cheese_item = Item(
            item_id="item_vegan_cheese_001",
            price=26.50,
            available=True,
            options={"variety": "assorted", "dairy_free": True, "vegan": True},
        )
        vegan_cheese_product.variants["item_vegan_cheese_001"] = vegan_cheese_item
        self.shopping.products["prod_vegan_cheese_001"] = vegan_cheese_product

        # Alternative 3: Gluten-free garlic bread
        gf_bread_product = Product(name="Gluten-Free Garlic Bread", product_id="prod_gf_bread_001")
        gf_bread_item = Item(
            item_id="item_gf_bread_001",
            price=7.99,
            available=True,
            options={"type": "rice flour", "gluten_free": True, "dairy_free": True},
        )
        gf_bread_product.variants["item_gf_bread_001"] = gf_bread_item
        self.shopping.products["prod_gf_bread_001"] = gf_bread_product

        # Alternative 4: Gluten-free dairy-free dessert
        gf_dessert_product = Product(name="Chocolate Mousse (GF/DF)", product_id="prod_gf_dessert_001")
        gf_dessert_item = Item(
            item_id="item_gf_dessert_001",
            price=13.99,
            available=True,
            options={"size": "large", "gluten_free": True, "dairy_free": True},
        )
        gf_dessert_product.variants["item_gf_dessert_001"] = gf_dessert_item
        self.shopping.products["prod_gf_dessert_001"] = gf_dessert_product

        # Seed an existing order placed a few days ago (Nov 16, 2025 at 10:00 AM)
        # Construct Order directly to avoid add_order's CartItem initialization bug
        order_date = datetime(2025, 11, 16, 10, 0, 0, tzinfo=UTC)
        order_id = "order_dinner_party_001"

        # Create CartItems for all order items (containing gluten and dairy)
        lasagna_cart_item = CartItem(
            item_id="item_lasagna_001",
            quantity=1,
            price=18.99,
            available=True,
            options={"size": "family", "contains": "wheat, dairy"},
        )
        cheese_cart_item = CartItem(
            item_id="item_cheese_001",
            quantity=1,
            price=24.50,
            available=True,
            options={"variety": "mixed", "contains": "dairy"},
        )
        bread_cart_item = CartItem(
            item_id="item_bread_001",
            quantity=1,
            price=6.99,
            available=True,
            options={"type": "sourdough", "contains": "wheat, dairy"},
        )
        tiramisu_cart_item = CartItem(
            item_id="item_tiramisu_001",
            quantity=1,
            price=12.99,
            available=True,
            options={"size": "large", "contains": "wheat, dairy, eggs"},
        )

        # Create Order with all items
        dinner_party_order = Order(
            order_id=order_id,
            order_status="processed",
            order_date=order_date,
            order_total=63.47,
            order_items={
                "item_lasagna_001": lasagna_cart_item,
                "item_cheese_001": cheese_cart_item,
                "item_bread_001": bread_cart_item,
                "item_tiramisu_001": tiramisu_cart_item,
            },
        )
        self.shopping.orders[order_id] = dinner_party_order

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.calendar, self.shopping]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")

        with EventRegisterer.capture_mode():
            # Event 1: Environment event - Rachel adds a calendar event notifying about dietary restrictions
            # This serves as the exogenous trigger that the agent can observe
            rachel_event = calendar_app.add_calendar_event_by_attendee(
                who_add="Rachel Foster",
                title="New Dietary Restrictions - Gluten Free & Dairy Free Required",
                start_datetime="2025-11-18 09:30:00",
                end_datetime="2025-11-18 09:30:00",
                description="Just developed lactose intolerance and celiac disease. Need to avoid all gluten and dairy going forward.",
                attendees=["Rachel Foster"],
            ).delayed(30)

            # Oracle events follow after the environment trigger
            # Agent searches calendar for upcoming events with Rachel to assess impact
            search_rachel_events = (
                calendar_app.search_events(query="Rachel Foster").oracle().depends_on(rachel_event, delay_seconds=3)
            )

            # Agent lists orders to check for dietary conflicts with upcoming dinner party
            list_orders_event = shopping_app.list_orders().oracle().depends_on(search_rachel_events, delay_seconds=2)

            # Agent examines the dinner party order details to identify problematic items
            order_details_event = (
                shopping_app.get_order_details(order_id="order_dinner_party_001")
                .oracle()
                .depends_on(list_orders_event, delay_seconds=1)
            )

            # Agent proposes canceling the existing order and replacing with dietary-friendly alternatives
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed Rachel Foster posted a calendar event about new dietary restrictions (gluten-free and dairy-free required). You have an existing shopping order for the dinner party on Saturday that includes items with gluten and dairy. Would you like me to cancel that order and place a new one with gluten-free, dairy-free alternatives?"
                )
                .oracle()
                .depends_on(order_details_event, delay_seconds=2)
            )

            # User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please update the order to accommodate Rachel's dietary needs, and prefer to purchase Gluten-Free Pasta and Gluten-Free Garlic Bread instead."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Agent cancels the existing order
            cancel_order_event = (
                shopping_app.cancel_order(order_id="order_dinner_party_001")
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Agent searches for gluten-free pasta alternative
            search_gf_pasta_event = (
                shopping_app.search_product(product_name="Gluten-Free Pasta")
                .oracle()
                .depends_on(cancel_order_event, delay_seconds=1)
            )

            # Agent adds gluten-free pasta to cart
            add_gf_pasta_event = (
                shopping_app.add_to_cart(item_id="item_gf_pasta_001", quantity=1)
                .oracle()
                .depends_on(search_gf_pasta_event, delay_seconds=1)
            )

            # Agent searches for gluten-free bread alternative
            search_gf_bread_event = (
                shopping_app.search_product(product_name="Gluten-Free Garlic Bread")
                .oracle()
                .depends_on(add_gf_pasta_event, delay_seconds=1)
            )

            # Agent adds gluten-free bread to cart
            add_gf_bread_event = (
                shopping_app.add_to_cart(item_id="item_gf_bread_001", quantity=1)
                .oracle()
                .depends_on(search_gf_bread_event, delay_seconds=1)
            )

            # Agent completes checkout with the new dietary-friendly items
            checkout_event = shopping_app.checkout().oracle().depends_on(add_gf_bread_event, delay_seconds=2)

        # Register ALL events here in self.events
        self.events = [
            rachel_event,
            search_rachel_events,
            list_orders_event,
            order_details_event,
            proposal_event,
            acceptance_event,
            cancel_order_event,
            search_gf_pasta_event,
            add_gf_pasta_event,
            search_gf_bread_event,
            add_gf_bread_event,
            checkout_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:  # noqa: C901
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only agent events as per requirements
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent must search calendar for Rachel's upcoming events
            # Accept equivalent methods: search_events
            calendar_search_found = False
            for e in agent_events:
                if e.action.class_name == "StatefulCalendarApp" and e.action.function_name == "search_events":
                    args = e.action.args if e.action.args else e.action.resolved_args
                    # Flexible on exact query text, just verify it exists
                    if "query" in args:
                        calendar_search_found = True
                        break

            # STRICT Check 2: Agent must examine shopping orders
            # Accept equivalent methods: list_orders or get_order_details
            orders_examined = False
            for e in agent_events:
                if e.action.class_name == "StatefulShoppingApp" and e.action.function_name in [
                    "list_orders",
                    "get_order_details",
                ]:
                    orders_examined = True
                    break

            # STRICT Check 3: Agent must send proposal message to user
            # Do NOT check message content - just verify the tool was called
            proposal_sent = False
            for e in agent_events:
                if e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user":
                    proposal_sent = True
                    break

            # STRICT Check 4: Agent must cancel the original order
            order_cancelled = False
            for e in agent_events:
                if e.action.class_name == "StatefulShoppingApp" and e.action.function_name == "cancel_order":
                    args = e.action.args if e.action.args else e.action.resolved_args
                    # Verify the correct order ID is referenced
                    if args.get("order_id") == "order_dinner_party_001":
                        order_cancelled = True
                        break

            # STRICT Check 5: Agent must search for replacement products
            # Accept search_product calls
            product_searches = []
            for e in agent_events:
                if e.action.class_name == "StatefulShoppingApp" and e.action.function_name == "search_product":
                    product_searches.append(e)
            # Flexible on exact count and search terms, but must have at least 1
            replacement_products_searched = len(product_searches) >= 1

            # STRICT Check 6: Agent must add replacement items to cart
            # Count add_to_cart calls
            cart_additions = []
            for e in agent_events:
                if e.action.class_name == "StatefulShoppingApp" and e.action.function_name == "add_to_cart":
                    args = e.action.args if e.action.args else e.action.resolved_args
                    # Verify non-empty item_id exists
                    if args.get("item_id"):
                        cart_additions.append(e)
            # Must add at least 1 replacement item
            replacement_items_added = len(cart_additions) >= 1

            # STRICT Check 7: Agent must complete checkout
            checkout_completed = False
            for e in agent_events:
                if e.action.class_name == "StatefulShoppingApp" and e.action.function_name == "checkout":
                    checkout_completed = True
                    break

            # Combine all checks
            success = (
                calendar_search_found
                and orders_examined
                and proposal_sent
                and order_cancelled
                and replacement_products_searched
                and replacement_items_added
                and checkout_completed
            )

            # Build rationale if validation fails
            if not success:
                failed_checks = []
                if not calendar_search_found:
                    failed_checks.append("calendar search for Rachel's events not found")
                if not orders_examined:
                    failed_checks.append("shopping orders not examined")
                if not proposal_sent:
                    failed_checks.append("proposal message to user not sent")
                if not order_cancelled:
                    failed_checks.append("original order not cancelled")
                if not replacement_products_searched:
                    failed_checks.append("replacement products not searched")
                if not replacement_items_added:
                    failed_checks.append("replacement items not added to cart")
                if not checkout_completed:
                    failed_checks.append("checkout not completed")

                rationale = "Missing critical agent actions: " + "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
