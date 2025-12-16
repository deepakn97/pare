from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import RentAFlat
from are.simulation.apps.cab import CabApp
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.shopping import ShoppingApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer


@register_scenario("city_living_home_setup_assistant")
class CityLivingHomeSetupAssistant(Scenario):
    """Scenario: The agent helps the user coordinate setting up a new home in the city.

    The user wants to move into a new apartment, buy some furniture,
    schedule the move-in date, and arrange a cab to visit the property beforehand.

    The scenario demonstrates integration across all apps:
    - RentAFlat: searching and saving apartments
    - ShoppingApp: buying essential furniture
    - CalendarApp: scheduling house visits and deliveries
    - CabApp: booking transportation to the property
    - SystemApp: retrieving current time for scheduling reference
    - AgentUserInterface: proactive communication workflow
    """

    start_time: float | None = 0
    duration: float | None = 36

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate all applications."""
        aui = AgentUserInterface()
        calendar = CalendarApp()
        rent_flat = RentAFlat()
        shopping = ShoppingApp()
        cab = CabApp()
        system = SystemApp(name="system")

        # Initialize the apps
        self.apps = [aui, calendar, rent_flat, shopping, cab, system]

    def build_events_flow(self) -> None:
        """Build the event flow for the scenario with proactive agent-user interaction."""
        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(CalendarApp)
        rent_flat = self.get_typed_app(RentAFlat)
        shopping = self.get_typed_app(ShoppingApp)
        cab = self.get_typed_app(CabApp)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # Step 1: User asks agent to help coordinate new city move
            user_request = aui.send_message_to_agent(
                content="I'm planning to move to the city next month. Can you help me find an apartment and set things up?"
            ).depends_on(None, delay_seconds=1)

            # Step 2: Agent searches apartments
            apartments_found = rent_flat.search_apartments(
                location="City Center", min_price=1200, max_price=2000, number_of_bedrooms=2
            ).depends_on(user_request, delay_seconds=1)

            # Step 3: Agent gets details of a promising apartment
            apt_details = rent_flat.get_apartment_details(apartment_id="apt_city_002").depends_on(
                apartments_found, delay_seconds=1
            )

            # Step 4: Agent proactively asks user if they want to schedule a visit
            proposal_message = aui.send_message_to_user(
                content="I found a nice 2-bedroom apartment near City Center. Would you like me to schedule a viewing visit this weekend?"
            ).depends_on(apt_details, delay_seconds=1)

            # Step 5: User approves the proposed action
            user_approval = aui.send_message_to_agent(
                content="Yes, please schedule a viewing this Saturday morning."
            ).depends_on(proposal_message, delay_seconds=1)

            # Step 6: Agent gets current system time to plan scheduling
            now_time = system.get_current_time().depends_on(user_approval, delay_seconds=1)

            # Step 7: Agent adds apartment visit event in the user's calendar
            schedule_visit = (
                calendar.add_calendar_event(
                    title="Apartment Viewing - City Center",
                    start_datetime="2024-07-06 10:00:00",
                    end_datetime="2024-07-06 11:00:00",
                    description="Viewing of 2-bedroom apartment at City Center.",
                    location="City Center Property Lane 14, Apt 5B",
                    attendees=["User", "Realtor"],
                    tag="ApartmentVisit",
                )
                .oracle()
                .depends_on(now_time, delay_seconds=1)
            )

            # Step 8: Agent fetches today's calendar events to confirm addition
            today_events = calendar.read_today_calendar_events().depends_on(schedule_visit, delay_seconds=1)

            # Step 9: Before the visit, agent searches cab options
            ride_quote = cab.get_quotation(
                start_location="User Home Address",
                end_location="City Center Property Lane 14",
                service_type="Default",
                ride_time="2024-07-06 09:30:00",
            ).depends_on(today_events, delay_seconds=1)

            # Step 10: Agent schedules cab order to reach on time
            cab_order = (
                cab.order_ride(
                    start_location="User Home Address",
                    end_location="City Center Property Lane 14",
                    service_type="Default",
                    ride_time="2024-07-06 09:30:00",
                )
                .oracle()
                .depends_on(ride_quote, delay_seconds=1)
            )

            # Step 11: After confirming ride, agent helps with shopping furniture
            furniture_search = shopping.search_product(product_name="Dining table", limit=3).depends_on(
                cab_order, delay_seconds=1
            )

            product_pick = shopping.get_product_details(product_id="product_table_05").depends_on(
                furniture_search, delay_seconds=1
            )

            # Step 12: Agent adds furniture to cart
            add_item = shopping.add_to_cart(item_id="product_table_05", quantity=1).depends_on(
                product_pick, delay_seconds=1
            )

            # Step 13: Agent applies available discount and checks out
            discount_codes = shopping.get_all_discount_codes().depends_on(add_item, delay_seconds=1)
            checkout_order = shopping.checkout(discount_code=None).oracle().depends_on(discount_codes, delay_seconds=1)

            # Step 14: Agent proposes to schedule furniture delivery date
            propose_delivery = aui.send_message_to_user(
                content="Would you like me to schedule furniture delivery for your move-in day?"
            ).depends_on(checkout_order, delay_seconds=1)

            # Step 15: User approves delivery scheduling
            user_approve_delivery = aui.send_message_to_agent(
                content="Yes, please schedule it for the same day as my move-in."
            ).depends_on(propose_delivery, delay_seconds=1)

            # Step 16: Agent adds furniture delivery calendar event
            delivery_event = (
                calendar.add_calendar_event(
                    title="Furniture Delivery Scheduled",
                    start_datetime="2024-08-01 15:00:00",
                    end_datetime="2024-08-01 17:00:00",
                    tag="Delivery",
                    description="Furniture delivery at new City Center apartment.",
                    location="City Center Property Lane 14, Apt 5B",
                    attendees=["User", "Delivery Service"],
                )
                .oracle()
                .depends_on(user_approve_delivery, delay_seconds=1)
            )

            # Step 17: Agent saves favorite apartment for move-in reference
            save_favorite = rent_flat.save_apartment(apartment_id="apt_city_002").depends_on(
                delivery_event, delay_seconds=1
            )

            # Step 18: Wait for next step or end notification
            idle_wait = system.wait_for_notification(timeout=3).depends_on(save_favorite, delay_seconds=1)

        self.events = [
            user_request,
            apartments_found,
            apt_details,
            proposal_message,
            user_approval,
            now_time,
            schedule_visit,
            today_events,
            ride_quote,
            cab_order,
            furniture_search,
            product_pick,
            add_item,
            discount_codes,
            checkout_order,
            propose_delivery,
            user_approve_delivery,
            delivery_event,
            save_favorite,
            idle_wait,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate the scenario execution."""
        try:
            events = env.event_log.list_view()
            scheduled_visits = [
                e
                for e in events
                if isinstance(e.action, Action)
                and e.action.class_name == "CalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Apartment Viewing" in str(e.action.args.get("title", ""))
            ]
            furniture_deliveries = [
                e
                for e in events
                if isinstance(e.action, Action)
                and e.action.class_name == "CalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Furniture Delivery" in str(e.action.args.get("title", ""))
            ]
            user_interactions = [
                e
                for e in events
                if isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
            ]
            travel_orders = [
                e
                for e in events
                if isinstance(e.action, Action)
                and e.action.class_name == "CabApp"
                and e.action.function_name == "order_ride"
            ]
            shop_orders = [
                e
                for e in events
                if isinstance(e.action, Action)
                and e.action.class_name == "ShoppingApp"
                and e.action.function_name == "checkout"
            ]
            # Check if all major assistant tasks were performed
            result = (
                len(scheduled_visits) > 0
                and len(furniture_deliveries) > 0
                and len(user_interactions) >= 2
                and len(travel_orders) > 0
                and len(shop_orders) > 0
            )
            return ScenarioValidationResult(success=result)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
