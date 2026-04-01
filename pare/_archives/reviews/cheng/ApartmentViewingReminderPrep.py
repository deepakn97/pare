"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.apartment_listing import Apartment
from are.simulation.apps.calendar import CalendarEvent
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulApartmentApp,
    StatefulCalendarApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("apartment_viewing_reminder_prep")
class ApartmentViewingReminderPrep(PASScenario):
    """Agent prepares user for upcoming apartment viewing by aggregating details from saved listings and calendar event.

    The user has a calendar event scheduled titled "Apartment Viewing at Riverside Lofts" for tomorrow at 3:00 PM with location "1250 River Street". The user also has this same apartment saved in their favorites within the apartment app. Shortly before the viewing, a calendar notification arrives reminding the user about the appointment. The agent must:
    1. Detect the upcoming apartment viewing reminder from the calendar
    2. Extract the property name ("Riverside Lofts") from the calendar event title
    3. Search the saved apartments list to locate the matching listing by name
    4. Retrieve full apartment details (price, bedrooms, amenities, contact info) from the apartment app
    5. Propose sending a preparation summary to the user that combines calendar timing/location with apartment specifications
    6. Upon acceptance, update the calendar event description to include key apartment details (price, bedrooms, amenities) so the user has everything in one place during the viewing

    This scenario exercises calendar-triggered proactive assistance, cross-app data enrichment (calendar metadata → apartment lookup → calendar augmentation), string-based matching between calendar event titles and apartment names, and contextual information synthesis to improve user preparation for time-sensitive appointments..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data.

        Baseline data:
        - Calendar: Event "Apartment Viewing at Riverside Lofts" scheduled for tomorrow (Nov 19, 2025) at 3:00 PM
          at location "1250 River Street"
        - Apartment: Riverside Lofts saved in favorites with full details (price, bedrooms, amenities)

        Note: The calendar notification that triggers the agent will be created as an early environment event
        in Step 3, not seeded here, so the agent can observe it arriving.
        """
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize calendar app
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Add the viewing appointment scheduled for tomorrow at 3:00 PM
        viewing_event = CalendarEvent(
            title="Apartment Viewing at Riverside Lofts",
            start_datetime=datetime(2025, 11, 19, 15, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 11, 19, 16, 0, 0, tzinfo=UTC).timestamp(),
            location="1250 River Street",
            description="Viewing appointment for Riverside Lofts apartment",
        )
        self.calendar.set_calendar_event(viewing_event)

        # Initialize apartment app
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Add Riverside Lofts apartment to the catalog and save it to favorites
        riverside_apt = Apartment(
            name="Riverside Lofts",
            location="Downtown",
            zip_code="93101",
            price=2800.0,
            bedrooms=2,
            bathrooms=2,
            property_type="Apartment",
            square_footage=1200,
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Gym", "Pool", "Parking", "Balcony"],
            apartment_id="riverside_lofts_001",
        )
        self.apartment.apartments[riverside_apt.apartment_id] = riverside_apt
        self.apartment.save_apartment(riverside_apt.apartment_id)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.calendar, self.apartment]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")

        with EventRegisterer.capture_mode():
            # Event 1: Leasing office adds a viewing confirmation to user's calendar (environment event)
            # This serves as the notification trigger that reminds the user about the upcoming viewing
            viewing_confirmation_event = calendar_app.add_calendar_event_by_attendee(
                who_add="Riverside Lofts Leasing Office",
                title="Confirmed: Apartment Viewing at Riverside Lofts",
                start_datetime="2025-11-19 15:00:00",
                end_datetime="2025-11-19 16:00:00",
                location="1250 River Street",
                description="Your viewing appointment has been confirmed. Please arrive 5 minutes early.",
            ).delayed(15)

            # Agent observes the calendar event notification mentioning "Riverside Lofts" and decides to help prepare
            # Event 2: Agent retrieves the saved apartments to find the matching listing by name (oracle)
            list_saved_event = (
                apartment_app.list_saved_apartments().oracle().depends_on(viewing_confirmation_event, delay_seconds=3)
            )

            # Agent now has the apartment_id from the list_saved_apartments result
            # Event 3: Agent retrieves full apartment details for the saved Riverside Lofts listing (oracle)
            get_details_event = (
                apartment_app.get_apartment_details(apartment_id="riverside_lofts_001")
                .oracle()
                .depends_on(list_saved_event, delay_seconds=2)
            )

            # Agent now has all the apartment details and calendar info
            # Event 4: Agent proposes to prepare a summary and enrich the calendar event (oracle)
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed you have an apartment viewing at Riverside Lofts tomorrow at 3:00 PM (1250 River Street). I found this apartment in your saved favorites. Would you like me to add the key details (2BR/2BA, $2,800/month, 1200 sqft, amenities: Gym, Pool, Parking, Balcony) to your calendar event so you have all the information handy during your visit?"
                )
                .oracle()
                .depends_on(get_details_event, delay_seconds=3)
            )

            # Event 5: User accepts the proposal (oracle)
            acceptance_event = (
                aui.accept_proposal(content="Yes, please add those details to the calendar event.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=5)
            )

            # Agent needs to find the calendar event to edit it
            # Event 6: Agent retrieves calendar events for the viewing time to get the event_id (oracle)
            get_calendar_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-19 14:00:00",
                    end_datetime="2025-11-19 17:00:00",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Event 7: Agent updates the calendar event with apartment details (oracle)
            # Note: In a real scenario, the agent would extract the event_id from get_calendar_event results
            # Here we use the event_id from the seeded data (the first viewing event)
            # The agent would identify the correct event by matching "Riverside Lofts" in the title
            edit_calendar_event = (
                calendar_app.edit_calendar_event(
                    event_id=next(iter(calendar_app.events.keys())),  # First event (the original viewing appointment)
                    description="Viewing appointment for Riverside Lofts apartment\n\nApartment Details:\n- Price: $2,800/month\n- Bedrooms: 2\n- Bathrooms: 2\n- Square Footage: 1200 sqft\n- Amenities: Gym, Pool, Parking, Balcony\n- Pet Policy: Cats allowed\n- Lease Term: 1 year",
                )
                .oracle()
                .depends_on(get_calendar_event, delay_seconds=2)
            )

        # Register ALL events
        self.events = [
            viewing_confirmation_event,
            list_saved_event,
            get_details_event,
            proposal_event,
            acceptance_event,
            get_calendar_event,
            edit_calendar_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only agent/oracle events (EventType.AGENT)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent listed saved apartments to find Riverside Lofts
            list_saved_found = any(
                e.action.class_name == "StatefulApartmentApp" and e.action.function_name == "list_saved_apartments"
                for e in agent_events
            )

            # STRICT Check 2: Agent retrieved apartment details for the specific apartment
            # The apartment_id should be present and non-empty
            get_details_found = any(
                e.action.class_name == "StatefulApartmentApp"
                and e.action.function_name == "get_apartment_details"
                and e.action.args.get("apartment_id")  # Must have an apartment_id
                for e in agent_events
            )

            # STRICT Check 3: Agent sent a proposal message to the user
            # Content is flexible; we only check that the tool was called
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 4: Agent queried the calendar to locate the viewing event
            # Accept either get_calendar_events_from_to or similar query functions
            get_calendar_found = any(
                e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name in ["get_calendar_events_from_to", "get_calendar_event"]
                for e in agent_events
            )

            # STRICT Check 5: Agent updated the calendar event with apartment details
            # The event_id and description should be present
            edit_calendar_found = any(
                e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "edit_calendar_event"
                and e.action.args.get("event_id")  # Must have an event_id
                and e.action.args.get("description")  # Must have a description
                for e in agent_events
            )

            # All strict checks must pass
            success = (
                list_saved_found and get_details_found and proposal_found and get_calendar_found and edit_calendar_found
            )

            # Build rationale for failure
            if not success:
                missing_checks = []
                if not list_saved_found:
                    missing_checks.append("list_saved_apartments not found")
                if not get_details_found:
                    missing_checks.append("get_apartment_details not found")
                if not proposal_found:
                    missing_checks.append("send_message_to_user proposal not found")
                if not get_calendar_found:
                    missing_checks.append("calendar query not found")
                if not edit_calendar_found:
                    missing_checks.append("edit_calendar_event not found")

                rationale = f"Missing critical checks: {', '.join(missing_checks)}"
            else:
                rationale = None

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
