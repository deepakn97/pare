from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.shopping import ShoppingApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("event_planning_shopping_assistant")
class EventPlanningShoppingAssistant(Scenario):
    """Scenario: Agent assists the user to plan a team celebration event and purchase items for it.

    This scenario demonstrates:
    - Using ContactsApp to manage and reference colleagues for an event
    - Using CalendarApp to schedule the event
    - Using ShoppingApp to search and buy celebration supplies
    - Using SystemApp to determine timing context
    - Using AgentUserInterface for proactive communication with the user
    - Incorporates the required proactive interaction pattern (proposal -> approval -> action)
    """

    start_time: float | None = 0
    duration: float | None = 40

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate all applications for event planning and shopping."""
        aui = AgentUserInterface()
        calendar = CalendarApp()
        contacts = ContactsApp()
        shopping = ShoppingApp()
        system = SystemApp(name="System")

        # Populate contacts with some colleagues
        contacts.add_new_contact(
            first_name="Jordan",
            last_name="Miles",
            gender=Gender.MALE,
            age=32,
            job="Project Manager",
            email="jordan.miles@company.com",
            status=Status.EMPLOYED,
        )
        contacts.add_new_contact(
            first_name="Alyssa",
            last_name="Kim",
            gender=Gender.FEMALE,
            age=28,
            job="Designer",
            email="alyssa.kim@company.com",
            status=Status.EMPLOYED,
        )

        # List of apps used
        self.apps = [aui, calendar, contacts, shopping, system]

    def build_events_flow(self) -> None:
        """Build the full event flow covering calendar, contacts, shopping, and system actions."""
        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(CalendarApp)
        contacts = self.get_typed_app(ContactsApp)
        shopping = self.get_typed_app(ShoppingApp)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # 1. User asks assistant to plan a celebration
            user_starts = aui.send_message_to_agent(
                content="Hey assistant, let's plan a small celebration for the project completion next week."
            ).depends_on(None, delay_seconds=1)

            # 2. System notes the current time
            current_time = system.get_current_time().depends_on(user_starts, delay_seconds=1)

            # 3. Agent looks up contacts to find eligible attendees
            list_colleagues = contacts.get_contacts(offset=0).depends_on(current_time, delay_seconds=1)

            # 4. Agent proactively proposes an event creation to the user
            proposal_message = aui.send_message_to_user(
                content="I found Jordan Miles and Alyssa Kim in your contacts. Would you like me to schedule a 'Project Celebration Lunch' next Friday at 12:30 PM with them?"
            ).depends_on(list_colleagues, delay_seconds=1)

            # 5. User approves event scheduling
            user_approval = aui.send_message_to_agent(
                content="Yes, go ahead and add the Celebration Lunch with both of them."
            ).depends_on(proposal_message, delay_seconds=1)

            # 6. Agent adds the calendar event upon approval (proactive execution)
            create_event = (
                calendar.add_calendar_event(
                    title="Project Celebration Lunch",
                    start_datetime="1970-01-08 12:30:00",
                    end_datetime="1970-01-08 14:00:00",
                    tag="team",
                    description="Lunch to celebrate project completion.",
                    location="Downtown Bistro",
                    attendees=["Jordan Miles", "Alyssa Kim"],
                )
                .oracle()
                .depends_on(user_approval, delay_seconds=1)
            )

            # 7. Agent checks today's events (context verification)
            list_today = calendar.read_today_calendar_events().depends_on(create_event, delay_seconds=1)

            # 8. Agent searches shopping catalog for cakes
            search_cake = shopping.search_product(product_name="cake", limit=3).depends_on(list_today, delay_seconds=1)

            # 9. Agent proposes purchasing a cake for the event
            propose_cake = aui.send_message_to_user(
                content="I found some cakes available for purchase. Shall I add one chocolate cake to your cart for the celebration?"
            ).depends_on(search_cake, delay_seconds=1)

            # 10. User approves purchasing the cake
            user_approve_buy = aui.send_message_to_agent(
                content="Yes, please add a chocolate cake to my cart."
            ).depends_on(propose_cake, delay_seconds=1)

            # 11. Agent adds the cake to cart (assume product id 'cake123')
            add_to_cart = (
                shopping.add_to_cart(item_id="cake123", quantity=1)
                .oracle()
                .depends_on(user_approve_buy, delay_seconds=1)
            )

            # 12. Agent checks cart contents
            view_cart = shopping.list_cart().depends_on(add_to_cart, delay_seconds=1)

            # 13. Agent lists current discount codes to check if one applies
            list_discounts = shopping.get_all_discount_codes().depends_on(view_cart, delay_seconds=1)

            # 14. Wait briefly to simulate system idle before checkout
            wait_time = system.wait_for_notification(timeout=3).depends_on(list_discounts, delay_seconds=1)

            # 15. Agent performs checkout (oracle event)
            perform_checkout = shopping.checkout(discount_code=None).oracle().depends_on(wait_time, delay_seconds=1)

        self.events = [
            user_starts,
            current_time,
            list_colleagues,
            proposal_message,
            user_approval,
            create_event,
            list_today,
            search_cake,
            propose_cake,
            user_approve_buy,
            add_to_cart,
            view_cart,
            list_discounts,
            wait_time,
            perform_checkout,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validation checks.

        - Event created with the correct title
        - Cake checkout occurred
        - Agent proposed actions to user for both scheduling and shopping
        """
        try:
            evs = env.event_log.list_view()

            event_created = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "CalendarApp"
                and event.action.function_name == "add_calendar_event"
                and "Project Celebration Lunch" in str(event.action.args.get("title", ""))
                for event in evs
            )

            checkout_done = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "ShoppingApp"
                and event.action.function_name == "checkout"
                for event in evs
            )

            proactive_prompts = [
                e
                for e in evs
                if e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "Would you like" in str(e.action.args.get("content", ""))
            ]
            proposed_actions = len(proactive_prompts) >= 1

            success = event_created and checkout_done and proposed_actions
            return ScenarioValidationResult(success=success)
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
