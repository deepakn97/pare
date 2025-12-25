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
    StatefulCalendarApp,
    StatefulEmailApp,
)
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("shopping_order_calendar_sync_delivery")
class ShoppingOrderCalendarSyncDelivery(PASScenario):
    """Agent proactively creates calendar events for product deliveries based on incoming order confirmation notifications.

    The user places a shopping order for "Bluetooth Speaker" and "Laptop Stand" and checks out. Immediately after, an order confirmation email arrives that includes delivery details: "Your order #12345 will be delivered on December 22, 2025 between 2:00 PM - 4:00 PM." The agent must:
    1. Detect the order confirmation notification with delivery time window
    2. Extract delivery date, time window, and ordered products from the notification
    3. Check calendar to ensure no conflicts during the delivery window
    4. Proactively offer to create a calendar event to remind the user about the delivery
    5. Create a calendar event with title containing product names and delivery time window
    6. Set appropriate reminder for the delivery day

    This scenario exercises shopping notification parsing, temporal information extraction (delivery window → calendar time), cross-app coordination (shopping → calendar), proactive schedule management, and delivery tracking assistance..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps here
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.shopping = StatefulShoppingApp(name="Shopping")
        self.email = StatefulEmailApp(name="Emails")

        # Populate apps with scenario specific data here
        # Shopping: Create product catalog with Bluetooth Speaker and Laptop Stand
        # These products will be available for the user to purchase
        bluetooth_speaker_pid = self.shopping.add_product(name="Bluetooth Speaker")
        self.bluetooth_speaker_iid = self.shopping.add_item_to_product(
            product_id=bluetooth_speaker_pid,
            price=49.99,
            options={"color": "Black"},
            available=True,
        )

        laptop_stand_pid = self.shopping.add_product(name="Laptop Stand")
        self.laptop_stand_iid = self.shopping.add_item_to_product(
            product_id=laptop_stand_pid,
            price=29.99,
            options={"color": "Silver", "material": "Aluminum"},
            available=True,
        )

        # Calendar: Empty baseline - agent will create delivery event after order confirmation

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.calendar, self.shopping, self.email]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")

        with EventRegisterer.capture_mode():
            # Environment event 1: User adds Bluetooth Speaker to cart
            add_speaker_event = shopping_app.add_to_cart(item_id=self.bluetooth_speaker_iid, quantity=1).delayed(10)

            # Environment event 2: User adds Laptop Stand to cart
            add_stand_event = shopping_app.add_to_cart(item_id=self.laptop_stand_iid, quantity=1).depends_on(
                add_speaker_event, delay_seconds=1
            )

            # Environment event 3: User checks out and creates order
            checkout_event = shopping_app.checkout().depends_on(add_stand_event, delay_seconds=2)

            # Environment event 4: Order confirmation arrives as an email that includes the delivery window.
            # NOTE: The Shopping app model does not encode delivery windows, so the delivery timing must arrive via an observable artifact
            # (email/message/notification text) that the agent can read via tool calls.
            order_confirmation_email_event = email_app.send_email_to_user_with_id(
                email_id="email-order-12345",
                sender="Acme Shop",
                subject="Order Confirmation #12345",
                content=(
                    "Thanks for your purchase!\n\n"
                    "Order #12345 items:\n"
                    "- Bluetooth Speaker\n"
                    "- Laptop Stand\n\n"
                    "Delivery: December 22, 2025 between 2:00 PM - 4:00 PM.\n"
                ),
            ).depends_on(checkout_event, delay_seconds=2)

            # Oracle event 1: Agent lists emails to notice the new order confirmation
            list_emails_event = (
                email_app.list_emails(folder_name="INBOX", offset=0, limit=10)
                .oracle()
                .depends_on(order_confirmation_email_event, delay_seconds=2)
            )

            # Oracle event 2: Agent reads the confirmation email to extract delivery window + items
            read_email_event = (
                email_app.get_email_by_id(email_id="email-order-12345", folder_name="INBOX")
                .oracle()
                .depends_on(list_emails_event, delay_seconds=1)
            )

            # Oracle event 3: Agent checks calendar for the delivery window observed in the email (Dec 22, 2025, 2-4 PM)
            check_calendar_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-12-22 14:00:00", end_datetime="2025-12-22 16:00:00"
                )
                .oracle()
                .depends_on(read_email_event, delay_seconds=1)
            )

            # Oracle event 4: Agent proposes creating calendar event for delivery
            proposal_event = (
                aui.send_message_to_user(
                    content="Your order confirmation email (#12345) says the delivery is scheduled for December 22, 2025 between 2:00 PM and 4:00 PM. Would you like me to add a calendar event to remind you about the delivery?"
                )
                .oracle()
                .depends_on(check_calendar_event, delay_seconds=2)
            )

            # Oracle event 5: User accepts proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please add it to my calendar.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle event 6: Agent creates calendar event for delivery
            create_event = (
                calendar_app.add_calendar_event(
                    title="Delivery: Bluetooth Speaker, Laptop Stand",
                    start_datetime="2025-12-22 14:00:00",
                    end_datetime="2025-12-22 16:00:00",
                    description="Delivery window for order. Please be available to receive the package.",
                    tag="delivery",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle event 7: Agent confirms calendar event creation
            confirmation_event = (
                aui.send_message_to_user(
                    content="I've added the delivery event to your calendar for December 22, 2025 from 2:00 PM to 4:00 PM."
                )
                .oracle()
                .depends_on(create_event, delay_seconds=1)
            )

        # Register ALL events here in self.events
        self.events = [
            add_speaker_event,
            add_stand_event,
            checkout_event,
            order_confirmation_email_event,
            list_emails_event,
            read_email_event,
            check_calendar_event,
            proposal_event,
            acceptance_event,
            create_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to agent events only
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent read the order confirmation email to learn delivery window
            email_read_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name in {"list_emails", "get_email_by_id"}
                for e in agent_events
            )

            # STRICT Check 2: Agent checked calendar for the delivery time window
            # This is essential to ensure no conflicts during delivery
            check_calendar_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "get_calendar_events_from_to"
                for e in agent_events
            )

            # STRICT Check 3: Agent proposed creating calendar event for delivery
            # The agent must proactively offer this service
            proposal_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 4: Agent created calendar event with delivery information
            # This is the core action - must create event with proper time window
            create_calendar_event_found = False
            for e in agent_events:
                if (
                    isinstance(e.action, Action)
                    and e.action.class_name == "StatefulCalendarApp"
                    and e.action.function_name == "add_calendar_event"
                ):
                    args = e.action.args if e.action.args else e.action.resolved_args
                    # Verify the event contains delivery-related information
                    # Be flexible on exact title/description wording
                    title = args.get("title", "")
                    start_time = args.get("start_datetime", "")
                    end_time = args.get("end_datetime", "")

                    # Check that times match delivery window (2025-12-22, 2-4 PM)
                    # Be flexible on format but strict on date/time values
                    if (
                        "2025-12-22" in start_time
                        and "2025-12-22" in end_time
                        and "14:00" in start_time
                        and "16:00" in end_time
                    ):
                        create_calendar_event_found = True
                        break

            # Determine success and rationale
            all_checks = [
                ("read_order_email", email_read_found),
                ("check_calendar", check_calendar_found),
                ("proposal", proposal_found),
                ("create_calendar_event", create_calendar_event_found),
            ]

            failed_checks = [name for name, passed in all_checks if not passed]

            if failed_checks:
                rationale = f"Missing critical agent actions: {', '.join(failed_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
