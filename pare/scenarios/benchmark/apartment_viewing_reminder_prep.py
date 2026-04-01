from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.calendar import CalendarEvent
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulApartmentApp,
    StatefulCalendarApp,
)
from pare.apps.reminder import StatefulReminderApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("apartment_viewing_reminder_prep")
class ApartmentViewingReminderPrep(PAREScenario):
    """Agent prepares user for upcoming apartment viewing by aggregating details from saved listings and calendar event.

    The user has a calendar event scheduled titled "Apartment Viewing at Riverside Lofts" for tomorrow at 3:00 PM with location "1250 River Street". The user also has this same apartment saved in their favorites within the apartment app. The day before the viewing, a user-created reminder notification fires prompting them to review the saved listing details and add key specs (beds/baths, price, sqft, amenities) into the calendar event notes for easy reference during the tour. The agent must:
    1. Detect the reminder notification (time-driven; emitted automatically when the reminder is due)
    2. Extract the property name ("Riverside Lofts") from the calendar event title
    3. Search the saved apartments list to locate the matching listing by name (motivated by the reminder's suggestion)
    4. Retrieve full apartment details (price, bedrooms, amenities, contact info) from the apartment app
    5. Propose adding key apartment details into the calendar event notes so the user has everything in one place during the viewing
    6. Upon acceptance, update the calendar event description to include key apartment details (price, bedrooms, amenities)

    This scenario exercises reminder-triggered proactive assistance, cross-app data enrichment (calendar metadata → apartment lookup → calendar augmentation), string-based matching between calendar event titles and apartment names, and contextual information synthesis to improve user preparation for time-sensitive appointments..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data.

        Baseline data:
        - Calendar: Event "Apartment Viewing at Riverside Lofts" scheduled for tomorrow (Nov 19, 2025) at 3:00 PM
          at location "1250 River Street"
        - Apartment: Riverside Lofts saved in favorites with full details (price, bedrooms, amenities)

        Note: The reminder notification that triggers the agent is time-driven in the Reminders app. We seed
        a reminder due shortly after start_time so it will fire once the runner advances simulated time.
        """
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize calendar app
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.reminder = StatefulReminderApp(name="Reminders")

        # Add the viewing appointment scheduled for tomorrow at 3:00 PM
        viewing_event = CalendarEvent(
            title="Apartment Viewing at Riverside Lofts",
            start_datetime=datetime(2025, 11, 19, 15, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 11, 19, 16, 0, 0, tzinfo=UTC).timestamp(),
            location="1250 River Street",
            description="Viewing appointment for Riverside Lofts apartment",
        )
        self.viewing_event_id = viewing_event.event_id
        self.calendar.set_calendar_event(viewing_event)

        # Initialize apartment app
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Add Riverside Lofts apartment to the catalog and save it to favorites via public APIs.
        self.riverside_lofts_id = self.apartment.add_new_apartment(
            name="Riverside Lofts",
            location="Downtown",
            zip_code="93101",
            price=2800.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1200,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Gym", "Pool", "Parking", "Balcony"],
        )
        self.apartment.save_apartment(self.riverside_lofts_id)

        # Seed a time-driven reminder that will automatically notify the user+agent when due.
        # Following benchmark convention, set it shortly after start_time so it fires once the runner advances time.
        self.reminder.add_reminder(
            title="Prep for Riverside Lofts viewing",
            due_datetime="2025-11-18 09:01:00",
            description=(
                "Viewing tomorrow at 3:00 PM (1250 River Street). Before the tour, review the saved Riverside Lofts "
                "listing and add key specs (beds/baths, price, sqft, amenities) into the calendar event notes so can "
                "have them handy during the viewing."
            ),
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.calendar, self.reminder, self.apartment]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")

        with EventRegisterer.capture_mode():
            # NOTE: Reminder notifications are time-driven in the Reminders app.
            # The reminder seeded in init (`due_datetime="2025-11-18 09:01:00"`) will automatically notify user+agent.
            # The agent does NOT need to poll reminders; we model reaction time by delaying the first oracle action.

            # Agent observes the reminder notification about prepping for the viewing and decides to help prepare.
            # Event 1: Agent retrieves the saved apartments to find the matching listing by name (oracle)
            # Motivation: the reminder explicitly suggests reviewing the saved listing details.
            list_saved_event = apartment_app.list_saved_apartments().oracle().delayed(70)

            # Agent now has the apartment_id from the list_saved_apartments result
            # Event 3: Agent retrieves full apartment details for the saved Riverside Lofts listing (oracle)
            get_details_event = (
                apartment_app.get_apartment_details(apartment_id=self.riverside_lofts_id)
                .oracle()
                .depends_on(list_saved_event, delay_seconds=2)
            )

            # Agent now has all the apartment details and calendar info
            # Event 4: Agent proposes to prepare a summary and enrich the calendar event (oracle)
            # Motivation: the reminder explicitly suggests adding key specs into the event notes for the tour.
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed you have an apartment viewing at Riverside Lofts tomorrow at 3:00 PM (1250 River Street). Your reminder suggested adding key specs into the event notes so you have them handy during the tour. I found Riverside Lofts in your saved favorites—would you like me to add the key details (2BR/2BA, $2,800/month, 1200 sqft, amenities: Gym, Pool, Parking, Balcony) to your calendar event?"
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
            edit_calendar_event = (
                calendar_app.edit_calendar_event(
                    event_id=self.viewing_event_id,
                    description="Viewing appointment for Riverside Lofts apartment\n\nApartment Details:\n- Price: $2,800/month\n- Bedrooms: 2\n- Bathrooms: 2\n- Square Footage: 1200 sqft\n- Amenities: Gym, Pool, Parking, Balcony\n- Pet Policy: Cats allowed\n- Lease Term: 1 year",
                )
                .oracle()
                .depends_on(get_calendar_event, delay_seconds=2)
            )

        # Register ALL events
        self.events = [
            list_saved_event,
            get_details_event,
            proposal_event,
            acceptance_event,
            get_calendar_event,
            edit_calendar_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only agent/oracle events (EventType.AGENT)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent sent a proposal message to the user
            # Content is flexible; we only check that the tool was called
            proposal_found = any(
                e.action.class_name == "PAREAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 2: Agent updated the calendar event with apartment details
            # The event_id and description should be present
            edit_calendar_found = any(
                e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "edit_calendar_event"
                and e.action.args.get("event_id")  # Must have an event_id
                and e.action.args.get("description")  # Must have a description
                for e in agent_events
            )

            # All strict checks must pass
            success = proposal_found and edit_calendar_found

            # Build rationale for failure
            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("send_message_to_user proposal not found")
                if not edit_calendar_found:
                    missing_checks.append("edit_calendar_event not found")

                rationale = f"Missing critical checks: {', '.join(missing_checks)}"
            else:
                rationale = None

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
