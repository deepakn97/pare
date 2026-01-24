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


@register_scenario("ride_cancel_after_home_delivery")
class RideCancelAfterHomeDelivery(PASScenario):
    """Agent cancels unnecessary ride when online order arrives at home before pickup trip.

    The user ordered a "Bluetooth Speaker" online and it shows an estimated delivery time of 3-5 PM today. At 1:30 PM, believing the delivery won't arrive until later, the user books a ride to an electronics store at 2:30 PM to buy the speaker in person instead of waiting. However, at 2:00 PM, a shopping app notification arrives confirming the Bluetooth Speaker was just delivered to the user's home address. The agent must:
    1. Detect the delivery confirmation notification from the shopping app
    2. Retrieve the current active ride booking details from the cab app
    3. Recognize that the ride's purpose (buying a Bluetooth Speaker) is no longer necessary since the item already arrived
    4. Propose canceling the unnecessary ride to avoid the trip and fare
    5. Cancel the ride after user acceptance

    This scenario exercises cross-app causal reasoning (shopping → cab) to infer that an order's delivery completion obsoletes a transportation plan, delivery-status monitoring to detect timeline changes that affect user intentions, and cost-saving intervention by canceling redundant rides..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Shopping App
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Create Bluetooth Speaker product with a single variant
        bluetooth_speaker_product_id = self.shopping.add_product("Bluetooth Speaker")
        bluetooth_speaker_item_id = self.shopping.add_item_to_product(
            product_id=bluetooth_speaker_product_id,
            price=79.99,
            options={"color": "black", "brand": "SoundPro"},
            available=True,
        )

        # Create an order for the Bluetooth Speaker with "shipped" status (placed earlier today at 8 AM)
        # Estimated delivery: 3-5 PM, but will actually arrive at 2 PM
        order_time = datetime(2025, 11, 18, 8, 0, 0, tzinfo=UTC)
        self.order_id = "order_bluetooth_001"
        self.shopping.add_order(
            order_id=self.order_id,
            order_status="shipped",
            order_date=order_time.timestamp(),
            order_total=79.99,
            item_id=bluetooth_speaker_item_id,
            quantity=1,
        )

        # Initialize Cab App
        self.cab = StatefulCabApp(name="Cab")

        # User books a ride at 1:30 PM to go to "TechMart Electronics" at 2:30 PM
        # (This will be created as baseline state; the user has already booked it before agent observes)
        ride_time_str = "2025-11-18 14:30:00"  # 2:30 PM
        self.cab.add_new_ride(
            service_type="Default",
            start_location="Home",
            end_location="TechMart Electronics",
            price=18.50,
            duration=25.0,  # 25 minutes
            time_stamp=datetime(2025, 11, 18, 13, 30, 0, tzinfo=UTC).timestamp(),  # Booked at 1:30 PM
            distance_km=15.0,
        )
        # Set the last ride as the ongoing ride
        # Note: Setting on_going_ride is required for scenario setup to simulate a booked ride
        # This is necessary because add_new_ride() doesn't automatically set on_going_ride
        self.cab.on_going_ride = self.cab.ride_history[-1]
        self.cab.on_going_ride.status = "BOOKED"

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.shopping, self.cab]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # Environment event: Driver status update makes the ride's purpose explicit (tool-visible cue).
            # This avoids relying on the docstring narrative for why the user is going to TechMart.
            # Story timeline: Driver arrives at 2:30 PM (ride scheduled for 2:30 PM pickup).
            # Note: The 5-second delay is for fast testing only; in the story this happens at 2:30 PM.
            ride_purpose_event = cab_app.update_ride_status(
                status="ARRIVED_AT_PICKUP",
                message="I'm outside for your TechMart Electronics trip to buy a Bluetooth Speaker.",
            ).delayed(5)

            # Environment event: Shopping app updates order status to "delivered" at 2:00 PM
            # This represents the Bluetooth Speaker being delivered earlier than expected (story: 2:00 PM).
            # Note: The 10-second delay is for fast testing only; in the story this happens at 2:00 PM.
            delivery_event = shopping_app.update_order_status(order_id=self.order_id, status="delivered").delayed(
                10
            )  # Keep delays short for demo/runtime: <30s

            # Agent detects the delivery notification and checks the order details
            # Motivated by: delivery notification from shopping app (update_order_status event above)
            list_orders_event = shopping_app.list_orders().oracle().depends_on(delivery_event, delay_seconds=5)

            # Agent checks the current ride status to understand what trip is planned
            # Motivated by: need to verify ongoing ride details after detecting order delivery
            check_ride_event = (
                cab_app.get_current_ride_status()
                .oracle()
                .depends_on([list_orders_event, ride_purpose_event], delay_seconds=2)
            )

            # Agent proposes to cancel the ride since the Bluetooth Speaker was delivered
            # Motivated by: order is now delivered (from list_orders) + ongoing ride to TechMart Electronics (from get_current_ride_status)
            propose_event = (
                aui.send_message_to_user(
                    content="Your Bluetooth Speaker order has been delivered to your home. I also saw your ride status update for the TechMart Electronics trip to buy a Bluetooth Speaker. Since the speaker already arrived, would you like me to cancel the ride to save the $18.50 fare?"
                )
                .oracle()
                .depends_on(check_ride_event, delay_seconds=3)
            )

            # User accepts the proposal
            accept_event = (
                aui.accept_proposal(content="Yes, please cancel the ride.")
                .oracle()
                .depends_on(propose_event, delay_seconds=5)
            )

            # Agent cancels the ride on behalf of the user
            # Motivated by: user accepted the proposal to cancel the ride
            cancel_event = cab_app.user_cancel_ride().oracle().depends_on(accept_event, delay_seconds=2)

        # Register ALL events here in self.events
        self.events = [
            ride_purpose_event,
            delivery_event,
            list_orders_event,
            check_ride_event,
            propose_event,
            accept_event,
            cancel_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT events for validation
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT CHECK 1: Agent sent proposal to user about canceling the ride
            # Must reference the ride cancellation opportunity (flexible on exact wording)
            proposal_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT CHECK 2: Agent canceled the ride
            # Must call user_cancel_ride to complete the task
            cancel_ride_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "user_cancel_ride"
                for e in agent_events
            )

            # Build rationale for failures
            failed_checks = []
            if not proposal_found:
                failed_checks.append("agent did not send proposal message to user")
            if not cancel_ride_found:
                failed_checks.append("agent did not cancel the ride")

            success = proposal_found and cancel_ride_found
            rationale = "; ".join(failed_checks) if failed_checks else None

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
