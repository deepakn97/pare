"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulApartmentApp,
    StatefulCalendarApp,
    StatefulEmailApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("apartment_viewing_schedule_conflict")
class ApartmentViewingScheduleConflict(PASScenario):
    """Agent resolves scheduling conflicts for apartment viewing appointments by proposing alternative times and coordinating with property managers.

    The user has saved three apartments to favorites and has existing calendar commitments including a "Team Standup" meeting on Thursday from 10:00 AM to 10:30 AM and a "Doctor Appointment" on Friday from 2:00 PM to 3:00 PM. The user receives email confirmations from two property managers scheduling apartment viewings: one for "Riverside Lofts Unit 3B" on Thursday at 10:00 AM, and another for "Downtown Studio 205" on Friday at 2:30 PM. The agent must:
    1. Parse the viewing appointment times and apartment names from the incoming emails
    2. Check the calendar to identify conflicts with existing events
    3. Search the saved apartments list to retrieve full details for each apartment (location, property manager contact)
    4. Propose rescheduling the conflicting viewings to the user
    5. After user acceptance, reply to each property manager email requesting alternative times (e.g., Thursday 11:00 AM, Friday 4:00 PM)
    6. Add placeholder calendar events for the proposed new viewing times

    This scenario exercises multi-event conflict detection across calendar domains (work vs. personal vs. apartment hunting), information synthesis from saved apartment records, batch scheduling coordination via email replies, and proactive time management when the user has not yet noticed the overlaps.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.apartment = StatefulApartmentApp(name="Apartment")
        self.email = StatefulEmailApp(name="Emails")
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Populate apartment app with saved apartments
        # The user is actively apartment hunting and has saved three apartments to favorites
        apt1_id = self.apartment.add_new_apartment(
            name="Riverside Lofts Unit 3B",
            location="123 River Street, Downtown",
            zip_code="90210",
            price=2200.0,
            number_of_bedrooms=2,
            number_of_bathrooms=1,
            square_footage=950,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Gym", "Parking", "River view"],
        )
        self.apartment.save_apartment(apt1_id)

        apt2_id = self.apartment.add_new_apartment(
            name="Downtown Studio 205",
            location="456 Main Avenue, City Center",
            zip_code="90211",
            price=1800.0,
            number_of_bedrooms=1,
            number_of_bathrooms=1,
            square_footage=650,
            property_type="Studio",
            furnished_status="Furnished",
            floor_level="Ground floor",
            pet_policy="No pets",
            lease_term="6 months",
            amenities=["Laundry", "24/7 Security"],
        )
        self.apartment.save_apartment(apt2_id)

        apt3_id = self.apartment.add_new_apartment(
            name="Garden View Apartments Unit 12",
            location="789 Oak Boulevard, Suburbs",
            zip_code="90212",
            price=2500.0,
            number_of_bedrooms=3,
            number_of_bathrooms=2,
            square_footage=1200,
            property_type="Apartment",
            furnished_status="Semi-furnished",
            floor_level="Ground floor",
            pet_policy="Pets allowed",
            lease_term="1 year",
            amenities=["Pool", "Garden", "Parking", "Playground"],
        )
        self.apartment.save_apartment(apt3_id)

        # Populate calendar app with existing commitments
        # Thursday Nov 20, 2025 at 10:00 AM - 10:30 AM: Team Standup (work)
        self.calendar.add_calendar_event(
            title="Team Standup",
            start_datetime="2025-11-20 10:00:00",
            end_datetime="2025-11-20 10:30:00",
            tag="Work",
            description="Weekly team sync meeting",
            location="Conference Room A",
            attendees=["User", "Alice Johnson", "Bob Smith"],
        )

        # Friday Nov 21, 2025 at 2:00 PM - 3:00 PM: Doctor Appointment (personal)
        self.calendar.add_calendar_event(
            title="Doctor Appointment",
            start_datetime="2025-11-21 14:00:00",
            end_datetime="2025-11-21 15:00:00",
            tag="Personal",
            description="Annual checkup with Dr. Martinez",
            location="HealthCare Clinic",
            attendees=["User"],
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.apartment, self.email, self.calendar]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Property manager for Riverside Lofts sends viewing confirmation for Thursday 10:00 AM
            email1_event = email_app.send_email_to_user_with_id(
                email_id="email-riverside-viewing",
                sender="manager@riverside-lofts.com",
                subject="Viewing Appointment Confirmation - Riverside Lofts Unit 3B",
                content="Thank you for your interest in Riverside Lofts Unit 3B! Your viewing appointment is confirmed for Thursday, November 20th at 10:00 AM. Please meet us at the lobby at 123 River Street. Looking forward to showing you the apartment!",
            ).delayed(5)

            # Environment Event 2: Property manager for Downtown Studio sends viewing confirmation for Friday 2:30 PM
            email2_event = email_app.send_email_to_user_with_id(
                email_id="email-downtown-viewing",
                sender="leasing@downtown-realty.com",
                subject="Apartment Viewing Scheduled - Downtown Studio 205",
                content="Hi! This confirms your viewing appointment for Downtown Studio 205 on Friday, November 21st at 2:30 PM. The address is 456 Main Avenue, City Center. We'll give you a complete tour of the unit and amenities. See you then!",
            ).delayed(10)

            # Oracle Event 1: Agent reads first viewing confirmation email (motivated by email1_event notification)
            read_email1 = (
                email_app.get_email_by_id(
                    email_id="email-riverside-viewing",
                    folder_name="INBOX",
                )
                .oracle()
                .depends_on(email1_event, delay_seconds=2)
            )

            # Oracle Event 2: Agent checks calendar for Thursday 10:00 AM conflict (motivated by viewing time mentioned in email1)
            check_thursday = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-20 10:00:00",
                    end_datetime="2025-11-20 10:30:00",
                )
                .oracle()
                .depends_on(read_email1, delay_seconds=1)
            )

            # Oracle Event 3: Agent reads second viewing confirmation email (motivated by email2_event notification)
            read_email2 = (
                email_app.get_email_by_id(
                    email_id="email-downtown-viewing",
                    folder_name="INBOX",
                )
                .oracle()
                .depends_on(email2_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent checks calendar for Friday 2:30 PM conflict (motivated by viewing time mentioned in email2)
            check_friday = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-21 14:00:00",
                    end_datetime="2025-11-21 15:00:00",
                )
                .oracle()
                .depends_on(read_email2, delay_seconds=1)
            )

            # Oracle Event 5: Agent lists saved apartments to gather full details (motivated by apartment names in emails)
            list_saved = (
                apartment_app.list_saved_apartments()
                .oracle()
                .depends_on([check_thursday, check_friday], delay_seconds=1)
            )

            # Oracle Event 6: Agent sends proposal to user (motivated by detected conflicts from check_thursday and check_friday)
            proposal_event = (
                aui.send_message_to_user(
                    content="I received apartment viewing confirmations that conflict with your existing schedule:\n\n1. Riverside Lofts Unit 3B viewing on Thursday Nov 20 at 10:00 AM conflicts with your Team Standup (10:00-10:30 AM)\n2. Downtown Studio 205 viewing on Friday Nov 21 at 2:30 PM conflicts with your Doctor Appointment (2:00-3:00 PM)\n\nWould you like me to reschedule both viewings to alternative times?"
                )
                .oracle()
                .depends_on(list_saved, delay_seconds=2)
            )

            # Oracle Event 7: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please reschedule both viewings and ask the property managers.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event 8: Agent checks Thursday 11:00 AM availability (motivated by need to find alternative after acceptance)
            check_thursday_alt = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-20 11:00:00",
                    end_datetime="2025-11-20 12:00:00",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 9: Agent checks Friday 4:00 PM availability (motivated by need to find alternative after acceptance)
            check_friday_alt = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-21 16:00:00",
                    end_datetime="2025-11-21 17:00:00",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 10: Agent replies to Riverside Lofts manager requesting reschedule (motivated by acceptance and confirmed alternative time)
            reply_riverside = (
                email_app.reply_to_email(
                    email_id="email-riverside-viewing",
                    folder_name="INBOX",
                    content="Thank you for scheduling the viewing. Unfortunately, I have a conflict at 10:00 AM on Thursday. Could we reschedule to 11:00 AM on the same day instead? Please let me know if that works.",
                )
                .oracle()
                .depends_on(check_thursday_alt, delay_seconds=2)
            )

            # Oracle Event 11: Agent replies to Downtown Studio manager requesting reschedule (motivated by acceptance and confirmed alternative time)
            reply_downtown = (
                email_app.reply_to_email(
                    email_id="email-downtown-viewing",
                    folder_name="INBOX",
                    content="Hi! I have a prior commitment at 2:30 PM on Friday. Would it be possible to move the viewing to 4:00 PM on the same day? I'm very interested in seeing the unit. Thanks!",
                )
                .oracle()
                .depends_on(check_friday_alt, delay_seconds=2)
            )

        # Register ALL events
        self.events = [
            email1_event,
            email2_event,
            read_email1,
            check_thursday,
            read_email2,
            check_friday,
            list_saved,
            proposal_event,
            acceptance_event,
            check_thursday_alt,
            check_friday_alt,
            reply_riverside,
            reply_downtown,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()
            agent_entries = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent sent proposal mentioning both viewing conflicts
            proposal_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name in ["send_message_to_user", "propose_task"]
                for e in agent_entries
            )

            # STRICT Check 2: Agent checked calendar for conflict detection (Thursday 10:00 AM range)
            # This is the original viewing time that conflicts with Team Standup
            thursday_check_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name in ["get_calendar_events_from_to", "list_calendar_events", "search_events"]
                and "2025-11-20" in str(e.action.args.get("start_datetime", ""))
                for e in agent_entries
            )

            # STRICT Check 3: Agent checked calendar for conflict detection (Friday 2:00-3:00 PM range)
            # This is the time when the Doctor Appointment occurs that conflicts with the 2:30 PM viewing
            friday_check_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name in ["get_calendar_events_from_to", "list_calendar_events", "search_events"]
                and ("2025-11-21" in str(e.action.args.get("start_datetime", "")))
                for e in agent_entries
            )

            # STRICT Check 4: Agent replied to Riverside Lofts property manager
            # Accept reply_to_email OR an equivalent outbound email action.
            riverside_reply_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name in ["reply_to_email", "send_email", "send_batch_email"]
                and (
                    e.action.args.get("email_id") == "email-riverside-viewing"
                    or "riverside-lofts.com" in str(e.action.args.get("recipients", [])).lower()
                )
                for e in agent_entries
            )

            # STRICT Check 5: Agent replied to Downtown Studio property manager
            downtown_reply_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name in ["reply_to_email", "send_email", "send_batch_email"]
                and (
                    e.action.args.get("email_id") == "email-downtown-viewing"
                    or "downtown-realty.com" in str(e.action.args.get("recipients", [])).lower()
                )
                for e in agent_entries
            )

            # Build rationale for failures
            missing_checks = []
            if not proposal_found:
                missing_checks.append("agent proposal mentioning both conflicts")
            if not thursday_check_found:
                missing_checks.append("Thursday 10:00 AM calendar check")
            if not friday_check_found:
                missing_checks.append("Friday 2:00-3:00 PM calendar check")
            if not riverside_reply_found:
                missing_checks.append("email reply to Riverside Lofts manager")
            if not downtown_reply_found:
                missing_checks.append("email reply to Downtown Studio manager")

            success = (
                proposal_found
                and thursday_check_found
                and friday_check_found
                and riverside_reply_found
                and downtown_reply_found
            )

            rationale = (
                "All validation checks passed" if success else f"Missing critical checks: {', '.join(missing_checks)}"
            )

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
