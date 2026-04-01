from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.contacts import Contact
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulCalendarApp,
    StatefulEmailApp,
)
from pare.apps.reminder import StatefulReminderApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("travel_conflict_recurring_meeting")
class TravelConflictRecurringMeeting(PAREScenario):
    """Agent detects travel itinerary conflicts with recurring calendar events and proposes rescheduling the affected instance. The user receives a flight confirmation email for a business trip next Thursday, departing at 2:00 PM. However, the user has a standing weekly team sync meeting every Thursday at 1:30 PM that typically runs one hour. The agent must: 1. Parse the flight confirmation email to extract departure date and time. 2. Identify the calendar conflict with the recurring weekly meeting occurring on the same day. 3. Calculate that the user needs to leave for the airport during the scheduled meeting time. 4. Propose rescheduling only that specific Thursday's meeting instance to an earlier time slot (e.g., 10:00 AM) without affecting future weeks. 5. After user acceptance, update the single occurrence and send updated invitations to all attendees with a note explaining the travel conflict. 6. Confirm the original recurring series remains intact for subsequent weeks.

    This scenario exercises email-to-calendar temporal correlation, recurring event instance modification (not series-wide changes), conflict detection with structured travel data, proactive attendee communication for schedule changes, and differentiation between one-time adjustments versus series modifications..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with baseline data for travel conflict scenario."""
        # Initialize required apps
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")
        self.email = StatefulEmailApp(name="Emails")
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.reminder = StatefulReminderApp(name="Reminders")

        # Populate baseline calendar with recurring weekly meeting instances
        # Weekly team sync meeting: Every Thursday 1:30 PM - 2:30 PM
        # Add past instances (2 weeks before) to establish the recurring pattern
        self.calendar.add_calendar_event(
            title="Weekly Team Sync",
            start_datetime="2025-11-06 13:30:00",  # Thursday Nov 6, 1:30 PM
            end_datetime="2025-11-06 14:30:00",  # Thursday Nov 6, 2:30 PM
            attendees=["Sarah Johnson", "Michael Chen", "Alex Rivera"],
            description="Weekly team coordination meeting",
            location="Conference Room A",
            tag="recurring",
        )

        self.calendar.add_calendar_event(
            title="Weekly Team Sync",
            start_datetime="2025-11-13 13:30:00",  # Thursday Nov 13, 1:30 PM
            end_datetime="2025-11-13 14:30:00",  # Thursday Nov 13, 2:30 PM
            attendees=["Sarah Johnson", "Michael Chen", "Alex Rivera"],
            description="Weekly team coordination meeting",
            location="Conference Room A",
            tag="recurring",
        )

        # This Thursday (Nov 20) - the one that will conflict with travel
        self.conflicting_meeting_id = self.calendar.add_calendar_event(
            title="Weekly Team Sync",
            start_datetime="2025-11-20 13:30:00",  # Thursday Nov 20, 1:30 PM
            end_datetime="2025-11-20 14:30:00",  # Thursday Nov 20, 2:30 PM
            attendees=["Sarah Johnson", "Michael Chen", "Alex Rivera"],
            description="Weekly team coordination meeting",
            location="Conference Room A",
            tag="recurring",
        )

        # Next Thursday (Nov 27) - future instance to prove series remains intact
        self.calendar.add_calendar_event(
            title="Weekly Team Sync",
            start_datetime="2025-11-27 13:30:00",  # Thursday Nov 27, 1:30 PM
            end_datetime="2025-11-27 14:30:00",  # Thursday Nov 27, 2:30 PM
            attendees=["Sarah Johnson", "Michael Chen", "Alex Rivera"],
            description="Weekly team coordination meeting",
            location="Conference Room A",
            tag="recurring",
        )

        # Seed a user-created reminder that will automatically notify the user+agent when due (time-driven).
        # This replaces the unrealistic "airline tells you to check your calendar" line in the flight email.
        self.reminder.add_reminder(
            title="Travel prep: check Nov 20 calendar conflicts (airport)",
            due_datetime="2025-11-18 09:01:00",
            description=(
                "Reminder: Please check your calendar for any meetings on Nov 20 that conflict with leaving for the "
                "airport, and reschedule as needed."
            ),
        )

        # Populate contacts with meeting attendees
        # Team member contacts for the weekly meeting
        # Sarah Johnson - team lead
        Contact(
            first_name="Sarah",
            last_name="Johnson",
            contact_id="contact-sarah-johnson",
            email="sarah.johnson@company.com",
            phone="555-101-2020",
        )

        # Michael Chen - team member
        Contact(
            first_name="Michael",
            last_name="Chen",
            contact_id="contact-michael-chen",
            email="michael.chen@company.com",
            phone="555-102-3030",
        )

        # Alex Rivera - team member
        Contact(
            first_name="Alex",
            last_name="Rivera",
            contact_id="contact-alex-rivera",
            email="alex.rivera@company.com",
            phone="555-103-4040",
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.calendar, self.reminder]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PAREAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Flight confirmation email arrives
            # Contains structured travel data: departure Thursday Nov 20 at 2:00 PM
            flight_email_event = email_app.send_email_to_user_with_id(
                email_id="flight-confirmation-email",
                sender="noreply@skylineairlines.com",
                subject="Flight Confirmation - SL482 to Boston",
                content=(
                    "Your flight is confirmed!\n\n"
                    "Flight: SL482\n"
                    "Date: Thursday, November 20, 2025\n"
                    "Departure: 2:00 PM from San Francisco Airport (SFO)\n"
                    "Arrival: 10:30 PM at Boston Logan (BOS)\n\n"
                    "Please arrive at the airport at least 90 minutes before departure (12:30 PM).\n"
                    "Booking Reference: XYZ789"
                ),
            ).delayed(30)

            # NOTE: Reminder notifications are time-driven in the Reminders app.
            # The reminder seeded in init (`due_datetime="2025-11-18 09:01:00"`) will automatically notify user+agent.
            # We model reaction time by delaying the first oracle action until after the reminder would have fired.

            # Oracle Event 2: Agent reads the flight confirmation details (after the reminder notification)
            read_flight_email_event = (
                email_app.get_email_by_id(email_id="flight-confirmation-email", folder_name="INBOX")
                .oracle()
                .delayed(70)
            )

            # Oracle Event 3: Agent checks calendar for conflicts on Nov 20 (motivated by the reminder + flight timing)
            check_calendar_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-20 00:00:00",
                    end_datetime="2025-11-20 23:59:59",
                )
                .oracle()
                .depends_on(read_flight_email_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent proposes rescheduling the conflicting meeting instance
            # Agent identifies conflict: meeting 1:30-2:30 PM overlaps with required airport departure time
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed your flight to Boston departs on Thursday, Nov 20 at 2:00 PM (you should leave by 12:30 PM). Your Weekly Team Sync is scheduled 1:30-2:30 PM that day, which conflicts with your travel. Would you like me to reschedule this week's meeting to 10:00 AM and notify the attendees?"
                )
                .oracle()
                .depends_on(check_calendar_event, delay_seconds=2)
            )

            # Oracle Event 5: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please do that.").oracle().depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent checks if 10 AM slot is available on Nov 20
            check_alternate_slot_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-20 10:00:00",
                    end_datetime="2025-11-20 11:00:00",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 7: Agent edits the specific Nov 20 meeting instance (not the series)
            edit_meeting_event = (
                calendar_app.edit_calendar_event(
                    event_id=self.conflicting_meeting_id,
                    start_datetime="2025-11-20 10:00:00",
                    end_datetime="2025-11-20 11:00:00",
                )
                .oracle()
                .depends_on(check_alternate_slot_event, delay_seconds=1)
            )

            # Oracle Event 8: Agent sends email to all attendees about the reschedule
            notify_attendees_event = (
                email_app.send_email(
                    recipients=[
                        "sarah.johnson@company.com",
                        "michael.chen@company.com",
                        "alex.rivera@company.com",
                    ],
                    subject="Weekly Team Sync Rescheduled - Nov 20 Only",
                    content="Hi team,\n\nI need to reschedule this Thursday's (Nov 20) Weekly Team Sync from 1:30 PM to 10:00 AM due to a flight departure at 2:00 PM.\n\nThis change is only for Nov 20. Our regular Thursday 1:30 PM time continues for all future weeks.\n\nSorry for the short notice, and thanks for your flexibility!",
                )
                .oracle()
                .depends_on(edit_meeting_event, delay_seconds=2)
            )

            # Oracle Event 9: Agent verifies the future instance (Nov 27) remains unchanged
            verify_future_instance_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-27 13:30:00",
                    end_datetime="2025-11-27 14:30:00",
                )
                .oracle()
                .depends_on(notify_attendees_event, delay_seconds=1)
            )

        # Register ALL events
        self.events = [
            flight_email_event,
            read_flight_email_event,
            check_calendar_event,
            proposal_event,
            acceptance_event,
            check_alternate_slot_event,
            edit_meeting_event,
            notify_attendees_event,
            verify_future_instance_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent sent proposal to the user about the travel conflict
            # STRICT: Must mention flight/travel, conflict with meeting, and propose rescheduling
            # FLEXIBLE: Exact wording and phrasing can vary
            proposal_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "PAREAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check Step 2: Agent edited the specific conflicting meeting instance (Nov 20)
            # STRICT: Must edit the correct event_id and change time to 10:00 AM slot
            # FLEXIBLE: End time can be 11:00 or 11:30 depending on meeting duration logic
            edit_meeting_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "edit_calendar_event"
                and e.action.args.get("event_id") == self.conflicting_meeting_id
                for e in log_entries
            )

            # Build success result: strict checks are required, flexible check is optional
            success = proposal_found and edit_meeting_found

            # Build rationale for failure
            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal about travel conflict")
                if not edit_meeting_found:
                    missing_checks.append("edit meeting event to 10:00 AM")

                rationale = "Missing critical validation checks: " + ", ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
