"""Scenario for coordinating cab ride to pick up order after failed delivery attempt."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCabApp,
    StatefulContactsApp,
    StatefulEmailApp,
    StatefulShoppingApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario

# Warehouse address for pickup
WAREHOUSE_ADDRESS = "789 Distribution Way, San Francisco, CA 94107"


@register_scenario("order_item_cab_delivery_coordination")
class OrderItemCabDeliveryCoordination(PASScenario):
    """Agent coordinates cab ride to retrieve order after failed delivery attempt.

    Story:
    1. User has an existing order for Wireless Headphones (status: shipped)
    2. Email arrives saying delivery was attempted but no one was home
    3. User must pick up from warehouse before 6:00 PM today
    4. Agent proposes booking a cab to retrieve the item
    5. User accepts
    6. Agent gets user's address from contacts and books cab to warehouse

    This scenario exercises email monitoring for delivery status changes,
    cross-app coordination between shopping notifications and ride services,
    and time-sensitive cab booking with proper location lookup.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    additional_system_prompt = """You ordered Wireless Headphones that were supposed to be delivered today.

ACCEPT proposals that:
- Offer to book a cab to pick up your order from the warehouse
- Mention the pickup location and deadline

REJECT proposals that:
- Don't explain why you need to pick it up (failed delivery attempt)
- Don't provide the warehouse address"""

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize contacts app (has default user with address)
        self.contacts = StatefulContactsApp(name="Contacts")

        # Store user's address for validation
        user_details = self.contacts.get_current_user_details()
        self.user_address = user_details.address

        # Initialize shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Add product and create order using proper API
        product_id = self.shopping.add_product(name="Wireless Headphones")
        item_id = self.shopping.add_item_to_product(
            product_id=product_id,
            price=79.99,
            options={"color": "black"},
            available=True,
        )

        # Create order (placed yesterday, status: shipped)
        order_time = datetime(2025, 11, 17, 14, 30, 0, tzinfo=UTC).timestamp()
        self.shopping.add_order(
            order_id="order_20251117_wireless_headphones",
            order_status="shipped",
            order_date=order_time,
            order_total=79.99,
            item_id=item_id,
            quantity=1,
        )

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails")

        # Initialize cab app
        self.cab = StatefulCabApp(name="Cab")

        self.apps = [self.agent_ui, self.system_app, self.contacts, self.shopping, self.email, self.cab]

    def build_events_flow(self) -> None:
        """Build event flow for cab booking after failed delivery."""
        aui = self.get_typed_app(PASAgentUserInterface)
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        # Get user's address for cab booking
        user_details = contacts_app.get_current_user_details()
        user_address = user_details.address

        with EventRegisterer.capture_mode():
            # ENV: Email about failed delivery attempt
            email_event = email_app.send_email_to_user_with_id(
                email_id="email_delivery_failed",
                sender="notifications@shopplatform.com",
                subject="Order #order_20251117_wireless_headphones - Delivery Attempted",
                content=(
                    "Dear Customer,\n\n"
                    "We attempted to deliver your order #order_20251117_wireless_headphones "
                    "(Wireless Headphones) today, but no one was home to receive it.\n\n"
                    "Your package is now available for pickup at our warehouse:\n"
                    f"{WAREHOUSE_ADDRESS}\n\n"
                    "Please collect your order today before 6:00 PM to avoid return to sender.\n\n"
                    "We apologize for any inconvenience.\n\n"
                    "Best regards,\n"
                    "ShopPlatform Team"
                ),
            ).delayed(10)

            # Oracle: Agent gets user details to find their address
            get_user_event = contacts_app.get_current_user_details().oracle().depends_on(email_event, delay_seconds=2)

            # Oracle: Agent proposes booking a cab to retrieve the item
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "I noticed your Wireless Headphones delivery was attempted but no one was home. "
                        f"The package is now at the warehouse at {WAREHOUSE_ADDRESS} and needs to be "
                        "picked up before 6:00 PM today. Would you like me to book a cab to retrieve it?"
                    )
                )
                .oracle()
                .depends_on(get_user_event, delay_seconds=2)
            )

            # Oracle: User accepts
            accept_event = (
                aui.accept_proposal(content="Yes, please book a cab for me to pick up the order.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=5)
            )

            # Oracle: Agent lists available cab services
            list_rides_event = (
                cab_app.list_rides(
                    start_location=user_address,
                    end_location=WAREHOUSE_ADDRESS,
                    ride_time=None,
                )
                .oracle()
                .depends_on(accept_event, delay_seconds=2)
            )

            # Oracle: Agent orders a cab ride
            order_ride_event = (
                cab_app.order_ride(
                    start_location=user_address,
                    end_location=WAREHOUSE_ADDRESS,
                    service_type="Standard",
                    ride_time=None,
                )
                .oracle()
                .depends_on(list_rides_event, delay_seconds=2)
            )

        self.events = [
            email_event,
            get_user_event,
            proposal_event,
            accept_event,
            list_rides_event,
            order_ride_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate essential outcomes.

        Checks:
        1. Agent sent proposal to user about cab booking
        2. Agent ordered a cab ride with correct start and end locations
        """
        try:
            log_entries = env.event_log.list_view()
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # Check 1: Proposal sent to user
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # Check 2: Cab ride ordered with correct start (user address) and end (warehouse) locations
            order_ride_found = any(
                e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "order_ride"
                and self.user_address in str(e.action.args.get("start_location", ""))
                and WAREHOUSE_ADDRESS in str(e.action.args.get("end_location", ""))
                for e in agent_events
            )

            success = proposal_found and order_ride_found

            if not success:
                missing = []
                if not proposal_found:
                    missing.append("proposal to user about cab booking")
                if not order_ride_found:
                    missing.append(f"cab ride ordered from user address to warehouse ({WAREHOUSE_ADDRESS})")
                return ScenarioValidationResult(
                    success=False,
                    rationale=f"Missing: {', '.join(missing)}",
                )

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
