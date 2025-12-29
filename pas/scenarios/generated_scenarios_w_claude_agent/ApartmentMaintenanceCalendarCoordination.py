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
    StatefulEmailApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("apartment_maintenance_calendar_coordination")
class ApartmentMaintenanceCalendarCoordination(PASScenario):
    """Agent coordinates apartment maintenance access around user's work schedule and notifies building management of availability windows.

    The user lives in "Riverside Lofts - Unit 3B" (saved to favorites) and has a busy work schedule with calendar events including "Client Presentation" on Thursday January 16, 2025 from 9:00 AM to 11:00 AM and "Team Sprint Planning" from 2:00 PM to 4:00 PM. An email arrives from building management (maintenance@riversidefts.com) with subject "Required: Annual HVAC Inspection & Filter Replacement" stating that all units must schedule a 1-hour maintenance window within the next 5 business days, and the maintenance team is available weekdays 8 AM - 5 PM. The agent must:
    1. Parse the maintenance requirement email and extract the time constraints (within 5 days, weekday 8 AM - 5 PM, 1-hour duration)
    2. Search saved apartments to confirm the user's current residence (Riverside Lofts Unit 3B) and retrieve property manager contact information
    3. Query the calendar for the next 5 business days to identify conflicts and find available 1-hour windows during the maintenance team's working hours
    4. Propose to the user a specific maintenance window that avoids calendar conflicts (e.g., Friday 10 AM - 11 AM)
    5. After user acceptance, reply to the building management email confirming the selected time slot and unit number
    6. Add a "HVAC Maintenance - Stay Home" calendar event at the confirmed time with location set to the user's apartment address

    This scenario exercises cross-app workflow coordination (email trigger → apartment lookup → calendar availability analysis), constraint satisfaction across multiple time requirements, proactive scheduling that respects both external deadlines and personal commitments, and closing-the-loop communication with service providers using information synthesized from all three domain apps.
    """

    start_time = datetime(2025, 1, 13, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize apartment app
        self.apartment = StatefulApartmentApp(name="Apartment")

        # Seed user's current residence to favorites
        riverside_apt = Apartment(
            name="Riverside Lofts - Unit 3B",
            location="123 River Street, Downtown",
            zip_code="90001",
            price=2400.0,
            bedrooms=2,
            bathrooms=2,
            property_type="Apartment",
            square_footage=950,
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["In-unit laundry", "Parking", "Gym", "Central heating/AC"],
            apartment_id="riverside_3b_001",
        )
        self.apartment.apartments[riverside_apt.apartment_id] = riverside_apt
        self.apartment.save_apartment(riverside_apt.apartment_id)

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails")

        # Initialize calendar app
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Seed existing calendar events for the user's busy schedule
        # Thursday January 16, 2025: Client Presentation 9 AM - 11 AM
        client_presentation = CalendarEvent(
            event_id="event_client_pres_001",
            title="Client Presentation",
            start_datetime=datetime(2025, 1, 16, 9, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 1, 16, 11, 0, 0, tzinfo=UTC).timestamp(),
            tag="Work",
            description="Quarterly review presentation for key client",
            location="Conference Room A",
            attendees=["User", "Sarah Chen", "Michael Torres"],
        )
        self.calendar.set_calendar_event(client_presentation)

        # Thursday January 16, 2025: Team Sprint Planning 2 PM - 4 PM
        sprint_planning = CalendarEvent(
            event_id="event_sprint_plan_001",
            title="Team Sprint Planning",
            start_datetime=datetime(2025, 1, 16, 14, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 1, 16, 16, 0, 0, tzinfo=UTC).timestamp(),
            tag="Work",
            description="Sprint planning session for Q1 roadmap",
            location="Team Room B",
            attendees=["User", "Development Team"],
        )
        self.calendar.set_calendar_event(sprint_planning)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.apartment, self.email, self.calendar]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")

        with EventRegisterer.capture_mode():
            # Environment event: Building management sends HVAC maintenance requirement email
            maintenance_email = email_app.send_email_to_user_with_id(
                email_id="email_maintenance_req_001",
                sender="maintenance@riversidefts.com",
                subject="Required: Annual HVAC Inspection & Filter Replacement",
                content="""Dear Riverside Lofts Resident,

This is a reminder that annual HVAC system inspection and filter replacement is required for all units. Per your lease agreement, you must schedule a maintenance window within the next 5 business days (by Friday, January 17, 2025).

Maintenance Team Availability:
- Monday through Friday
- 8:00 AM to 5:00 PM
- Duration: 1 hour per unit

Please reply to this email with your preferred date and time slot, along with your unit number for our records.

Thank you for your cooperation.

Best regards,
Riverside Lofts Maintenance Team
maintenance@riversidefts.com""",
            )

            # Agent reads the maintenance email to understand requirements
            # Motivated by: the incoming email notification that just appeared
            agent_reads_email = (
                email_app.get_email_by_id(email_id="email_maintenance_req_001", folder_name="INBOX")
                .oracle()
                .depends_on(maintenance_email, delay_seconds=2)
            )

            # Agent retrieves saved apartment to get unit details and property info
            # Motivated by: email asks for unit number confirmation; agent needs to verify current residence details
            agent_lists_saved = (
                apartment_app.list_saved_apartments().oracle().depends_on(agent_reads_email, delay_seconds=3)
            )

            # Agent checks calendar for the next 5 business days to find conflicts
            # Motivated by: email specifies 5-day window and weekday 8 AM-5 PM availability; agent needs to find free slots
            agent_checks_calendar = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-01-13 08:00:00", end_datetime="2025-01-17 17:00:00", offset=0, limit=50
                )
                .oracle()
                .depends_on(agent_lists_saved, delay_seconds=5)
            )

            # Agent proposes a maintenance window that avoids the Thursday conflicts
            # Motivated by: email requested scheduling within 5 days; calendar shows Thursday conflicts; Friday 10-11 AM is free
            # Explicitly depends on the environment email trigger and agent investigation
            agent_proposal = (
                aui.send_message_to_user(
                    content="""I noticed you received a maintenance requirement email from Riverside Lofts management. They need to schedule an annual HVAC inspection within the next 5 business days (by Friday, January 17).

Based on your calendar, you have conflicts on Thursday, January 16 (Client Presentation 9-11 AM and Team Sprint Planning 2-4 PM).

I found an available window: **Friday, January 17, 2025, 10:00 AM - 11:00 AM**

Would you like me to:
1. Reply to the building management confirming this time slot
2. Add a calendar reminder for the maintenance visit
3. Include your unit number in the confirmation"""
                )
                .oracle()
                .depends_on([agent_checks_calendar], delay_seconds=3)
            )

            # User accepts the agent's proposal
            user_acceptance = (
                aui.accept_proposal(
                    content="Yes, please confirm Friday 10-11 AM and add the calendar event. Note that you can find my current apartment information from my saved apartment."
                )
                .oracle()
                .depends_on(agent_proposal, delay_seconds=5)
            )

            # Agent replies to the maintenance email confirming the selected time
            # Motivated by: user accepted the proposal; need to notify building management per email request
            agent_replies_email = (
                email_app.reply_to_email(
                    email_id="email_maintenance_req_001",
                    folder_name="INBOX",
                    content="""Hello,

I would like to schedule the annual HVAC inspection for:

Date: Friday, January 17, 2025
Time: 10:00 AM - 11:00 AM
Unit: 3B

Please confirm this appointment at your earliest convenience.

Thank you,
User""",
                )
                .oracle()
                .depends_on(user_acceptance, delay_seconds=3)
            )

            # Agent adds calendar event for the maintenance visit
            # Motivated by: user accepted proposal including calendar reminder; need to block the time and set location
            agent_adds_calendar = (
                calendar_app.add_calendar_event(
                    title="HVAC Maintenance - Stay Home",
                    start_datetime="2025-01-17 10:00:00",
                    end_datetime="2025-01-17 11:00:00",
                    description="Annual HVAC inspection and filter replacement by Riverside Lofts maintenance team",
                    location="123 River Street, Downtown - Unit 3B",
                    tag="Home",
                )
                .oracle()
                .depends_on(user_acceptance, delay_seconds=2)
            )

            # Agent confirms completion to user
            # Motivated by: both follow-up actions (email reply and calendar event) are complete
            agent_completion = (
                aui.send_message_to_user(
                    content="Done! I've confirmed Friday, January 17 at 10 AM with building management and added the maintenance appointment to your calendar."
                )
                .oracle()
                .depends_on([agent_replies_email, agent_adds_calendar], delay_seconds=2)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            maintenance_email,
            agent_reads_email,
            agent_lists_saved,
            agent_checks_calendar,
            agent_proposal,
            user_acceptance,
            agent_replies_email,
            agent_adds_calendar,
            agent_completion,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT events for validation
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent read the maintenance email
            agent_read_email = any(
                e.action.class_name == "StatefulEmailApp"
                and e.action.function_name in ["get_email_by_id", "list_emails"]
                and e.action.args.get("email_id") == "email_maintenance_req_001"
                for e in agent_events
            )

            # STRICT Check 2: Agent queried calendar for availability
            agent_checked_calendar = any(
                e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name in ["get_calendar_events_from_to", "list_calendar_events", "search_events"]
                for e in agent_events
            )

            # STRICT Check 3: Agent proposed maintenance window to user
            # Accept any message to user from the agent UI (content flexible)
            agent_proposed = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 4: Agent replied to maintenance email
            # Accept reply_to_email with the correct email_id (content flexible)
            agent_replied_email = any(
                e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == "email_maintenance_req_001"
                and e.action.args.get("content") is not None
                and "3b" in e.action.args.get("content").lower()
                for e in agent_events
            )

            # STRICT Check 5: Agent added calendar event for maintenance
            # Check that add_calendar_event was called with non-empty title and datetime (exact values flexible)
            agent_added_calendar = any(
                e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and e.action.args.get("title") is not None
                and e.action.args.get("start_datetime") is not None
                and e.action.args.get("end_datetime") is not None
                for e in agent_events
            )

            # Build success result
            success = (
                agent_read_email
                and agent_checked_calendar
                and agent_proposed
                and agent_replied_email
                and agent_added_calendar
            )

            # Build rationale for failure cases
            if not success:
                missing_checks = []
                if not agent_read_email:
                    missing_checks.append("agent did not read maintenance email")
                if not agent_checked_calendar:
                    missing_checks.append("agent did not query calendar for availability")
                if not agent_proposed:
                    missing_checks.append("agent did not propose maintenance window to user")
                if not agent_replied_email:
                    missing_checks.append("agent did not reply to maintenance email")
                if not agent_added_calendar:
                    missing_checks.append("agent did not add calendar event")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
