from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import ApartmentListingApp, RentAFlat
from are.simulation.apps.city import CityApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("apartment_search_and_share")
class ApartmentSearchAndShare(Scenario):
    """Scenario demonstrating an agent helping a user find a safe apartment.

    The agent helps a user find a safe apartment and offering to share apartment details with a friend upon confirmation.
    """

    start_time: float | None = 0
    duration: float | None = 40

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all applications and populate them with mock data for testing the scenario."""
        # Initialize apps
        aui = AgentUserInterface()
        contacts = ContactsApp()
        system = SystemApp(name="sysapp")
        city = CityApp()
        a_listing = ApartmentListingApp()
        rentaflat = RentAFlat()

        # Add a new contact "Jordan" that could receive apartment info
        contacts.add_new_contact(
            first_name="Jordan",
            last_name="Lee",
            gender=Gender.OTHER,
            status=Status.EMPLOYED,
            age=29,
            city_living="Cedarville",
            country="USA",
            email="jordanlee@example.com",
            phone="+1 403 239 4820",
            description="Close friend looking for a flat too.",
            job="Teacher",
        )

        # Prepare mock data (no real data needed; agent will make calls)
        self.apps = [aui, contacts, system, city, a_listing, rentaflat]

    def build_events_flow(self) -> None:
        """Define event flow for the scenario: user requests flat search, agent finds data, proposes sharing."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        contacts = self.get_typed_app(ContactsApp)
        city = self.get_typed_app(CityApp)
        listing = self.get_typed_app(ApartmentListingApp)
        rentaflat = self.get_typed_app(RentAFlat)

        with EventRegisterer.capture_mode():
            # User starts conversation asking for help finding an apartment
            e1 = aui.send_message_to_agent(
                content="Hey Assistant, I'm looking for a 2-bedroom apartment around Cedarville under $1500."
            ).depends_on(None, delay_seconds=1)

            # System fetches current date/time as part of search context
            e2 = system.get_current_time().depends_on(e1, delay_seconds=1)

            # Agent searches for listings in ApartmentListingApp and RentAFlat
            e3 = listing.search_apartments(location="Cedarville", number_of_bedrooms=2, max_price=1500).depends_on(
                e2, delay_seconds=1
            )

            e4 = rentaflat.search_apartments(location="Cedarville", number_of_bedrooms=2, max_price=1500).depends_on(
                e3, delay_seconds=1
            )

            # Check city crime rate to ensure safe neighborhood
            e5 = city.get_crime_rate(zip_code="67205").depends_on(e4, delay_seconds=1)

            # Agent proactively proposes sharing an ideal apartment with Jordan for extra opinion
            e6 = aui.send_message_to_user(
                content=(
                    "I found a few safe options under $1500 in Cedarville. "
                    "Would you like me to share the best one with your friend Jordan Lee for a second opinion?"
                )
            ).depends_on(e5, delay_seconds=1)

            # User provides explicit, contextual confirmation of the sharing proposal
            e7 = aui.send_message_to_agent(content="Yes, please share the apartment details with Jordan.").depends_on(
                e6, delay_seconds=1
            )

            # Agent gets Jordan's contact info
            e8 = contacts.search_contacts(query="Jordan Lee").depends_on(e7, delay_seconds=1)

            # Agent saves the chosen apartment to favorites
            e9 = listing.save_apartment(apartment_id="apt_42").depends_on(e8, delay_seconds=1)

            # Agent shares apartment details with Jordan (oracle ground truth event)
            e10 = (
                aui.send_message_to_user(
                    content="I've shared the apartment details with Jordan at jordanlee@example.com."
                )
                .oracle()
                .depends_on(e9, delay_seconds=1)
            )

            # Wait a little for potential user acknowledgment
            e11 = system.wait_for_notification(timeout=10).depends_on(e10, delay_seconds=1)

        self.events = [e1, e2, e3, e4, e5, e6, e7, e8, e9, e10, e11]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent performed safe apartment search and executed user-approved sharing action."""
        try:
            all_events = env.event_log.list_view()
            # Check that the agent proposed a sharing action
            proposed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "share" in e.action.args.get("content", "").lower()
                for e in all_events
            )
            # Check that the agent executed sending/sharing action after approval
            completed_share = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.function_name == "send_message_to_user"
                and "jordan" in e.action.args.get("content", "").lower()
                and "shared" in e.action.args.get("content", "").lower()
                for e in all_events
            )
            # Confirm it also queried safety info (crime rate)
            checked_safety = any(
                e.event_type == EventType.SYSTEM
                or (
                    isinstance(e.action, Action)
                    and e.action.class_name == "CityApp"
                    and e.action.function_name == "get_crime_rate"
                )
                for e in all_events
            )
            success = proposed and completed_share and checked_safety
            return ScenarioValidationResult(success=success)
        except Exception as ex:
            return ScenarioValidationResult(success=False, exception=ex)
