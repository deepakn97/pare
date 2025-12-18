from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.shopping import ShoppingApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer


@register_scenario("online_shopping_proactive_checkout")
class OnlineShoppingProactiveCheckout(Scenario):
    """A full e-commerce flow where the agent helps the user buy a laptop and accessories.

    Demonstrates full use of all available apps:
    - AgentUserInterface: Interaction between user and agent
    - ShoppingApp: Product search, cart management, discount code, checkout, and order handling
    - SystemApp: Current time retrieval and notification waiting
    Includes proactive interaction pattern: agent proposes checkout; user confirms; agent executes.
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all the required apps for the scenario."""
        aui = AgentUserInterface()
        shop = ShoppingApp()
        system = SystemApp(name="system_shop")

        self.apps = [aui, shop, system]

    def build_events_flow(self) -> None:
        """Define the proactive e-commerce workflow event sequence."""
        aui = self.get_typed_app(AgentUserInterface)
        shop = self.get_typed_app(ShoppingApp)
        sys = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # Step 1 – User initiates the conversation asking for a laptop  # noqa: RUF003
            user_initiate = aui.send_message_to_agent(
                content="Hey assistant, can you help me find a lightweight laptop and a wireless mouse for work?"
            ).depends_on(None, delay_seconds=1)

            # Step 2 – System gets current time for contextual note  # noqa: RUF003
            time_check = sys.get_current_time().depends_on(user_initiate, delay_seconds=1)

            # Step 3 – Agent searches for laptops  # noqa: RUF003
            search_laptop = shop.search_product(product_name="lightweight laptop", limit=3).depends_on(
                time_check, delay_seconds=1
            )

            # Step 4 – Agent searches for wireless mouse  # noqa: RUF003
            search_mouse = shop.search_product(product_name="wireless mouse", limit=2).depends_on(
                search_laptop, delay_seconds=1
            )

            # Step 5 – Agent fetches all available discount codes  # noqa: RUF003
            get_codes = shop.get_all_discount_codes().depends_on(search_mouse, delay_seconds=1)

            # Step 6 – Agent sends proactive message proposing bundle purchase  # noqa: RUF003
            agent_propose_checkout = aui.send_message_to_user(
                content=(
                    "I found a suitable lightweight laptop and a wireless mouse. "
                    "A 'WORKSET10' discount may apply to both. Would you like me to add them to your cart and proceed to checkout?"
                )
            ).depends_on(get_codes, delay_seconds=1)

            # Step 7 – User agrees explicitly with a contextual message  # noqa: RUF003
            user_response = aui.send_message_to_agent(
                content="Yes, please add both to the cart and apply the WORKSET10 discount during checkout."
            ).depends_on(agent_propose_checkout, delay_seconds=1)

            # Step 8 – Agent adds selected items to the cart (representative IDs)  # noqa: RUF003
            add_laptop = shop.add_to_cart(item_id="laptop_item_id_001", quantity=1).depends_on(
                user_response, delay_seconds=1
            )
            add_mouse = shop.add_to_cart(item_id="mouse_item_id_002", quantity=1).depends_on(
                add_laptop, delay_seconds=1
            )

            # Step 9 – Agent lists cart to review content  # noqa: RUF003
            review_cart = shop.list_cart().depends_on(add_mouse, delay_seconds=1)

            # Step 10 – Agent retrieves discount info and confirms valid for cart  # noqa: RUF003
            check_discount = shop.get_discount_code_info(discount_code="WORKSET10").depends_on(
                review_cart, delay_seconds=1
            )

            # Step 11 – Agent performs checkout applying the discount  # noqa: RUF003
            perform_checkout = (
                shop.checkout(discount_code="WORKSET10").oracle().depends_on(check_discount, delay_seconds=1)
            )

            # Step 12 – Agent confirms order placed message  # noqa: RUF003
            confirm_message = (
                aui.send_message_to_user(
                    content="Your laptop and mouse have been successfully ordered with the WORKSET10 discount applied!"
                )
                .oracle()
                .depends_on(perform_checkout, delay_seconds=1)
            )

            # Step 13 – Agent waits for notification (simulating order shipment notification)  # noqa: RUF003
            wait_followup = sys.wait_for_notification(timeout=3).depends_on(confirm_message, delay_seconds=1)

            # Step 14 – Agent lists recent orders to validate final step  # noqa: RUF003
            list_order_final = shop.list_orders().depends_on(wait_followup, delay_seconds=1)

        self.events = [
            user_initiate,
            time_check,
            search_laptop,
            search_mouse,
            get_codes,
            agent_propose_checkout,
            user_response,
            add_laptop,
            add_mouse,
            review_cart,
            check_discount,
            perform_checkout,
            confirm_message,
            wait_followup,
            list_order_final,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Ensure the agent completed checkout and messaged user confirmation."""
        try:
            actions = [e.action for e in env.event_log.list_view() if isinstance(e.action, Action)]

            checkout_done = any(
                a.class_name == "ShoppingApp"
                and a.function_name == "checkout"
                and a.args.get("discount_code") == "WORKSET10"
                for a in actions
            )
            user_notified = any(
                a.class_name == "AgentUserInterface"
                and a.function_name == "send_message_to_user"
                and "successfully ordered" in a.args.get("content", "").lower()
                for a in actions
            )
            discount_checked = any(
                a.class_name == "ShoppingApp"
                and a.function_name == "get_discount_code_info"
                and a.args.get("discount_code") == "WORKSET10"
                for a in actions
            )

            system_used = any(a.class_name == "SystemApp" for a in actions)
            all_criteria = checkout_done and user_notified and discount_checked and system_used
            return ScenarioValidationResult(success=all_criteria)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
