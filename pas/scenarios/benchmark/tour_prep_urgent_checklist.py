"""Scenario: Agent creates apartment tour preparation checklist from tour confirmation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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
    """Agent creates tour preparation checklist from tour confirmation and user's apartment priorities.

    The user has saved two apartments (Lakeview Plaza and Cedar Heights) and has a note documenting
    their apartment priorities (washer/dryer, natural light, budget, pet-friendly, commute). They
    receive a tour confirmation message from Lakeview Plaza leasing office for tomorrow. A friend
    also messages wishing them luck. The agent synthesizes information from the tour confirmation,
    the user's priorities note, and the saved apartment details to create a comprehensive tour
    preparation checklist and reply to confirm attendance.

    This scenario tests:
    - Message-triggered task preparation
    - Cross-app data synthesis (messages + notes + saved apartments)
    - Structured checklist generation from multiple sources
    - Contextual communication within message threads
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    additional_system_prompt = """You have a Lakeview Plaza apartment tour scheduled for tomorrow.
You have a note with your apartment priorities and the apartment details saved.

BEFORE the tour confirmation message arrives:
- Browse your messages or notes app

AFTER you receive the tour confirmation AND your friend's message:

ACCEPT proposals that:
- Offer to create a tour preparation checklist with documents to bring and questions to ask
- Offer to reply to the leasing office confirming attendance (this can be a separate proposal)

REJECT proposals that:
- Arrive before both messages have been received
- Only offer to reply without creating any checklist"""

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize apps
        self.apartment = StatefulApartmentApp(name="Apartment")
        self.messaging = StatefulMessagingApp(name="Messages")
        self.note = StatefulNotesApp(name="Notes")

        # Add users to messaging app
        self.messaging.add_users(["Lakeview Plaza Leasing", "Alex Chen"])

        # Store user IDs for later use
        self.leasing_office_id = self.messaging.get_user_id("Lakeview Plaza Leasing")
        self.alex_id = self.messaging.get_user_id("Alex Chen")

        # Create conversations
        current_user_id = self.messaging.current_user_id
        self.leasing_conversation = ConversationV2(
            participant_ids=[current_user_id, self.leasing_office_id],
            title="Lakeview Plaza Leasing",
        )
        self.messaging.add_conversation(self.leasing_conversation)

        self.alex_conversation = ConversationV2(
            participant_ids=[current_user_id, self.alex_id],
            title="Alex Chen",
        )
        self.messaging.add_conversation(self.alex_conversation)

        # Save conversation IDs for build_events_flow
        self.leasing_conversation_id = self.leasing_conversation.conversation_id
        self.alex_conversation_id = self.alex_conversation.conversation_id

        # Add saved apartments
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

        # Add apartment priorities note
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
        """Build event flow - tour confirmation triggers checklist creation."""
        aui = self.get_typed_app(PASAgentUserInterface)
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")

        with EventRegisterer.capture_mode():
            # ENV Event 1: Tour confirmation from leasing office
            tour_confirmation_event = messaging_app.create_and_add_message(
                conversation_id=self.leasing_conversation_id,
                sender_id=self.leasing_office_id,
                content=(
                    "Your tour is confirmed for tomorrow 10 AM at 789 Lakeview Dr. "
                    "Please bring photo ID and proof of income (recent pay stubs). "
                    "If you're driving, visitor parking can be limited—reply to confirm you're coming "
                    "and let us know if you'd like parking instructions."
                ),
            ).delayed(5)

            # ENV Event 2: Friend wishes luck (natural message)
            friend_message_event = messaging_app.create_and_add_message(
                conversation_id=self.alex_conversation_id,
                sender_id=self.alex_id,
                content=(
                    "Good luck with the Lakeview tour tomorrow! Don't forget to check "
                    "what questions you wanted to ask - I know you had a whole list of must-haves."
                ),
            ).delayed(8)

            # Oracle: Agent lists saved apartments to get Lakeview details
            list_saved_event = (
                apartment_app.list_saved_apartments()
                .oracle()
                .depends_on([tour_confirmation_event, friend_message_event], delay_seconds=2)
            )

            # Oracle: Agent proposes creating tour prep checklist
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "I saw your Lakeview Plaza tour confirmation for tomorrow at 10 AM. "
                        "They asked you to bring photo ID and proof of income. Alex also reminded you "
                        "about your apartment must-haves. Would you like me to create a tour prep "
                        "checklist with the required documents, questions based on your priorities, "
                        "and reply to confirm your attendance?"
                    )
                )
                .oracle()
                .depends_on(list_saved_event, delay_seconds=2)
            )

            # Oracle: User accepts
            acceptance_event = (
                aui.accept_proposal(content="Yes, please create the checklist and send a confirmation reply.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle: Agent creates tour prep note
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
                        "- Proof of income (recent pay stubs)\n\n"
                        "Questions to Ask (from your must-haves):\n"
                        "- Confirm cat policy details (deposit, restrictions)\n"
                        "- Check natural light in bedroom (window orientation)\n"
                        "- Verify commute time to 450 Market St\n"
                        "- Inspect washer/dryer condition\n\n"
                        "Property Summary:\n"
                        "- Rent: $1750/month (within $1800 budget)\n"
                        "- Amenities: Washer/Dryer in-unit, Large windows, Parking, Gym\n"
                        "- Pet Policy: Cats allowed"
                    ),
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle: Agent replies to leasing office
            reply_event = (
                messaging_app.send_message(
                    user_id=self.leasing_office_id,
                    content="Thank you for confirming! I'll be there tomorrow at 10 AM with my photo ID and proof of income. Could you please send parking instructions? Looking forward to the tour!",
                )
                .oracle()
                .depends_on(create_note_event, delay_seconds=2)
            )

        self.events = [
            tour_confirmation_event,
            friend_message_event,
            list_saved_event,
            proposal_event,
            acceptance_event,
            create_note_event,
            reply_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent creates tour checklist and replies to leasing office."""
        try:
            log_entries = env.event_log.list_view()

            # Essential outcome 1: Agent sent proposal to user
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "tour" in e.action.args.get("content", "").lower()
                for e in log_entries
            )

            # Essential outcome 2: Agent created tour prep note in Personal folder
            # Check that note includes required documents AND apartment must-haves
            note_created = False
            note_includes_documents = False
            note_includes_priorities = False
            for e in log_entries:
                if (
                    e.event_type == EventType.AGENT
                    and isinstance(e.action, Action)
                    and e.action.class_name == "StatefulNotesApp"
                    and e.action.function_name == "create_note"
                    and e.action.args.get("folder") == "Personal"
                ):
                    note_created = True
                    note_content = e.action.args.get("content", "").lower()
                    # Check for required documents (photo ID and proof of income)
                    has_id = "id" in note_content or "identification" in note_content
                    has_income = "income" in note_content or "pay stub" in note_content
                    note_includes_documents = has_id and has_income
                    # Check for apartment must-haves (washer/dryer, light, pet/cat, commute/office)
                    has_washer = "washer" in note_content or "dryer" in note_content
                    has_light = "light" in note_content or "window" in note_content
                    has_pet = "pet" in note_content or "cat" in note_content
                    has_commute = "commute" in note_content or "market" in note_content
                    # Require at least 2 of the priorities to be mentioned
                    priorities_mentioned = sum([has_washer, has_light, has_pet, has_commute])
                    note_includes_priorities = priorities_mentioned >= 2
                    break

            # Essential outcome 3: Agent replied to leasing office
            reply_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == self.leasing_office_id
                for e in log_entries
            )

            success = (
                proposal_found and note_created and note_includes_documents and note_includes_priorities and reply_sent
            )

            if not success:
                missing = []
                if not proposal_found:
                    missing.append("proposal about tour prep")
                if not note_created:
                    missing.append("tour prep note in Personal folder")
                elif not note_includes_documents:
                    missing.append("note missing required documents (photo ID and proof of income)")
                elif not note_includes_priorities:
                    missing.append(
                        "note missing apartment must-haves (need at least 2 of: washer/dryer, light/windows, pet/cat, commute)"
                    )
                if not reply_sent:
                    missing.append("reply to leasing office")
                rationale = f"Missing: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
