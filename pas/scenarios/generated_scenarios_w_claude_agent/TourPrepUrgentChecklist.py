"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.messaging_v2 import ConversationV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulMessagingApp,
)
from pas.apps.apartment import StatefulApartmentApp
from pas.apps.note import StatefulNotesApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("tour_prep_urgent_checklist")
class TourPrepUrgentChecklist(PASScenario):
    """Agent creates structured apartment tour preparation checklist from urgent tour confirmation message. The user has saved two apartments to their favorites (Lakeview Plaza and Cedar Heights) and created a "Personal" folder note titled "Apartment Must-Haves" listing priorities: washer/dryer in-unit, natural light in bedroom, max $1800/month, pet-friendly for cat, within 3 miles of office at 450 Market St. The user receives a message notification from the Lakeview Plaza leasing office stating "Your tour is confirmed for tomorrow 10 AM at 789 Lakeview Dr. Please bring photo ID, proof of income, and any questions about the unit." The agent must: 1. Parse the tour confirmation with time, location, and required documents from the message, 2. Search notes to retrieve the user's documented apartment priorities, 3. Search saved apartments to locate Lakeview Plaza and extract its key details (rent, amenities, pet policy, location), 4. Create a comprehensive tour preparation note in "Personal" folder combining the required documents list from the message, the user's priority questions derived from their must-haves note, and a reminder to verify commute distance, 5. Reply to the leasing office message confirming attendance and asking one clarifying question about parking availability during the tour.

    This scenario exercises message-triggered task preparation, cross-app data synthesis (messages → notes → saved apartments), structured checklist generation from multiple information sources, priority-driven question formulation, and contextual communication within existing message threads.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.apartment = StatefulApartmentApp(name="Apartment")
        self.messaging = StatefulMessagingApp(name="Messages")
        self.note = StatefulNotesApp(name="Notes")

        # Populate messaging app with contact mapping
        self.messaging.current_user_id = "user_001"
        self.messaging.current_user_name = "User"
        self.messaging.add_users(["Lakeview Plaza Leasing", "Alex Chen"])

        # Create a conversation with Lakeview Plaza Leasing
        leasing_office_id = self.messaging.get_user_id("Lakeview Plaza Leasing")
        self.leasing_conversation = ConversationV2(
            participant_ids=[self.messaging.current_user_id, leasing_office_id],
            title="Lakeview Plaza Leasing",
        )
        self.messaging.add_conversation(self.leasing_conversation)

        # Create a conversation with a roommate/friend who may provide planning context
        alex_id = self.messaging.get_user_id("Alex Chen")
        self.alex_conversation = ConversationV2(
            participant_ids=[self.messaging.current_user_id, alex_id],
            title="Alex Chen",
        )
        self.messaging.add_conversation(self.alex_conversation)

        # Populate apartment app with two saved apartments
        lakeview_id = self.apartment.add_new_apartment(
            name="Lakeview Plaza",
            location="789 Lakeview Dr, San Francisco, CA",
            zip_code="94102",
            price=1750.0,
            number_of_bedrooms=1,
            number_of_bathrooms=1,
            square_footage=750,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Washer/Dryer in-unit", "Large windows", "Parking available", "Gym"],
        )
        self.apartment.save_apartment(lakeview_id)

        cedar_id = self.apartment.add_new_apartment(
            name="Cedar Heights",
            location="125 Cedar St, San Francisco, CA",
            zip_code="94103",
            price=1800.0,
            number_of_bedrooms=1,
            number_of_bathrooms=1,
            square_footage=800,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Ground floor",
            pet_policy="No pets",
            lease_term="1 year",
            amenities=["Dishwasher", "Balcony"],
        )
        self.apartment.save_apartment(cedar_id)

        # Populate notes app with apartment priorities note
        self.note.create_note_with_time(
            folder="Personal",
            title="Apartment Must-Haves",
            content=(
                "Key priorities for apartment search:\n"
                "- Washer/dryer in-unit (essential)\n"
                "- Natural light in bedroom\n"
                "- Max budget: $1800/month\n"
                "- Pet-friendly for cat\n"
                "- Within 3 miles of office at 450 Market St"
            ),
            pinned=False,
            created_at="2025-11-15 14:30:00",
            updated_at="2025-11-15 14:30:00",
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.apartment, self.messaging, self.note]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")

        # Get the leasing office user ID and conversation ID
        leasing_office_id = messaging_app.get_user_id("Lakeview Plaza Leasing")
        # Get conversation ID - we need to retrieve it from the seeded conversation
        existing_convs = messaging_app.get_existing_conversation_ids([leasing_office_id])
        if len(existing_convs) > 0:
            leasing_conversation_id = existing_convs[0]
        else:
            # Fallback: create conversation if it doesn't exist
            leasing_conversation_id = self.leasing_conversation.conversation_id

        # IMPORTANT: Do not call app methods like get_user_id() inside capture_mode(),
        # because they return Events rather than concrete values.
        alex_id = messaging_app.get_user_id("Alex Chen")
        alex_conversation_id = self.alex_conversation.conversation_id

        with EventRegisterer.capture_mode():
            # Environment Event 1: Tour confirmation message from leasing office
            # This is the concrete environment trigger that motivates all agent actions
            tour_confirmation_event = messaging_app.create_and_add_message(
                conversation_id=leasing_conversation_id,
                sender_id=leasing_office_id,
                content=(
                    "Your tour is confirmed for tomorrow 10 AM at 789 Lakeview Dr. "
                    "Please bring photo ID and proof of income (recent pay stubs). "
                    "If you're driving, visitor parking can be limited—reply to confirm you're coming "
                    "and let us know if you'd like parking instructions."
                ),
            ).delayed(5)

            # Environment Event 2: Roommate/friend reminder that explicitly references the note title
            # This ensures the agent has an observable basis for querying the notes app with a specific string.
            note_hint_event = messaging_app.create_and_add_message(
                conversation_id=alex_conversation_id,
                sender_id=alex_id,
                content=(
                    "Since you said you're rushing tomorrow, maybe make a quick checklist. "
                    "Before the Lakeview tour, check your note titled 'Apartment Must-Haves' so you remember what questions to ask "
                    "(laundry, natural light, cat policy, commute). You can also create a tour prep checklist (docs + questions + property summary) in your notes. For the property summary, you can get those details from the saved apartments in the apartment app."
                ),
            ).delayed(7)

            # Oracle Event 1: Agent searches notes to find user's apartment priorities
            # Motivation: tour_confirmation_event mentions "questions about the unit", and note_hint_event explicitly mentions the note title "Apartment Must-Haves".
            search_notes_event = (
                note_app.search_notes(query="Apartment Must-Haves")
                .oracle()
                .depends_on([tour_confirmation_event, note_hint_event], delay_seconds=2)
            )

            # Oracle Event 2: Agent lists saved apartments to find Lakeview Plaza details
            # Motivation: tour_confirmation_event specifies "Lakeview" tour location - agent needs to retrieve saved apartment details to cross-reference with priorities
            list_saved_event = (
                apartment_app.list_saved_apartments().oracle().depends_on(search_notes_event, delay_seconds=1)
            )

            # Oracle Event 3: Agent proposes creating tour preparation checklist
            # Motivation: tour_confirmation_event explicitly states "tomorrow 10 AM" and "Please bring..." - agent offers to synthesize requirements with user's priorities into checklist
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "I saw your Lakeview Plaza tour confirmation for tomorrow at 10 AM. "
                        "They asked you to bring photo ID + proof of income and to reply to confirm (parking can be limited). "
                        "Alex also reminded you about your 'Apartment Must-Haves' note for questions to ask. "
                        "Would you like me to create a tour prep checklist (docs + questions + property summary) and send a quick confirmation reply asking for parking instructions?"
                    )
                )
                .oracle()
                .depends_on(list_saved_event, delay_seconds=2)
            )

            # Oracle Event 4: User accepts the proposal
            # Motivation: proposal_event dependency
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes—please create the checklist and send a confirmation reply asking about parking."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent creates comprehensive tour prep note combining all sources
            # Motivation: acceptance_event grants permission; earlier search_notes_event and list_saved_event revealed priorities and property details to synthesize
            create_note_event = (
                note_app.create_note(
                    folder="Personal",
                    title="Lakeview Plaza Tour Prep - Nov 19 10 AM",
                    content=(
                        "Tour Details:\n"
                        "- Date/Time: Tomorrow 10 AM\n"
                        "- Location: 789 Lakeview Dr\n\n"
                        "Required Documents:\n"
                        "- Photo ID\n"
                        "- Proof of income\n\n"
                        "Questions to Ask (Based on Your Must-Haves):\n"
                        "- Confirm cat policy details (size/breed restrictions, deposit)\n"
                        "- Ask about natural light in bedroom (window orientation)\n"
                        "- Verify commute time to 450 Market St (currently 789 Lakeview Dr)\n"
                        "- Check washer/dryer specs (size, brand, any issues)\n\n"
                        "Property Summary:\n"
                        "- Rent: $1750/month (within budget)\n"
                        "- Amenities: Washer/Dryer in-unit, Large windows, Parking, Gym\n"
                        "- Pet Policy: Cats allowed"
                    ),
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent replies to leasing office confirming attendance and asking about parking
            # Motivation: tour_confirmation_event expects response; list_saved_event revealed "Parking available" amenity - agent confirms attendance and clarifies parking logistics for tour
            reply_message_event = (
                messaging_app.send_message(
                    user_id=leasing_office_id,
                    content="Thank you for confirming the tour for tomorrow at 10 AM. I'll bring photo ID and proof of income. Quick question: Is visitor parking available on-site, and if so, where should I park for the tour?",
                )
                .oracle()
                .depends_on(create_note_event, delay_seconds=3)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            tour_confirmation_event,
            note_hint_event,
            search_notes_event,
            list_saved_event,
            proposal_event,
            acceptance_event,
            create_note_event,
            reply_message_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent searched notes for apartment priorities
            # This observation step is critical - agent must retrieve user's documented priorities
            search_notes_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "search_notes"
                for e in log_entries
            )

            # STRICT Check 2: Agent observed saved apartments to find Lakeview Plaza details
            # Multiple equivalent methods can satisfy this goal: list_saved_apartments, get_saved_apartments, or search_apartments
            list_saved_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulApartmentApp"
                and e.action.function_name in ["list_saved_apartments", "get_saved_apartments", "search_apartments"]
                for e in log_entries
            )

            # STRICT Check 3: Agent sent proposal about creating tour prep checklist
            # Flexible on wording, but must reference key elements (tour confirmation context)
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "tour" in e.action.args.get("content", "").lower()
                for e in log_entries
            )

            # STRICT Check 4: Agent created the tour prep note in Personal folder
            # Must verify folder, but flexible on title and content wording
            create_note_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "create_note"
                and e.action.args.get("folder") == "Personal"
                and "Lakeview" in e.action.args.get("title", "")
                for e in log_entries
            )

            # STRICT Check 5: Agent replied to the leasing office message
            # Multiple equivalent methods can satisfy this goal: send_message, reply_to_message, or send_batch_reply
            # Flexible on exact message content - just verify the action happened with the correct recipient
            reply_message_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name in ["send_message", "reply_to_message", "send_batch_reply"]
                and e.action.args.get("user_id")  # Verify user_id is present and non-empty
                for e in log_entries
            )

            # All strict checks must pass
            success = (
                search_notes_found and list_saved_found and proposal_found and create_note_found and reply_message_found
            )

            if not success:
                # Build rationale for failure
                missing_checks = []
                if not search_notes_found:
                    missing_checks.append("agent did not search notes for apartment priorities")
                if not list_saved_found:
                    missing_checks.append("agent did not list/search saved apartments")
                if not proposal_found:
                    missing_checks.append("agent did not send tour prep proposal to user")
                if not create_note_found:
                    missing_checks.append("agent did not create tour prep note in Personal folder")
                if not reply_message_found:
                    missing_checks.append("agent did not reply to leasing office message")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
