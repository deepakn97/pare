"""Scenario: Agent detects mismatch between booked cab destination and calendar meeting location."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import (
    AbstractEnvironment,
    Action,
    EventRegisterer,
    EventType,
)

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
    StatefulReminderApp,
)
from pas.apps.cab import StatefulCabApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("cab_destination_mismatch_detection")
class CabDestinationMismatchDetection(PASScenario):
    """Agent detects mismatch between booked cab destination and calendar meeting location.

    The user has a calendar meeting "Client Presentation" scheduled at 2:00 PM at "789 Corporate Plaza,
    Suite 400". They have already booked a cab for 1:00 PM (one hour before the meeting) but made a
    mistake - the cab is booked to "789 Corporate Drive" instead of "789 Corporate Plaza" (a common
    typo/confusion with similar addresses). A reminder "Leave for Office" is set for 1:00 PM.

    When the reminder becomes due, the agent must:
    1. Notice the reminder about leaving for office
    2. Check the calendar to find what meeting the user is heading to
    3. Check the current cab booking details
    4. Detect the mismatch between cab destination and meeting location
    5. Propose canceling the incorrectly-booked cab and rebooking to the correct address
    6. After user acceptance, cancel the wrong cab and book a new one to the correct location

    This scenario exercises anomaly detection across apps, proactive error correction before it causes
    problems, and coordination between reminder triggers, calendar context, and transportation booking.
    """

    start_time = datetime(2025, 11, 18, 12, 55, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.cab = StatefulCabApp(name="Cab")
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.reminder = StatefulReminderApp(name="Reminders")

        # Add calendar meeting at correct location
        self.meeting_event_id = self.calendar.add_calendar_event(
            title="Client Presentation",
            start_datetime="2025-11-18 14:00:00",
            end_datetime="2025-11-18 15:30:00",
            location="789 Corporate Plaza, Suite 400",
            description="Q4 sales presentation to Acme Corp stakeholders",
            attendees=["John Smith", "Sarah Chen"],
        )

        # Book cab to WRONG address (similar but incorrect - common typo)
        self.cab.order_ride(
            start_location="123 Home Street",
            end_location="789 Corporate Drive",  # WRONG! Should be "789 Corporate Plaza, Suite 400"
            service_type="Default",
            ride_time="2025-11-18 13:00:00",
        )

        # Add reminder for 1 hour before meeting (generic, no location details)
        self.reminder_id = self.reminder.add_reminder(
            title="Leave for Office",
            due_datetime="2025-11-18 12:56:00",
            description="Time to head out",
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.cab, self.calendar, self.reminder]

    def build_events_flow(self) -> None:
        """Build event flow - reminder trigger, mismatch detection, cab rebooking."""
        aui = self.get_typed_app(PASAgentUserInterface)
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")

        with EventRegisterer.capture_mode():
            # Oracle: Agent checks calendar for upcoming meetings
            check_calendar_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-18 13:00:00",
                    end_datetime="2025-11-18 16:00:00",
                )
                .oracle()
                .delayed(62)
            )

            # Oracle: Agent checks current cab booking
            check_cab_event = (
                cab_app.get_current_ride_status().oracle().depends_on(check_calendar_event, delay_seconds=1)
            )

            # Oracle: Agent detects mismatch and proposes fix
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed your cab is booked to 789 Corporate Drive, but your Client Presentation meeting is at 789 Corporate Plaza, Suite 400. Would you like me to cancel the current cab and book a new one to the correct address?"
                )
                .oracle()
                .depends_on(check_cab_event, delay_seconds=2)
            )

            # Oracle: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please fix that!")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle: Agent cancels the incorrectly-booked cab
            cancel_cab_event = cab_app.user_cancel_ride().oracle().depends_on(acceptance_event, delay_seconds=1)

            # Oracle: Agent books new cab to correct address
            rebook_cab_event = (
                cab_app.order_ride(
                    start_location="123 Home Street",
                    end_location="789 Corporate Plaza, Suite 400",
                    service_type="Default",
                    ride_time="2025-11-18 13:00:00",
                )
                .oracle()
                .depends_on(cancel_cab_event, delay_seconds=1)
            )

        self.events = [
            check_calendar_event,
            check_cab_event,
            proposal_event,
            acceptance_event,
            cancel_cab_event,
            rebook_cab_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent achieved the essential outcomes for this scenario.

        Essential outcomes (what we check):
        - Agent sent proposal to user about the destination mismatch
        - Agent cancelled the incorrectly-booked cab
        - Agent booked a new cab to the correct address

        Not checked (intermediate steps the agent might do differently):
        - How agent found the meeting (get_calendar_events_from_to, list_events, etc.)
        - How agent checked cab status (get_current_ride_status, get_ride_history, etc.)
        """
        try:
            log_entries = env.event_log.list_view()

            # CHECK 1: Agent sent proposal to user about mismatch
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # CHECK 2: Agent cancelled the wrong cab
            cab_cancelled = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "user_cancel_ride"
                for e in log_entries
            )

            # CHECK 3: Agent booked new cab to correct address (Corporate Plaza)
            correct_cab_booked = False
            for e in log_entries:
                if (
                    e.event_type == EventType.AGENT
                    and isinstance(e.action, Action)
                    and e.action.class_name == "StatefulCabApp"
                    and e.action.function_name == "order_ride"
                ):
                    end_location = e.action.args.get("end_location", "").lower()
                    if "corporate plaza" in end_location:
                        correct_cab_booked = True
                        break

            success = proposal_found and cab_cancelled and correct_cab_booked

            if not success:
                failed_checks = []
                if not proposal_found:
                    failed_checks.append("agent did not send proposal about destination mismatch")
                if not cab_cancelled:
                    failed_checks.append("agent did not cancel the incorrectly-booked cab")
                if not correct_cab_booked:
                    failed_checks.append("agent did not book new cab to correct address (Corporate Plaza)")
                rationale = "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
