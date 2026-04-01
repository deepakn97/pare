from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.shopping import Shopping
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("online_shopping_discount_checkout")
class OnlineShoppingDiscountCheckout(Scenario):
    """Scenario: Demonstrate an intelligent assistant that helps the user shop online.

    The scenario covers:
    - Listing catalog items (Shopping)
    - Searching for a product
    - Checking valid discount codes
    - Proposing to apply a discount code proactively
    - Waiting for user confirmation
    - Checking out after confirmation
    - Getting system time and waiting for notification in between steps

    **Proactive Interaction Pattern (mandatory centerpiece):**
    - Agent proposes to apply a discount after finding eligible items
    - User responds confirming the proposal
    - Agent executes checkout with the discount code
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize AgentUserInterface, Shopping, and SystemApp."""
        aui = AgentUserInterface()
        shopping = Shopping()
        system = SystemApp(name="system-util")
        self.apps = [aui, shopping, system]

    def build_events_flow(self) -> None:
        """Define sequence of events showing intelligent shopping interaction."""
        aui = self.get_typed_app(AgentUserInterface)
        shop = self.get_typed_app(Shopping)
        sys = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # User begins the conversation
            user_request = aui.send_message_to_agent(
                content="Hey Assistant, I would like to buy a pair of wireless headphones. Can you find me some options?"
            ).depends_on(None, delay_seconds=1)

            # Agent searches products matching intent
            event_search = (
                shop.search_product(product_name="wireless headphones")
                .oracle()
                .depends_on(user_request, delay_seconds=1)
            )

            # Agent gets details on one candidate item
            event_details = (
                shop.get_product_details(product_id="headphones123").oracle().depends_on(event_search, delay_seconds=1)
            )

            # Agent lists all products for good measure (Catalog exploration)
            event_list_all = (
                shop.list_all_products(offset=0, limit=5).oracle().depends_on(event_details, delay_seconds=1)
            )

            # Agent adds the target item to cart
            event_add_cart = (
                shop.add_to_cart(item_id="headphones123", quantity=1)
                .oracle()
                .depends_on(event_list_all, delay_seconds=1)
            )

            # Agent retrieves all personal discount codes
            event_get_codes = shop.get_all_discount_codes().oracle().depends_on(event_add_cart, delay_seconds=1)

            # Agent chooses one discount code to check its validity for this item
            event_check_code = (
                shop.get_discount_code_info(discount_code="SPRING2024")
                .oracle()
                .depends_on(event_get_codes, delay_seconds=1)
            )

            # Agent proactively proposes applying the discount to user
            proactive_proposal = aui.send_message_to_user(
                content=(
                    "I found that the discount code SPRING2024 offers a 15% discount on your selected headphones. "
                    "Would you like me to apply it and complete the checkout now?"
                )
            ).depends_on(event_check_code, delay_seconds=1)

            # User gives detailed confirmation
            user_confirms = aui.send_message_to_agent(
                content="Yes, please go ahead and apply SPRING2024 for the checkout."
            ).depends_on(proactive_proposal, delay_seconds=1)

            # Agent executes checkout after user's approval
            event_checkout = (
                shop.checkout(discount_code="SPRING2024").oracle().depends_on(user_confirms, delay_seconds=1)
            )

            # Agent lists orders afterwards as confirmation retrieval
            event_list_orders = shop.list_orders().oracle().depends_on(event_checkout, delay_seconds=1)

            # System fetches current time and performs wait to simulate asynchronous delay before confirming complete
            event_current_time = sys.get_current_time().oracle().depends_on(event_list_orders, delay_seconds=1)
            event_system_wait = (
                sys.wait_for_notification(timeout=5).oracle().depends_on(event_current_time, delay_seconds=1)
            )

            # After waiting, agent sends user confirmation
            final_message = (
                aui.send_message_to_user(
                    content="Your order for wireless headphones has been successfully placed with the SPRING2024 discount!"
                )
                .oracle()
                .depends_on(event_system_wait, delay_seconds=1)
            )

        self.events = [
            user_request,
            event_search,
            event_details,
            event_list_all,
            event_add_cart,
            event_get_codes,
            event_check_code,
            proactive_proposal,
            user_confirms,
            event_checkout,
            event_list_orders,
            event_current_time,
            event_system_wait,
            final_message,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validation: confirm that the checkout event occurred after user approval."""
        try:
            events = env.event_log.list_view()

            # Ensure the checkout with 'SPRING2024' took place after the user confirmed
            checkout_done = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "Shopping"
                and event.action.function_name == "checkout"
                and event.action.args.get("discount_code") == "SPRING2024"
                for event in events
            )

            # Ensure the system time and wait were called (to validate SystemApp use)
            system_ops = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "SystemApp"
                and event.action.function_name in ["get_current_time", "wait_for_notification"]
                for event in events
            )

            # Ensure that proactive proposal was indeed sent to the user mentioning discount
            proactive_sent = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "AgentUserInterface"
                and event.action.function_name == "send_message_to_user"
                and "discount" in event.action.args.get("content", "").lower()
                and "spring2024" in event.action.args.get("content", "").lower()
                for event in events
            )

            # All conditions must hold True
            success = checkout_done and system_ops and proactive_sent
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
