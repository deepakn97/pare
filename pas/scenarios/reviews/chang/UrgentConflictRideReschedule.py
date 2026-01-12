"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.cab import Ride
from are.simulation.apps.calendar import CalendarEvent
from are.simulation.apps.contacts import Contact
from are.simulation.apps.email_client import Email, EmailFolderName
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCabApp,
    StatefulCalendarApp,
    StatefulEmailApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("urgent_conflict_ride_reschedule")
class UrgentConflictRideReschedule(PASScenario):
    """Agent resolves calendar conflict and transportation booking when an urgent meeting preempts a scheduled appointment.

    The user has a "Vendor Contract Review" meeting scheduled with the legal team on Thursday, December 19th from 2:00 PM to 3:30 PM at the company's North Campus office. A cab ride has already been booked for 1:15 PM pickup to arrive on time. An urgent email arrives from the CEO's assistant (Amanda Foster) at 12:30 PM requesting the user attend an emergency board meeting at the Downtown Executive Center starting at 2:15 PM - the message emphasizes "Please confirm attendance immediately as your presence is critical." The agent must:
    1. Parse the urgent meeting request email to extract location, time, and priority signals
    2. Search the calendar to identify the 2:00 PM "Vendor Contract Review" conflict
    3. Check cab ride history/status to verify the existing 1:15 PM booking to North Campus
    4. Recognize the urgency hierarchy (CEO emergency request vs. routine vendor review)
    5. Propose canceling the existing cab order, rescheduling the Vendor Contract Review to a later time slot (checking for availability on the same day after 4:00 PM), and booking a new cab to Downtown Executive Center at 1:30 PM
    6. Upon user acceptance, cancel the current cab order, edit the calendar event to move it to the available time slot, order the new cab, and send a reply email confirming attendance to Amanda Foster plus a rescheduling notification to the legal team for the vendor meeting

    This scenario exercises email-triggered conflict detection, priority-based decision making, calendar event rescheduling (not just creation/deletion), cab order cancellation workflows, coordinated multi-app state changes, and stakeholder notification via email replies to multiple parties.
    """

    start_time = datetime(2024, 12, 19, 12, 30, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.email = StatefulEmailApp(name="Emails", user_email="user@company.com")
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.cab = StatefulCabApp(name="Cab")

        # Populate contacts
        amanda_foster = Contact(
            first_name="Amanda",
            last_name="Foster",
            email="amanda.foster@company.com",
            job="Executive Assistant to CEO",
            phone="555-0101",
        )

        sarah_chen = Contact(
            first_name="Sarah",
            last_name="Chen",
            email="sarah.chen@company.com",
            job="Senior Legal Counsel",
            phone="555-0102",
        )

        michael_torres = Contact(
            first_name="Michael",
            last_name="Torres",
            email="michael.torres@company.com",
            job="Legal Director",
            phone="555-0103",
        )

        # Populate calendar with the existing Vendor Contract Review meeting
        vendor_meeting = CalendarEvent(
            title="Vendor Contract Review",
            start_datetime=datetime(2024, 12, 19, 14, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2024, 12, 19, 15, 30, 0, tzinfo=UTC).timestamp(),
            location="North Campus - Building 5, Conference Room A",
            description="Quarterly review of vendor contracts with legal team. Review payment terms, renewal clauses, and compliance requirements.",
            attendees=["Sarah Chen", "Michael Torres"],
            tag="Work",
        )
        self.vendor_meeting_event_id = vendor_meeting.event_id
        self.calendar.set_calendar_event(vendor_meeting)

        # Populate cab ride history with the existing booking
        existing_ride = Ride(
            ride_id="ride_12345abc",
            status="BOOKED",
            service_type="Default",
            start_location="User Home",
            end_location="North Campus - Building 5",
            price=18.50,
            duration=25.0 * 60,  # 25 minutes in seconds
            time_stamp=datetime(2024, 12, 19, 13, 15, 0, tzinfo=UTC).timestamp(),
            distance_km=15.2,
            delay=5.0 * 60,  # 5 minutes delay in seconds
        )
        self.cab.ride_history.append(existing_ride)
        self.cab.on_going_ride = existing_ride

        # Populate email with historical context (earlier email about vendor meeting)
        earlier_email = Email(
            email_id="email_vendor_001",
            sender="sarah.chen@company.com",
            recipients=["user@company.com"],
            subject="Reminder: Vendor Contract Review - Thursday 2 PM",
            content="Hi,\n\nJust a reminder about our Vendor Contract Review meeting this Thursday, December 19th at 2:00 PM in North Campus Building 5, Conference Room A.\n\nMichael and I have prepared the materials. We'll be reviewing the Q4 vendor contracts, payment terms, and compliance requirements.\n\nSee you there!\n\nBest,\nSarah Chen\nSenior Legal Counsel",
            timestamp=datetime(2024, 12, 18, 10, 30, 0, tzinfo=UTC).timestamp(),
            is_read=True,
        )
        self.email.folders[EmailFolderName.INBOX].add_email(earlier_email)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.calendar, self.cab]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Urgent email arrives from CEO's assistant
            # This is the triggering exogenous signal
            urgent_email_event = email_app.send_email_to_user_with_id(
                email_id="email_urgent_board_001",
                sender="amanda.foster@company.com",
                subject="URGENT: Emergency Board Meeting - Your Attendance Required",
                content="Hi,\n\nThe CEO needs you to attend an emergency board meeting TODAY at the Downtown Executive Center starting at 2:15 PM. This is regarding the Q4 strategic initiative and your presence is critical.\n\nPlease confirm attendance immediately as the board is waiting on your input.\n\nLocation: Downtown Executive Center, Board Room\nTime: Today, December 19th, 2:15 PM - 3:30 PM\n\nBest regards,\nAmanda Foster\nExecutive Assistant to CEO",
            ).delayed(5)

            # Agent reads the urgent email (motivated by notification from urgent_email_event)
            read_urgent_email_event = (
                email_app.get_email_by_id(
                    email_id="email_urgent_board_001",
                    folder_name="INBOX",
                )
                .oracle()
                .depends_on(urgent_email_event, delay_seconds=2)
            )

            # Agent checks calendar for conflicts around 2:15 PM (motivated by time mentioned in urgent email)
            check_calendar_conflict_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2024-12-19 14:00:00",
                    end_datetime="2024-12-19 15:30:00",
                )
                .oracle()
                .depends_on(read_urgent_email_event, delay_seconds=2)
            )

            # Agent checks current cab booking status (motivated by knowing there's a scheduled meeting with transportation)
            check_cab_status_event = (
                cab_app.get_current_ride_status().oracle().depends_on(check_calendar_conflict_event, delay_seconds=1)
            )

            # Agent checks afternoon availability for rescheduling (motivated by need to move Vendor Contract Review)
            check_afternoon_availability_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2024-12-19 16:00:00",
                    end_datetime="2024-12-19 18:00:00",
                )
                .oracle()
                .depends_on(check_cab_status_event, delay_seconds=1)
            )

            # Agent proposes resolution: cancel cab, reschedule meeting, book new cab (motivated by urgent email from CEO's assistant)
            proposal_event = (
                aui.send_message_to_user(
                    content="I received an urgent email from Amanda Foster (CEO's assistant) requesting your immediate attendance at an emergency board meeting at the Downtown Executive Center at 2:15 PM today. This conflicts with your Vendor Contract Review meeting (2:00-3:30 PM) and your existing cab booking (1:15 PM pickup to North Campus).\n\nWould you like me to:\n1. Cancel the current cab to North Campus\n2. Reschedule the Vendor Contract Review to 4:00 PM today (you're free then)\n3. Book a new cab to Downtown Executive Center for 1:30 PM pickup\n4. Notify the legal team and confirm attendance with Amanda?"
                )
                .oracle()
                .depends_on(check_afternoon_availability_event, delay_seconds=2)
            )

            # User accepts the proposal
            user_acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please proceed with all those changes. This board meeting is critical."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Agent cancels existing cab booking (motivated by user acceptance)
            cancel_cab_event = cab_app.user_cancel_ride().oracle().depends_on(user_acceptance_event, delay_seconds=1)

            # Agent edits calendar event to reschedule to 4:00 PM (motivated by user acceptance)
            reschedule_meeting_event = (
                calendar_app.edit_calendar_event(
                    event_id=self.vendor_meeting_event_id,
                    start_datetime="2024-12-19 16:00:00",
                    end_datetime="2024-12-19 17:30:00",
                )
                .oracle()
                .depends_on(cancel_cab_event, delay_seconds=1)
            )

            # Agent books new cab to Downtown Executive Center (motivated by user acceptance)
            book_new_cab_event = (
                cab_app.order_ride(
                    start_location="User Home",
                    end_location="Downtown Executive Center",
                    service_type="Default",
                    ride_time="2024-12-19 13:30:00",
                )
                .oracle()
                .depends_on(reschedule_meeting_event, delay_seconds=2)
            )

            # Agent adds urgent board meeting to calendar (motivated by user acceptance)
            add_board_meeting_event = (
                calendar_app.add_calendar_event(
                    title="Emergency Board Meeting",
                    start_datetime="2024-12-19 14:15:00",
                    end_datetime="2024-12-19 15:30:00",
                    location="Downtown Executive Center, Board Room",
                    attendees=["CEO", "Amanda Foster"],
                    tag="Work",
                    description="Q4 strategic initiative discussion - urgent board meeting",
                )
                .oracle()
                .depends_on(book_new_cab_event, delay_seconds=1)
            )

            # Agent replies to Amanda confirming attendance (motivated by user acceptance and urgent email request)
            confirm_to_amanda_event = (
                email_app.reply_to_email(
                    email_id="email_urgent_board_001",
                    folder_name="INBOX",
                    content="Hi Amanda,\n\nConfirmed - I will attend the emergency board meeting at the Downtown Executive Center at 2:15 PM today. I've rearranged my schedule to accommodate this critical meeting.\n\nSee you there.\n\nBest regards",
                )
                .oracle()
                .depends_on(add_board_meeting_event, delay_seconds=2)
            )

            # Agent sends rescheduling notification to legal team (motivated by user acceptance and need to inform displaced meeting attendees)
            notify_legal_team_event = (
                email_app.send_email(
                    recipients=["sarah.chen@company.com", "michael.torres@company.com"],
                    subject="Vendor Contract Review Rescheduled to 4:00 PM Today",
                    content="Hi Sarah and Michael,\n\nDue to an urgent board meeting that just came up, I need to reschedule our Vendor Contract Review meeting from 2:00 PM to 4:00 PM today (same location: North Campus Building 5, Conference Room A).\n\nApologies for the short notice. Please let me know if the new time works for you.\n\nBest regards",
                )
                .oracle()
                .depends_on(confirm_to_amanda_event, delay_seconds=1)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            urgent_email_event,
            read_urgent_email_event,
            check_calendar_conflict_event,
            check_cab_status_event,
            check_afternoon_availability_event,
            proposal_event,
            user_acceptance_event,
            cancel_cab_event,
            reschedule_meeting_event,
            book_new_cab_event,
            add_board_meeting_event,
            confirm_to_amanda_event,
            notify_legal_team_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only agent/oracle events
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent sent proposal to the user
            proposal_found = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 2: Agent read the urgent email
            read_urgent_email_found = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name in ["get_email_by_id", "list_emails"]
                and (
                    e.action.args.get("email_id") == "email_urgent_board_001"
                    or "email_urgent_board_001" in str(e.metadata.return_value)
                )
                for e in agent_events
            )

            # STRICT Check 3: Agent checked calendar for conflicts
            calendar_check_found = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name in ["get_calendar_events_from_to", "get_all_calendar_events"]
                for e in agent_events
            )

            # STRICT Check 4: Agent checked cab status
            cab_check_found = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name in ["get_current_ride_status", "get_ride_history"]
                for e in agent_events
            )

            # STRICT Check 5: Agent canceled the existing cab booking
            cancel_cab_found = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "user_cancel_ride"
                for e in agent_events
            )

            # STRICT Check 6: Agent rescheduled the vendor meeting (edited calendar event)
            reschedule_meeting_found = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "edit_calendar_event"
                and e.action.args.get("event_id") == self.vendor_meeting_event_id
                for e in agent_events
            )

            # STRICT Check 7: Agent booked new cab to Downtown Executive Center
            book_new_cab_found = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "order_ride"
                and "downtown executive center" in str(e.action.args.get("end_location", "")).lower()
                for e in agent_events
            )

            # STRICT Check 8: Agent notified legal team about rescheduling
            notify_legal_team_found = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "send_email"
                and (
                    "sarah.chen@company.com" in str(e.action.args.get("recipients", ""))
                    or "michael.torres@company.com" in str(e.action.args.get("recipients", ""))
                )
                for e in agent_events
            )

            # Combine all checks
            all_checks = [
                ("proposal_found", proposal_found),
                ("read_urgent_email_found", read_urgent_email_found),
                ("calendar_check_found", calendar_check_found),
                ("cab_check_found", cab_check_found),
                ("cancel_cab_found", cancel_cab_found),
                ("reschedule_meeting_found", reschedule_meeting_found),
                ("book_new_cab_found", book_new_cab_found),
                ("notify_legal_team_found", notify_legal_team_found),
            ]

            success = all(check[1] for check in all_checks)

            if not success:
                failed_checks = [name for name, result in all_checks if not result]
                rationale = f"Missing critical agent actions: {', '.join(failed_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
