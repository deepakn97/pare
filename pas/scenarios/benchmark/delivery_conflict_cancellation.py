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
    StatefulEmailApp,
)
from pas.apps.reminder import StatefulReminderApp
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("delivery_conflict_cancellation")
class DeliveryConflictCancellation(PASScenario):
    """Agent detects a delivery time conflict between an incoming order shipment notification and an existing reminder about being unavailable, then cancels the order.

    The user has a reminder titled "Out of town - Boston trip" due on Thursday covering the time period they'll be traveling. The shopping app sends a notification that an order for "Smart Home Camera" has shipped and will be delivered Thursday between 2-4 PM, requiring signature on delivery. The agent must:
    1. Parse the incoming delivery notification extracting the delivery date and time window (Thursday 2-4 PM)
    2. Check reminders (as suggested by the delivery email) and identify the conflicting "Out of town" reminder for the same day
    3. Recognize the user cannot receive the signature-required delivery while traveling
    4. Retrieve the order details to confirm it is cancellable
    5. Propose canceling the order before it reaches the delivery address
    6. After user acceptance, cancel the order via `cancel_order()`
    7. Delete or update the reminder to note the cancellation was handled

    This scenario exercises temporal conflict detection between delivery logistics and personal availability, order status reasoning, cross-app correlation (shopping notifications + reminder calendar), proactive order cancellation, and post-cancellation reminder cleanup.

    ---.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize reminder app
        self.reminder = StatefulReminderApp(name="Reminders")

        # Initialize shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Initialize email app (used to deliver delivery-window details as an observable artifact).
        self.email = StatefulEmailApp(name="Emails")

        # Populate reminder app with baseline data
        # Add a reminder for the user being out of town on Thursday
        # Thursday is November 20, 2025 (start_time is Nov 18, 2025 at 9:00 AM)
        self.reminder.add_reminder(
            title="Out of town - Boston trip",
            due_datetime="2025-11-20 08:00:00",
            description="Away for business trip. Not home to receive deliveries.",
            repetition_unit=None,
            repetition_value=None,
        )

        # Populate shopping app with baseline data
        # Add a Smart Home Camera product to the catalog
        product_id = self.shopping.add_product(name="Smart Home Camera")
        item_id = self.shopping.add_item_to_product(
            product_id=product_id,
            price=149.99,
            options={"color": "white", "resolution": "1080p"},
            available=True,
        )

        # Create a "shipped" order for this item that was placed earlier
        # Order was placed on Nov 17, one day before start_time
        # Use load_orders_from_dict to avoid CartItem initialization bug in add_order
        order_datetime = datetime(2025, 11, 17, 14, 0, 0, tzinfo=UTC)
        self.shopping.load_orders_from_dict({
            "order_camera_001": {
                "order_id": "order_camera_001",
                "order_status": "shipped",
                "order_date": order_datetime.isoformat(),
                "order_total": 149.99,
                "order_items": {
                    item_id: {
                        "item_id": item_id,
                        "quantity": 1,
                        "price": 149.99,
                        "available": True,
                        "options": {"color": "white", "resolution": "1080p"},
                    }
                },
            }
        })

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.reminder, self.shopping, self.email]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Shopping app sends order shipment notification
            # This is the trigger - order has shipped and will be delivered Thursday 2-4 PM
            shipment_notification_event = shopping_app.update_order_status(
                order_id="order_camera_001", status="shipped"
            ).delayed(3)

            # Environment Event 2: Order confirmation email arrives with delivery window + signature requirement.
            # NOTE: Meta-ARE Shopping order details do NOT include delivery windows, so this must be delivered via observable text.
            delivery_email_event = email_app.send_email_to_user_with_id(
                email_id="email-order-camera-001",
                sender="Acme Shop",
                subject="Delivery scheduled for your Smart Home Camera order",
                content=(
                    "Order: Smart Home Camera (order_camera_001)\n"
                    "Status: shipped\n\n"
                    "Delivery scheduled: Thursday (Nov 20) between 2:00 PM - 4:00 PM.\n"
                    "Signature required on delivery.\n"
                    "\n"
                    "If you might be away during the delivery window, please check your reminders/calendar for conflicts. "
                    "If you won't be available to sign, cancel the order before delivery.\n"
                ),
            ).depends_on(shipment_notification_event, delay_seconds=2)

            # Oracle Event 1: Agent reads the delivery email to learn the delivery window.
            # Motivated by: delivery email provides the only source of delivery-window timing.
            read_delivery_email_event = (
                email_app.get_email_by_id(email_id="email-order-camera-001", folder_name="INBOX")
                .oracle()
                .depends_on(delivery_email_event, delay_seconds=2)
            )

            # Oracle Event 1b: Agent retrieves order details to confirm it exists and is cancellable.
            # Motivated by: email references order_id "order_camera_001"; agent confirms order state.
            get_order_event = (
                shopping_app.get_order_details(order_id="order_camera_001")
                .oracle()
                .depends_on(read_delivery_email_event, delay_seconds=1)
            )

            # Oracle Event 2: Agent checks reminders for conflicts with Thursday delivery
            # Motivated by: delivery email explicitly instructs checking reminders/calendar for conflicts with the signature-required window.
            check_reminders_event = (
                reminder_app.get_all_reminders().oracle().depends_on(get_order_event, delay_seconds=1)
            )

            # Oracle Event 3: Agent proposes canceling the order due to delivery conflict
            # Motivated by: reminders revealed "Out of town - Boston trip" on Nov 20, conflicting with delivery
            proposal_event = (
                aui.send_message_to_user(
                    content="Your Smart Home Camera order (order_camera_001) has shipped. The delivery email says it's scheduled for Thursday (Nov 20) between 2-4 PM and requires a signature. You also have an 'Out of town - Boston trip' reminder that day, so you likely won't be home to sign. Would you like me to cancel the order before delivery?"
                )
                .oracle()
                .depends_on(check_reminders_event, delay_seconds=2)
            )

            # Oracle Event 4: User accepts the proposal to cancel the order
            acceptance_event = (
                aui.accept_proposal(content="Yes, please cancel the order. I won't be home to receive it.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent cancels the order
            # Motivated by: user accepted the cancellation proposal
            cancel_order_event = (
                shopping_app.cancel_order(order_id="order_camera_001")
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 6: Agent confirms cancellation to user
            # Motivated by: successful order cancellation needs user acknowledgment
            confirmation_event = (
                aui.send_message_to_user(
                    content="I've successfully cancelled your Smart Home Camera order. You won't be charged for the missed delivery."
                )
                .oracle()
                .depends_on(cancel_order_event, delay_seconds=1)
            )

        # Register ALL events
        self.events = [
            shipment_notification_event,
            delivery_email_event,
            read_delivery_email_event,
            get_order_event,
            check_reminders_event,
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

            # STRICT Check 1: Agent retrieved order details to understand delivery window
            # After receiving shipment notification, agent must get order details
            get_order_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_order_details"
                and e.action.args.get("order_id") == "order_camera_001"
                for e in log_entries
            )

            # STRICT Check 2: Agent checked reminders to detect availability conflict
            # Must query reminders to discover the "Out of town" conflict
            check_reminders_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulReminderApp"
                and e.action.function_name == "get_all_reminders"
                for e in log_entries
            )

            # STRICT Check 3: Agent sent proposal to user about the delivery conflict
            # Must propose canceling order and reference both delivery and unavailability
            # FLEXIBLE: exact wording can vary but must reference core conflict
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 4: Agent cancelled the order after user acceptance
            # Must execute cancel_order with correct order_id
            cancel_order_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "cancel_order"
                and e.action.args.get("order_id") == "order_camera_001"
                for e in log_entries
            )

            # Build success result and rationale
            strict_checks = [
                ("get_order_details", get_order_found),
                ("check_reminders", check_reminders_found),
                ("proposal_sent", proposal_found),
                ("order_cancelled", cancel_order_found),
            ]

            failed_checks = [name for name, passed in strict_checks if not passed]

            success = all(passed for _, passed in strict_checks)

            if not success:
                rationale = f"Missing critical agent actions: {', '.join(failed_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
