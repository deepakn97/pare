from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.cab import CabApp
from are.simulation.apps.shopping import ShoppingApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("weekend_grocery_pickup")
class WeekendGroceryPickup(Scenario):
    """A lifestyle scenario: the agent helps user order groceries and then arranges a cab pickup for the order.

    The agent interacts with the user to propose picking up the groceries from the store
    after confirming the order checkout, using both ShoppingApp and CabApp. It features
    a proactive interaction pattern where the agent proposes an action, the user confirms,
    and the agent executes accordingly.
    """

    start_time: float | None = 0
    duration: float | None = 60

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize applications with baseline data."""
        aui = AgentUserInterface()
        store = ShoppingApp()
        ride_service = CabApp()

        # Apps available to the environment
        self.apps = [aui, store, ride_service]

    def build_events_flow(self) -> None:
        """Build the oracle event flow for the weekend grocery pickup."""
        aui = self.get_typed_app(AgentUserInterface)
        shop = self.get_typed_app(ShoppingApp)
        cab = self.get_typed_app(CabApp)

        with EventRegisterer.capture_mode():
            # Step 1: user asks the assistant to order some groceries
            user_initial = aui.send_message_to_agent(
                content="Hey Assistant, can you help me order some groceries and arrange a ride to pick them up?"
            ).depends_on(None, delay_seconds=2)

            # Step 2: agent searches for some groceries like 'organic milk'
            search_milk = (
                shop.search_product(product_name="organic milk").oracle().depends_on(user_initial, delay_seconds=2)
            )

            # Step 3: get details for the first found [mock id]
            get_info = (
                shop.get_product_details(product_id="milk_organic_1").oracle().depends_on(search_milk, delay_seconds=2)
            )

            # Step 4: add product to cart
            add_item = (
                shop.add_to_cart(item_id="milk_organic_1", quantity=2).oracle().depends_on(get_info, delay_seconds=1)
            )

            # Step 5: optionally the agent lists discount codes available
            get_codes = shop.get_all_discount_codes().oracle().depends_on(add_item, delay_seconds=2)
            # Suppose "GROCERY10" applies to all items

            # Step 6: checkout with the discount applied
            checkout = shop.checkout(discount_code="GROCERY10").oracle().depends_on(get_codes, delay_seconds=2)

            # Step 7: agent proactively proposes to book a cab for pick-up
            propose_ride = aui.send_message_to_user(
                content="Your grocery order is complete with a 10% discount. Would you like me to book a cab from your home to the grocery store for pickup?"
            ).depends_on(checkout, delay_seconds=2)

            # Step 8: user responds approving the ride booking
            user_confirms = aui.send_message_to_agent(
                content="Yes, please arrange a Premium cab from my house to GreenMart Superstore."
            ).depends_on(propose_ride, delay_seconds=2)

            # Step 9: agent checks ride quotes and availability (uses quotation and list_rides)
            ride_quote = (
                cab.get_quotation(
                    start_location="Home, Oak Street", end_location="GreenMart Superstore", service_type="Premium"
                )
                .oracle()
                .depends_on(user_confirms, delay_seconds=1)
            )

            available_rides = (
                cab.list_rides(start_location="Home, Oak Street", end_location="GreenMart Superstore")
                .oracle()
                .depends_on(ride_quote, delay_seconds=1)
            )

            # Step 10: agent orders the ride
            ride_booking = (
                cab.order_ride(
                    start_location="Home, Oak Street", end_location="GreenMart Superstore", service_type="Premium"
                )
                .oracle()
                .depends_on(available_rides, delay_seconds=2)
            )

            # Step 11: final status check (confirmation)
            ride_status = cab.get_current_ride_status().oracle().depends_on(ride_booking, delay_seconds=2)

        self.events = [
            user_initial,
            search_milk,
            get_info,
            add_item,
            get_codes,
            checkout,
            propose_ride,
            user_confirms,
            ride_quote,
            available_rides,
            ride_booking,
            ride_status,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Ensure that the scenario succeeded: groceries were checked out and a ride was booked."""
        try:
            events = env.event_log.list_view()
            confirmed_checkout = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.function_name == "checkout"
                and e.action.class_name == "ShoppingApp"
                and e.action.args.get("discount_code") == "GROCERY10"
                for e in events
            )
            ride_ordered = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.function_name == "order_ride"
                and e.action.class_name == "CabApp"
                and "GreenMart Superstore" in e.action.args.get("end_location", "")
                for e in events
            )
            proposal_made = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.function_name == "send_message_to_user"
                and e.action.class_name == "AgentUserInterface"
                and "book a cab" in e.action.args.get("content", "").lower()
                for e in events
            )
            user_approved = any(
                (e.event_type != EventType.AGENT and "Premium cab" in getattr(e.action.args, "content", ""))
                or (hasattr(e, "data") and "Premium cab" in str(e.data))
                for e in events
            )
            success = confirmed_checkout and ride_ordered and proposal_made and user_approved
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
