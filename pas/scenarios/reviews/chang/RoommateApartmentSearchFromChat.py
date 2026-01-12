"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.contacts import Contact
from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulApartmentApp,
    StatefulMessagingApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("roommate_apartment_search_from_chat")
class RoommateApartmentSearchFromChat(PASScenario):
    """Agent searches and curates apartment listings based on roommate group discussion. The user is in a group message conversation with two potential roommates (Alex and Jordan) discussing moving in together. Alex sends a message saying "We should look for 3-bedroom apartments in downtown, preferably under $2500 total with parking." Jordan follows up with "And pet-friendly since I have a dog!" The agent must: 1. Parse the search criteria from the group messages (3 bedrooms, downtown location, max $2500, parking amenity, pet-friendly policy), 2. Search apartments using these filters to find matching listings, 3. Save the top 3-4 matching apartments to favorites for the user to review, 4. Send a summary message back to the group conversation listing the saved apartments by name with key details (price, bedrooms, pet policy, parking). This scenario exercises multi-participant conversation parsing, constraint synthesis from natural language, apartment search with multi-field filters, proactive curation via save operation, and group communication with structured information.."""

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize StatefulMessagingApp
        self.messaging = StatefulMessagingApp(name="Messages")

        # Add contacts: two potential roommates
        alex_contact = Contact(
            first_name="Alex",
            last_name="Chen",
            phone="+1234567890",
        )
        jordan_contact = Contact(
            first_name="Jordan",
            last_name="Rivera",
            phone="+1234567891",
        )

        # Register the contacts in the messaging app using add_contacts method
        self.messaging.add_contacts([
            ("Alex Chen", "+1234567890"),
            ("Jordan Rivera", "+1234567891"),
        ])

        # Create a group conversation with Alex and Jordan
        # Get user IDs for Alex and Jordan
        alex_id = self.messaging.name_to_id["Alex Chen"]
        jordan_id = self.messaging.name_to_id["Jordan Rivera"]

        # Create the group conversation with existing history about apartment hunting
        group_conversation = ConversationV2(
            participant_ids=[self.messaging.current_user_id, alex_id, jordan_id],
            title="Alex Chen, Jordan Rivera",
            messages=[
                MessageV2(
                    sender_id=alex_id,
                    content="Hey! So I think we should seriously start looking for places soon. Our leases are all up in December right?",
                    timestamp=self.start_time - 86400,  # 1 day ago
                ),
                MessageV2(
                    sender_id=self.messaging.current_user_id,
                    content="Yeah mine ends Dec 15. Would love to find something by then!",
                    timestamp=self.start_time - 86000,  # shortly after
                ),
                MessageV2(
                    sender_id=jordan_id,
                    content="Same here, Dec 20 for me. Let's do this!",
                    timestamp=self.start_time - 85000,
                ),
            ],
        )

        # Add the conversation to the messaging app
        self.messaging.add_conversation(group_conversation)

        # Initialize StatefulApartmentApp with some apartment listings
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Add apartments to the database (some matching criteria, some not)
        # Matching apartments (3 bed, downtown, <$2500, parking, pet-friendly)
        self.apartment.add_new_apartment(
            name="Downtown Lofts",
            location="Downtown",
            zip_code="90012",
            price=2400.0,
            number_of_bedrooms=3,
            number_of_bathrooms=2,
            square_footage=1200,
            property_type="Apartment",
            pet_policy="Pets allowed",
            amenities=["Parking", "Gym", "Pool"],
        )

        self.apartment.add_new_apartment(
            name="Metro Heights",
            location="Downtown",
            zip_code="90013",
            price=2300.0,
            number_of_bedrooms=3,
            number_of_bathrooms=2,
            square_footage=1150,
            property_type="Apartment",
            pet_policy="Pets allowed",
            amenities=["Parking", "Laundry"],
        )

        self.apartment.add_new_apartment(
            name="Central Plaza Apartments",
            location="Downtown",
            zip_code="90014",
            price=2450.0,
            number_of_bedrooms=3,
            number_of_bathrooms=2,
            square_footage=1300,
            property_type="Apartment",
            pet_policy="Dogs allowed",
            amenities=["Parking", "Balcony", "Dishwasher"],
        )

        # Non-matching apartments (for filtering test)
        self.apartment.add_new_apartment(
            name="Uptown Suites",
            location="Uptown",  # Wrong location
            zip_code="90015",
            price=2200.0,
            number_of_bedrooms=3,
            number_of_bathrooms=2,
            square_footage=1100,
            property_type="Apartment",
            pet_policy="Pets allowed",
            amenities=["Parking"],
        )

        self.apartment.add_new_apartment(
            name="Downtown Luxury",
            location="Downtown",
            zip_code="90016",
            price=2800.0,  # Too expensive
            number_of_bedrooms=3,
            number_of_bathrooms=2,
            square_footage=1400,
            property_type="Apartment",
            pet_policy="Pets allowed",
            amenities=["Parking", "Concierge"],
        )

        self.apartment.add_new_apartment(
            name="Downtown Studios",
            location="Downtown",
            zip_code="90017",
            price=2000.0,
            number_of_bedrooms=2,  # Too few bedrooms
            number_of_bathrooms=1,
            square_footage=900,
            property_type="Apartment",
            pet_policy="Pets allowed",
            amenities=["Parking"],
        )

        self.apartment.add_new_apartment(
            name="Pet-Free Downtown",
            location="Downtown",
            zip_code="90018",
            price=2350.0,
            number_of_bedrooms=3,
            number_of_bathrooms=2,
            square_footage=1250,
            property_type="Apartment",
            pet_policy="No pets",  # Not pet-friendly
            amenities=["Parking", "Gym"],
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.apartment]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")

        # Get the conversation ID for the group chat BEFORE capture_mode
        alex_id = messaging_app.name_to_id["Alex Chen"]
        jordan_id = messaging_app.name_to_id["Jordan Rivera"]
        conv_ids = messaging_app.get_existing_conversation_ids([alex_id, jordan_id])
        group_conv_id = conv_ids[0]

        with EventRegisterer.capture_mode():
            # Environment event 1: Alex sends message with search criteria
            env1 = messaging_app.create_and_add_message(
                conversation_id=group_conv_id,
                sender_id=alex_id,
                content="We should look for 3-bedroom apartments in downtown, preferably under $2500 total with parking.",
            )

            # Environment event 2: Jordan adds pet-friendly requirement
            env2 = messaging_app.create_and_add_message(
                conversation_id=group_conv_id,
                sender_id=jordan_id,
                content="And pet-friendly since I have a dog!",
            ).delayed(1)

            # Oracle event: Agent reads the group conversation to see the search criteria mentioned in env1 and env2
            oracle1 = (
                messaging_app.read_conversation(
                    conversation_id=group_conv_id,
                    offset=0,
                    limit=10,
                )
                .oracle()
                .depends_on([env1, env2], delay_seconds=3)
            )

            # Oracle event: Agent searches apartments with the criteria from the group messages
            # The search will reveal matching apartments that the agent can then reference
            oracle2 = (
                apartment_app.search_apartments(
                    location="downtown",
                    number_of_bedrooms=3,
                    max_price=2500.0,
                    amenities=["Parking"],
                    pet_policy="Pets allowed",
                )
                .oracle()
                .depends_on(oracle1, delay_seconds=2)
            )

            # Oracle event: Agent sends proposal to user with search results
            # This proposal cites the triggering environment events (env1 and env2) and the search results from oracle2
            proposal = (
                aui.send_message_to_user(
                    content="I saw your group discussion about finding an apartment. I searched for 3-bedroom places in downtown under $2500 with parking that allow pets, and found several matching apartments. Would you like me to share the details with Alex and Jordan?"
                )
                .oracle()
                .depends_on([oracle2, env1, env2], delay_seconds=2)
            )

            # User accepts the proposal
            user_accept = aui.accept_proposal(content="Yes please!").oracle().depends_on(proposal, delay_seconds=3)

            # Oracle event: After user acceptance, agent sends message to the group conversation with the apartment recommendations
            # This depends on user acceptance (user_accept)
            oracle3 = (
                messaging_app.send_message_to_group_conversation(
                    conversation_id=group_conv_id,
                    content=(
                        "Hi Alex and Jordan! I searched for 3-bedroom apartments in Downtown under $2,500 with Parking. Here are the pet-friendly options:\n\n"
                        "- Downtown Lofts (Downtown, $2,400) — 3BR/2BA — pet policy: Pets allowed — amenities: Parking, Gym, Pool\n"
                        "- Metro Heights (Downtown, $2,300) — 3BR/2BA — pet policy: Pets allowed — amenities: Parking, Laundry\n\n"
                        "- Central Plaza Apartments (Downtown, $2,450) — 3BR/2BA — pet policy: Dogs allowed — amenities: Parking, Balcony, Dishwasher\n\n"
                        "Want me to pull more details on any of these (sq ft, zip code, move-in timeline), or widen the search beyond Downtown?"
                    ),
                )
                .oracle()
                .depends_on(user_accept, delay_seconds=2)
            )

        # Register ALL events here in self.events
        self.events = [
            env1,
            env2,
            oracle1,
            oracle2,
            proposal,
            user_accept,
            oracle3,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT events for validation
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent sent proposal to user after detecting roommate requirements
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # FLEXIBLE Check 2: Agent read/observed the group conversation to understand requirements
            # Accept multiple ways of observing conversation state
            conversation_read = any(
                e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name in ["read_conversation", "get_conversation"]
                for e in agent_events
            )

            # STRICT Check 3: Agent searched apartments with appropriate filters
            # The search must have occurred (exact filter values are flexible)
            apartment_search = any(
                e.action.class_name == "StatefulApartmentApp" and e.action.function_name == "search_apartments"
                for e in agent_events
            )

            # FLEXIBLE Check 4: Agent sent response message to group conversation
            # Accept either send_message_to_group_conversation or send_message depending on API
            group_message_sent = any(
                e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name
                in ["send_message_to_group_conversation", "send_message", "create_and_add_message"]
                for e in agent_events
            )

            # Build success result and rationale
            if not proposal_found:
                rationale = "Agent did not send a proposal to the user via PASAgentUserInterface.send_message_to_user"
                success = False
            elif not apartment_search:
                rationale = "Agent did not perform apartment search using StatefulApartmentApp.search_apartments"
                success = False
            elif not group_message_sent:
                rationale = "Agent did not send search results to the group conversation via StatefulMessagingApp messaging method"
                success = False
            else:
                rationale = "All critical checks passed"
                success = True

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
