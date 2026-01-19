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


@register_scenario("apartment_comparison_decision_aid")
class ApartmentComparisonDecisionAid(PASScenario):
    """Agent synthesizes apartment comparison data to support user's final rental decision. The user has saved three apartments to their favorites (Oakwood Terrace, Riverside Lofts, and Sunset Meadows) and created individual tour notes in the "Personal" folder documenting each visit with details about pricing, amenities, neighborhood feel, and pet policy. After touring all three, the user receives a message notification from their property manager stating they must vacate their current unit by the end of next month, creating urgency for a decision. The property manager's message explicitly suggests reviewing the user's tour notes to decide quickly. The agent must: 1. Detect the move-out deadline notification, 2. Search the user's saved apartments to retrieve all favorited options, 3. Search notes to locate tour documentation, 4. Extract and compare key decision factors (price, pet-friendliness for their dog, commute-relevant location data, lease terms) across all three apartments, 5. Create a consolidated comparison note in the "Personal" folder presenting side-by-side analysis with a recommendation based on the user's documented priorities.

    This scenario exercises deadline-triggered decision support, multi-item data aggregation (saved apartments → tour notes), structured information extraction and synthesis, comparative analysis across user-authored content, and proactive recommendation generation to resolve time-sensitive housing decisions..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Notes App
        self.note = StatefulNotesApp(name="Notes")

        # Initialize Apartment App
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Initialize Messaging App
        self.messaging = StatefulMessagingApp(name="Messages")

        # Populate Apartment App with baseline data
        # Add three apartments that the user has toured and saved
        oakwood_id = self.apartment.add_new_apartment(
            name="Oakwood Terrace",
            location="Downtown",
            zip_code="93101",
            price=2400.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1100,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="3rd floor",
            pet_policy="Dogs allowed with deposit",
            lease_term="1 year",
            amenities=["Parking", "Gym", "Dog park", "In-unit laundry"],
        )

        riverside_id = self.apartment.add_new_apartment(
            name="Riverside Lofts",
            location="Eastside near River",
            zip_code="93103",
            price=2650.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1050,
            property_type="Loft",
            furnished_status="Unfurnished",
            floor_level="2nd floor",
            pet_policy="Small dogs under 30lbs allowed",
            lease_term="1 year",
            amenities=["River View", "Balcony", "Parking", "Walk to downtown"],
        )

        sunset_id = self.apartment.add_new_apartment(
            name="Sunset Meadows",
            location="Westside near park",
            zip_code="93105",
            price=2200.0,
            number_of_bedrooms=2,
            number_of_bathrooms=1,
            square_footage=1000,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Ground floor",
            pet_policy="No pets allowed",
            lease_term="1 year",
            amenities=["Garden access", "Parking", "Storage unit", "Quiet area"],
        )

        # User has saved all three apartments to favorites
        self.apartment.save_apartment(oakwood_id)
        self.apartment.save_apartment(riverside_id)
        self.apartment.save_apartment(sunset_id)

        # Populate Notes App with baseline data
        # User has created tour notes for each apartment in the "Personal" folder
        # Note for Oakwood Terrace - toured Nov 12
        self.oakwood_note_id = self.note.create_note_with_time(
            folder="Personal",
            title="Oakwood Terrace Tour Notes",
            content="""Tour Date: November 12, 2025

Price: $2400/month (within budget!)

Amenities & Features:
- Great gym facility on site
- Dog park specifically for residents - Bella would love this!
- In-unit washer/dryer included
- Covered parking spot
- 3rd floor unit with good natural light

Pet Policy: Dogs allowed with $300 deposit. Manager very friendly about pets.

Location:
- Downtown location - 10 min walk to my office
- Close to grocery stores and restaurants
- Some street noise on weekends but not too bad
- Good public transit access

Lease Terms: 1 year minimum, can renew month-to-month after

Overall Impression: Really liked this place. Modern finishes, pet-friendly, and great commute. Slightly above my ideal price but all the amenities included make it worthwhile.""",
            pinned=False,
            created_at="2025-11-12 15:30:00",
            updated_at="2025-11-12 15:30:00",
        )

        # Note for Riverside Lofts - toured Nov 14
        self.riverside_note_id = self.note.create_note_with_time(
            folder="Personal",
            title="Riverside Lofts Apartment Tour Notes",
            content="""Apartment Tour Date: November 14, 2025

Price: $2650/month (highest of my options)

Amenities & Features:
- Beautiful river view from balcony
- Lots of natural light, open floor plan
- Close to riverside walking trails
- Parking included
- 2 bathrooms which is nice

Pet Policy: Small dogs under 30 lbs allowed. Bella is 35 lbs so this could be a dealbreaker. Manager said "might be flexible" but not guaranteed.

Location:
- Eastside location near the river
- 20 min walk to office (bit far but along nice trail)
- Quieter neighborhood, more residential
- 10 min walk to grocery store

Lease Terms: 1 year lease required

Overall Impression: Love the aesthetic and views. Concerned about Bella being over the weight limit - need to follow up on this. Also furthest from work and most expensive.""",
            pinned=False,
            created_at="2025-11-14 11:00:00",
            updated_at="2025-11-14 11:00:00",
        )

        # Note for Sunset Meadows - toured Nov 16
        self.sunset_note_id = self.note.create_note_with_time(
            folder="Personal",
            title="Sunset Meadows Apartment Tour Notes",
            content="""Apartment Tour Date: November 16, 2025

Price: $2200/month (best price!)

Amenities & Features:
- Ground floor with garden access
- Quiet, peaceful complex
- Storage unit included
- Updated kitchen appliances
- Only 1 bathroom
- Community laundry room (no in-unit)

Pet Policy: NO PETS ALLOWED - this is a major issue for Bella.

Location:
- Westside near the park
- 25 min bus ride to office (no good walking route)
- Very quiet residential area
- A bit isolated, need car for groceries

Lease Terms: 1 year lease

Overall Impression: Great price and peaceful setting, but the no-pets policy is a deal-breaker. Also the commute would be tough without a car. Only toured this to keep options open but probably not viable with Bella.""",
            pinned=False,
            created_at="2025-11-16 14:00:00",
            updated_at="2025-11-16 14:00:00",
        )

        # Populate Messaging App with baseline data
        # Add property manager contact and create a conversation
        self.messaging.add_users(["Property Manager"])
        self.user_id = self.messaging.current_user_id
        self.property_manager_id = self.messaging.name_to_id["Property Manager"]
        self.pm_conversation = ConversationV2(participant_ids=[self.user_id, self.property_manager_id])
        self.messaging.add_conversation(self.pm_conversation)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.note, self.apartment, self.messaging]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")

        with EventRegisterer.capture_mode():
            # Environment event: Property manager sends move-out deadline notification
            # This is the exogenous trigger that creates urgency for apartment decision
            env_move_out_message = messaging_app.create_and_add_message(
                conversation_id=self.pm_conversation.conversation_id,
                sender_id=self.property_manager_id,
                content=(
                    "Hi Alex — this is your property manager. I wanted to give you a heads-up that your lease ends on "
                    "December 31, 2025, and the building is scheduled for major renovations immediately after that date. "
                    "Because of the construction schedule, we'll need you to fully move out by 12/31.\n\n"
                    "If you're deciding where to go next, it may help to review the apartments you've saved and any tour "
                    "notes you've taken (price, pet policy, commute, etc.) and make a quick pros/cons comparison so you can "
                    "choose in time.\n\n"
                    "Let me know if you have questions about move-out logistics or timing. Thanks."
                ),
            ).delayed(10)

            # Agent detects the move-out deadline in the message and recognizes the urgency to make an apartment decision
            # Agent reads the conversation to understand the move-out timeline
            oracle_read_conversation = (
                messaging_app.read_conversation(conversation_id=self.pm_conversation.conversation_id)
                .oracle()
                .depends_on(env_move_out_message, delay_seconds=3)
            )

            # Agent searches saved apartments to retrieve all favorited options
            # Motivation: the property manager message explicitly references reviewing the user's saved/favorited apartments list.
            oracle_list_saved = (
                apartment_app.list_saved_apartments().oracle().depends_on(oracle_read_conversation, delay_seconds=2)
            )

            # Agent searches notes to locate tour documentation for saved apartments
            # Motivation: the property manager message explicitly suggests reviewing the user's tour notes (Notes app) to decide quickly.
            oracle_search_notes = (
                note_app.search_notes(query="Apartment").oracle().depends_on(oracle_list_saved, delay_seconds=2)
            )

            # Agent sends proposal to create comparison analysis based on the move-out deadline message
            proposal = (
                aui.send_message_to_user(
                    content="I saw your property manager's message about needing to vacate by December 31st. They suggested reviewing your tour notes and making a side-by-side comparison to decide quickly. I also see you have 3 apartments saved with tour notes. Would you like me to create a comparison analysis to help you decide (pricing, pet policies for Bella, commute factors)?"
                )
                .oracle()
                .depends_on([env_move_out_message, oracle_search_notes], delay_seconds=3)
            )

            # User accepts the proposal
            user_accept = (
                aui.accept_proposal(content="Yes, please proceed.").oracle().depends_on(proposal, delay_seconds=5)
            )

            # Agent creates consolidated comparison note in Personal folder
            oracle_create_comparison = (
                note_app.create_note(
                    folder="Personal",
                    title="Apartment Decision Comparison",
                    content="""Apartment Comparison Analysis - Move-out Deadline: Dec 31, 2025

RECOMMENDATION: Oakwood Terrace is the best fit based on your priorities.

Key Decision Factors:

1. PET POLICY (Critical for Bella):
   ✓ Oakwood Terrace: Dogs allowed with $300 deposit - manager pet-friendly
   ⚠ Riverside Lofts: Small dogs under 30 lbs only (Bella is 35 lbs) - uncertain
   ✗ Sunset Meadows: NO PETS - deal-breaker

2. PRICE COMPARISON:
   - Sunset Meadows: $2,200/month (lowest, but not viable)
   - Oakwood Terrace: $2,400/month (within budget)
   - Riverside Lofts: $2,650/month (highest)

3. COMMUTE TO OFFICE:
   ✓ Oakwood Terrace: 10 min walk - best commute
   ~ Riverside Lofts: 20 min walk along trail - acceptable
   ✗ Sunset Meadows: 25 min bus ride - least convenient

4. AMENITIES:
   - Oakwood: Dog park, gym, in-unit laundry, parking
   - Riverside: River view, balcony, 2 bathrooms, parking
   - Sunset: Garden access, storage, 1 bathroom, community laundry

5. LEASE TERMS:
   All require 1-year minimum lease

RATIONALE:
Oakwood Terrace meets all your critical needs: accepts Bella without restrictions, excellent walkable commute, strong amenities including dog park, and reasonable price. Riverside Lofts has uncertainty around Bella's weight and is most expensive. Sunset Meadows is eliminated by no-pet policy.

Next Steps:
- Contact Oakwood Terrace to confirm availability
- Verify move-in timeline works with Dec 31 deadline
- Schedule lease signing""",
                )
                .oracle()
                .depends_on(user_accept, delay_seconds=5)
            )

        # Register ALL events here in self.events
        self.events = [
            env_move_out_message,
            oracle_read_conversation,
            oracle_list_saved,
            oracle_search_notes,
            proposal,
            user_accept,
            oracle_create_comparison,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to agent/oracle events only (no environment events)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent sent proposal referencing the move-out situation
            # The agent must proactively offer to create a comparison analysis
            # FLEXIBLE on exact wording, but must reference the deadline/message context
            proposal_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and e.action.args.get("content") is not None
                for e in agent_events
            )

            # STRICT Check 2: Agent created the comparison note in Personal folder
            # The agent must synthesize the findings into a comparison note
            # FLEXIBLE on exact content/title, STRICT on folder="Personal" and tool being create_note
            comparison_note_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "create_note"
                and e.action.args.get("title") is not None
                and e.action.args.get("content") is not None
                for e in agent_events
            )

            # All strict checks must pass for success
            success = proposal_sent and comparison_note_created

            if not success:
                # Build rationale for failure
                missing_checks = []
                if not proposal_sent:
                    missing_checks.append("no proposal message sent to user")
                if not comparison_note_created:
                    missing_checks.append("comparison note not created in Personal folder")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
