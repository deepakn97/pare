"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
)
from pas.apps.apartment import StatefulApartmentApp
from pas.apps.note import Note, StatefulNotesApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("apartment_price_update_sync")
class ApartmentPriceUpdateSync(PASScenario):
    """Agent updates existing apartment tour notes when saved apartment pricing changes. The user has previously toured Oakwood Terrace, saved it to their favorites in the Apartment app, and created detailed tour notes in the Notes app under the "Personal" folder documenting impressions, amenities, and the original price of $1,800/month. A notification arrives indicating that Oakwood Terrace's rental price has been updated to $1,650/month. The agent must: 1. Detect the apartment price update notification and extract the apartment identifier and new price, 2. Search saved apartments to confirm the apartment is still in the user's favorites, 3. Search notes to locate the corresponding tour documentation by apartment name, 4. Update the existing note to reflect the new pricing information while preserving original tour observations, 5. Notify the user of the price drop in context of their apartment search.

    This scenario exercises cross-app data synchronization (apartment updates → notes updates), information freshness maintenance, price-change detection and alerting, and contextual note editing that preserves user-authored content while integrating new system-provided data..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Apartment App
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Initialize Notes App
        self.note = StatefulNotesApp(name="Notes")

        # Populate Apartment App with baseline data
        # Add Oakwood Terrace apartment to the catalog with initial price $1,800/month
        self.oakwood_id = self.apartment.add_new_apartment(
            name="Oakwood Terrace",
            location="Downtown District",
            zip_code="93101",
            price=1800.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1050,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="3rd floor",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Parking", "Gym", "Pool", "Laundry in unit"],
        )

        # User has saved Oakwood Terrace to favorites (pre-existing state)
        self.apartment.save_apartment(self.oakwood_id)

        # Populate Notes App with baseline data
        # Create a detailed tour note in the Personal folder documenting the apartment
        # with the original $1,800/month price (created 3 days ago)
        oakwood_note = Note(
            note_id="",
            title="Oakwood Terrace Tour",
            content="""Toured Oakwood Terrace on November 15, 2025.

Location: Downtown District (93101)
Price: $1,800/month
Bedrooms: 2 | Bathrooms: 2 | Size: 1,050 sq ft

Amenities:
- Parking included
- Gym access
- Pool
- In-unit laundry

Impressions:
- Great natural light in living room
- Modern finishes and appliances
- Close to public transit and restaurants
- Building manager seemed responsive and professional

Overall: Strong candidate. Price is within budget. Would like to revisit if anything changes.""",
            pinned=False,
            created_at=datetime(2025, 11, 15, 14, 30, 0, tzinfo=UTC).timestamp(),
            updated_at=datetime(2025, 11, 15, 14, 30, 0, tzinfo=UTC).timestamp(),
        )
        self.note.folders["Personal"].add_note(oakwood_note)
        # Store the note ID (Note.__post_init__ generates it if empty)
        self.oakwood_note_id = oakwood_note.note_id

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.apartment, self.note]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Apartment price update notification
            # Oakwood Terrace price drops from $1,800 to $1,650
            price_update_event = apartment_app.update_apartment(apartment_id=self.oakwood_id, new_price=1650.0).delayed(
                1
            )

            # Oracle Event 1: Agent lists saved apartments to identify which one was updated
            # Motivated by: price update notification from apartment app (environment event)
            list_saved_event = (
                apartment_app.list_saved_apartments().oracle().depends_on(price_update_event, delay_seconds=2)
            )

            # Oracle Event 2: Agent gets apartment details to confirm name and new price
            # Motivated by: need to identify which saved apartment matches the update notification
            get_details_event = (
                apartment_app.get_apartment_details(apartment_id=self.oakwood_id)
                .oracle()
                .depends_on(list_saved_event, delay_seconds=1)
            )

            # Oracle Event 3: Agent searches notes for "Oakwood Terrace" to find corresponding tour note
            # Motivated by: apartment details revealed the name "Oakwood Terrace" from prior oracle call
            search_notes_event = (
                note_app.search_notes(query="Oakwood Terrace").oracle().depends_on(get_details_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent sends proposal to user about the price drop
            # Motivated by: detected price update notification showing Oakwood Terrace dropped to $1,650
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed that Oakwood Terrace, one of your saved apartments, has a price update. The rent dropped from $1,800 to $1,650/month (an $150 decrease). Would you like me to update your tour notes to reflect this new pricing?"
                )
                .oracle()
                .depends_on(search_notes_event, delay_seconds=2)
            )

            # Oracle Event 5: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please update the notes with the new price.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event 6: Agent retrieves the note by ID to prepare for update
            # Motivated by: search results from earlier search_notes call revealed the note
            get_note_event = (
                note_app.get_note_by_id(note_id=self.oakwood_note_id)
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 7: Agent updates the note content with new pricing
            # Motivated by: user accepted proposal, and prior get_note_by_id revealed current note content
            update_note_event = (
                note_app.update_note(
                    note_id=self.oakwood_note_id,
                    content="""Toured Oakwood Terrace on November 15, 2025.

Location: Downtown District (93101)
Price: $1,650/month (UPDATED - was $1,800/month, reduced by $150)
Bedrooms: 2 | Bathrooms: 2 | Size: 1,050 sq ft

Amenities:
- Parking included
- Gym access
- Pool
- In-unit laundry

Impressions:
- Great natural light in living room
- Modern finishes and appliances
- Close to public transit and restaurants
- Building manager seemed responsive and professional

Overall: Strong candidate. Price is now well within budget after reduction. Would like to revisit if anything changes.""",
                )
                .oracle()
                .depends_on(get_note_event, delay_seconds=2)
            )

            # Oracle Event 8: Agent sends summary confirmation to user
            # Motivated by: successful completion of note update per user's acceptance
            summary_event = (
                aui.send_message_to_user(
                    content="Done! I've updated your Oakwood Terrace tour notes to reflect the new $1,650/month price (down from $1,800)."
                )
                .oracle()
                .depends_on(update_note_event, delay_seconds=1)
            )

        # Register ALL events
        self.events = [
            price_update_event,
            list_saved_event,
            get_details_event,
            search_notes_event,
            proposal_event,
            acceptance_event,
            get_note_event,
            update_note_event,
            summary_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent sent a proposal to the user about the price update
            # The proposal must mention Oakwood Terrace and reference the price drop
            # We accept that the exact wording may vary, but key elements must be present
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 2: Agent queried saved apartments or apartment details
            # This proves the agent detected and investigated the apartment update
            # We accept either list_saved_apartments OR get_apartment_details OR list_all_apartments as equivalent
            apartment_query_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulApartmentApp"
                and e.action.function_name in ["list_all_apartments", "list_saved_apartments", "get_apartment_details"]
                for e in log_entries
            )

            # STRICT Check 3: Agent searched notes to locate the corresponding tour note
            # This proves cross-app coordination (apartment → notes)
            notes_search_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "search_notes"
                for e in log_entries
            )

            # STRICT Check 4: Agent updated the note with new pricing information
            # Must verify the note was actually modified, and the new price $1,650 appears
            note_update_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "update_note"
                and e.action.args.get("note_id") == self.oakwood_note_id
                and (
                    "1,650" in str(e.action.args.get("content", "")) or "1650" in str(e.action.args.get("content", ""))
                )
                for e in log_entries
            )

            # All critical checks must pass for success
            success = proposal_found and apartment_query_found and notes_search_found and note_update_found

            # Generate rationale if validation fails
            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal about Oakwood Terrace price update")
                if not apartment_query_found:
                    missing_checks.append("apartment query (list_saved_apartments or get_apartment_details)")
                if not notes_search_found:
                    missing_checks.append("notes search for 'Oakwood Terrace'")
                if not note_update_found:
                    missing_checks.append("note update with new $1,650 pricing")

                rationale = f"Missing critical agent actions: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
