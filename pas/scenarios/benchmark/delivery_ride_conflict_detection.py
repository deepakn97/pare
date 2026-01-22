from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
)
from pas.apps.cab import StatefulCabApp
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("delivery_ride_conflict_detection")
class DeliveryRideConflictDetection(PASScenario):
    """Agent detects timing conflict between incoming delivery and active cab ride, then proposes ride cancellation.

    The user has placed an order for groceries that is scheduled for delivery. They also have an active cab ride booked that will take them away from their delivery address during the expected delivery window. When a delivery notification arrives confirming the imminent arrival, the agent must:
    1. Parse the delivery notification containing the delivery time window and address
    2. Check the current ride status using get_current_ride_status()
    3. Identify that the active ride's pickup time and destination conflict with being present for the delivery
    4. Propose canceling the cab ride to ensure the user can receive their delivery
    5. Execute user_cancel_ride() upon user acceptance

    This scenario exercises cross-app temporal reasoning (shopping delivery notifications → cab ride coordination), conflict detection between physical location requirements, and proactive cancellation to prevent missed deliveries..
    """

    start_time = datetime(2025, 11, 18, 10, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize shopping app with grocery order
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Create a grocery product with variants
        grocery_product_id = self.shopping.add_product("Fresh Groceries Bundle")
        grocery_item_id = self.shopping.add_item_to_product(
            product_id=grocery_product_id,
            price=45.99,
            options={"items": "milk, bread, eggs, vegetables"},
            available=True,
        )

        # Create an order that was placed earlier (2 hours ago) and is currently "shipped"
        order_timestamp = self.start_time - 2 * 3600  # 2 hours before start_time

        # Add the order using the app's public method
        self.shopping.add_order(
            order_id="ord_grocery_123",
            order_status="shipped",
            order_date=order_timestamp,
            order_total=45.99,
            item_id=grocery_item_id,
            quantity=1,
        )

        # Initialize cab app with an active ride
        self.cab = StatefulCabApp(name="Cab")

        # Create a ride that will be booked at 9:30 AM (30 minutes from start_time)
        # The ride is from "123 Main St" to "Downtown Office" starting at 10:00 AM
        # This conflicts with the delivery window (9:45 AM - 10:15 AM)
        ride_time_str = "2025-11-18 10:00:00"
        ride = self.cab.order_ride(
            start_location="123 Main St",
            end_location="Downtown Office",
            service_type="Default",
            ride_time=ride_time_str,
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.shopping, self.cab]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Delivery notification arrives (delayed 5 seconds from start_time)
            # The order is out for delivery with expected delivery window
            # Note: Using "shipped" status as the delivery notification, since "delivered" means already received
            delivery_notification = shopping_app.update_order_status(
                order_id="ord_grocery_123", status="shipped"
            ).delayed(5)

            # Oracle Event 1: Agent checks current ride status (motivated by delivery notification)
            # The agent needs to verify if there's an active ride that might conflict
            ride_status_check = (
                cab_app.get_current_ride_status().oracle().depends_on(delivery_notification, delay_seconds=2)
            )

            # Oracle Event 2: Agent proposes canceling the ride to ensure user is present for delivery
            # Based on the ride status check, the agent identifies the conflict
            proposal_event = (
                aui.send_message_to_user(
                    content="Your grocery delivery is arriving soon at 123 Main St. However, you have a cab ride scheduled at 10:00 AM to Downtown Office. You may miss your delivery. Would you like me to cancel the cab ride?"
                )
                .oracle()
                .depends_on(ride_status_check, delay_seconds=2)
            )

            # Oracle Event 3: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please cancel the ride so I can receive my delivery.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent cancels the cab ride based on user acceptance
            cancel_ride_event = cab_app.user_cancel_ride().oracle().depends_on(acceptance_event, delay_seconds=1)

        # Register ALL events here in self.events
        self.events = [
            delivery_notification,
            ride_status_check,
            proposal_event,
            acceptance_event,
            cancel_ride_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check: Agent canceled the ride
            # This is the core resolution action
            cancel_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "user_cancel_ride"
                for e in log_entries
            )

            if not cancel_found:
                return ScenarioValidationResult(success=False, rationale="Ride cancellation not found")

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
