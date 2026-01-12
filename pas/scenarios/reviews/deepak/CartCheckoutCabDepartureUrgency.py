"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
)
from pas.apps.cab import StatefulCabApp
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("cart_checkout_cab_departure_urgency")
class CartCheckoutCabDepartureUrgency(PASScenario):
    """Agent detects imminent cab arrival and prompts user to complete pending shopping cart checkout before departure.

    The user has added items to their shopping cart but has not yet checked out. They have also booked a cab ride to the airport or another location requiring departure from home. When a cab status notification arrives indicating the driver is nearby or has arrived, the agent must:
    1. Parse the incoming cab arrival or approaching notification using get_current_ride_status()
    2. Check if the user has items in their shopping cart using list_cart()
    3. Recognize the time pressure created by imminent departure
    4. Propose completing the cart checkout before leaving (preventing abandoned cart and potential need to re-order later)
    5. Execute checkout() with any available discount codes upon user acceptance

    This scenario exercises temporal urgency detection (cab notifications → shopping deadlines), cross-app state correlation (active ride status → pending cart state), and proactive task completion prompting under time constraints rather than conflict resolution..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with baseline data for cart checkout under cab departure urgency scenario.

        Baseline state:
        - Shopping: Cart contains items (phone case, wireless earbuds) that were added earlier but not yet checked out
        - Cab: User has previously booked a ride to the airport scheduled for departure
        - System: Standard home screen
        - Agent UI: Standard interface

        The cab status update (driver arriving soon) will be delivered as an environment event in Step 3.
        """
        # Initialize core apps
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize shopping app with items already in cart
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Seed product catalog with items that are already in the cart
        shopping_products: dict[str, dict[str, Any]] = {
            "prod-phone-case-001": {
                "name": "Premium Phone Case",
                "product_id": "prod-phone-case-001",
                "variants": {
                    "item-phone-case-001": {
                        "price": 29.99,
                        "available": True,
                        "item_id": "item-phone-case-001",
                        "options": {"color": "black", "material": "silicone"},
                    }
                },
            },
            "prod-wireless-earbuds-001": {
                "name": "Wireless Earbuds",
                "product_id": "prod-wireless-earbuds-001",
                "variants": {
                    "item-wireless-earbuds-001": {
                        "price": 79.99,
                        "available": True,
                        "item_id": "item-wireless-earbuds-001",
                        "options": {"color": "white", "battery_life": "24h"},
                    }
                },
            },
        }
        self.shopping.load_products_from_dict(shopping_products)

        # Add items to cart (user has added these but not yet checked out)
        self.shopping.add_to_cart(item_id="item-phone-case-001", quantity=1)
        self.shopping.add_to_cart(item_id="item-wireless-earbuds-001", quantity=1)

        # Initialize cab app with a previously booked ride
        self.cab = StatefulCabApp(name="Cab")

        # Book a ride to the airport (ride was booked earlier, now driver is approaching)
        # The ride status will be updated via environment event in Step 3
        ride = self.cab.order_ride(
            start_location="123 Main St, San Francisco, CA",
            end_location="San Francisco International Airport (SFO)",
            service_type="Default",
            ride_time=None,  # ASAP ride
        )
        # Store ride_id for later use in Step 3 events
        if ride and hasattr(ride, "ride_id"):
            self.ride_id = ride.ride_id
        else:
            # Fallback: get from on_going_ride
            self.ride_id = self.cab.on_going_ride.ride_id if self.cab.on_going_ride else "ride-001"

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.shopping, self.cab]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Cab status update - driver is arriving soon
            # This is the exogenous trigger that creates urgency for the agent to act
            cab_status_event = cab_app.update_ride_status(
                status="ARRIVED_AT_PICKUP",
                message="Your driver has arrived at the pickup location. Please come out when ready.",
            ).delayed(15)

            # Oracle Event 1: Agent checks current ride status to understand the timing
            # Motivated by: cab status notification above indicates driver arrival
            check_ride_event = cab_app.get_current_ride_status().oracle().depends_on(cab_status_event, delay_seconds=2)

            # Oracle Event 2: Agent checks shopping cart to see if there are pending items
            # Motivated by: agent recognizes imminent departure creates deadline for pending purchases
            check_cart_event = shopping_app.list_cart().oracle().depends_on(check_ride_event, delay_seconds=1)

            # Oracle Event 3: Agent proposes completing checkout before departure
            # Motivated by: agent observed driver arrival (cab status) and found items in cart (list_cart result)
            proposal_event = (
                aui.send_message_to_user(
                    content="Your cab driver has arrived for your trip to SFO. I noticed you have items in your shopping cart (Premium Phone Case and Wireless Earbuds, total $109.98). Would you like me to complete the checkout now before you leave?"
                )
                .oracle()
                .depends_on(check_cart_event, delay_seconds=2)
            )

            # Oracle Event 4: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please complete the checkout.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent completes the checkout
            # Motivated by: user accepted the proposal to complete checkout
            checkout_event = shopping_app.checkout().oracle().depends_on(acceptance_event, delay_seconds=1)

        # TODO: Register ALL events here in self.events
        self.events = [
            cab_status_event,
            check_ride_event,
            check_cart_event,
            proposal_event,
            acceptance_event,
            checkout_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent checked the current ride status
            # The agent must query ride status to understand the cab arrival context
            ride_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "get_current_ride_status"
                for e in log_entries
            )

            # STRICT Check 2: Agent checked the shopping cart
            # The agent must query the cart to discover pending items
            cart_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "list_cart"
                for e in log_entries
            )

            # FLEXIBLE Check 3: Agent sent proposal about completing checkout
            # We verify the agent sent a message but don't strictly validate exact wording
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 4: Agent completed the checkout
            # The agent must actually execute the checkout after user acceptance
            checkout_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                for e in log_entries
            )

            # All strict checks must pass for success
            success = ride_check_found and cart_check_found and proposal_found and checkout_found

            if not success:
                # Build rationale explaining which checks failed
                missing = []
                if not ride_check_found:
                    missing.append("agent did not check ride status")
                if not cart_check_found:
                    missing.append("agent did not check shopping cart")
                if not proposal_found:
                    missing.append("agent did not send proposal message to user")
                if not checkout_found:
                    missing.append("agent did not complete checkout")

                rationale = "; ".join(missing)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
