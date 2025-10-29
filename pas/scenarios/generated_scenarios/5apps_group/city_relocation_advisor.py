from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import RentAFlat
from are.simulation.apps.cab import CabApp
from are.simulation.apps.city import CityApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("city_relocation_advisor")
class CityRelocationAdvisor(Scenario):
    """An agent helps the user plan a safe relocation by checking apartments.

    The agent checks apartments, crime rates, and transport accessibility, then proposes to arrange a cab visit
    to a chosen apartment after user approval.
    """

    start_time: float | None = 0
    duration: float | None = 60

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize all needed applications and populate where necessary."""
        aui = AgentUserInterface()
        system = SystemApp(name="system_time_check")
        rent_flat = RentAFlat()
        cab = CabApp()
        city_info = CityApp()

        # Simulate initial data or defaults for app logic context.
        # No data needed to prepopulate these simulation API apps; they query dynamically.
        self.apps = [aui, system, rent_flat, cab, city_info]

    def build_events_flow(self) -> None:
        """Define oracle and interaction flow for relocation assistance."""
        aui = self.get_typed_app(AgentUserInterface)
        rent_flat = self.get_typed_app(RentAFlat)
        system = self.get_typed_app(SystemApp)
        cab = self.get_typed_app(CabApp)
        city = self.get_typed_app(CityApp)

        with EventRegisterer.capture_mode():
            # User starts relocation conversation
            e0 = aui.send_message_to_agent(
                content="Hi, can you help me find a safe apartment in the downtown area within $1500 range?"
            ).depends_on(None, delay_seconds=1)

            # The agent first checks current system time for reference
            e1 = system.get_current_time().oracle().depends_on(e0, delay_seconds=1)

            # The agent searches for apartments
            e2 = (
                rent_flat.search_apartments(
                    location="Downtown", max_price=1500, number_of_bedrooms=1, property_type="Apartment"
                )
                .oracle()
                .depends_on(e1, delay_seconds=1)
            )

            # After results, check the city's safety levels (Crime rate API)
            e3 = city.get_crime_rate(zip_code="11223").oracle().depends_on(e2, delay_seconds=1)

            # Agent proposes to user: scheduling a cab to visit top apartment
            e4 = aui.send_message_to_user(
                content="I found a nice apartment downtown under $1500, and its area has a reasonably low crime rate. "
                "Would you like me to arrange a cab ride so you can visit it this afternoon?"
            ).depends_on(e3, delay_seconds=1)

            # User responds with affirmative contextual approval
            e5 = aui.send_message_to_agent(content="Yes, please book a cab to visit it today at 3 PM.").depends_on(
                e4, delay_seconds=2
            )

            # The agent requests a ride quotation (CabApp)
            e6 = (
                cab.get_quotation(
                    start_location="User Home, City Center",
                    end_location="Main St Apartment, Downtown",
                    service_type="Default",
                    ride_time="2024-07-30 15:00:00",
                )
                .oracle()
                .depends_on(e5, delay_seconds=1)
            )

            # The agent then confirms the cab booking after user approval
            e7 = (
                cab.order_ride(
                    start_location="User Home, City Center",
                    end_location="Main St Apartment, Downtown",
                    service_type="Default",
                    ride_time="2024-07-30 15:00:00",
                )
                .oracle()
                .depends_on(e6, delay_seconds=1)
            )

            # Agent saves this apartment for user's favorites
            e8 = rent_flat.save_apartment(apartment_id="Apt_11223_Downtown_1B").oracle().depends_on(e7, delay_seconds=1)

            # Finally, agent informs user that all actions are done
            e9 = (
                aui.send_message_to_user(
                    content="The cab is booked and the apartment is added to your saved list. "
                    "You're all set for the visit at 3 PM!"
                )
                .oracle()
                .depends_on(e8, delay_seconds=1)
            )

        self.events = [e0, e1, e2, e3, e4, e5, e6, e7, e8, e9]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validation: ensure the agent checked city safety, booked cab, and saved apartment."""
        try:
            logs = env.event_log.list_view()

            used_city_info = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "CityApp"
                and event.action.function_name == "get_crime_rate"
                for event in logs
            )

            booked_ride = any(
                event.event_type == EventType.AGENT
                and event.action.class_name == "CabApp"
                and event.action.function_name == "order_ride"
                for event in logs
            )

            saved_apartment = any(
                event.action.class_name == "RentAFlat" and event.action.function_name == "save_apartment"
                for event in logs
            )

            proposed_and_approved = any(
                event.event_type == EventType.AGENT
                and event.action.class_name == "AgentUserInterface"
                and "Would you like me to arrange a cab" in event.action.args["content"]
                for event in logs
            ) and any(
                event.event_type != EventType.AGENT and "Yes, please book a cab" in event.action.args["content"]
                for event in logs
            )

            return ScenarioValidationResult(
                success=used_city_info and booked_ride and saved_apartment and proposed_and_approved
            )
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
