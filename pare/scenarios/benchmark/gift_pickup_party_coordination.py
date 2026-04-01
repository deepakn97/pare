"""Scenario for coordinating gift pickup and cab to birthday party."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulCabApp,
    StatefulCalendarApp,
    StatefulEmailApp,
    StatefulShoppingApp,
)
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("gift_pickup_party_coordination")
class GiftPickupPartyCoordination(PAREScenario):
    """Agent coordinates gift pickup and cab booking for birthday party.

    Story:
    1. User has a birthday party for friend Sarah tonight at 7pm
    2. User ordered a gift (Wireless Headphones) online for store pickup
    3. Email arrives from store: "Your order is ready for pickup at Tech Store, 123 Tech Plaza"
    4. Agent sees email, checks calendar (finds party tonight at 456 Oak Avenue)
    5. Agent notices: gift ready + party tonight = need to coordinate pickup
    6. Agent proposes booking cab to store first, then to party location
    7. User accepts
    8. Agent books the cab

    This scenario exercises cross-app coordination between Email (pickup notification trigger),
    Calendar (event timing/location), Shopping (order details), and Cab (transportation booking).
    """

    start_time = datetime(2025, 11, 18, 16, 0, 0, tzinfo=UTC).timestamp()  # 4pm, 3 hours before party
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with data for gift pickup coordination scenario."""
        # Required infrastructure apps
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize apps
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.shopping = StatefulShoppingApp(name="Shopping")
        self.email = StatefulEmailApp(name="Emails")
        self.cab = StatefulCabApp(name="Cab")

        # Add calendar event for Sarah's birthday party tonight at 7pm
        self.party_event_id = self.calendar.add_calendar_event(
            title="Sarah's Birthday Party",
            start_datetime="2025-11-18 19:00:00",
            end_datetime="2025-11-18 22:00:00",
            description="Birthday party for Sarah. Don't forget the gift!",
            location="456 Oak Avenue",
        )

        # Set up shopping order for the gift (processed, ready for pickup)
        product_id = self.shopping.add_product(name="Wireless Noise Cancelling Headphones")
        item_id = self.shopping.add_item_to_product(
            product_id=product_id,
            price=149.99,
            options={"color": "Rose Gold", "size": "One Size"},
            available=True,
        )

        # Order placed a few days ago, now processed
        order_date = datetime(2025, 11, 15, 10, 0, 0, tzinfo=UTC).timestamp()
        self.shopping.add_order(
            order_id="order-gift-headphones",
            order_status="processed",
            order_date=order_date,
            order_total=149.99,
            item_id=item_id,
            quantity=1,
        )

        # Register all apps
        self.apps = [
            self.agent_ui,
            self.system_app,
            self.calendar,
            self.shopping,
            self.email,
            self.cab,
        ]

    def build_events_flow(self) -> None:
        """Build event flow - store email triggers agent to coordinate pickup and cab."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")

        with EventRegisterer.capture_mode():
            # ENV Event: Email arrives from store saying order is ready for pickup
            # This is the trigger that starts the agent's coordination workflow
            pickup_email = email_app.send_email_to_user_only(
                sender="orders@techstore.com",
                subject="Your Order is Ready for Pickup!",
                content=(
                    "Great news! Your order is ready for pickup.\n\n"
                    "Order Details:\n"
                    "- Item: Wireless Noise Cancelling Headphones (Rose Gold)\n"
                    "- Price: $149.99\n"
                    "- Order ID: order-gift-headphones\n\n"
                    "Pickup Location: Tech Store\n"
                    "Address: 123 Tech Plaza\n"
                    "Store Hours: 10:00 AM - 9:00 PM\n\n"
                    "Please bring a valid ID when picking up your order.\n\n"
                    "Thank you for shopping with us!\n"
                    "Tech Store Team"
                ),
            ).delayed(30)

            # Oracle: Agent checks today's calendar events to see what's happening
            check_calendar = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-18 00:00:00",
                    end_datetime="2025-11-18 23:59:59",
                )
                .oracle()
                .depends_on(pickup_email, delay_seconds=2)
            )

            # Oracle: Agent checks shopping orders to confirm item details
            check_orders = shopping_app.list_orders().oracle().depends_on(check_calendar, delay_seconds=1)

            # Oracle: Agent proposes coordinated cab booking
            proposal = (
                aui.send_message_to_user(
                    content=(
                        "Your gift order (Wireless Headphones) is ready for pickup at Tech Store "
                        "(123 Tech Plaza). I see you have Sarah's Birthday Party at 7pm tonight "
                        "at 456 Oak Avenue. Would you like me to book a cab to pick up the gift first, "
                        "then continue to the party? This way you'll have the gift in time."
                    )
                )
                .oracle()
                .depends_on(check_orders, delay_seconds=2)
            )

            # Oracle: User accepts the proposal
            acceptance = (
                aui.accept_proposal(content="Yes, that would be great! Please book it.")
                .oracle()
                .depends_on(proposal, delay_seconds=2)
            )

            # Oracle: Agent books the cab to Tech Store for 5:30pm
            # This gives time to pick up the gift and get to the 7pm party
            book_cab = (
                cab_app.order_ride(
                    start_location="Home",
                    end_location="123 Tech Plaza",
                    service_type="Default",
                    ride_time="2025-11-18 17:30:00",
                )
                .oracle()
                .depends_on(acceptance, delay_seconds=1)
            )

            # Oracle: Agent confirms to user
            confirmation = (
                aui.send_message_to_user(
                    content=(
                        "I've booked a cab to Tech Store (123 Tech Plaza) to pick up your gift. "
                        "After you get the headphones, you can head to Sarah's party at 456 Oak Avenue. "
                        "You have plenty of time before 7pm!"
                    )
                )
                .oracle()
                .depends_on(book_cab, delay_seconds=1)
            )

        self.events = [
            pickup_email,
            check_calendar,
            check_orders,
            proposal,
            acceptance,
            book_cab,
            confirmation,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent coordinated gift pickup and cab booking.

        Essential outcomes checked:
        1. Agent sent proposal to user about coordinated pickup + party transport
        2. Agent booked a cab ride
        """
        try:
            log_entries = env.event_log.list_view()

            # Check 1: Agent sent proposal to user
            proposal_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PAREAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 2: Agent booked a cab (order_ride was called)
            cab_booked = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "order_ride"
                for e in log_entries
            )

            success = proposal_sent and cab_booked

            if not success:
                missing = []
                if not proposal_sent:
                    missing.append("proposal to user about gift pickup and party transport")
                if not cab_booked:
                    missing.append("cab booking for the trip")
                return ScenarioValidationResult(
                    success=False,
                    rationale=f"Missing required actions: {', '.join(missing)}",
                )

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
