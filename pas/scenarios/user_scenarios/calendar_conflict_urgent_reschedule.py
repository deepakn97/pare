"""Proactive calendar conflict resolution with urgent meeting prioritization."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.contacts import Contact
from are.simulation.scenarios.scenario import Scenario, ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
    StatefulContactsApp,
    StatefulEmailApp,
)
from pas.scenarios.registry import register_scenario


@register_scenario("calendar_conflict_urgent_reschedule")
class CalendarConflictUrgentReschedule(Scenario):
    """Agent detects calendar conflict with urgent meeting and proactively reschedules existing event.

    The user has a "Design Review" meeting scheduled with Emma Davis on Tuesday, November 19th
    from 2:00 PM to 3:00 PM. This meeting was previously coordinated via email, and there's an
    existing email thread where Emma confirmed the time.

    The user receives a new email from their manager, David Wilson, requesting an urgent meeting
    for the same day at 2:30 PM, which overlaps with the Design Review. The agent must:
    1. Detect the incoming urgent meeting request
    2. Check calendar and identify the conflict
    3. Recognize the urgency and manager priority
    4. Propose rescheduling the existing Design Review meeting
    5. Find alternative time slot
    6. Update the existing calendar event (edit_calendar_event)
    7. Add manager's urgent meeting to calendar
    8. Reply to Emma in the existing email thread about the reschedule

    This scenario exercises conflict detection, priority-based decision making, calendar event
    modification (not creation), and contextual email communication within existing threads.
    """

    # Scenario starts on 2025-11-18 at 9:00 AM UTC (Monday morning)
    # Design Review is scheduled for next day (Nov 19), manager's email arrives today
    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        # Initialize apps
        self.email = StatefulEmailApp(name="StatefulEmailApp")
        self.calendar = StatefulCalendarApp(name="StatefulCalendarApp")
        self.contacts = StatefulContactsApp(name="StatefulContactsApp")
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="HomeScreenSystemApp")

        # Populate contacts
        # Emma Davis (colleague - Design Review participant)
        self.contacts.add_contact(
            Contact(
                first_name="Emma",
                last_name="Davis",
                contact_id="contact-emma-davis",
                email="emma.davis@company.com",
                phone="555-234-5678",
            )
        )

        # David Wilson (manager - urgent meeting requester)
        self.contacts.add_contact(
            Contact(
                first_name="David",
                last_name="Wilson",
                contact_id="contact-david-wilson",
                email="david.wilson@company.com",
                phone="555-345-6789",
            )
        )

        # Populate calendar - Add existing Design Review meeting (already scheduled)
        # Store the returned event_id so we can edit it later
        self.design_review_event_id = self.calendar.add_calendar_event(
            title="Design Review with Emma",
            start_datetime="2025-11-19 14:00:00",  # Tuesday Nov 19, 2:00 PM
            end_datetime="2025-11-19 15:00:00",  # Tuesday Nov 19, 3:00 PM
            attendees=["Emma Davis"],
            location="Conference Room B",
        )

        # Populate email - Create email chain with Emma about Design Review meeting
        # Email 1: Emma's initial proposal with two time options
        email1_id = self.email.create_and_add_email(
            sender="emma.davis@company.com",
            recipients=[self.email.user_email],
            subject="Design Review Meeting",
            content="Hi! I'd like to schedule our design review. Are you available Tuesday Nov 19 at 2 PM? I'm also free Wednesday Nov 20 at 10 AM if that works better.",
        )

        # Email 2: User's reply accepting Tuesday 2 PM
        email2_id = self.email.reply_to_email(
            email_id=email1_id,
            content="Tuesday Nov 19 at 2 PM works great for me. Let's go with that.",
        )

        # Email 3: Emma's confirmation of Tuesday 2 PM
        # Store this email_id so the agent can reply to it later for rescheduling
        self.emma_email_id = self.email.reply_to_email_from_user(
            sender="emma.davis@company.com",
            email_id=email2_id,
            content="Perfect! See you Tuesday Nov 19 at 2 PM. Looking forward to discussing the new features!",
        )

        # Register all apps
        self.apps = [self.email, self.calendar, self.contacts, self.agent_ui, self.system_app]

    def build_events_flow(self) -> None:
        """Build event flow - urgent meeting request triggers conflict detection and rescheduling."""
        aui = self.get_typed_app(PASAgentUserInterface)
        email = self.get_typed_app(StatefulEmailApp)
        calendar = self.get_typed_app(StatefulCalendarApp)

        with EventRegisterer.capture_mode():
            # Event 1: Incoming urgent email from manager (environment event)
            manager_email_event = email.send_email_to_user_only(
                sender="david.wilson@company.com",
                subject="Urgent: Executive Review Meeting",
                content="We need to discuss the Q4 roadmap urgently. Can you meet tomorrow (Tuesday Nov 19) at 2:00 PM? This is time-sensitive and I need your input before the board meeting on Wednesday.",
            ).delayed(2)

            # Event 2: Agent checks calendar for manager's proposed time (oracle)
            check_conflict_event = (
                calendar.get_calendar_events_from_to(
                    start_datetime="2025-11-19 14:00:00",
                    end_datetime="2025-11-19 15:00:00",
                )
                .oracle()
                .depends_on(manager_email_event, delay_seconds=2)
            )

            # Event 3: Agent proposes rescheduling Design Review (oracle)
            proposal_event = (
                aui.send_message_to_user(
                    content="I received an urgent meeting request from your manager David Wilson for tomorrow at 2:00 PM. This conflicts with your Design Review meeting with Emma Davis (2:00-3:00 PM). Would you like me to reschedule the Design Review to accommodate this urgent request?"
                )
                .oracle()
                .depends_on(check_conflict_event, delay_seconds=2)
            )

            # Event 4: User accepts proposal (oracle)
            acceptance_event = (
                aui.accept_proposal(content="Yes, please reschedule the Design Review and notify Emma.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Event 5: Agent checks alternative time slot (oracle)
            check_alternative_event = (
                calendar.get_calendar_events_from_to(
                    start_datetime="2025-11-20 10:00:00",
                    end_datetime="2025-11-20 11:00:00",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Event 6: Agent updates existing Design Review event (oracle)
            edit_event = (
                calendar.edit_calendar_event(
                    event_id=self.design_review_event_id,
                    start_datetime="2025-11-20 10:00:00",
                    end_datetime="2025-11-20 11:00:00",
                )
                .oracle()
                .depends_on(check_alternative_event, delay_seconds=1)
            )

            # Event 7: Agent adds manager's urgent meeting (oracle)
            add_manager_meeting_event = (
                calendar.add_calendar_event(
                    title="Executive Review Meeting with David",
                    start_datetime="2025-11-19 14:00:00",
                    end_datetime="2025-11-19 15:00:00",
                    attendees=["David Wilson"],
                    location="Manager's Office",
                )
                .oracle()
                .depends_on(edit_event, delay_seconds=1)
            )

            # Event 8: Agent replies to Emma about reschedule (oracle)
            notify_emma_event = (
                email.reply_to_email(
                    email_id=self.emma_email_id,
                    content="Hi Emma, something urgent came up with my manager tomorrow at 2:00 PM. Can we move our design review to Wednesday Nov 20 at 10 AM instead? Sorry for the last-minute change!",
                )
                .oracle()
                .depends_on(add_manager_meeting_event, delay_seconds=2)
            )

        # Register ALL events
        self.events = [
            manager_email_event,
            check_conflict_event,
            proposal_event,
            acceptance_event,
            check_alternative_event,
            edit_event,
            add_manager_meeting_event,
            notify_emma_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detected conflict, rescheduled existing event, and notified Emma."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1: Agent sent proposal mentioning the conflict with manager's meeting
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(name in e.action.args.get("content", "") for name in ["David Wilson", "manager"])
                and any(keyword in e.action.args.get("content", "") for keyword in ["conflict", "urgent"])
                and any(keyword in e.action.args.get("content", "") for keyword in ["Design Review", "Emma"])
                for e in log_entries
            )

            # Check 2: Agent checked calendar for conflicts
            calendar_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "get_calendar_events_from_to"
                for e in log_entries
            )

            # Check 3: Agent EDITED the existing Design Review event (not created new one)
            edit_event_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "edit_calendar_event"
                and e.action.args.get("event_id") == self.design_review_event_id
                and e.action.args.get("start_datetime") == "2025-11-20 10:00:00"
                and e.action.args.get("end_datetime") == "2025-11-20 11:00:00"
                for e in log_entries
            )

            # Check 4: Agent added manager's urgent meeting
            manager_meeting_added = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and e.action.args.get("start_datetime") == "2025-11-19 14:00:00"
                and e.action.args.get("end_datetime") == "2025-11-19 15:00:00"
                and any(keyword in e.action.args.get("title", "") for keyword in ["David", "Executive"])
                for e in log_entries
            )

            # Check 5: Agent replied to Emma's email about the reschedule
            emma_notified = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == self.emma_email_id
                and any(
                    keyword in e.action.args.get("content", "")
                    for keyword in ["reschedule", "move", "change", "urgent"]
                )
                and any(
                    keyword in e.action.args.get("content", "") for keyword in ["Wednesday", "Nov 20", "10 AM", "10:00"]
                )
                for e in log_entries
            )

            success = (
                proposal_found and calendar_check_found and edit_event_found and manager_meeting_added and emma_notified
            )
            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
