from __future__ import annotations

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.shopping import ShoppingApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("productivity_supply_planner")
class ProductivitySupplyPlanner(Scenario):
    """A scenario demonstrating a productivity and purchasing planning workflow.

    The agent proactively coordinates:
    - Time management (SystemApp)
    - Purchase planning (ShoppingApp)
    - Tracking purchase reminders (ReminderApp)
    - Scheduling delivery and setup slots (CalendarApp)
    - Interaction and confirmation with the user (AgentUserInterface)

    Proactive flow pattern:
      1. Agent proposes order placement to the user.
      2. User confirms explicitly.
      3. Agent executes the purchase and schedules a calendar event with a reminder.
    """

    start_time: float | None = 0
    duration: float | None = 30

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and populate applications for a productivity and supply scenario."""
        aui = AgentUserInterface()
        calendar = CalendarApp()
        reminder = ReminderApp()
        shop = ShoppingApp()
        system = SystemApp(name="system")

        # Populate the shopping app with some catalog detail
        shop.list_all_products(offset=0, limit=10)
        _ = shop.get_all_discount_codes()

        self.apps = [aui, calendar, reminder, shop, system]

    def build_events_flow(self) -> None:
        """Define the workflow events for the scenario."""
        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(CalendarApp)
        reminder = self.get_typed_app(ReminderApp)
        shop = self.get_typed_app(ShoppingApp)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # User initiates the interaction
            start_request = aui.send_message_to_agent(
                content="I want to organize an office supply restock for next week. Can you help me plan it?"
            ).depends_on(None, delay_seconds=1)

            # System reports current time
            sys_time = system.get_current_time().depends_on(start_request, delay_seconds=1)

            # Agent searches for items to restock
            search_item = shop.search_product(product_name="notebook", offset=0, limit=2).depends_on(
                sys_time, delay_seconds=1
            )

            # Agent proposes an action (proactive interaction)
            propose_action = aui.send_message_to_user(
                content="I found some notebooks on sale with a valid discount. Should I add two packs to your cart and place the order?"
            ).depends_on(search_item, delay_seconds=1)

            # User approves the proposed purchase
            user_confirms = aui.send_message_to_agent(
                content="Yes, please add the notebooks and proceed with the purchase using the discount."
            ).depends_on(propose_action, delay_seconds=1)

            # Agent adds items to the cart
            add_to_cart = shop.add_to_cart(item_id="notebook_001", quantity=2).depends_on(
                user_confirms, delay_seconds=1
            )

            # Agent checks for discount code applicability
            discount_info = shop.get_discount_code_info(discount_code="OFFICE10").depends_on(
                add_to_cart, delay_seconds=1
            )

            # Agent proceeds to checkout with discount
            oracle_checkout = (
                shop.checkout(discount_code="OFFICE10").oracle().depends_on(discount_info, delay_seconds=1)
            )

            # System waits for order confirmation
            sys_wait = system.wait_for_notification(timeout=2).depends_on(oracle_checkout, delay_seconds=1)

            # Agent schedules a calendar event for delivery
            delivery_event = calendar.add_calendar_event(
                title="Notebook Delivery Appointment",
                start_datetime="1970-01-08 10:00:00",
                end_datetime="1970-01-08 11:00:00",
                tag="Delivery",
                description="Expected delivery of office supplies",
                location="Main Office",
                attendees=["Logistics Team"],
            ).depends_on(sys_wait, delay_seconds=1)

            # Reminder for checking delivery progress
            delivery_reminder = reminder.add_reminder(
                title="Track Delivery",
                due_datetime="1970-01-08 09:00:00",
                description="Verify shipment status before arrival",
                repetition_unit=None,
            ).depends_on(delivery_event, delay_seconds=1)

            # Agent reports scheduled tasks to the user
            completion_notice = aui.send_message_to_user(
                content="The purchase was completed and a delivery appointment has been scheduled for next Wednesday. A reminder will notify you a few hours before delivery."
            ).depends_on(delivery_reminder, delay_seconds=1)

        self.events = [
            start_request,
            sys_time,
            search_item,
            propose_action,
            user_confirms,
            add_to_cart,
            discount_info,
            oracle_checkout,
            sys_wait,
            delivery_event,
            delivery_reminder,
            completion_notice,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate overall workflow correctness."""
        try:
            events = env.event_log.list_view()
            # validation targets:
            purchase_done = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "ShoppingApp"
                and event.action.function_name == "checkout"
                and event.action.args.get("discount_code") == "OFFICE10"
                for event in events
            )
            scheduled_delivery = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "CalendarApp"
                and event.action.function_name == "add_calendar_event"
                and "Delivery" in (event.action.args.get("tag") or "")
                for event in events
            )
            reminder_created = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "ReminderApp"
                and event.action.function_name == "add_reminder"
                and "Track" in (event.action.args.get("title") or "")
                for event in events
            )
            proactive_confirm = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "AgentUserInterface"
                and event.action.function_name == "send_message_to_user"
                and "Should I add" in event.action.args.get("content", "")
                for event in events
            )

            user_response_ack = any(
                event.event_type == EventType.USER
                and isinstance(event.action, Action)
                and "please add the notebooks" in event.action.args.get("content", "").lower()
                for event in events
            )

            return ScenarioValidationResult(
                success=purchase_done
                and scheduled_delivery
                and reminder_created
                and proactive_confirm
                and user_response_ack
            )
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
