from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.shopping import ShoppingApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("proactive_gift_reminder_workflow")
class ProactiveGiftReminderWorkflow(Scenario):
    """Scenario: Agent proactively helps the user buy a birthday gift for a friend.

    The agent detects a birthday event in the calendar, suggests buying a gift,
    confirms with the user, shops for the item, and schedules a reminder to give the gift.

    This scenario uses all major app categories:
        - AgentUserInterface: communication of proposal and confirmation
        - CalendarApp: finding and adding events/reminders
        - ContactsApp: storing and retrieving friend details
        - ShoppingApp: searching and ordering a gift
        - SystemApp: managing time and waiting to simulate timing and notification
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate all applications."""
        aui = AgentUserInterface()
        calendar = CalendarApp()
        contacts = ContactsApp()
        shopping = ShoppingApp()
        system = SystemApp(name="System")

        # Add a friend contact with a birthday coming up
        contact_id = contacts.add_new_contact(
            first_name="Lara",
            last_name="Nguyen",
            gender=Gender.FEMALE,
            nationality="Canadian",
            city_living="Montreal",
            country="Canada",
            status=Status.EMPLOYED,
            job="Architect",
            description="Close friend with birthday coming soon",
            phone="+1 514 987 6543",
            email="lara.nguyen@example.com",
        )

        # Add a calendar event for Lara's birthday
        calendar.add_calendar_event(
            title="Lara Nguyen's Birthday",
            start_datetime="2024-08-15 00:00:00",
            end_datetime="2024-08-15 23:59:59",
            tag="Birthday",
            description="Reminder: Lara's birthday. Need to get her a nice gift!",
            location="Montreal",
            attendees=["Lara Nguyen"],
        )

        # Pre-fill the store catalog (done implicitly by ShoppingApp API simulation)
        # All other apps are now ready for interaction
        self.apps = [aui, calendar, contacts, shopping, system]

    def build_events_flow(self) -> None:
        """Define sequential interactive and oracle events."""
        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(CalendarApp)
        shopping = self.get_typed_app(ShoppingApp)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # 1. User starts interaction: asks for daily planning
            user_greeting = aui.send_message_to_agent(content="What's on my schedule today?").depends_on(
                None, delay_seconds=1
            )

            # 2. System retrieves current time (simulated context)
            check_time = system.get_current_time().oracle().depends_on(user_greeting, delay_seconds=1)

            # 3. Agent reads today's events
            scan_calendar = calendar.read_today_calendar_events().oracle().depends_on(check_time, delay_seconds=1)

            # 4. Agent notices Lara's birthday tomorrow and proposes buying a gift
            agent_proposes = aui.send_message_to_user(
                content="I see that Lara Nguyen's birthday is tomorrow. "
                "Would you like me to help you pick and order a thoughtful gift?"
            ).depends_on(scan_calendar, delay_seconds=1)

            # 5. User approves action
            user_approval = aui.send_message_to_agent(
                content="Yes, please find something nice and order it."
            ).depends_on(agent_proposes, delay_seconds=1)

            # 6. Agent searches for gift in ShoppingApp
            find_gift = (
                shopping.search_product(product_name="handmade mug", limit=3)
                .oracle()
                .depends_on(user_approval, delay_seconds=1)
            )

            # 7. Agent gets product details of the first item
            get_details = (
                shopping.get_product_details(product_id="product_1").oracle().depends_on(find_gift, delay_seconds=1)
            )

            # 8. Agent adds item to cart and checks available discount codes
            add_to_cart = (
                shopping.add_to_cart(item_id="product_1", quantity=1).oracle().depends_on(get_details, delay_seconds=1)
            )

            discount_codes = shopping.get_all_discount_codes().oracle().depends_on(add_to_cart, delay_seconds=1)

            apply_discount_info = (
                shopping.get_discount_code_info(discount_code="BDAY15")
                .oracle()
                .depends_on(discount_codes, delay_seconds=1)
            )

            # 9. After verifying the discount, agent checks out the order
            checkout_order = (
                shopping.checkout(discount_code="BDAY15").oracle().depends_on(apply_discount_info, delay_seconds=1)
            )

            # 10. Agent confirms purchase to the user
            gift_purchased = aui.send_message_to_user(
                content="The handmade mug has been ordered with the BDAY15 discount. "
                "Would you like me to add a reminder to give it to Lara tomorrow?"
            ).depends_on(checkout_order, delay_seconds=1)

            # 11. User confirms to add reminder
            reminder_confirmation = aui.send_message_to_agent(
                content="Yes, set a reminder for the morning of her birthday."
            ).depends_on(gift_purchased, delay_seconds=1)

            # 12. Agent adds new calendar event for the reminder
            add_reminder = (
                calendar.add_calendar_event(
                    title="Give Lara her birthday gift",
                    start_datetime="2024-08-15 09:00:00",
                    end_datetime="2024-08-15 09:15:00",
                    tag="Gift",
                    description="Remember to give the handmade mug to Lara when you see her.",
                    location="Montreal",
                    attendees=["User"],
                )
                .oracle()
                .depends_on(reminder_confirmation, delay_seconds=1)
            )

            # 13. System waits to simulate a quiet period before the next day
            waiting = system.wait_for_notification(timeout=3).oracle().depends_on(add_reminder, delay_seconds=1)

            # 14. Agent retrieves orders for log confirmation
            review_orders = shopping.list_orders().oracle().depends_on(waiting, delay_seconds=1)

        self.events = [
            user_greeting,
            check_time,
            scan_calendar,
            agent_proposes,
            user_approval,
            find_gift,
            get_details,
            add_to_cart,
            discount_codes,
            apply_discount_info,
            checkout_order,
            gift_purchased,
            reminder_confirmation,
            add_reminder,
            waiting,
            review_orders,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate agent behavior for full workflow completion."""
        try:
            events = env.event_log.list_view()

            proposed_action = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "AgentUserInterface"
                and "birthday" in ev.action.args["content"].lower()
                and "gift" in ev.action.args["content"].lower()
                for ev in events
            )

            ordered_item = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "ShoppingApp"
                and ev.action.function_name == "checkout"
                and ev.action.args.get("discount_code") == "BDAY15"
                for ev in events
            )

            reminder_added = any(
                (
                    ev.event_type == EventType.AGENT
                    and isinstance(ev.action, Action)
                    and ev.action.class_name == "CalendarApp"
                    and ev.action.function_name == "add_calendar_event"
                    and "Lara" in ev.action.args.get("title", "")
                )
                or "gift" in str(ev.action.args.get("title", "")).lower()
                for ev in events
            )

            return ScenarioValidationResult(success=(proposed_action and ordered_item and reminder_added))
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
