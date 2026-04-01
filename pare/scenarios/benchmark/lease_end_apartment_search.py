from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulApartmentApp,
    StatefulCalendarApp,
    StatefulReminderApp,
)
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("lease_end_apartment_search")
class LeaseEndApartmentSearch(PAREScenario):
    """Agent asks permission to list apartments after a lease-end reminder, then summarizes options.

    The user has a calendar event titled "Current Lease Ends" scheduled for February 28th, 2026. A reminder notification arrives reminding the user that their lease expires in 30 days. The agent must:
    1. Detect the lease expiration reminder notification
    2. Retrieve the lease end event details from the calendar
    3. Proactively ask the user whether to list available apartments
    4. After user acceptance, list available apartments in the apartment app
    5. Summarize a few options with key details like neighborhood and pet policy

    This scenario exercises reminder-triggered proactive assistance, a permission-gated cross-app workflow (reminder → calendar → apartment listings), and concise synthesis of apartment attributes for user decision support.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Calendar app
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Initialize Reminder app
        self.reminder = StatefulReminderApp(name="Reminders")

        # Seed baseline calendar event: Current lease ends on February 28, 2026
        self.lease_end_event_id = self.calendar.add_calendar_event(
            title="Current Lease Ends",
            start_datetime="2026-02-28 09:00:00",
            end_datetime="2026-02-28 17:00:00",
            tag="personal",
            description="Last day of current apartment lease. Must move out by end of day.",
            location="Current Apartment",
        )

        # Initialize Apartment app
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Seed apartment listings available for March 2026 move-in
        # Apartment 1: Downtown studio
        self.apt1_id = self.apartment.add_new_apartment(
            name="Modern Downtown Studio",
            location="Downtown",
            zip_code="93101",
            price=1800.0,
            number_of_bedrooms=1,
            number_of_bathrooms=1,
            property_type="Apartment",
            square_footage=650,
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Gym", "Parking", "In-unit laundry"],
        )

        # Apartment 2: Suburban 2-bedroom
        self.apt2_id = self.apartment.add_new_apartment(
            name="Spacious Garden Apartment",
            location="Westside",
            zip_code="93105",
            price=2400.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            property_type="Apartment",
            square_footage=1100,
            furnished_status="Unfurnished",
            floor_level="Ground floor",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Pool", "Parking", "Balcony", "In-unit laundry"],
        )

        # Apartment 3: Affordable 1-bedroom
        self.apt3_id = self.apartment.add_new_apartment(
            name="Cozy Eastside Unit",
            location="Eastside",
            zip_code="93103",
            price=1500.0,
            number_of_bedrooms=1,
            number_of_bathrooms=1,
            property_type="Apartment",
            square_footage=750,
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="No pets",
            lease_term="1 year",
            amenities=["Parking", "Storage"],
        )

        # Apartment 4: Luxury option
        self.apt4_id = self.apartment.add_new_apartment(
            name="Executive Loft",
            location="Downtown",
            zip_code="93101",
            price=3200.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            property_type="Condo",
            square_footage=1400,
            furnished_status="Semi-furnished",
            floor_level="Penthouse",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Gym", "Pool", "Concierge", "Parking", "In-unit laundry", "Rooftop deck"],
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.calendar, self.apartment, self.reminder]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")

        with EventRegisterer.capture_mode():
            # Event 1: Reminder notification (environment event)
            # Simulates a 30-day reminder for lease ending
            reminder_event = reminder_app.add_reminder(
                title="Lease ending in 30 days",
                due_datetime="2026-01-29 09:00:00",
                description="Your current lease ends on February 28, 2026. Start looking for new apartments now to ensure smooth transition.",
            ).delayed(15)

            # Agent detects the reminder notification and retrieves the original lease end event from calendar
            get_lease_event = (
                calendar_app.get_calendar_event(event_id=self.lease_end_event_id)
                .oracle()
                .depends_on(reminder_event, delay_seconds=3)
            )

            # Agent asks user for permission BEFORE searching (searching is still an agent action, but user may not want it).
            # The proposal references the reminder as the trigger.
            proposal_event = (
                aui.send_message_to_user(
                    content="I received a reminder that your lease ends on February 28, 2026 (30 days away). Would you like me to list available apartments and summarize a few options for a March move-in?"
                )
                .oracle()
                .depends_on(get_lease_event, delay_seconds=2)
            )

            # User asks the agent to run the search.
            acceptance_event = (
                aui.accept_proposal(content="Yes, please search and summarize a few good options.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=5)
            )

            # Agent lists all apartments (now explicitly requested by the user).
            list_apartments_event = (
                apartment_app.list_all_apartments().oracle().depends_on(acceptance_event, delay_seconds=2)
            )

            # Agent summarizes key results to the user (no auto-saving; keep the scenario simple).
            summary_event = (
                aui.send_message_to_user(
                    content="I listed the available apartments and here are a few options with key details:\n"
                    "- Modern Downtown Studio — Downtown — $1,800 — 1BR/1BA — pet policy: Cats allowed\n"
                    "- Cozy Eastside Unit — Eastside — $1,500 — 1BR/1BA — pet policy: No pets\n"
                    "- Spacious Garden Apartment — Westside — $2,400 — 2BR/2BA — pet policy: Pets allowed\n"
                    "- Executive Loft — Downtown — $3,200 — 2BR/2BA (Condo) — pet policy: Pets allowed\n\n"
                )
                .oracle()
                .depends_on(list_apartments_event, delay_seconds=2)
            )

        # Register ALL events
        self.events = [
            reminder_event,
            get_lease_event,
            proposal_event,
            acceptance_event,
            list_apartments_event,
            summary_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT events for validation
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent retrieved lease end event details from calendar
            # The agent must check calendar to understand the lease end date
            lease_event_retrieved = any(
                e.action.class_name == "StatefulCalendarApp" and e.action.function_name == "get_calendar_event"
                for e in agent_events
            )

            # STRICT Check 2: Agent sent a proposal to ask permission to search
            proposal_found = any(
                e.action.class_name == "PAREAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 3: Agent listed apartments after user acceptance
            apartment_list_found = any(
                e.action.class_name == "StatefulApartmentApp" and e.action.function_name == "list_all_apartments"
                for e in agent_events
            )

            # STRICT Check 4: Agent summarized results to the user after searching
            # Ensure there are at least 2 messages (proposal + summary)
            user_messages = [
                e
                for e in agent_events
                if e.action.class_name == "PAREAgentUserInterface" and e.action.function_name == "send_message_to_user"
            ]
            summary_found = len(user_messages) >= 2

            # All critical checks must pass for success
            success = proposal_found and lease_event_retrieved and apartment_list_found and summary_found

            if not success:
                rationale_parts = []
                if not lease_event_retrieved:
                    rationale_parts.append("agent did not retrieve lease end calendar event")
                if not proposal_found:
                    rationale_parts.append("no agent proposal to user found")
                if not apartment_list_found:
                    rationale_parts.append("agent did not list apartments")
                if not summary_found:
                    rationale_parts.append("agent did not summarize search results to user")
                rationale = "; ".join(rationale_parts)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
