from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulMessagingApp,
)
from pare.apps.apartment import StatefulApartmentApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("space_constraint_saved_apartment_filter")
class SpaceConstraintSavedApartmentFilter(PAREScenario):
    """Agent filters saved apartments based on a space constraint reminder from the user's girlfriend.

    The user has multiple apartments saved to favorites with varying square footages (mix of studios, 1BR, and 2BR units). The user's girlfriend sends a message reminding them that anything under 500 sqft is too small for two people and asks to remove those from the saved list. The agent must: 1) detect the girlfriend's message and extract the explicit threshold (under 500 sqft), 2) retrieve the user's saved apartments, 3) identify which saved apartments are under 500 sqft, 4) propose removing those undersized apartments, and 5) upon acceptance, remove them and confirm what's left.

    This scenario exercises constraint-based filtering within apartment search (message → apartment), numerical threshold reasoning over apartment square footage, and proactive list curation based on a partner's explicit preference.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize apartment app
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Initialize messaging app (used for girlfriend reminder)
        self.messaging = StatefulMessagingApp(name="Messages")
        from are.simulation.apps.messaging_v2 import ConversationV2

        # Populate apartment app with baseline data
        # Create apartments with varying square footages
        # Small studio - insufficient space (350 sq ft)
        self.apt_id_studio = self.apartment.add_new_apartment(
            name="Cozy Studio Downtown",
            location="Downtown",
            zip_code="93101",
            price=1200.0,
            number_of_bedrooms=0,
            number_of_bathrooms=1,
            square_footage=350,
            property_type="Studio",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="No pets",
            lease_term="1 year",
            amenities=["Gym", "Parking"],
        )
        self.apartment.save_apartment(self.apt_id_studio)

        # Small 1BR - insufficient space (480 sq ft)
        self.apt_id_1br_small = self.apartment.add_new_apartment(
            name="Compact 1BR Near Campus",
            location="Isla Vista",
            zip_code="93117",
            price=1500.0,
            number_of_bedrooms=1,
            number_of_bathrooms=1,
            square_footage=480,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Ground floor",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Pool", "Laundry"],
        )
        self.apartment.save_apartment(self.apt_id_1br_small)

        # Medium 1BR - borderline space (650 sq ft)
        apt_id_1br_medium = self.apartment.add_new_apartment(
            name="Modern 1BR Midtown",
            location="Midtown",
            zip_code="93103",
            price=1800.0,
            number_of_bedrooms=1,
            number_of_bathrooms=1,
            square_footage=650,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Gym", "Pool", "Parking"],
        )
        self.apartment.save_apartment(apt_id_1br_medium)

        # Large 2BR - adequate space (900 sq ft)
        apt_id_2br_large = self.apartment.add_new_apartment(
            name="Spacious 2BR with Balcony",
            location="Mesa",
            zip_code="93109",
            price=2400.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=900,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Gym", "Pool", "Parking", "Balcony"],
        )
        self.apartment.save_apartment(apt_id_2br_large)

        # Extra large 2BR - adequate space (1100 sq ft)
        apt_id_2br_xlarge = self.apartment.add_new_apartment(
            name="Luxury 2BR Ocean View",
            location="Waterfront",
            zip_code="93109",
            price=3200.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1100,
            property_type="Condo",
            furnished_status="Unfurnished",
            floor_level="Penthouse",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Gym", "Pool", "Parking", "Balcony", "Ocean View"],
        )
        self.apartment.save_apartment(apt_id_2br_xlarge)

        # Seed girlfriend conversation (message is delivered as an environment event in build_events_flow)
        self.messaging.add_users(["Girlfriend"])
        self.user_id = self.messaging.current_user_id
        self.girlfriend_id = self.messaging.name_to_id["Girlfriend"]
        self.gf_conversation = ConversationV2(participant_ids=[self.user_id, self.girlfriend_id])
        self.messaging.add_conversation(self.gf_conversation)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.apartment]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")

        with EventRegisterer.capture_mode():
            # Environment event: Girlfriend reminder message about minimum space for two people
            girlfriend_message_event = messaging_app.create_and_add_message(
                conversation_id=self.gf_conversation.conversation_id,
                sender_id=self.girlfriend_id,
                content=(
                    "Hey — quick reminder: anything under 500 sqft is going to feel way too small for two people. "
                    "Can you remove any saved apartments under 500 sqft from our list?"
                ),
            ).delayed(3)

            # Oracle event: Agent reads the conversation to ground the explicit 500 sqft threshold
            read_girlfriend_message = (
                messaging_app.read_conversation(conversation_id=self.gf_conversation.conversation_id)
                .oracle()
                .depends_on(girlfriend_message_event, delay_seconds=2)
            )

            # Oracle event: Agent lists saved apartments to analyze space constraints
            # Motivated by: girlfriend explicitly asked to remove anything under 500 sqft.
            agent_list_saved_apts = (
                apartment_app.list_saved_apartments().oracle().depends_on(read_girlfriend_message, delay_seconds=3)
            )

            # Oracle event: Agent proposes removing undersized apartments from saved list
            # Motivated by: girlfriend's explicit threshold (<500 sqft) and the saved apartments list.
            agent_proposal = (
                aui.send_message_to_user(
                    content="I saw your girlfriend's message about removing any saved apartments under 500 sqft. I checked your saved list and found two that are under 500 sqft (350 sqft studio and 480 sqft 1BR). Would you like me to remove those from your saved apartments?"
                )
                .oracle()
                .depends_on(agent_list_saved_apts, delay_seconds=15)
            )

            # User event: User accepts the proposal
            user_acceptance = (
                aui.accept_proposal(content="Yes, please proceed.")
                .oracle()
                .depends_on(agent_proposal, delay_seconds=30)
            )

            # Oracle event: Agent removes the studio apartment from saved list
            # Motivated by: user acceptance + knowledge of which apartments are undersized from the list_saved_apartments results
            agent_remove_studio = (
                apartment_app.remove_saved_apartment(apartment_id=self.apt_id_studio)
                .oracle()
                .depends_on(user_acceptance, delay_seconds=5)
            )

            # Oracle event: Agent removes the small 1BR apartment from saved list
            # Motivated by: same - user acceptance + knowledge from list_saved_apartments results
            agent_remove_1br_small = (
                apartment_app.remove_saved_apartment(apartment_id=self.apt_id_1br_small)
                .oracle()
                .depends_on(user_acceptance, delay_seconds=2)
            )

            # Oracle event: Agent sends summary message to user
            # Motivated by: completion of apartment removal actions
            agent_summary = (
                aui.send_message_to_user(
                    content="Done! I removed the two small apartments. Your saved list now has three spacious options that will comfortably fit your furniture."
                )
                .oracle()
                .depends_on([agent_remove_studio, agent_remove_1br_small], delay_seconds=10)
            )

        # Register ALL events here in self.events
        self.events = [
            girlfriend_message_event,
            read_girlfriend_message,
            agent_list_saved_apts,
            agent_proposal,
            user_acceptance,
            agent_remove_studio,
            agent_remove_1br_small,
            agent_summary,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # FLEXIBLE Check 1: Agent sent proposal/message to user about the space constraint
            # Content checking is flexible - just verify the agent communicated with the user
            agent_sent_proposal = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PAREAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 2: Agent removed the studio apartment (350 sq ft)
            # Must remove the specific undersized apartment
            studio_removed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulApartmentApp"
                and e.action.function_name == "remove_saved_apartment"
                and e.action.args.get("apartment_id") == self.apt_id_studio
                for e in log_entries
            )

            # STRICT Check 3: Agent removed the small 1BR apartment (480 sq ft)
            # Must remove the specific undersized apartment
            small_1br_removed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulApartmentApp"
                and e.action.function_name == "remove_saved_apartment"
                and e.action.args.get("apartment_id") == self.apt_id_1br_small
                for e in log_entries
            )

            # Determine success and build rationale
            all_checks = {
                "agent_sent_proposal": agent_sent_proposal,
                "studio_removed": studio_removed,
                "small_1br_removed": small_1br_removed,
            }

            success = all(all_checks.values())

            if not success:
                failed_checks = [name for name, passed in all_checks.items() if not passed]
                rationale = f"Validation failed. Missing required agent actions: {', '.join(failed_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
