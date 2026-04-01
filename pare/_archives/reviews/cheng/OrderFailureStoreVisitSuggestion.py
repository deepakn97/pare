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


@register_scenario("order_failure_store_visit_suggestion")
class OrderFailureStoreVisitSuggestion(PASScenario):
    """Agent detects shopping order failure notification and proactively suggests booking a cab ride to the store for in-person resolution.

    The user has placed an online shopping order for in-store pickup or delivery. They receive a notification that the order has failed due to payment issues, item unavailability, or address problems. The agent must:
    1. Parse the order failure notification containing the order details and failure reason using view_order() or list_orders()
    2. Identify the merchant or store location associated with the failed order
    3. Recognize that the user may need to visit the store in person to resolve the issue or complete the purchase
    4. Propose booking a cab ride to the store location using get_quotation() for the user's current location to the store
    5. Execute order_ride() to book the ride upon user acceptance

    This scenario exercises failure recovery through cross-app coordination (shopping failure → mobility solution), proactive problem-solving that bridges digital and physical shopping channels, and service recovery assistance by facilitating in-person resolution when online processes fail..
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

        # Add a product representing an electronics item at TechMart store
        product_id = self.shopping.add_product(name="Wireless Headphones")
        self.shopping.add_item_to_product(
            product_id=product_id,
            price=79.99,
            options={"color": "black", "brand": "AudioPro", "store": "TechMart Downtown"},
            available=True,
        )

        # Initialize cab app with store location for distance calculation
        self.cab = StatefulCabApp(name="Cab")

        # Seed a previous ride to TechMart so the distance is known
        self.cab.add_new_ride(
            service_type="Default",
            start_location="456 Oak Avenue",
            end_location="TechMart Downtown, 789 Main Street",
            price=12.50,
            duration=15.0,
            time_stamp=self.start_time - 86400,  # 1 day ago
            distance_km=8.5,
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.shopping, self.cab]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Order failure notification
            # User receives notification that their shopping order has been cancelled
            order_failure_event = shopping_app.update_order_status(
                order_id="test-order-001", status="cancelled"
            ).delayed(30)

            # Oracle Event 1: Agent lists orders to understand the failure details
            # Motivated by: order failure notification from environment event
            list_orders_event = shopping_app.list_orders().oracle().depends_on(order_failure_event, delay_seconds=2)

            # Oracle Event 2: Agent gets order details to extract store location
            # Motivated by: need to understand which store/merchant the failed order is associated with
            get_order_event = (
                shopping_app.get_order_details(order_id="test-order-001")
                .oracle()
                .depends_on(list_orders_event, delay_seconds=1)
            )

            # Oracle Event 3: Agent gets cab quotation to the store location
            # Motivated by: extracted store location from order details, checking ride feasibility
            get_quotation_event = (
                cab_app.get_quotation(
                    start_location="456 Oak Avenue",
                    end_location="TechMart Downtown, 789 Main Street",
                    service_type="Default",
                )
                .oracle()
                .depends_on(get_order_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent proposes ride booking to resolve order issue
            # Motivated by: detected order failure + confirmed ride availability from quotation
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed your order was cancelled. Would you like me to book a cab ride to TechMart Downtown so you can resolve this in person or purchase the item directly at the store?"
                )
                .oracle()
                .depends_on(get_quotation_event, delay_seconds=2)
            )

            # Oracle Event 5: User accepts the proposal
            # Motivated by: user responds affirmatively to agent's ride booking proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please book the ride.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent books the cab ride to the store
            # Motivated by: user acceptance from previous event
            book_ride_event = (
                cab_app.order_ride(
                    start_location="456 Oak Avenue",
                    end_location="TechMart Downtown, 789 Main Street",
                    service_type="Default",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

        # Register ALL events
        self.events = [
            order_failure_event,
            list_orders_event,
            get_order_event,
            get_quotation_event,
            proposal_event,
            acceptance_event,
            book_ride_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1 (STRICT): Agent sent proposal to the user suggesting a cab ride to the store
            # The agent must propose a ride to TechMart after detecting the order failure
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 2 (STRICT): Agent listed or retrieved order details to understand the failure
            # The agent must investigate the failed order using list_orders or get_order_details
            order_investigation_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name in ["list_orders", "get_order_details"]
                for e in log_entries
            )

            # Check 3 (STRICT): Agent got cab quotation to the store location
            # The agent must check ride availability using get_quotation with correct endpoints
            quotation_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "get_quotation"
                for e in log_entries
            )

            # Check 4 (STRICT): Agent booked the cab ride after user acceptance
            # The agent must complete the ride booking using order_ride
            ride_booked = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "order_ride"
                for e in log_entries
            )

            # Build success result and rationale
            missing_checks = []
            if not proposal_found:
                missing_checks.append("agent proposal message to user not found")
            if not order_investigation_found:
                missing_checks.append("order investigation (list_orders/get_order_details) not found")
            if not quotation_found:
                missing_checks.append("cab quotation to TechMart not found")
            if not ride_booked:
                missing_checks.append("cab ride booking to TechMart not found")

            success = proposal_found and order_investigation_found and quotation_found and ride_booked

            if not success:
                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
