"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.calendar import CalendarEvent
from are.simulation.apps.shopping import CartItem, Order
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
    StatefulEmailApp,
)
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("shopping_refund_event_conflict")
class ShoppingRefundEventConflict(PASScenario):
    """Agent proactively cancels a product order and initiates refund when a conflicting calendar event makes the purchase unnecessary.

    The user has placed an order for "Professional Camera Tripod" (order #67890) with expected delivery on December 28, 2025 between 10:00 AM - 12:00 PM. Later, the user receives an email confirming that their calendar event "Photography Workshop" scheduled for December 29, 2025 at 2:00 PM has been cancelled by the organizer due to venue issues. The workshop cancellation email states "All attendees will be notified once we reschedule" and mentions that equipment rental (including tripods) was included in the original workshop package. The agent must:
    1. Detect the workshop cancellation email and extract the event details
    2. Search the calendar to locate and verify the cancelled "Photography Workshop" event
    3. Recognize that the user ordered photography equipment (tripod) likely in preparation for this workshop
    4. Check recent shopping orders to find the camera tripod order
    5. Verify the order has not yet been delivered and can still be cancelled
    6. Proactively offer to cancel the tripod order since the workshop is cancelled and equipment was included anyway
    7. Cancel the order and confirm the refund process with the user

    This scenario exercises temporal reasoning (order delivery vs event timing), cross-app causal inference (event cancellation → purchase motivation removal), semantic association (photography workshop → camera equipment), order management (cancellation eligibility), and proactive cost-saving assistance.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Shopping App
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Add camera tripod product to catalog
        product_id = self.shopping.add_product(name="Professional Camera Tripod")
        item_id = self.shopping.add_item_to_product(
            product_id=product_id,
            price=149.99,
            options={"color": "black", "weight": "3.5 lbs", "max_height": "67 inches"},
            available=True,
        )

        # Create existing order for the tripod (placed earlier, not yet delivered)
        # Order date: November 15, 2025 (3 days before start_time)
        order_date = datetime(2025, 11, 15, 14, 30, 0, tzinfo=UTC).timestamp()

        # Create CartItem for the order (without 'name' field)
        tripod_cart_item = CartItem(
            item_id=item_id,
            quantity=1,
            price=149.99,
            available=True,
            options={"color": "black", "weight": "3.5 lbs", "max_height": "67 inches"},
        )

        # Create Order and add to shopping app's orders dictionary
        tripod_order = Order(
            order_id="67890",
            order_status="processed",
            order_date=order_date,
            order_total=149.99,
            order_items={item_id: tripod_cart_item},
        )
        self.shopping.orders["67890"] = tripod_order

        # Initialize Calendar App
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Add the Photography Workshop event (scheduled for December 29, 2025 at 2:00 PM)
        workshop_start = datetime(2025, 12, 29, 14, 0, 0, tzinfo=UTC).timestamp()
        workshop_end = datetime(2025, 12, 29, 17, 0, 0, tzinfo=UTC).timestamp()

        workshop_event = CalendarEvent(
            event_id="workshop_evt_001",
            title="Photography Workshop",
            start_datetime=workshop_start,
            end_datetime=workshop_end,
            tag="Workshop",
            description="Professional photography workshop with equipment rental included (camera, lenses, tripods)",
            location="Creative Arts Studio, 456 Main Street",
            attendees=["Sarah Mitchell", "User"],
        )
        self.calendar.set_calendar_event(workshop_event)

        # Initialize Email App
        self.email = StatefulEmailApp(name="Emails")

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.shopping, self.calendar, self.email]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Workshop cancellation email arrives
            # This is the trigger that starts the entire flow
            workshop_cancel_email_event = email_app.send_email_to_user_with_id(
                email_id="workshop_cancel_001",
                sender="events@creativeartsphoto.com",
                subject="Photography Workshop Cancellation - December 29",
                content="Dear Participant,\n\nWe regret to inform you that the Photography Workshop scheduled for December 29, 2025 at 2:00 PM has been cancelled due to unexpected venue issues. All attendees will be notified once we reschedule for a later date.\n\nPlease note that the original workshop package included full equipment rental (professional cameras, lenses, and tripods), so you won't need to bring or purchase your own equipment when we reschedule.\n\nWe apologize for any inconvenience this may cause.\n\nBest regards,\nCreative Arts Photography Team",
            ).delayed(10)

            # Oracle Event 1: Agent searches calendar for the Photography Workshop event
            # The agent needs to verify the workshop event exists in the calendar
            search_workshop_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-12-29 14:00:00",
                    end_datetime="2025-12-29 17:00:00",
                )
                .oracle()
                .depends_on(workshop_cancel_email_event, delay_seconds=2)
            )

            # Oracle Event 2: Agent lists recent shopping orders to find camera-related purchases
            # The agent needs to discover the tripod order that's related to the cancelled workshop
            list_orders_event = shopping_app.list_orders().oracle().depends_on(search_workshop_event, delay_seconds=1)

            # Oracle Event 3: Agent gets details of the specific tripod order
            # The agent needs to verify the order status and determine if it can be cancelled
            get_order_details_event = (
                shopping_app.get_order_details(order_id="67890").oracle().depends_on(list_orders_event, delay_seconds=1)
            )

            # Oracle Event 4: Agent sends proposal to user
            # The agent proposes cancelling the order since the workshop is cancelled
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed the Photography Workshop on December 29 has been cancelled. You have an order for a Professional Camera Tripod (order #67890, $149.99) that was likely purchased for this workshop. Since the workshop included equipment rental (including tripods), would you like me to cancel this order and process a refund?"
                )
                .oracle()
                .depends_on(get_order_details_event, delay_seconds=2)
            )

            # Oracle Event 5: User accepts the proposal
            # The user agrees to cancel the order
            acceptance_event = (
                aui.accept_proposal(content="Yes, please cancel the tripod order and get me a refund.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent cancels the order
            # The agent executes the order cancellation
            cancel_order_event = (
                shopping_app.cancel_order(order_id="67890").oracle().depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 7: Agent confirms completion to user
            # The agent notifies the user that the order has been cancelled
            confirmation_event = (
                aui.send_message_to_user(
                    content="I've successfully cancelled order #67890 for the Professional Camera Tripod. Your refund of $149.99 will be processed within 3-5 business days."
                )
                .oracle()
                .depends_on(cancel_order_event, delay_seconds=1)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            workshop_cancel_email_event,
            search_workshop_event,
            list_orders_event,
            get_order_details_event,
            proposal_event,
            acceptance_event,
            cancel_order_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT events (oracle events)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent searched calendar for the workshop event
            calendar_search_found = any(
                e.action.class_name == "StatefulCalendarApp" and e.action.function_name == "get_calendar_events_from_to"
                for e in agent_events
                if isinstance(e.action, Action)
            )

            # STRICT Check 2: Agent listed shopping orders
            list_orders_found = any(
                e.action.class_name == "StatefulShoppingApp" and e.action.function_name == "list_orders"
                for e in agent_events
                if isinstance(e.action, Action)
            )

            # STRICT Check 3: Agent got order details for the specific order
            get_order_details_found = any(
                e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_order_details"
                and e.action.args.get("order_id") == "67890"
                for e in agent_events
                if isinstance(e.action, Action)
            )

            # STRICT Check 4: Agent sent a proposal message to user
            # We only check that the message was sent, not the exact content
            proposal_message_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
                if isinstance(e.action, Action)
            )

            # STRICT Check 5: Agent cancelled the order
            cancel_order_found = any(
                e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "cancel_order"
                and e.action.args.get("order_id") == "67890"
                for e in agent_events
                if isinstance(e.action, Action)
            )

            # Collect all strict checks
            all_strict_checks = [
                ("calendar_search", calendar_search_found),
                ("list_orders", list_orders_found),
                ("get_order_details", get_order_details_found),
                ("proposal_message", proposal_message_found),
                ("cancel_order", cancel_order_found),
            ]

            # Determine success and build rationale
            failed_checks = [name for name, passed in all_strict_checks if not passed]
            success = len(failed_checks) == 0

            if not success:
                rationale = f"Missing critical agent actions: {', '.join(failed_checks)}"
            else:
                rationale = "All validation checks passed"

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
