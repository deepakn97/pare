"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.apartment_listing import Apartment
from are.simulation.apps.contacts import Contact
from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulMessagingApp,
)
from pas.apps.apartment import StatefulApartmentApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("apartment_feature_comparison_query")
class ApartmentFeatureComparisonQuery(PASScenario):
    """Agent answers comparative query about saved apartments by retrieving and analyzing listing details. The user has saved three apartments to favorites during their apartment search. They are messaging with their friend Jordan discussing the options. Jordan sends a message asking "Out of the apartments you saved, which ones have parking included and are pet-friendly? I remember you mentioned needing both." The agent must: 1. Parse the dual-criteria query (parking + pet policy) from the incoming message, 2. List all saved apartments to identify candidates, 3. Retrieve full details for each saved apartment to check amenities and pet policy fields, 4. Compare the listings against both criteria, 5. Send a reply message to Jordan listing which apartments match (with names, key details, and why they qualify) and which don't meet the requirements. This scenario exercises query parsing from conversation context, systematic iteration over saved apartment listings, multi-field filtering logic, and comparative summarization in a conversational reply.."""

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # TODO: Initialize scenario specific apps here
        self.messaging = StatefulMessagingApp(name="Messages")
        self.apartment = StatefulApartmentApp(name="Apartment")

        # TODO: Populate apps with scenario specific data here

        # Add contacts and users for messaging
        jordan_contact = Contact(
            first_name="Jordan", last_name="Lee", phone="+1-555-0101", email="jordan.lee@example.com"
        )

        # Set up messaging app with user names and IDs
        self.messaging.current_user_id = "user_main"
        self.messaging.current_user_name = "Me"
        self.messaging.add_users(["Jordan Lee"])
        jordan_id = self.messaging.name_to_id["Jordan Lee"]

        # Create earlier conversation history discussing apartment search
        earlier_messages = [
            MessageV2(
                sender_id="user_main",
                content="Hey Jordan! I've been apartment hunting and saved a few places that look promising.",
                timestamp=datetime(2025, 11, 17, 14, 30, 0, tzinfo=UTC).timestamp(),
            ),
            MessageV2(
                sender_id=jordan_id,
                content="That's great! What are you looking for?",
                timestamp=datetime(2025, 11, 17, 14, 35, 0, tzinfo=UTC).timestamp(),
            ),
            MessageV2(
                sender_id="user_main",
                content="I need parking for my car and a place that's pet-friendly since I'm planning to adopt a cat.",
                timestamp=datetime(2025, 11, 17, 14, 40, 0, tzinfo=UTC).timestamp(),
            ),
            MessageV2(
                sender_id=jordan_id,
                content="Those are important! Let me know which ones you end up liking.",
                timestamp=datetime(2025, 11, 17, 15, 0, 0, tzinfo=UTC).timestamp(),
            ),
        ]

        conversation = ConversationV2(
            participant_ids=["user_main", jordan_id],
            messages=earlier_messages,
            title="Jordan Lee",
            last_updated=datetime(2025, 11, 17, 15, 0, 0, tzinfo=UTC).timestamp(),
        )
        self.messaging.add_conversation(conversation)

        # Populate apartment app with three saved apartments with varying criteria

        # Apartment 1: Has both parking and is pet-friendly
        apt1 = Apartment(
            name="Riverside Lofts",
            location="Downtown",
            zip_code="90210",
            price=2200.0,
            bedrooms=2,
            bathrooms=1,
            property_type="Apartment",
            square_footage=950,
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Parking", "Gym", "Pool", "In-unit laundry"],
            apartment_id="apt_001",
        )

        # Apartment 2: Has parking but NO pets allowed
        apt2 = Apartment(
            name="Sunset Gardens",
            location="Midtown",
            zip_code="90211",
            price=1900.0,
            bedrooms=1,
            bathrooms=1,
            property_type="Apartment",
            square_footage=800,
            furnished_status="Unfurnished",
            floor_level="Ground floor",
            pet_policy="No pets",
            lease_term="1 year",
            amenities=["Parking", "Gym", "Balcony"],
            apartment_id="apt_002",
        )

        # Apartment 3: Pet-friendly but NO parking
        apt3 = Apartment(
            name="Green Valley Studios",
            location="Westside",
            zip_code="90212",
            price=1750.0,
            bedrooms=1,
            bathrooms=1,
            property_type="Studio",
            square_footage=650,
            furnished_status="Semi-furnished",
            floor_level="Upper floors",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Gym", "Rooftop terrace", "In-unit laundry"],
            apartment_id="apt_003",
        )

        # Add apartments to the app and mark them as saved
        self.apartment.apartments["apt_001"] = apt1
        self.apartment.apartments["apt_002"] = apt2
        self.apartment.apartments["apt_003"] = apt3

        self.apartment.saved_apartments = ["apt_001", "apt_002", "apt_003"]
        apt1.saved = True
        apt2.saved = True
        apt3.saved = True

        # TODO: Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.apartment]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")

        with EventRegisterer.capture_mode():
            # Environment event: Jordan sends a message asking the comparison question
            # This is the triggering environment event that motivates agent action
            jordan_id = messaging_app.name_to_id["Jordan Lee"]
            conversation_id = next(iter(messaging_app.conversations.keys()))

            env_msg = messaging_app.create_and_add_message(
                conversation_id=conversation_id,
                sender_id=jordan_id,
                content="Out of the apartments you saved, which ones have parking included and are pet-friendly? I remember you mentioned needing both.",
            )

            # Oracle event: Agent reads the incoming message to understand the query
            # Motivation: New message notification from Jordan about saved apartments
            agent_read = (
                messaging_app.read_conversation(conversation_id=conversation_id, offset=0, limit=10)
                .oracle()
                .depends_on(env_msg, delay_seconds=2)
            )

            # Oracle event: Agent lists saved apartments to identify candidates for comparison
            # Motivation: Jordan's message asks about "apartments you saved", so agent must retrieve the saved list
            list_saved = apartment_app.list_saved_apartments().oracle().depends_on(agent_read, delay_seconds=3)

            # Oracle event: Agent retrieves details for apartment 1 to check parking + pet policy
            # Motivation: Need to inspect amenities and pet_policy fields for comparison
            get_apt1 = (
                apartment_app.get_apartment_details(apartment_id="apt_001")
                .oracle()
                .depends_on(list_saved, delay_seconds=2)
            )

            # Oracle event: Agent retrieves details for apartment 2
            # Motivation: Systematic comparison requires checking all saved apartments
            get_apt2 = (
                apartment_app.get_apartment_details(apartment_id="apt_002")
                .oracle()
                .depends_on(get_apt1, delay_seconds=2)
            )

            # Oracle event: Agent retrieves details for apartment 3
            # Motivation: Complete the systematic review of all saved apartments
            get_apt3 = (
                apartment_app.get_apartment_details(apartment_id="apt_003")
                .oracle()
                .depends_on(get_apt2, delay_seconds=2)
            )

            # Oracle event: Agent sends proposal with comparative analysis
            # Motivation: Jordan's message explicitly asked "which ones have parking and are pet-friendly", so agent responds with findings
            # The proposal cites the triggering message and provides a compact comparison
            proposal = (
                aui.send_message_to_user(
                    content="I can help answer Jordan's question about which saved apartments have both parking and pet-friendly policies. Based on your saved listings: Riverside Lofts meets both criteria (parking included, pets allowed). Sunset Gardens has parking but doesn't allow pets. Green Valley Studios is pet-friendly but has no parking. Would you like me to send this comparison to Jordan?"
                )
                .oracle()
                .depends_on(get_apt3, delay_seconds=3)
            )

            # Oracle/user event: User accepts the proposal
            # Motivation: User agrees to have agent send the comparison message
            acceptance = (
                aui.accept_proposal(content="Yes, please send that to Jordan.")
                .oracle()
                .depends_on(proposal, delay_seconds=5)
            )

            # Oracle event: Agent sends the comparison message to Jordan
            # Motivation: User accepted the proposal, so agent follows through by replying to Jordan
            send_reply = (
                messaging_app.send_message(
                    user_id=jordan_id,
                    content="Of my saved apartments: Riverside Lofts has both parking and is pet-friendly ($2200, 2BR in Downtown). Sunset Gardens has parking but no pets ($1900, 1BR in Midtown). Green Valley Studios allows cats but no parking ($1750, studio in Westside). Only Riverside Lofts meets both requirements!",
                )
                .oracle()
                .depends_on(acceptance, delay_seconds=4)
            )

        # TODO: Register ALL events here in self.events
        self.events = [env_msg, agent_read, list_saved, get_apt1, get_apt2, get_apt3, proposal, acceptance, send_reply]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:  # noqa: C901
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT events for validation
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent read the conversation to detect Jordan's query
            read_conversation_found = False
            for e in agent_events:
                if e.action.class_name == "StatefulMessagingApp" and e.action.function_name == "read_conversation":
                    read_conversation_found = True
                    break

            # STRICT Check 2: Agent listed saved apartments
            list_saved_found = False
            for e in agent_events:
                if e.action.class_name == "StatefulApartmentApp" and e.action.function_name == "list_saved_apartments":
                    list_saved_found = True
                    break

            # STRICT Check 3: Agent retrieved details for all three apartments
            # This ensures systematic comparison logic
            retrieved_apartment_ids = set()
            for e in agent_events:
                if e.action.class_name == "StatefulApartmentApp" and e.action.function_name == "get_apartment_details":
                    apt_id = e.action.args.get("apartment_id")
                    if apt_id:
                        retrieved_apartment_ids.add(apt_id)

            all_apartments_retrieved = (
                "apt_001" in retrieved_apartment_ids
                and "apt_002" in retrieved_apartment_ids
                and "apt_003" in retrieved_apartment_ids
            )

            # STRICT Check 4: Agent sent proposal to user (flexible on content)
            proposal_found = False
            for e in agent_events:
                if e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user":
                    proposal_found = True
                    break

            # STRICT Check 5: Agent sent reply message to Jordan
            # Accept either send_message or any equivalent messaging method
            reply_sent_found = False
            for e in agent_events:
                if e.action.class_name == "StatefulMessagingApp" and e.action.function_name in [
                    "send_message",
                    "reply_to_message",
                    "create_and_add_message",
                ]:
                    # Verify it has a recipient identifier (structural check)
                    has_recipient = (
                        "user_id" in e.action.args or "sender_id" in e.action.args or "conversation_id" in e.action.args
                    )
                    if not has_recipient:
                        continue

                    # Verify the reply includes the qualified-apartment result (content check)
                    content = e.action.args.get("content") or e.action.args.get("message") or e.action.args.get("text")
                    if isinstance(content, str):
                        normalized = content.lower()
                        if "riverside lofts" in normalized:
                            reply_sent_found = True
                            break

            # Aggregate all strict checks
            success = (
                read_conversation_found
                and list_saved_found
                and all_apartments_retrieved
                and proposal_found
                and reply_sent_found
            )

            # Build rationale for failures
            if not success:
                missing_checks = []
                if not read_conversation_found:
                    missing_checks.append("agent did not read conversation")
                if not list_saved_found:
                    missing_checks.append("agent did not list saved apartments")
                if not all_apartments_retrieved:
                    missing_checks.append(
                        f"agent did not retrieve all three apartment details (found: {retrieved_apartment_ids})"
                    )
                if not proposal_found:
                    missing_checks.append("agent did not send proposal to user")
                if not reply_sent_found:
                    missing_checks.append("agent did not send reply message to Jordan")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
