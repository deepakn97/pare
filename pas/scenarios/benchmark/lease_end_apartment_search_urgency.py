"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulApartmentApp,
    StatefulEmailApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("lease_end_apartment_search_urgency")
class LeaseEndApartmentSearchUrgency(PASScenario):
    """Agent proactively initiates apartment search workflow when landlord's email indicates approaching lease termination and no new housing is secured.

    The user has a calendar event "Current Lease Ends - Move Out" scheduled for 30 days from now with location "Oak Street Apartments, Unit 204". An email arrives from the current landlord with subject "Lease Renewal Deadline - Response Required by [14 days from now]" stating that if the user does not renew, they must vacate on the scheduled date. The agent must:
    1. Parse the lease renewal deadline from the landlord's email
    2. Search the apartment app for available apartments matching the user's current criteria (similar price range, bedrooms, location preferences inferred from current apartment details if available, or use default search)
    3. Identify that no apartments are currently saved to favorites, indicating no active search
    4. Propose saving a few suitable 2-bedroom apartments to favorites as starting points for the user's search
    5. After user acceptance, save 2-3 suitable apartments to favorites

    This scenario exercises deadline-driven planning, multi-stage task decomposition (search initiation + milestone planning), and proactive goal inference when no explicit request exists.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario-specific apps
        self.email = StatefulEmailApp(name="Emails")
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Populate email: Add landlord contact for the incoming email
        landlord_email = "landlord@oakstreetapts.com"

        # Populate apartment app: Seed a few available apartments in the market
        # These represent the baseline rental market that the agent can search
        self.maple_heights_id = self.apartment.add_new_apartment(
            name="Maple Heights",
            location="Downtown",
            zip_code="90210",
            price=1800.0,
            number_of_bedrooms=2,
            number_of_bathrooms=1,
            square_footage=950,
            property_type="Apartment",
            furnished_status="Unfurnished",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Parking", "Gym", "Pool"],
        )

        self.riverside_lofts_id = self.apartment.add_new_apartment(
            name="Riverside Lofts",
            location="Riverside District",
            zip_code="90211",
            price=2100.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1100,
            property_type="Apartment",
            furnished_status="Unfurnished",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Parking", "Gym", "In-unit laundry"],
        )

        self.sunset_studios_id = self.apartment.add_new_apartment(
            name="Sunset Studios",
            location="West Side",
            zip_code="90212",
            price=1650.0,
            number_of_bedrooms=2,
            number_of_bathrooms=1,
            square_footage=850,
            property_type="Apartment",
            furnished_status="Unfurnished",
            pet_policy="No pets",
            lease_term="1 year",
            amenities=["Parking"],
        )

        # No apartments are saved to favorites - this absence signals no active search

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.apartment]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")

        with EventRegisterer.capture_mode():
            # Event 1: Incoming email from landlord about lease renewal deadline (environment event)
            # This is the primary trigger that motivates the agent's proactive behavior
            landlord_email_event = email_app.send_email_to_user_with_id(
                email_id="landlord-lease-renewal-email",
                sender="landlord@oakstreetapts.com",
                subject="Lease Renewal Deadline - Response Required by Dec 2",
                content=(
                    "Dear Tenant,\n\n"
                    "This is a reminder that your lease at Oak Street Apartments, Unit 204 expires on December 18, 2025. "
                    "If you wish to renew your lease, please respond by December 2, 2025 (14 days from now). If we do not receive "
                    "confirmation by this date, we will assume you are vacating on the scheduled move-out date.\n\n"
                    "If you plan to vacate and have not started looking yet, we recommend beginning your housing search now due to limited availability. "
                    "It may help to save a few promising 2-bedroom listings to your favorites/saved list so you can compare options.\n\n"
                    "Best regards,\n"
                    "Oak Street Management"
                ),
            ).delayed(10)

            # Event 2: Agent checks if any apartments are already saved (oracle)
            # Motivation: To determine if the user has already started apartment hunting
            check_saved_apartments_event = (
                apartment_app.list_saved_apartments().oracle().depends_on(landlord_email_event, delay_seconds=1)
            )

            # Event 3: Agent searches for available apartments (oracle)
            # Motivation: No saved apartments found, so agent looks for suitable options in the market
            search_apartments_event = (
                apartment_app.search_apartments(
                    number_of_bedrooms=2,
                    max_price=2200.0,
                )
                .oracle()
                .depends_on(check_saved_apartments_event, delay_seconds=1)
            )

            # Event 4: Agent proposes to help manage the lease deadline and start apartment search (oracle)
            # Motivation: Landlord email requires response by Dec 2, calendar shows lease end Dec 18, no apartments saved
            proposal_event = (
                aui.send_message_to_user(
                    content="I saw the lease renewal deadline email from your landlord. Your current lease ends on December 18 (30 days away), and you need to respond by December 2 (14 days). The email also suggested starting your housing search now if you're planning to move. I noticed you haven't saved any apartments yet—would you like me to save a couple suitable 2-bedroom apartments (under $2200) as starting points for your search?"
                )
                .oracle()
                .depends_on(search_apartments_event, delay_seconds=2)
            )

            # Event 5: User accepts the proposal (oracle)
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please save a couple suitable 2-bedroom apartments as starting points."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Event 6: Agent saves first apartment to favorites (oracle)
            # Motivation: Saving Maple Heights (2BR, $1800, good amenities) as a search starting point
            save_apartment_1_event = (
                apartment_app.save_apartment(apartment_id=self.maple_heights_id)
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Event 7: Agent saves second apartment to favorites (oracle)
            # Motivation: Saving Riverside Lofts (2BR, $2100, pets allowed) as a search starting point
            save_apartment_2_event = (
                apartment_app.save_apartment(apartment_id=self.riverside_lofts_id)
                .oracle()
                .depends_on(save_apartment_1_event, delay_seconds=1)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            landlord_email_event,
            check_saved_apartments_event,
            search_apartments_event,
            proposal_event,
            acceptance_event,
            save_apartment_1_event,
            save_apartment_2_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT events for validation
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent checked for saved apartments
            # The agent must verify if the user has already started apartment hunting
            saved_apartments_check_found = any(
                e.action.class_name == "StatefulApartmentApp" and e.action.function_name == "list_saved_apartments"
                for e in agent_events
            )

            # STRICT Check 2: Agent searched for apartments
            # The agent must search for available apartments to help the user
            apartment_search_found = any(
                e.action.class_name == "StatefulApartmentApp" and e.action.function_name == "search_apartments"
                for e in agent_events
            )

            # STRICT Check 3: Agent sent proposal to user
            # The agent must propose a comprehensive help plan to the user
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 4: Agent saved at least 1 apartments to favorites
            # The agent must save apartments as starting points for the user's search
            save_apartment_events = [
                e
                for e in agent_events
                if e.action.class_name == "StatefulApartmentApp" and e.action.function_name == "save_apartment"
            ]
            apartments_saved = len(save_apartment_events) >= 1

            # Combine all checks
            success = saved_apartments_check_found and apartment_search_found and proposal_found and apartments_saved

            # Build rationale if validation fails
            if not success:
                missing = []
                if not saved_apartments_check_found:
                    missing.append("saved apartments check")
                if not apartment_search_found:
                    missing.append("apartment search")
                if not proposal_found:
                    missing.append("proposal to user")
                if not apartments_saved:
                    missing.append("saving at least 1 apartment")

                rationale = f"Missing required agent actions: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
