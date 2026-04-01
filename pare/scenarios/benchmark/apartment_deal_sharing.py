"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.apartment_listing import Apartment
from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
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


@register_scenario("apartment_deal_sharing")
class ApartmentDealSharing(PAREScenario):
    """Agent proactively shares price-reduced apartment listing with friend based on budget discussion. The user has saved multiple apartments to favorites and is casually apartment hunting. Earlier, the user participated in a group conversation where a friend (Sarah) mentioned needing to find a 2-bedroom apartment under $2000/month near downtown. A notification arrives that one of the user's saved apartments ("Riverside Lofts") has reduced its price from $2200 to $1850. The agent must: 1. Parse the price drop notification to identify the apartment by name and new price, 2. Search saved apartments to locate Riverside Lofts and retrieve its full details (bedrooms, location, amenities), 3. Search recent group conversations to find Sarah's budget and location requirements, 4. Match the reduced-price apartment to Sarah's stated needs, 5. Send a message to Sarah (or the group conversation) recommending the apartment with key details and the price reduction. This scenario exercises cross-app memory (messages → apartments), temporal reasoning about recent conversations, opportunistic information matching, and proactive social coordination without explicit user request.."""

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize apartment app
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Initialize messaging app
        self.messaging = StatefulMessagingApp(name="Messages")

        # Populate apartment app with saved listings
        # Create several apartments, including Riverside Lofts which will have its price reduced
        riverside_id = "riverside_lofts_001"
        skyline_id = "skyline_tower_002"
        harbor_id = "harbor_view_003"

        self.apartment.apartments[riverside_id] = Apartment(
            apartment_id=riverside_id,
            name="Riverside Lofts",
            location="Downtown",
            zip_code="90012",
            price=2200.0,  # Will be reduced to 1850 via environment event
            bedrooms=2,
            bathrooms=2,
            property_type="Apartment",
            square_footage=950,
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Gym", "Pool", "Parking", "In-unit laundry"],
            saved=True,
        )

        self.apartment.apartments[skyline_id] = Apartment(
            apartment_id=skyline_id,
            name="Skyline Tower",
            location="Midtown",
            zip_code="90017",
            price=2500.0,
            bedrooms=1,
            bathrooms=1,
            property_type="Condo",
            square_footage=750,
            furnished_status="Furnished",
            floor_level="Penthouse",
            pet_policy="No pets",
            lease_term="1 year",
            amenities=["Gym", "Concierge"],
            saved=True,
        )

        self.apartment.apartments[harbor_id] = Apartment(
            apartment_id=harbor_id,
            name="Harbor View Suites",
            location="Waterfront",
            zip_code="90731",
            price=1800.0,
            bedrooms=2,
            bathrooms=1,
            property_type="Apartment",
            square_footage=880,
            furnished_status="Unfurnished",
            floor_level="Ground floor",
            pet_policy="Cats allowed",
            lease_term="6 months",
            amenities=["Parking", "Balcony"],
            saved=True,
        )

        self.apartment.saved_apartments = [riverside_id, skyline_id, harbor_id]

        # Populate messaging app with contacts and conversation history
        # Add users to messaging app
        self.messaging.current_user_id = "user_me"
        self.messaging.current_user_name = "Me"

        sarah_id = "user_sarah"
        sarah_name = "Sarah"
        mike_id = "user_mike"
        mike_name = "Mike"

        self.messaging.id_to_name = {
            "user_me": "Me",
            sarah_id: sarah_name,
            mike_id: mike_name,
        }
        self.messaging.name_to_id = {
            "Me": "user_me",
            sarah_name: sarah_id,
            mike_name: mike_id,
        }

        # Create a group conversation where Sarah mentioned her apartment needs
        # This conversation happened 2 days ago
        group_conv_id = "group_apt_hunting_001"
        base_timestamp = self.start_time - (2 * 24 * 3600)  # 2 days before start_time

        group_conversation = ConversationV2(
            conversation_id=group_conv_id,
            participant_ids=["user_me", sarah_id, mike_id],
            title="Apartment Hunting",
            last_updated=base_timestamp + 3600,
        )

        # Add messages where Sarah mentions her requirements
        group_conversation.messages = [
            MessageV2(
                sender_id=mike_id,
                content="Hey everyone, how's the apartment search going?",
                timestamp=base_timestamp,
            ),
            MessageV2(
                sender_id="user_me",
                content="Still looking! Found a few interesting places.",
                timestamp=base_timestamp + 300,
            ),
            MessageV2(
                sender_id=sarah_id,
                content="I'm struggling to find something affordable. I really need a 2-bedroom place under $2000 per month, preferably near downtown for my commute.",
                timestamp=base_timestamp + 600,
            ),
            MessageV2(
                sender_id=sarah_id,
                content="It's so hard to find anything decent in that price range in a good location!",
                timestamp=base_timestamp + 900,
            ),
            MessageV2(
                sender_id=mike_id,
                content="Yeah, the market is tough right now. Good luck with the search!",
                timestamp=base_timestamp + 1200,
            ),
        ]

        self.messaging.add_conversation(group_conversation)

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.apartment, self.messaging]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Price drop notification for Riverside Lofts
            # This is the exogenous trigger that will motivate the agent to act
            price_update_event = apartment_app.update_apartment(
                apartment_id="riverside_lofts_001",
                new_price=1850.0,
            ).delayed(10)

            # Oracle Event 1: Agent lists saved apartments to discover which apartment was updated
            # Motivation: The price update notification reveals apartment_id; agent needs full details to match requirements
            list_saved_event = (
                apartment_app.list_saved_apartments().oracle().depends_on(price_update_event, delay_seconds=3)
            )

            # Oracle Event 2: Agent searches conversation history for budget/apartment requirements
            # Motivation: To find Sarah's stated budget and location needs from recent messages
            search_conversations_event = (
                messaging_app.search(query="apartment").oracle().depends_on(list_saved_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent reads the group conversation to extract Sarah's exact requirements
            # Motivation: search() found the conversation ID; agent needs message content with requirements
            read_conversation_event = (
                messaging_app.read_conversation(
                    conversation_id="group_apt_hunting_001",
                    offset=0,
                    limit=10,
                )
                .oracle()
                .depends_on(search_conversations_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent sends proposal to user about sharing the apartment with Sarah
            # Motivation: Riverside Lofts price drop ($2200→$1850) matches Sarah's stated requirement
            # (<$2000, 2-bedroom, near downtown) from the group conversation
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed that Riverside Lofts reduced its price from $2200 to $1850. This matches Sarah's requirements from your group chat (2-bedroom under $2000 near downtown). Would you like me to share this with her?"
                )
                .oracle()
                .depends_on(read_conversation_event, delay_seconds=3)
            )

            # Oracle Event 5: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please send it to Sarah.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=5)
            )

            # Oracle Event 6: Agent gets apartment details to include in the message
            # Motivation: User approved sharing; agent needs full details (amenities, location, etc.) to compose helpful message
            get_details_event = (
                apartment_app.get_apartment_details(apartment_id="riverside_lofts_001")
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 7: Agent sends message to Sarah in the group conversation with apartment details
            # Motivation: User accepted; agent shares discovered apartment match with Sarah
            send_message_event = (
                messaging_app.send_message_to_group_conversation(
                    conversation_id="group_apt_hunting_001",
                    content="Hi Sarah! I found a 2-bedroom apartment that matches your requirements: Riverside Lofts in Downtown, just reduced from $2200 to $1850/month. It has 2 bathrooms, 950 sq ft, and amenities including gym, pool, parking, and in-unit laundry. Let me know if you'd like more details!",
                )
                .oracle()
                .depends_on(get_details_event, delay_seconds=3)
            )

        # Register ALL events
        self.events = [
            price_update_event,
            list_saved_event,
            search_conversations_event,
            read_conversation_event,
            proposal_event,
            acceptance_event,
            get_details_event,
            send_message_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1: Agent sent proposal to user about sharing apartment with Sarah (STRICT)
            # Must mention: Riverside Lofts, price reduction, and Sarah
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PAREAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "Riverside Lofts" in e.action.args.get("content", "")
                and "Sarah" in e.action.args.get("content", "")
                and any(
                    keyword in e.action.args.get("content", "")
                    for keyword in ["1850", "$1850", "price", "reduced", "reduction", "drop"]
                )
                for e in log_entries
            )

            # Check 2: Agent listed or searched saved apartments (STRICT)
            # Multiple valid methods: list_saved_apartments or search_apartments or get_apartment_details
            apartment_discovery_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulApartmentApp"
                and e.action.function_name in ["list_saved_apartments", "search_apartments", "get_apartment_details"]
                for e in log_entries
            )

            # Check 3: Agent searched conversations to find Sarah's requirements (STRICT)
            # Multiple valid methods: search or list_conversations or read_conversation
            conversation_search_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name in ["search", "list_conversations", "read_conversation"]
                for e in log_entries
            )

            # Check 4: Agent read the group conversation to extract Sarah's exact requirements (STRICT)
            conversation_read_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "read_conversation"
                and e.action.args.get("conversation_id") == "group_apt_hunting_001"
                for e in log_entries
            )

            # Check 5: Agent sent message to Sarah in the group conversation (STRICT)
            # Must reference Riverside Lofts and Sarah, but content can vary
            message_to_sarah_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message_to_group_conversation"
                and e.action.args.get("conversation_id") == "group_apt_hunting_001"
                for e in log_entries
            )

            # All strict checks must pass
            success = (
                proposal_found
                and apartment_discovery_found
                and conversation_search_found
                and conversation_read_found
                and message_to_sarah_found
            )

            if not success:
                # Build rationale for failure
                missing = []
                if not proposal_found:
                    missing.append("agent proposal to user about sharing Riverside Lofts with Sarah")
                if not apartment_discovery_found:
                    missing.append("agent discovery of apartment details")
                if not conversation_search_found:
                    missing.append("agent search of conversations for requirements")
                if not conversation_read_found:
                    missing.append("agent read of group conversation 'group_apt_hunting_001'")
                if not message_to_sarah_found:
                    missing.append("agent message to Sarah in group conversation")

                rationale = f"Missing critical checks: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
