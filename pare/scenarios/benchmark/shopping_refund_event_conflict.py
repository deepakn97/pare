"""Scenario: Agent cancels redundant tripod order when workshop reminder clarifies equipment is included."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulCalendarApp,
    StatefulEmailApp,
)
from pare.apps.shopping import StatefulShoppingApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("shopping_refund_event_conflict")
class ShoppingRefundEventConflict(PAREScenario):
    """Agent proactively cancels a redundant tripod order when a workshop reminder email clarifies that a tripod is included in the registration package.

    The user registered for a "Photography Workshop" on December 29, 2025 and received a confirmation email stating that a tripod is included in the package but participants must bring their own camera. The user then placed two separate orders: one for a camera (needed) and one for a tripod (not realizing it's included). Both orders are scheduled for delivery on December 28, 2025. A reminder email arrives from the workshop organizers reiterating that tripods are provided as part of registration but cameras are not. The agent must:
    1. Detect the workshop reminder email mentioning equipment details
    2. Check recent shopping orders to find camera and tripod orders
    3. Cross-reference with the original registration email to confirm tripod is included
    4. Recognize that the tripod order is redundant since it's included in the workshop
    5. Proactively offer to cancel just the tripod order (keeping the camera order)
    6. Cancel the tripod order and confirm the refund process with the user

    This scenario exercises cross-app reasoning (email → shopping), redundancy detection, selective order cancellation, and proactive cost-saving assistance.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with baseline data for the scenario."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Shopping App
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Add camera product to catalog
        camera_product_id = self.shopping.add_product(name="Digital Camera")
        self.camera_item_id = self.shopping.add_item_to_product(
            product_id=camera_product_id,
            price=599.99,
            options={"brand": "Canon", "model": "EOS R50"},
            available=True,
        )

        # Add tripod product to catalog
        tripod_product_id = self.shopping.add_product(name="Professional Camera Tripod")
        self.tripod_item_id = self.shopping.add_item_to_product(
            product_id=tripod_product_id,
            price=149.99,
            options={"color": "black", "max_height": "67 inches"},
            available=True,
        )

        # Create two separate orders (placed Nov 15, delivery expected Dec 28)
        order_date = datetime(2025, 11, 15, 14, 30, 0, tzinfo=UTC).timestamp()

        # Order 1: Camera (user needs this - not included in workshop)
        self.camera_order_id = self.shopping.add_order(
            order_id="ORD-CAM-001",
            order_status="processed",
            order_date=order_date,
            order_total=599.99,
            item_id=self.camera_item_id,
            quantity=1,
        )

        # Order 2: Tripod (redundant - workshop includes tripod)
        self.tripod_order_id = self.shopping.add_order(
            order_id="ORD-TRI-002",
            order_status="processed",
            order_date=order_date,
            order_total=149.99,
            item_id=self.tripod_item_id,
            quantity=1,
        )

        # Initialize Calendar App
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Add the Photography Workshop event (December 29, 2025 at 2:00 PM)
        self.calendar.add_calendar_event(
            title="Photography Workshop",
            start_datetime="2025-12-29 14:00:00",
            end_datetime="2025-12-29 17:00:00",
            tag="Workshop",
            description="Professional photography workshop at Creative Arts Studio",
            location="Creative Arts Studio, 456 Main Street",
            attendees=["Sarah Mitchell"],
        )

        # Initialize Email App
        self.email = StatefulEmailApp(name="Emails")

        # Baseline email 1: Workshop registration confirmation (from earlier)
        self.email.send_email_to_user_with_id(
            email_id="workshop_registration_001",
            sender="events@creativeartsphoto.com",
            subject="Registration Confirmed - Photography Workshop Dec 29",
            content=(
                "Dear Participant,\n\n"
                "Thank you for registering for our Photography Workshop on December 29, 2025!\n\n"
                "IMPORTANT - Equipment Information:\n"
                "- A professional tripod is INCLUDED in your registration package\n"
                "- You must bring your own camera (cameras are NOT provided)\n\n"
                "Location: Creative Arts Studio, 456 Main Street\n"
                "Time: 2:00 PM - 5:00 PM\n\n"
                "See you there!\n"
                "Creative Arts Photography Team"
            ),
        )

        # Baseline email 2: Camera order confirmation
        self.email.send_email_to_user_with_id(
            email_id="camera_order_confirmation",
            sender="orders@photogearsupply.com",
            subject="Order Confirmation - Digital Camera (ORD-CAM-001)",
            content=(
                "Thank you for your order!\n\n"
                "Order ID: ORD-CAM-001\n"
                "Item: Digital Camera (Canon EOS R50)\n"
                "Price: $599.99\n\n"
                "Expected Delivery: December 28, 2025\n\n"
                "Thank you for shopping with Photo Gear Supply!"
            ),
        )

        # Baseline email 3: Tripod order confirmation
        self.email.send_email_to_user_with_id(
            email_id="tripod_order_confirmation",
            sender="orders@photogearsupply.com",
            subject="Order Confirmation - Professional Camera Tripod (ORD-TRI-002)",
            content=(
                "Thank you for your order!\n\n"
                "Order ID: ORD-TRI-002\n"
                "Item: Professional Camera Tripod\n"
                "Price: $149.99\n\n"
                "Expected Delivery: December 28, 2025\n\n"
                "Thank you for shopping with Photo Gear Supply!"
            ),
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.shopping, self.calendar, self.email]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Workshop reminder email arrives
            # This is the trigger - reminds user that tripod is included, camera is not
            workshop_reminder_event = email_app.send_email_to_user_with_id(
                email_id="workshop_reminder_001",
                sender="events@creativeartsphoto.com",
                subject="Reminder: Photography Workshop Dec 29 - Equipment Info",
                content=(
                    "Dear Participant,\n\n"
                    "This is a friendly reminder about your upcoming Photography Workshop on December 29, 2025!\n\n"
                    "EQUIPMENT REMINDER:\n"
                    "- A professional tripod is INCLUDED in your registration - no need to bring or purchase one\n"
                    "- You MUST bring your own camera (cameras are NOT provided)\n\n"
                    "We look forward to seeing you!\n"
                    "Creative Arts Photography Team"
                ),
            ).delayed(10)

            # Oracle Event 1: Agent lists shopping orders to check what user has ordered
            list_orders_event = shopping_app.list_orders().oracle().depends_on(workshop_reminder_event, delay_seconds=2)

            # Oracle Event 2: Agent gets details of the tripod order
            get_tripod_order_event = (
                shopping_app.get_order_details(order_id=self.tripod_order_id)
                .oracle()
                .depends_on(list_orders_event, delay_seconds=1)
            )

            # Oracle Event 3: Agent sends proposal to user
            # Agent recognizes tripod order is redundant since workshop includes one
            proposal_event = (
                aui.send_message_to_user(
                    content=f"I noticed you have an order for a Professional Camera Tripod (order {self.tripod_order_id}, $149.99). The workshop reminder email confirms that a tripod is included in your registration package. Would you like me to cancel the tripod order and save $149.99? Your camera order will remain active since you need to bring your own camera."
                )
                .oracle()
                .depends_on(get_tripod_order_event, delay_seconds=2)
            )

            # Oracle Event 4: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please cancel the tripod order.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent cancels the tripod order
            cancel_order_event = (
                shopping_app.cancel_order(order_id=self.tripod_order_id)
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 6: Agent confirms completion to user
            confirmation_event = (
                aui.send_message_to_user(
                    content=f"Done! I've cancelled order {self.tripod_order_id} for the Professional Camera Tripod. Your refund of $149.99 will be processed within 3-5 business days. Your camera order remains active for delivery on December 28."
                )
                .oracle()
                .depends_on(cancel_order_event, delay_seconds=1)
            )

        self.events = [
            workshop_reminder_event,
            list_orders_event,
            get_tripod_order_event,
            proposal_event,
            acceptance_event,
            cancel_order_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent achieved the essential outcomes for this scenario.

        Essential outcomes (what we check):
        - Agent sent proposal to user before taking action
        - Agent cancelled the tripod order (ORD-TRI-002)

        Not checked (intermediate steps the agent might do differently):
        - How agent discovered the orders (list_orders vs get_order_details)
        - Whether agent checked calendar
        """
        try:
            log_entries = env.event_log.list_view()
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # CHECK 1: Agent sent proposal to user
            proposal_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PAREAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # CHECK 2: Agent cancelled the tripod order
            cancel_order_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "cancel_order"
                and e.action.args.get("order_id") == self.tripod_order_id
                for e in agent_events
            )

            success = proposal_found and cancel_order_found

            if not success:
                failed_checks = []
                if not proposal_found:
                    failed_checks.append("agent did not send proposal to user about cancelling tripod order")
                if not cancel_order_found:
                    failed_checks.append(f"agent did not cancel the tripod order ({self.tripod_order_id})")
                rationale = "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
