"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.contacts import Contact
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulApartmentApp,
    StatefulEmailApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("budget_constrained_apartment_filter")
class BudgetConstrainedApartmentFilter(PASScenario):
    """Agent filters saved apartments based on budget constraint mentioned in incoming email from roommate.

    The user has saved five apartments to their favorites with varying monthly rents ($1800, $2200, $2500, $2800, $3200). An email arrives from the user's roommate stating "Hey, I can only afford up to $2400/month for rent. Can you please filter our saved/favorited apartment list so we're only looking at places within that budget?" The agent must:
    1. Detect the incoming email with explicit budget constraint
    2. Extract the maximum monthly rent amount ($2400) from the email content
    3. Retrieve the list of all saved apartments
    4. Identify which saved apartments exceed the budget limit
    5. Propose removing over-budget apartments from the saved list
    6. Upon user acceptance, unsave each apartment that exceeds $2400/month
    7. Confirm to the user which apartments were removed and which remain

    This scenario exercises email-based constraint extraction, cross-app filtering logic (email → apartment), budget comparison across multiple items, bulk removal operations based on numerical thresholds, and proactive list curation without requiring new searches or additions..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Email App
        self.email = StatefulEmailApp(name="Emails", user_email="user@apartment-search.com")

        # Initialize Apartment App
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Populate Contacts - Roommate contact
        roommate = Contact(first_name="Alex", last_name="Chen", email="alex.chen@email.com", phone="+1-555-0123")
        # Note: Contact app not explicitly used but roommate details define the email sender

        # Populate Apartments - Five saved apartments with varying prices
        # Apartment 1: Within budget ($1800)
        apt1_id = self.apartment.add_new_apartment(
            name="Riverside Studios",
            location="Downtown District",
            zip_code="90210",
            price=1800.0,
            number_of_bedrooms=2,
            number_of_bathrooms=1,
            square_footage=850,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Parking", "Laundry"],
        )
        self.apartment.save_apartment(apt1_id)

        # Apartment 2: Within budget ($2200)
        apt2_id = self.apartment.add_new_apartment(
            name="Central Plaza Residences",
            location="City Center",
            zip_code="90211",
            price=2200.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=950,
            property_type="Apartment",
            furnished_status="Semi-furnished",
            floor_level="Upper floors",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Gym", "Pool", "Parking"],
        )
        self.apartment.save_apartment(apt2_id)

        # Apartment 3: Over budget ($2500)
        apt3_id = self.apartment.add_new_apartment(
            name="Luxury Lofts",
            location="Arts District",
            zip_code="90212",
            price=2500.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1100,
            property_type="Loft",
            furnished_status="Furnished",
            floor_level="Penthouse",
            pet_policy="No pets",
            lease_term="1 year",
            amenities=["Gym", "Pool", "Parking", "Concierge"],
        )
        self.apartment.save_apartment(apt3_id)

        # Apartment 4: Over budget ($2800)
        apt4_id = self.apartment.add_new_apartment(
            name="Skyline Towers",
            location="Financial District",
            zip_code="90213",
            price=2800.0,
            number_of_bedrooms=3,
            number_of_bathrooms=2,
            square_footage=1250,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Penthouse",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Gym", "Pool", "Parking", "Doorman", "Rooftop"],
        )
        self.apartment.save_apartment(apt4_id)

        # Apartment 5: Over budget ($3200)
        apt5_id = self.apartment.add_new_apartment(
            name="Prestige Heights",
            location="Uptown",
            zip_code="90214",
            price=3200.0,
            number_of_bedrooms=3,
            number_of_bathrooms=3,
            square_footage=1500,
            property_type="Condo",
            furnished_status="Furnished",
            floor_level="Penthouse",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Gym", "Pool", "Parking", "Concierge", "Valet", "Spa"],
        )
        self.apartment.save_apartment(apt5_id)

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
            # Environment Event 1: Roommate sends budget constraint email
            budget_email_id = "budget_constraint_email_001"
            env_event_1 = email_app.send_email_to_user_with_id(
                email_id=budget_email_id,
                sender="alex.chen@email.com",
                subject="Budget Update for Apartment Search",
                content="Hey! I've been looking at our finances and I can only afford up to $2400/month for rent. Can you please filter our saved/favorited apartments so we're only looking at places within that budget? If any saved places are over $2400, let's remove them from the saved list. Thanks!",
            )

            # Oracle Event 1: Agent retrieves the budget constraint email
            # Motivated by: environment event 1 (new email notification)
            oracle_event_1 = (
                email_app.get_email_by_id(email_id=budget_email_id, folder_name="INBOX")
                .oracle()
                .depends_on(env_event_1, delay_seconds=2)
            )

            # Oracle Event 2: Agent lists all saved apartments to identify which exceed the budget
            # Motivated by: the budget constraint email explicitly mentions filtering saved apartments
            oracle_event_2 = apartment_app.list_saved_apartments().oracle().depends_on(oracle_event_1, delay_seconds=1)

            # Oracle Event 3: Agent proposes removing over-budget apartments
            # Motivated by: agent has discovered 3 apartments (Luxury Lofts $2500, Skyline Towers $2800, Prestige Heights $3200) exceed the $2400 budget limit
            oracle_event_3 = (
                aui.send_message_to_user(
                    content="I noticed Alex sent an email about keeping your apartment search within a $2400/month budget. I checked your saved apartments and found 3 that exceed this limit:\n\n• Luxury Lofts ($2500)\n• Skyline Towers ($2800)\n• Prestige Heights ($3200)\n\nWould you like me to remove these from your saved list? This will leave you with Riverside Studios ($1800) and Central Plaza Residences ($2200)."
                )
                .oracle()
                .depends_on(oracle_event_2, delay_seconds=3)
            )

            # User Event 1: User accepts the proposal to remove over-budget apartments
            user_event_1 = (
                aui.accept_proposal(content="Yes, please remove those apartments from my saved list.")
                .oracle()
                .depends_on(oracle_event_3, delay_seconds=5)
            )

            # Oracle Event 4: Agent removes Luxury Lofts (apartment 3)
            # Motivated by: user acceptance to remove over-budget apartments; Luxury Lofts was identified as exceeding the $2400 budget
            oracle_event_4 = (
                apartment_app.remove_saved_apartment(apartment_id="apt3_id_placeholder")
                .oracle()
                .depends_on(user_event_1, delay_seconds=1)
            )

            # Oracle Event 5: Agent removes Skyline Towers (apartment 4)
            # Motivated by: user acceptance to remove over-budget apartments; Skyline Towers was identified as exceeding the $2400 budget
            oracle_event_5 = (
                apartment_app.remove_saved_apartment(apartment_id="apt4_id_placeholder")
                .oracle()
                .depends_on(oracle_event_4, delay_seconds=1)
            )

            # Oracle Event 6: Agent removes Prestige Heights (apartment 5)
            # Motivated by: user acceptance to remove over-budget apartments; Prestige Heights was identified as exceeding the $2400 budget
            oracle_event_6 = (
                apartment_app.remove_saved_apartment(apartment_id="apt5_id_placeholder")
                .oracle()
                .depends_on(oracle_event_5, delay_seconds=1)
            )

            # Oracle Event 7: Agent confirms completion to the user
            # Motivated by: all over-budget apartments have been successfully removed
            oracle_event_7 = (
                aui.send_message_to_user(
                    content="Done! I've removed the 3 apartments that exceeded your $2400 budget. Your saved apartments now only include Riverside Studios ($1800) and Central Plaza Residences ($2200)."
                )
                .oracle()
                .depends_on(oracle_event_6, delay_seconds=2)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            env_event_1,
            oracle_event_1,
            oracle_event_2,
            oracle_event_3,
            user_event_1,
            oracle_event_4,
            oracle_event_5,
            oracle_event_6,
            oracle_event_7,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1 (STRICT): Agent read the budget constraint email
            email_read_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "get_email_by_id"
                for e in log_entries
            )

            # Check 2 (STRICT): Agent listed saved apartments to identify which exceed the budget
            apartments_listed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulApartmentApp"
                and e.action.function_name == "list_saved_apartments"
                for e in log_entries
            )

            # Check 3 (STRICT): Agent proposed removing over-budget apartments
            # Content-flexible: we only check that a message was sent, not exact wording
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 4 (STRICT): Agent removed apartments that exceed $2400 budget
            # We expect at least 3 removal operations (for the apartments priced at $2500, $2800, $3200)
            removal_count = sum(
                1
                for e in log_entries
                if e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulApartmentApp"
                and e.action.function_name == "remove_saved_apartment"
            )
            sufficient_removals = removal_count >= 3

            # All strict checks must pass
            success = email_read_found and apartments_listed and proposal_found and sufficient_removals

            if not success:
                rationale_parts = []
                if not email_read_found:
                    rationale_parts.append("agent did not read budget constraint email")
                if not apartments_listed:
                    rationale_parts.append("agent did not list saved apartments")
                if not proposal_found:
                    rationale_parts.append("agent did not send proposal message to user")
                if not sufficient_removals:
                    rationale_parts.append(f"agent removed only {removal_count} apartments (expected at least 3)")
                rationale = "; ".join(rationale_parts)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
