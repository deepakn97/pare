from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import ApartmentListingApp
from are.simulation.apps.cab import CabApp
from are.simulation.apps.shopping import ShoppingApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("urban_relocation_day")
class UrbanRelocationDay(Scenario):
    """A comprehensive scenario demonstrating integrated use of apartment search, shopping, and cab booking.

    The agent helps a user plan a day for relocating to a new city apartment.
    The workflow includes:
    - Searching and saving a suitable apartment listing
    - Ordering essential household items online
    - Booking a cab ride to visit the apartment
    - Using proactive confirmation interaction before finalizing the cab order.

    This scenario showcases every available app: SystemApp, ApartmentListingApp, ShoppingApp, CabApp, and AgentUserInterface.
    """

    start_time: float | None = 0
    duration: float | None = 45

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate apps with example data for urban relocation."""
        aui = AgentUserInterface()
        system = SystemApp(name="system")
        apartments = ApartmentListingApp()
        shopping = ShoppingApp()
        cabs = CabApp()

        self.apps = [aui, system, apartments, shopping, cabs]

    def build_events_flow(self) -> None:
        """Defines the event flow for proactive workflow of relocation day."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        apartments = self.get_typed_app(ApartmentListingApp)
        shopping = self.get_typed_app(ShoppingApp)
        cabs = self.get_typed_app(CabApp)

        with EventRegisterer.capture_mode():
            user_intro = aui.send_message_to_agent(
                content="Hey Assistant, can you help me prepare for my relocation day? I need to find a new flat, buy essentials, and arrange transport."
            ).depends_on(None, delay_seconds=1)

            sys_get_time = system.get_current_time().depends_on(user_intro, delay_seconds=1)

            apt_search = apartments.search_apartments(
                location="Downtown", min_price=1200, max_price=2200, number_of_bedrooms=2
            ).depends_on(sys_get_time, delay_seconds=1)

            show_found = aui.send_message_to_user(
                content="I found several 2-bedroom apartments in Downtown that fit your budget. Would you like me to save the one near Riverside Park?"
            ).depends_on(apt_search, delay_seconds=1)

            user_confirm_save = aui.send_message_to_agent(content="Yes, save the Riverside Park one.").depends_on(
                show_found, delay_seconds=1
            )

            save_flat = (
                apartments.save_apartment(apartment_id="apartment_riverside_002")
                .oracle()
                .depends_on(user_confirm_save, delay_seconds=1)
            )

            list_saved = apartments.list_saved_apartments().depends_on(save_flat, delay_seconds=1)

            shop_search = shopping.search_product(product_name="kitchen set").depends_on(list_saved, delay_seconds=1)
            shop_add = shopping.add_to_cart(item_id="product_kitchen_set_01", quantity=1).depends_on(
                shop_search, delay_seconds=1
            )
            cart_list = shopping.list_cart().depends_on(shop_add, delay_seconds=1)
            get_codes = shopping.get_all_discount_codes().depends_on(cart_list, delay_seconds=1)
            apply_code_info = shopping.get_discount_code_info(discount_code="MOVINGDAY10").depends_on(
                get_codes, delay_seconds=1
            )

            proactive_proposal = aui.send_message_to_user(
                content="I found a discount code 'MOVINGDAY10' for your kitchen set. Would you like me to use it and checkout your cart?"
            ).depends_on(apply_code_info, delay_seconds=1)

            user_accept_checkout = aui.send_message_to_agent(
                content="Yes, go ahead and order the kitchen set with that discount."
            ).depends_on(proactive_proposal, delay_seconds=1)

            checkout_order = (
                shopping.checkout(discount_code="MOVINGDAY10")
                .oracle()
                .depends_on(user_accept_checkout, delay_seconds=1)
            )

            list_orders = shopping.list_orders().depends_on(checkout_order, delay_seconds=1)
            order_detail = shopping.get_order_details(order_id="order_001").depends_on(list_orders, delay_seconds=1)

            propose_cab = aui.send_message_to_user(
                content="Your order for the kitchen set is confirmed. Would you like me to book a Premium cab ride to visit your new Riverside Park apartment this afternoon?"
            ).depends_on(order_detail, delay_seconds=1)

            user_confirms_cab = aui.send_message_to_agent(
                content="Yes, please book that Premium cab ride for me now."
            ).depends_on(propose_cab, delay_seconds=1)

            get_time2 = system.get_current_time().depends_on(user_confirms_cab, delay_seconds=1)
            quote = cabs.get_quotation(
                start_location="Current Apartment, Uptown",
                end_location="Riverside Park Apartments, Downtown",
                service_type="Premium",
                ride_time=None,
            ).depends_on(get_time2, delay_seconds=1)
            order_ride = (
                cabs.order_ride(
                    start_location="Current Apartment, Uptown",
                    end_location="Riverside Park Apartments, Downtown",
                    service_type="Premium",
                    ride_time=None,
                )
                .oracle()
                .depends_on(quote, delay_seconds=1)
            )

            system_wait = system.wait_for_notification(timeout=3).depends_on(order_ride, delay_seconds=1)
            ride_status = cabs.get_current_ride_status().depends_on(system_wait, delay_seconds=1)
            confirm_msg = (
                aui.send_message_to_user(
                    content="Your cab to Riverside Park Apartments is successfully booked. Have a safe trip!"
                )
                .depends_on(ride_status, delay_seconds=1)
                .oracle()
            )

        self.events = [
            user_intro,
            sys_get_time,
            apt_search,
            show_found,
            user_confirm_save,
            save_flat,
            list_saved,
            shop_search,
            shop_add,
            cart_list,
            get_codes,
            apply_code_info,
            proactive_proposal,
            user_accept_checkout,
            checkout_order,
            list_orders,
            order_detail,
            propose_cab,
            user_confirms_cab,
            get_time2,
            quote,
            order_ride,
            system_wait,
            ride_status,
            confirm_msg,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Verify that agent completed all major tasks: saved flat, checked out, and booked cab."""
        try:
            events = env.event_log.list_view()
            saved_apartment = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.function_name == "save_apartment"
                for event in events
            )
            completed_checkout = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.function_name == "checkout"
                for event in events
            )
            booked_ride = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.function_name == "order_ride"
                for event in events
            )
            proactive_pattern = any(
                event.event_type == EventType.AGENT
                and event.action.class_name == "AgentUserInterface"
                and "Would you like me" in event.action.args.get("content", "")
                for event in events
            )
            user_confirmed = any(
                event.event_type == EventType.USER and "Yes" in event.action.args.get("content", "") for event in events
            )

            success = saved_apartment and completed_checkout and booked_ride and proactive_pattern and user_confirmed
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
