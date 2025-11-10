from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.cab import CabApp
from are.simulation.apps.city import CityApp
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.shopping import ShoppingApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("daily_errand_plan_with_city_safety")
class DailyErrandPlanWithCitySafety(Scenario):
    """Comprehensive proactive scenario using all apps.

    The user wants to buy groceries, check local safety, schedule a reminder for pickup,
    and arrange a cab to a safe store location.
    The agent gathers data, proposes a transportation+shopping-action plan,
    and proceeds only after user approval.
    """

    start_time: float | None = 0
    duration: float | None = 40

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate all applications used in the scenario."""
        aui = AgentUserInterface()
        system = SystemApp(name="system-clock")
        reminders = ReminderApp()
        city = CityApp()
        cab = CabApp()
        shop = ShoppingApp()

        # Populate system with current time
        self.initial_time = system.get_current_time()
        self.apps = [aui, system, reminders, city, cab, shop]

    def build_events_flow(self) -> None:
        """Define the event flow with proactive agent proposal and user confirmation pattern."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        reminders = self.get_typed_app(ReminderApp)
        city = self.get_typed_app(CityApp)
        cab = self.get_typed_app(CabApp)
        shop = self.get_typed_app(ShoppingApp)

        # --- EVENT SEQUENCE DEFINITION ---
        with EventRegisterer.capture_mode():
            # --- 0: User initiates scenario ---
            e0 = aui.send_message_to_agent(
                content="Hey Assistant, I need to buy ingredients for dinner today. Can you find a grocery store and check if it's safe to visit?"
            ).depends_on(None, delay_seconds=1)

            # --- 1: Agent checks city data for safety rating ---
            e1 = city.get_crime_rate(zip_code="94107").oracle().depends_on(e0, delay_seconds=1)

            # --- 2: Agent searches for a grocery store and lists products ---
            e2 = shop.search_product(product_name="tomatoes", limit=3).oracle().depends_on(e1, delay_seconds=2)

            e3 = shop.list_all_products(limit=5).oracle().depends_on(e2, delay_seconds=1)

            # --- 3: Agent prepares a proactive transport proposal ---
            e4 = aui.send_message_to_user(
                content=(
                    "The grocery store nearby seems to be in a safe area. I found some ingredients available, "
                    "and a cab service is available to take you there. Should I order a cab to the MarketView grocery?"
                )
            ).depends_on(e3, delay_seconds=1)

            # --- 4: User confirms ---
            e5 = aui.send_message_to_agent(
                content="Yes, please go ahead and order the cab to MarketView grocery."
            ).depends_on(e4, delay_seconds=1)

            # --- 5: Agent gets quotation and orders the cab (post confirmation) ---
            ride_time = system.get_current_time()["datetime"]
            e6 = (
                cab.get_quotation(
                    start_location="123 Main Street",
                    end_location="MarketView grocery",
                    service_type="Default",
                    ride_time=ride_time,
                )
                .oracle()
                .depends_on(e5, delay_seconds=1)
            )
            e7 = (
                cab.order_ride(
                    start_location="123 Main Street",
                    end_location="MarketView grocery",
                    service_type="Default",
                    ride_time=ride_time,
                )
                .oracle()
                .depends_on(e6, delay_seconds=1)
            )

            # --- 6: Add grocery items to cart and checkout ---
            e8 = shop.add_to_cart(item_id="item_tomato_001", quantity=2).oracle().depends_on(e7, delay_seconds=1)
            e9 = shop.checkout().oracle().depends_on(e8, delay_seconds=1)

            # --- 7: Create a reminder for pickup ---
            reminder_time = "1970-01-01 18:00:00"
            e10 = (
                reminders.add_reminder(
                    title="Pick up grocery order",
                    due_datetime=reminder_time,
                    description="Remember to pick up the groceries before dinner.",
                )
                .oracle()
                .depends_on(e9, delay_seconds=1)
            )

            # --- 8: Agent ends by confirming plan and scheduling completion ---
            e11 = (
                aui.send_message_to_user(
                    content="Cab booked, order placed, and reminder set for pickup. You're all good for dinner today!"
                )
                .oracle()
                .depends_on(e10, delay_seconds=1)
            )

        self.events = [e0, e1, e2, e3, e4, e5, e6, e7, e8, e9, e10, e11]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that all actions across apps were executed properly."""
        try:
            events = env.event_log.list_view()

            # Check that all core operations happened
            # 1. Cab ordered
            ride_order_done = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CabApp"
                and e.action.function_name == "order_ride"
                for e in events
            )
            # 2. Reminder created
            reminder_added = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ReminderApp"
                and e.action.function_name == "add_reminder"
                for e in events
            )
            # 3. Shopping checkout completed
            checkout_done = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ShoppingApp"
                and e.action.function_name == "checkout"
                for e in events
            )
            # 4. City check performed
            city_safety_checked = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CityApp"
                and e.action.function_name == "get_crime_rate"
                for e in events
            )
            # 5. Agent proposed proactive step and user approved
            proactive_chain = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "cab" in e.action.args.get("content", "").lower()
                and "should i order" in e.action.args.get("content", "").lower()
                for e in events
            ) and any(
                e.event_type == EventType.USER
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "order the cab" in e.action.args.get("content", "").lower()
                for e in events
            )

            success_all = (
                ride_order_done and reminder_added and checkout_done and city_safety_checked and proactive_chain
            )
            return ScenarioValidationResult(success=success_all)
        except Exception as ex:
            return ScenarioValidationResult(success=False, exception=ex)
