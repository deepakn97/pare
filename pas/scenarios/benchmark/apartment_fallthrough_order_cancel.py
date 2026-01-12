"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.apartment_listing import Apartment
from are.simulation.apps.shopping import CartItem, Item, Order, Product
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
)
from pas.apps.apartment import StatefulApartmentApp
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("apartment_fallthrough_order_cancel")
class ApartmentFallthroughOrderCancel(PASScenario):
    """Agent cancels furniture order when apartment application is rejected, preventing unnecessary delivery.

    The user has placed a large furniture order (expensive items like couch, dining table) and has an apartment application pending for a specific apartment they've saved. An apartment notification arrives informing the user that their rental application for "Downtown Loft 2BR" has been **rejected** or the apartment is **no longer available**. The agent must: 1) detect the apartment rejection/unavailability notification as eliminating the user's immediate housing need, 2) check the user's shopping orders to identify pending furniture orders, 3) recognize that the furniture order was likely intended for the now-unavailable apartment, 4) retrieve order details to confirm the order has not yet shipped (can still be cancelled), 5) propose cancelling the furniture order to prevent delivery to an address the user doesn't have, and 6) cancel the order if user accepts.

    This scenario exercises reverse dependency reasoning (apartment failure → shopping cleanup), proactive loss mitigation, cross-app temporal reasoning (application rejection arrives before furniture ships), and multi-step coordination where housing failure triggers e-commerce action to prevent wasted expense.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Apartment App
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Seed baseline apartment listings - user has one saved apartment they applied to
        downtown_loft_id = "apt_downtown_loft_2br_001"
        self.apartment.apartments[downtown_loft_id] = Apartment(
            apartment_id=downtown_loft_id,
            name="Downtown Loft 2BR",
            location="Downtown",
            zip_code="90001",
            price=2800.0,
            bedrooms=2,
            bathrooms=2,
            property_type="Loft",
            square_footage=1200,
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Parking", "Gym", "Rooftop deck"],
            saved=True,
        )
        self.apartment.saved_apartments = [downtown_loft_id]

        # Initialize Shopping App
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Seed furniture products
        couch_product_id = "prod_modern_couch_001"
        couch_item_id = "item_couch_gray_001"
        dining_table_product_id = "prod_dining_table_001"
        dining_table_item_id = "item_table_oak_001"

        # Modern Couch product
        self.shopping.products[couch_product_id] = Product(
            product_id=couch_product_id,
            name="Modern Sectional Couch",
            variants={
                couch_item_id: Item(
                    item_id=couch_item_id,
                    price=1299.99,
                    available=True,
                    options={"color": "Gray", "size": "3-seater"},
                )
            },
        )

        # Dining Table product
        self.shopping.products[dining_table_product_id] = Product(
            product_id=dining_table_product_id,
            name="Oak Dining Table",
            variants={
                dining_table_item_id: Item(
                    item_id=dining_table_item_id,
                    price=799.99,
                    available=True,
                    options={"material": "Oak", "seats": "6"},
                )
            },
        )

        # Seed an existing furniture order placed 2 days ago (still "processed", not shipped yet)
        furniture_order_id = "order_furniture_001"
        order_date = datetime(2025, 11, 16, 14, 30, 0, tzinfo=UTC)
        order_total = 1299.99 + 799.99  # couch + table

        self.shopping.orders[furniture_order_id] = Order(
            order_id=furniture_order_id,
            order_status="processed",
            order_date=order_date,
            order_total=order_total,
            order_items={
                couch_item_id: CartItem(
                    item_id=couch_item_id,
                    quantity=1,
                    price=1299.99,
                    available=True,
                    options={"color": "Gray", "size": "3-seater"},
                ),
                dining_table_item_id: CartItem(
                    item_id=dining_table_item_id,
                    quantity=1,
                    price=799.99,
                    available=True,
                    options={"material": "Oak", "seats": "6"},
                ),
            },
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.apartment, self.shopping]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Environment event 1: Apartment application is rejected (apartment is removed from listing)
            # This triggers the entire scenario - user's saved apartment becomes unavailable
            apartment_rejection_event = apartment_app.delete_apartment(
                apartment_id="apt_downtown_loft_2br_001"
            ).delayed(15)

            # Oracle event 1: Agent checks user's orders to find pending furniture deliveries
            # Motivated by: apartment rejection notification suggests user no longer has housing secured
            list_orders_event = (
                shopping_app.list_orders().oracle().depends_on(apartment_rejection_event, delay_seconds=3)
            )

            # Oracle event 2: Agent retrieves order details to confirm status and items
            # Motivated by: list_orders output reveals order_furniture_001 exists; need details to verify it's cancellable
            get_order_details_event = (
                shopping_app.get_order_details(order_id="order_furniture_001")
                .oracle()
                .depends_on(list_orders_event, delay_seconds=2)
            )

            # Oracle event 3: Agent proposes cancelling the furniture order
            # Motivated by: order details show "processed" status (not shipped), and apartment rejection means no delivery address
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed that your application for Downtown Loft 2BR was rejected and the listing has been removed. You have a pending furniture order (couch and dining table, $2,099.98 total) that hasn't shipped yet. Would you like me to cancel this order to avoid delivery complications?"
                )
                .oracle()
                .depends_on(get_order_details_event, delay_seconds=2)
            )

            # Oracle event 4: User accepts the proposal to cancel
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please cancel the furniture order. I'll need to find a new apartment first."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle event 5: Agent cancels the furniture order
            # Motivated by: user explicitly accepted the cancellation proposal
            cancel_order_event = (
                shopping_app.cancel_order(order_id="order_furniture_001")
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle event 6: Agent confirms completion to user
            # Motivated by: cancel_order completed successfully, user should be notified
            confirmation_event = (
                aui.send_message_to_user(
                    content="I've cancelled your furniture order. You should receive a refund of $2,099.98 within 5-7 business days."
                )
                .oracle()
                .depends_on(cancel_order_event, delay_seconds=1)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            apartment_rejection_event,
            list_orders_event,
            get_order_details_event,
            proposal_event,
            acceptance_event,
            cancel_order_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:  # noqa: C901
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT events (oracle actions)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent listed orders to identify pending furniture deliveries
            list_orders_found = False
            for e in agent_events:
                if e.action.class_name == "StatefulShoppingApp" and e.action.function_name == "list_orders":
                    list_orders_found = True
                    break

            # STRICT Check 2: Agent retrieved order details for the furniture order
            get_order_details_found = False
            order_id_checked = None
            for e in agent_events:
                if e.action.class_name == "StatefulShoppingApp" and e.action.function_name == "get_order_details":
                    args = e.action.args if e.action.args else e.action.resolved_args
                    order_id_checked = args.get("order_id", "")
                    if order_id_checked:
                        get_order_details_found = True
                        break

            # STRICT Check 3: Agent sent a proposal message to the user
            # Content check is FLEXIBLE - only verify the tool was called
            proposal_sent = False
            for e in agent_events:
                if e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user":
                    proposal_sent = True
                    break

            # STRICT Check 4: Agent cancelled the furniture order
            cancel_order_found = False
            cancelled_order_id = None
            for e in agent_events:
                if e.action.class_name == "StatefulShoppingApp" and e.action.function_name == "cancel_order":
                    args = e.action.args if e.action.args else e.action.resolved_args
                    cancelled_order_id = args.get("order_id", "")
                    if cancelled_order_id:
                        cancel_order_found = True
                        break

            # FLEXIBLE Check: The cancelled order should be the same as the one we checked details for
            # This is structurally important for logical consistency
            order_id_consistency = True
            if get_order_details_found and cancel_order_found and order_id_checked and cancelled_order_id:
                order_id_consistency = order_id_checked == cancelled_order_id

            # Assemble success criteria
            success = (
                list_orders_found
                and get_order_details_found
                and proposal_sent
                and cancel_order_found
                and order_id_consistency
            )

            # Build rationale for failures
            rationale_parts = []
            if not list_orders_found:
                rationale_parts.append("agent did not list orders")
            if not get_order_details_found:
                rationale_parts.append("agent did not retrieve order details")
            if not proposal_sent:
                rationale_parts.append("agent did not send proposal message")
            if not cancel_order_found:
                rationale_parts.append("agent did not cancel the furniture order")
            if not order_id_consistency:
                rationale_parts.append(f"order ID mismatch: checked {order_id_checked}, cancelled {cancelled_order_id}")

            rationale = "; ".join(rationale_parts) if rationale_parts else "all checks passed"

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
