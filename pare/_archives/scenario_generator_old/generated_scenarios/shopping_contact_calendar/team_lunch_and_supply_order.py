from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.shopping import ShoppingApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("team_lunch_and_supply_order")
class TeamLunchAndSupplyOrder(Scenario):
    """Scenario: The agent helps organize a team lunch and order office supplies.

    Demonstrates coordinated usage of all applications:
    - SystemApp: current time to decide scheduling slot
    - CalendarApp: creates a lunch event
    - ContactsApp: manages contacts (adds missing colleague)
    - ShoppingApp: orders supplies for meeting
    - AgentUserInterface: interactive user confirmation pattern (proposal, user approval, execution)
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and prepopulate the applications."""
        aui = AgentUserInterface()
        system = SystemApp(name="System")
        calendar = CalendarApp()
        contacts = ContactsApp()
        shopping = ShoppingApp()

        # Populate existing contacts and add new one dynamically
        contacts.add_new_contact(
            first_name="Emily",
            last_name="Roberts",
            gender=Gender.FEMALE,
            status=Status.EMPLOYED,
            age=29,
            email="emily.roberts@example.com",
            job="Designer",
            phone="+1 202 555 0139",
        )

        contacts.add_new_contact(
            first_name="Liam",
            last_name="Carter",
            gender=Gender.MALE,
            status=Status.EMPLOYED,
            age=31,
            email="liam.carter@example.com",
            job="Project Manager",
            phone="+1 202 555 0163",
        )

        self.apps = [aui, system, calendar, contacts, shopping]

    def build_events_flow(self) -> None:
        """Build the flow of events where the agent organizes team lunch and orders supplies."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        calendar = self.get_typed_app(CalendarApp)
        contacts = self.get_typed_app(ContactsApp)
        shopping = self.get_typed_app(ShoppingApp)

        with EventRegisterer.capture_mode():
            # User initiates request
            user_msg = aui.send_message_to_agent(
                content="Hey Assistant, can you help plan our Friday team lunch and also restock some office notebooks?"
            ).depends_on(None, delay_seconds=1)

            # Agent checks current system time
            system_time = system.get_current_time().depends_on(user_msg, delay_seconds=1)

            # Agent looks up existing contacts
            contact_search = contacts.search_contacts(query="Emily").depends_on(system_time, delay_seconds=1)

            # Agent proposes a plan combining lunch setup & a shopping step
            proposal_to_user = aui.send_message_to_user(
                content=(
                    "I found Emily and Liam on your team. Shall I schedule the team lunch for Friday noon, "
                    "and place an order for 10 office notebooks and pens?"
                )
            ).depends_on(contact_search, delay_seconds=1)

            # User gives explicit approval
            user_approval = aui.send_message_to_agent(
                content="Yes, that sounds good—schedule the lunch and order the items."
            ).depends_on(proposal_to_user, delay_seconds=2)

            # Agent executes lunch event creation
            lunch_event = (
                calendar.add_calendar_event(
                    title="Team Lunch - Downtown Bistro",
                    start_datetime="1970-01-09 12:00:00",
                    end_datetime="1970-01-09 13:00:00",
                    tag="Team",
                    description="Casual Friday team lunch to discuss design ideas.",
                    location="Downtown Bistro",
                    attendees=["Emily Roberts", "Liam Carter"],
                )
                .oracle()
                .depends_on(user_approval, delay_seconds=1)
            )

            # Agent searches for supplies to order
            search_supplies = shopping.search_product(product_name="notebook", limit=3).depends_on(
                lunch_event, delay_seconds=1
            )

            # Agent gets details about the first product found
            get_details = shopping.get_product_details(product_id="1").depends_on(search_supplies, delay_seconds=1)

            # Agent adds item to cart
            add_items = shopping.add_to_cart(item_id="1", quantity=10).depends_on(get_details, delay_seconds=1)

            # Agent lists available discounts
            discount_codes = shopping.get_all_discount_codes().depends_on(add_items, delay_seconds=1)

            # Agent proceeds with checkout (order supplies)
            checkout_order = shopping.checkout(discount_code=None).oracle().depends_on(discount_codes, delay_seconds=1)

            # Finally, agent informs the user that tasks are completed
            final_confirmation = (
                aui.send_message_to_user(
                    content="I've scheduled the lunch with Emily and Liam and placed the supply order successfully!"
                )
                .oracle()
                .depends_on(checkout_order, delay_seconds=1)
            )

        self.events = [
            user_msg,
            system_time,
            contact_search,
            proposal_to_user,
            user_approval,
            lunch_event,
            search_supplies,
            get_details,
            add_items,
            discount_codes,
            checkout_order,
            final_confirmation,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Check that lunch event and order actions occurred with confirmation flow."""
        try:
            events = env.event_log.list_view()

            proposal_done = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "schedule" in e.action.args["content"].lower()
                and "order" in e.action.args["content"].lower()
                for e in events
            )

            calendar_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Team Lunch" in e.action.args["title"]
                for e in events
            )

            checkout_completed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ShoppingApp"
                and e.action.function_name == "checkout"
                for e in events
            )

            final_msg = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "scheduled the lunch" in e.action.args["content"].lower()
                and "placed the supply order" in e.action.args["content"].lower()
                for e in events
            )

            return ScenarioValidationResult(
                success=(proposal_done and calendar_created and checkout_completed and final_msg)
            )
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
