from __future__ import annotations

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.sandbox_file_system import Files
from are.simulation.apps.shopping import ShoppingApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("ecommerce_followup_workflow")
class EcommerceFollowupWorkflow(Scenario):
    """A comprehensive ecommerce workflow scenario involving shopping, scheduling, and reminders.

    The user asks the assistant to find a new laptop, schedule its delivery on the calendar,
    create a receipt folder, and set a reminder for a follow-up discount offer.
    The scenario demonstrates usage of all available apps:
      - ShoppingApp: searching and checkout
      - CalendarApp: scheduling delivery
      - ReminderApp: adding reminder
      - Files: creating local receipt files
      - SystemApp: tracking time
      - AgentUserInterface: core communication with proactive pattern
    """

    start_time: float | None = 0
    duration: float | None = 50

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize all applications with basic data."""
        aui = AgentUserInterface()
        system = SystemApp(name="system")
        calendar = CalendarApp()
        reminder = ReminderApp()
        shopping = ShoppingApp()
        fs = Files(name="sandbox", sandbox_dir=kwargs.get("sandbox_dir"))

        # set up basic directory for receipts
        fs.makedirs(path="receipts", exist_ok=True)

        self.apps = [aui, system, calendar, reminder, shopping, fs]

    def build_events_flow(self) -> None:
        """Define the events sequence with proactive confirmation interaction."""
        aui = self.get_typed_app(AgentUserInterface)
        shopping = self.get_typed_app(ShoppingApp)
        calendar = self.get_typed_app(CalendarApp)
        reminder = self.get_typed_app(ReminderApp)
        fs = self.get_typed_app(Files)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # Step 0: user request to find a laptop and handle purchase planning
            user_request = aui.send_message_to_agent(
                content="I want to buy a gaming laptop. Can you handle the purchase details and add follow-ups?"
            ).depends_on(None, delay_seconds=0)

            # Step 1: agent searches for laptops in shop
            search_event = shopping.search_product(product_name="gaming laptop").depends_on(
                user_request, delay_seconds=1
            )

            # Step 2: agent gets discount info
            discount_event = shopping.get_all_discount_codes().depends_on(search_event, delay_seconds=1)

            # Step 3: agent finds a laptop and adds to cart
            add_cart_event = shopping.add_to_cart(item_id="laptop_123", quantity=1).depends_on(
                discount_event, delay_seconds=1
            )

            # Step 4: agent proactively proposes scheduling and reminder to the user
            propose_action = aui.send_message_to_user(
                content=(
                    "I found a gaming laptop that matches your request. "
                    "Would you like me to complete the purchase, schedule delivery next Tuesday at 10 AM, "
                    "create a receipt in your files, and set a reminder to check for discounts next month?"
                )
            ).depends_on(add_cart_event, delay_seconds=1)

            # Step 5: user approves proposal
            user_approval = aui.send_message_to_agent(
                content="Yes, go ahead with all of those steps please."
            ).depends_on(propose_action, delay_seconds=1)

            # Step 6: system checks current time before scheduling
            get_time_event = system.get_current_time().depends_on(user_approval, delay_seconds=1)

            # Step 7: agent performs checkout of the laptop (oracle)
            checkout_event = shopping.checkout(discount_code=None).oracle().depends_on(get_time_event, delay_seconds=1)

            # Step 8: agent creates a receipt file and saves purchase info
            mkdir_event = fs.mkdir(path="receipts/october_orders", create_parents=True).depends_on(
                checkout_event, delay_seconds=1
            )

            write_receipt_event = fs.open(path="receipts/october_orders/laptop_receipt.txt", mode="w").depends_on(
                mkdir_event, delay_seconds=1
            )

            # Step 9: agent schedules calendar delivery
            add_delivery_event = calendar.add_calendar_event(
                title="Laptop Delivery",
                start_datetime="2024-10-15 10:00:00",
                end_datetime="2024-10-15 11:00:00",
                description="Gaming laptop delivery from store",
                location="Home address",
                attendees=["Delivery Service"],
            ).depends_on(write_receipt_event, delay_seconds=1)

            # Step 10: agent creates reminder for next discount check
            reminder_event = reminder.add_reminder(
                title="Check new laptop deals",
                due_datetime="2024-11-15 09:00:00",
                description="Follow-up on November discount sale.",
                repetition_unit="month",
                repetition_value=1,
            ).depends_on(add_delivery_event, delay_seconds=1)

            # Step 11: list today's calendar events to confirm
            list_events = calendar.read_today_calendar_events().depends_on(reminder_event, delay_seconds=1)

            # Step 12: Wait briefly for confirmation
            wait_event = system.wait_for_notification(timeout=2).depends_on(list_events, delay_seconds=1)

            # Step 13: agent summarizes completion
            completion_notify = (
                aui.send_message_to_user(
                    content=(
                        "All steps are done: purchase confirmed, delivery scheduled, "
                        "receipt saved, and reminder created."
                    )
                )
                .oracle()
                .depends_on(wait_event, delay_seconds=1)
            )

        self.events = [
            user_request,
            search_event,
            discount_event,
            add_cart_event,
            propose_action,
            user_approval,
            get_time_event,
            checkout_event,
            mkdir_event,
            write_receipt_event,
            add_delivery_event,
            reminder_event,
            list_events,
            wait_event,
            completion_notify,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Confirm that checkout, calendar, and reminder tasks completed successfully."""
        try:
            event_log = env.event_log.list_view()
            did_checkout = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ShoppingApp"
                and e.action.function_name == "checkout"
                for e in event_log
            )
            did_schedule = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Delivery" in e.action.args.get("title", "")
                for e in event_log
            )
            did_remind = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ReminderApp"
                and e.action.function_name == "add_reminder"
                for e in event_log
            )
            did_message = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "All steps are done" in e.action.args.get("content", "")
                for e in event_log
            )
            success = did_checkout and did_schedule and did_remind and did_message
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
