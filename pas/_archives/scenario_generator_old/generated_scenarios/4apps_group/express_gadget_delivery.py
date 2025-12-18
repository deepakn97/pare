from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.cab import CabApp
from are.simulation.apps.shopping import Shopping
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("express_gadget_delivery")
class ExpressGadgetDelivery(Scenario):
    """Scenario: User buys a gadget online and the assistant arranges express delivery by cab.

    This comprehensive scenario demonstrates full integration of available applications:
    - SystemApp: used to get the current time for scheduling delivery.
    - Shopping: used for searching, adding to cart, and checking out.
    - CabApp: used to find and order an express delivery ride.
    - AgentUserInterface: used to proactively propose the delivery step and get user approval.

    The scenario reproduces a realistic assistant workflow:
    1. User asks to buy a portable Bluetooth speaker.
    2. Agent searches available products, adds the best one to cart.
    3. Agent checks if discount codes can apply.
    4. Agent proposes to purchase and book express cab delivery.
    5. User approves.
    6. Agent completes the checkout and orders the cab to deliver items.
    """

    start_time: float | None = 0
    duration: float | None = 30

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all apps required for this scenario."""
        aui = AgentUserInterface()
        system = SystemApp(name="system")
        shopping = Shopping()
        cab = CabApp()

        # all apps used in the scenario
        self.apps = [aui, system, shopping, cab]

    def build_events_flow(self) -> None:
        """Define the flow of the proactive express-delivery shopping scenario."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        shopping = self.get_typed_app(Shopping)
        cab = self.get_typed_app(CabApp)

        with EventRegisterer.capture_mode():
            # 1. User asks for a portable Bluetooth speaker
            user_start = (
                aui.send_message_to_agent(
                    content="Hi assistant, I want to buy a portable Bluetooth speaker for a friend."
                )
                .depends_on(None, delay_seconds=1)
                .with_id("user_start")
            )

            # 2. Agent searches product and finds one (oracle)
            search_products = (
                shopping.search_product(product_name="Bluetooth speaker", limit=5)
                .oracle()
                .depends_on(user_start, delay_seconds=1)
            )

            # 3. Agent checks discount codes
            retrieve_discounts = shopping.get_all_discount_codes().oracle().depends_on(search_products, delay_seconds=1)

            # 4. Agent adds selected product to cart
            add_to_cart = (
                shopping.add_to_cart(item_id="speaker123", quantity=1)
                .oracle()
                .depends_on(retrieve_discounts, delay_seconds=1)
            )

            # 5. Agent proposes to buy and arrange cab delivery
            agent_proposal = aui.send_message_to_user(
                content=(
                    "I found a good portable Bluetooth speaker and added it to your cart. "
                    "Would you like me to complete the purchase and arrange express cab delivery to your friend's address?"
                )
            ).depends_on(add_to_cart, delay_seconds=1)

            # 6. User approves the purchase and delivery
            user_approval = aui.send_message_to_agent(
                content=("Yes, please proceed with the purchase and arrange express cab delivery to 42 Orchard Avenue.")
            ).depends_on(agent_proposal, delay_seconds=1)

            # 7. Agent checks out the cart (oracle ground truth)
            checkout = shopping.checkout().oracle().depends_on(user_approval, delay_seconds=1)

            # 8. Agent gets current time to use for cab quotation
            current_time = system.get_current_time().oracle().depends_on(checkout, delay_seconds=1)

            # 9. Agent requests  cab quotation for express delivery
            quotation = (
                cab.get_quotation(
                    start_location="Store Warehouse",
                    end_location="42 Orchard Avenue",
                    service_type="Van",
                    ride_time=None,
                )
                .oracle()
                .depends_on(current_time, delay_seconds=1)
            )

            # 10. Agent finalizes the cab order for express shipping
            order_cab = (
                cab.order_ride(
                    start_location="Store Warehouse",
                    end_location="42 Orchard Avenue",
                    service_type="Van",
                    ride_time=None,
                )
                .oracle()
                .depends_on(quotation, delay_seconds=1)
            )

            # 11. Agent informs user that the purchase and delivery are arranged
            final_notice = (
                aui.send_message_to_user(
                    content=(
                        "Your Bluetooth speaker has been purchased and an express delivery cab is on its way to 42 Orchard Avenue."
                    )
                )
                .oracle()
                .depends_on(order_cab, delay_seconds=1)
            )

        self.events = [
            user_start,
            search_products,
            retrieve_discounts,
            add_to_cart,
            agent_proposal,
            user_approval,
            checkout,
            current_time,
            quotation,
            order_cab,
            final_notice,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate success: agent checked out and ordered a cab after user approval."""
        try:
            events = env.event_log.list_view()
            did_checkout = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "Shopping"
                and e.action.function_name == "checkout"
                for e in events
            )
            ordered_cab = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CabApp"
                and e.action.function_name == "order_ride"
                for e in events
            )
            user_prompt_present = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "express cab delivery" in e.action.args.get("content", "").lower()
                for e in events
            )
            approval_detected = any(
                e.event_type == EventType.USER
                and "please proceed" in getattr(e.action, "args", {}).get("content", "").lower()
                for e in events
            )
            success = all([did_checkout, ordered_cab, user_prompt_present, approval_detected])
            return ScenarioValidationResult(success=success)
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
