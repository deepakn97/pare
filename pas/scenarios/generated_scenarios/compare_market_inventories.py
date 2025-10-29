from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.shopping import Shopping, ShoppingApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("compare_market_inventories")
class CompareMarketInventories(Scenario):
    """Scenario: The agent compares two online store inventories and proactively suggests ordering a matching product.

    This scenario demonstrates a full workflow involving all available apps:
    - Uses both ShoppingApp and Shopping to compare item availability
    - Uses SystemApp to timestamp actions and wait between events
    - Uses AgentUserInterface for proactive communication with user (proposal + user approval pattern)
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize agent, shopping, and system applications."""
        self.apps = [AgentUserInterface(), ShoppingApp(), Shopping(), SystemApp(name="system_monitor")]

    def build_events_flow(self) -> None:
        """Define sequence of events including proactive approval interaction."""
        aui = self.get_typed_app(AgentUserInterface)
        shop_app = self.get_typed_app(ShoppingApp)
        shop_alt = self.get_typed_app(Shopping)
        sys_app = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # 1. User asks to compare availability of a product across two marketplaces
            user_request = (
                aui.send_message_to_agent(
                    content="Can you compare if 'EcoSmart Water Bottle' is available in both our marketplaces?"
                )
                .depends_on(None, delay_seconds=0)
                .with_id("user_request")
            )

            # 2. Agent (oracle) retrieves current time to timestamp the comparison
            get_time = sys_app.get_current_time().oracle().depends_on(user_request, delay_seconds=1).with_id("get_time")

            # 3. Agent searches for 'EcoSmart Water Bottle' in ShoppingApp (Marketplace A)
            search_a = (
                shop_app.search_product(product_name="EcoSmart Water Bottle")
                .oracle()
                .depends_on(get_time, delay_seconds=1)
                .with_id("search_a")
            )

            # 4. Agent searches for 'EcoSmart Water Bottle' in Shopping marketplace (Marketplace B)
            search_b = (
                shop_alt.search_product(product_name="EcoSmart Water Bottle")
                .oracle()
                .depends_on(search_a, delay_seconds=1)
                .with_id("search_b")
            )

            # 5. Agent proposes an action to user (Proactive Interaction step)
            proposal = (
                aui.send_message_to_user(
                    content="The 'EcoSmart Water Bottle' is available in Marketplace A with a discount. Would you like me to add it to your cart?"
                )
                .depends_on(search_b, delay_seconds=1)
                .with_id("proposal_message")
            )

            # 6. User confirms they want to proceed with ordering
            user_response = (
                aui.send_message_to_agent(
                    content="Yes, please add it to the cart and check out with the best discount code."
                )
                .depends_on(proposal, delay_seconds=2)
                .with_id("user_approval")
            )

            # 7. Agent retrieves all discount codes
            fetch_discounts = (
                shop_app.get_all_discount_codes()
                .oracle()
                .depends_on(user_response, delay_seconds=1)
                .with_id("fetch_discounts")
            )

            # 8. Agent adds the product to cart
            add_cart = (
                shop_app.add_to_cart(item_id="EcoSmart_Water_Bottle_ID", quantity=1)
                .oracle()
                .depends_on(fetch_discounts, delay_seconds=1)
                .with_id("add_cart")
            )

            # 9. Agent lists cart to verify item presence
            list_cart = shop_app.list_cart().oracle().depends_on(add_cart, delay_seconds=1).with_id("list_cart")

            # 10. Agent proceeds to checkout using a discount code
            checkout = (
                shop_app.checkout(discount_code="SPRINGSALE")
                .oracle()
                .depends_on(list_cart, delay_seconds=1)
                .with_id("checkout")
            )

            # 11. Wait for confirmation from system that checkout is complete
            wait_notif = (
                sys_app.wait_for_notification(timeout=5)
                .oracle()
                .depends_on(checkout, delay_seconds=1)
                .with_id("wait_for_notification")
            )

            # 12. Agent sends a summary update to user after successful checkout
            completion_msg = (
                aui.send_message_to_user(
                    content="I successfully placed your order for the EcoSmart Water Bottle using the SPRINGSALE discount!"
                )
                .oracle()
                .depends_on(wait_notif, delay_seconds=1)
                .with_id("completion_update")
            )

        self.events = [
            user_request,
            get_time,
            search_a,
            search_b,
            proposal,
            user_response,
            fetch_discounts,
            add_cart,
            list_cart,
            checkout,
            wait_notif,
            completion_msg,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Custom validation to confirm successful proactive purchase flow."""
        try:
            evts = env.event_log.list_view()
            # Check if checkout was performed successfully
            checkout_done = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ShoppingApp"
                and e.action.function_name == "checkout"
                and e.action.args.get("discount_code") == "SPRINGSALE"
                for e in evts
            )

            # Also check that agent proposed the action and sent completion message
            proposal_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "Would you like me to add it to your cart" in e.action.args.get("content", "")
                for e in evts
            )

            completion_reported = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "successfully placed your order" in e.action.args.get("content", "")
                for e in evts
            )

            return ScenarioValidationResult(success=(checkout_done and proposal_sent and completion_reported))
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
