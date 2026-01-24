from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulApartmentApp,
)
from pas.apps.reminder import StatefulReminderApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("lease_end_apartment_search_urgency")
class LeaseEndApartmentSearchUrgency(PASScenario):
    """Agent proactively initiates apartment search workflow when landlord's email indicates approaching lease termination and no new housing is secured.

    The user has a calendar event "Current Lease Ends - Move Out" scheduled for 30 days from now with location "Oak Street Apartments, Unit 204". A user-created reminder notification fires that the lease renewal response deadline is coming up in 14 days and suggests starting the housing search now. The agent must:
    1. Detect the reminder notification (time-driven; emitted automatically when the reminder is due) and infer urgency to start searching
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
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario-specific apps
        self.reminder = StatefulReminderApp(name="Reminders")
        self.apartment = StatefulApartmentApp(name="Apartment")

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

        # Seed a time-driven reminder that will automatically notify the user+agent when due.
        # Following benchmark convention, set it shortly after start_time so it fires once the runner advances time.
        self.reminder.add_reminder(
            title="Lease renewal decision due soon — start apartment search",
            due_datetime="2025-11-18 09:01:00",
            description=(
                "Lease at Oak Street Apartments, Unit 204 ends Dec 18, 2025.\n"
                "Start looking for new apartments under $2200 now, and save at least two promising 2BR listings to compare."
            ),
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.reminder, self.apartment]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")

        with EventRegisterer.capture_mode():
            # NOTE: Reminder notifications are time-driven in the Reminders app.
            # The reminder seeded in init (`due_datetime="2025-11-18 09:01:00"`) will automatically notify user+agent.
            # The agent does NOT need to poll reminders; we model reaction time by delaying the first oracle action.

            # Event 1: Agent checks if any apartments are already saved (oracle)
            # Motivation: reminder prompted starting the search; agent checks if user already saved any apartments.
            check_saved_apartments_event = apartment_app.list_saved_apartments().oracle().delayed(70)

            # Event 2: Agent searches for available apartments (oracle)
            # Motivation: No saved apartments found, so agent looks for suitable options in the market
            search_apartments_event = (
                apartment_app.search_apartments(
                    number_of_bedrooms=2,
                    max_price=2200.0,
                )
                .oracle()
                .depends_on(check_saved_apartments_event, delay_seconds=1)
            )

            # Event 3: Agent proposes saving a few suitable apartments as starting points (oracle)
            # Motivation: reminder indicates a deadline is approaching and suggests saving listings; no apartments saved yet.
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed your reminder about the lease renewal decision coming up. Your lease ends Dec 18, and you need to decide by Dec 2. I also see you haven't saved any apartments yet—would you like me to save a couple suitable 2-bedroom apartments (under $2200) as starting points for your search?"
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

        self.events = [
            check_saved_apartments_event,
            search_apartments_event,
            proposal_event,
            acceptance_event,
            save_apartment_1_event,
            save_apartment_2_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT events for validation
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent sent proposal to user
            # The agent must propose a comprehensive help plan to the user
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 2: Agent saved at least 2 apartments to favorites
            # The agent must save apartments as starting points for the user's search
            save_apartment_events = [
                e
                for e in agent_events
                if e.action.class_name == "StatefulApartmentApp" and e.action.function_name == "save_apartment"
            ]
            apartments_saved = len(save_apartment_events) >= 2

            # Combine all checks
            success = proposal_found and apartments_saved

            # Build rationale if validation fails
            if not success:
                missing = []
                if not proposal_found:
                    missing.append("proposal to user")
                if not apartments_saved:
                    missing.append("saving at least 2 apartments")

                rationale = f"Missing required agent actions: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
