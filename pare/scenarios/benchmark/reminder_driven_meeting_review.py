"""Scenario: Agent summarizes meeting notes triggered by a reminder, then shares via email."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import (
    AbstractEnvironment,
    Action,
    ConditionCheckEvent,
    EventRegisterer,
    EventType,
)

from pare.apps import HomeScreenSystemApp, PAREAgentUserInterface, StatefulCalendarApp, StatefulEmailApp
from pare.apps.note import StatefulNotesApp
from pare.apps.reminder import StatefulReminderApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("reminder_driven_meeting_review")
class ReminderDrivenMeetingReview(PAREScenario):
    """Agent consolidates client meeting notes into a summary triggered by a reminder.

    The user has three client meetings from the previous week (Jan 13-17, 2025) with associated meeting
    notes in the Notes app. A reminder triggers at 9:01 AM on Jan 20th to summarize these meetings.

    Flow:
    1. Reminder triggers (ENV event simulated via delayed action)
    2. Agent proposes to summarize meeting outcomes from notes
    3. User accepts
    4. Agent reads each meeting note
    5. Agent creates consolidated summary note
    6. Colleague emails asking for the meeting summary (triggered by ConditionCheckEvent)
    7. Agent proposes to share the summary
    8. User accepts
    9. Agent replies to email with summary content

    This scenario exercises reminder-triggered workflows, note reading and synthesis, and cross-app
    coordination between Notes and Email apps.
    """

    start_time = datetime(2025, 1, 20, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Reminder app with trigger reminder at 9:01 AM
        self.reminder = StatefulReminderApp(name="Reminders")
        self.reminder.add_reminder(
            title="Summarize client meeting outcomes",
            due_datetime="2025-01-20 09:01:00",
            description="Review meeting notes from last week and create a consolidated summary",
        )

        # Initialize Calendar app with three client meetings from last week
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.calendar.add_calendar_event(
            title="Client Meeting - Sarah Thompson",
            start_datetime="2025-01-13 10:00:00",
            end_datetime="2025-01-13 11:00:00",
            description="Q1 budget proposal discussion",
            location="Conference Room A",
            attendees=["Sarah Thompson"],
        )
        self.calendar.add_calendar_event(
            title="Client Meeting - Marcus Rodriguez",
            start_datetime="2025-01-15 14:00:00",
            end_datetime="2025-01-15 15:00:00",
            description="Phase 2 implementation planning",
            location="Zoom Meeting",
            attendees=["Marcus Rodriguez"],
        )
        self.calendar.add_calendar_event(
            title="Client Meeting - Jennifer Lee",
            start_datetime="2025-01-17 15:00:00",
            end_datetime="2025-01-17 16:30:00",
            description="Contract renewal discussion",
            location="Conference Room B",
            attendees=["Jennifer Lee"],
        )

        # Initialize Notes app with meeting notes for each client
        self.notes = StatefulNotesApp(name="Notes")
        self.sarah_note_id = self.notes.create_note(
            folder="Work",
            title="Meeting Notes: Client Meeting - Sarah Thompson",
            content="""Meeting Notes - Sarah Thompson
Date: January 13, 2025, 10:00 AM
Location: Conference Room A

Attendees: Sarah Thompson (Client), User

Discussion Points:
- Reviewed Q1 budget proposal ($450K total)
- Sarah expressed concerns about timeline for Phase 1
- Discussed resource allocation for development team

Outcome:
- Client approved Q1 budget proposal with minor adjustments
- Agreed to extend Phase 1 deadline by 2 weeks
- Will allocate 3 additional developers starting February

Action Items:
- Send revised timeline by Jan 22
- Schedule follow-up for Phase 1 kickoff""",
        )
        self.marcus_note_id = self.notes.create_note(
            folder="Work",
            title="Meeting Notes: Client Meeting - Marcus Rodriguez",
            content="""Meeting Notes - Marcus Rodriguez
Date: January 15, 2025, 2:00 PM
Location: Zoom Meeting

Attendees: Marcus Rodriguez (Client), User

Discussion Points:
- Phase 2 implementation plan review
- Technical requirements for API integration
- Deployment schedule and rollout strategy

Outcome:
- Client approved Phase 2 implementation plan
- Confirmed technical specs for REST API
- Deployment scheduled for March 15th

Action Items:
- Share API documentation by Jan 25
- Set up staging environment by Feb 1""",
        )
        self.jennifer_note_id = self.notes.create_note(
            folder="Work",
            title="Meeting Notes: Client Meeting - Jennifer Lee",
            content="""Meeting Notes - Jennifer Lee
Date: January 17, 2025, 3:00 PM
Location: Conference Room B

Attendees: Jennifer Lee (Client), User

Discussion Points:
- Contract renewal terms for 2025-2027
- Pricing structure adjustments
- Support package options (Basic vs Premium)

Outcome:
- Agreed on 2-year contract renewal
- 5% price increase approved
- Client selected Premium support package

Action Items:
- Draft renewal contract by Jan 24
- Send pricing breakdown to finance team""",
        )

        # Initialize Email app for colleague request
        self.email = StatefulEmailApp(name="Emails")

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.reminder, self.calendar, self.notes, self.email]

    def build_events_flow(self) -> None:
        """Build event flow - reminder trigger, note summarization, email sharing."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")
        notes_app = self.get_typed_app(StatefulNotesApp, "Notes")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")

        # Condition: Check if agent created the summary note
        def summary_note_created(env: AbstractEnvironment) -> bool:
            """Check if agent created a summary note in the Work folder."""
            for event in env.event_log.list_view():
                if (
                    event.event_type == EventType.AGENT
                    and isinstance(event.action, Action)
                    and event.action.class_name == "StatefulNotesApp"
                    and event.action.function_name == "create_note"
                    and event.action.args.get("folder") == "Work"
                ):
                    return True
            return False

        with EventRegisterer.capture_mode():
            # ORACLE Event 1: Agent proposes to summarize meeting outcomes
            proposal_event = (
                aui.send_message_to_user(
                    content="Your reminder to summarize client meeting outcomes is due. I can see you have meeting notes for Sarah Thompson, Marcus Rodriguez, and Jennifer Lee from last week. Would you like me to review these notes and create a consolidated summary?"
                )
                .oracle()
                .delayed(80)
            )

            # ORACLE Event 2: User accepts
            acceptance_event = (
                aui.accept_proposal(content="Yes, please summarize the meeting outcomes.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # ORACLE Event 3: Agent lists notes in Work folder
            list_notes_event = (
                notes_app.list_notes(folder="Work").oracle().depends_on(acceptance_event, delay_seconds=1)
            )

            # ORACLE Event 4: Agent reads Sarah's meeting note
            read_sarah_note_event = (
                notes_app.get_note_by_id(note_id=self.sarah_note_id)
                .oracle()
                .depends_on(list_notes_event, delay_seconds=1)
            )

            # ORACLE Event 5: Agent reads Marcus's meeting note
            read_marcus_note_event = (
                notes_app.get_note_by_id(note_id=self.marcus_note_id)
                .oracle()
                .depends_on(read_sarah_note_event, delay_seconds=1)
            )

            # ORACLE Event 6: Agent reads Jennifer's meeting note
            read_jennifer_note_event = (
                notes_app.get_note_by_id(note_id=self.jennifer_note_id)
                .oracle()
                .depends_on(read_marcus_note_event, delay_seconds=1)
            )

            # ORACLE Event 7: Agent creates consolidated summary note
            create_summary_event = (
                notes_app.create_note(
                    folder="Work",
                    title="Client Meeting Summary - Week of Jan 13",
                    content="""Summary of Client Meetings - Week of January 13, 2025

1. Sarah Thompson (Jan 13)
   - Approved Q1 budget proposal with minor adjustments
   - Extended Phase 1 deadline by 2 weeks
   - Allocating 3 additional developers in February

2. Marcus Rodriguez (Jan 15)
   - Approved Phase 2 implementation plan
   - Confirmed REST API technical specs
   - Deployment scheduled for March 15th

3. Jennifer Lee (Jan 17)
   - Agreed on 2-year contract renewal
   - 5% price increase approved
   - Selected Premium support package

All meetings concluded successfully with positive outcomes.""",
                )
                .oracle()
                .depends_on(read_jennifer_note_event, delay_seconds=2)
            )

            # ORACLE Event 8: Agent notifies user of completion
            notify_event = (
                aui.send_message_to_user(
                    content="I've created a consolidated summary of all three client meetings in your Work folder titled 'Client Meeting Summary - Week of Jan 13'."
                )
                .oracle()
                .depends_on(create_summary_event, delay_seconds=1)
            )

            # CONDITION Event: Wait for summary note to be created (starts checking after 100 seconds)
            summary_created_condition = ConditionCheckEvent.from_condition(summary_note_created).delayed(100)

            # ENV Event 2: Colleague emails asking for meeting summary
            colleague_email_event = email_app.send_email_to_user_with_id(
                email_id="email-colleague-summary-request",
                sender="mike.chen@company.com",
                subject="Client Meeting Summary Request",
                content="Hi, I heard you had meetings with Sarah, Marcus, and Jennifer last week. Could you share a summary of the outcomes? I need to update the quarterly report.",
            ).depends_on(summary_created_condition, delay_seconds=10)

            # ORACLE Event 9: Agent proposes to share the summary
            share_proposal_event = (
                aui.send_message_to_user(
                    content="Mike Chen is asking for a summary of your client meetings. I have the consolidated summary ready. Would you like me to share it with him?"
                )
                .oracle()
                .depends_on(colleague_email_event, delay_seconds=2)
            )

            # ORACLE Event 10: User accepts sharing
            share_acceptance_event = (
                aui.accept_proposal(content="Yes, please share the summary with Mike.")
                .oracle()
                .depends_on(share_proposal_event, delay_seconds=2)
            )

            # ORACLE Event 11: Agent replies to email with summary
            reply_email_event = (
                email_app.reply_to_email(
                    email_id="email-colleague-summary-request",
                    content="""Hi Mike,

Here's the summary of client meetings from last week:

1. Sarah Thompson (Jan 13) - Approved Q1 budget with minor adjustments, extended Phase 1 deadline by 2 weeks
2. Marcus Rodriguez (Jan 15) - Approved Phase 2 implementation, deployment scheduled for March 15th
3. Jennifer Lee (Jan 17) - Agreed on 2-year contract renewal with 5% price increase

Let me know if you need any additional details for the quarterly report.

Best regards""",
                )
                .oracle()
                .depends_on(share_acceptance_event, delay_seconds=1)
            )

            # ORACLE Event 12: Agent confirms sharing
            confirm_share_event = (
                aui.send_message_to_user(content="I've shared the meeting summary with Mike Chen via email.")
                .oracle()
                .depends_on(reply_email_event, delay_seconds=1)
            )

        self.events = [
            proposal_event,
            acceptance_event,
            list_notes_event,
            read_sarah_note_event,
            read_marcus_note_event,
            read_jennifer_note_event,
            create_summary_event,
            notify_event,
            summary_created_condition,
            colleague_email_event,
            share_proposal_event,
            share_acceptance_event,
            reply_email_event,
            confirm_share_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent summarizes meeting notes and shares via email."""
        try:
            log_entries = env.event_log.list_view()
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # Check 1: Agent read meeting notes (at least one get_note_by_id or list_notes)
            notes_read = any(
                e.action.class_name == "StatefulNotesApp" and e.action.function_name in ["list_notes", "get_note_by_id"]
                for e in agent_events
            )

            # Check 2: Agent created summary note in Work folder
            summary_created = any(
                e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "create_note"
                and e.action.args.get("folder") == "Work"
                for e in agent_events
            )

            # Check 3: Agent sent proposal to user
            proposal_found = any(
                e.action.class_name == "PAREAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # Check 4: Agent replied to colleague's email
            email_replied = any(
                e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == "email-colleague-summary-request"
                for e in agent_events
            )

            success = notes_read and summary_created and proposal_found and email_replied

            if not success:
                missing = []
                if not notes_read:
                    missing.append("agent did not read meeting notes")
                if not summary_created:
                    missing.append("agent did not create summary note in Work folder")
                if not proposal_found:
                    missing.append("agent did not send proposal to user")
                if not email_replied:
                    missing.append("agent did not reply to colleague's email")
                return ScenarioValidationResult(success=False, rationale="; ".join(missing))

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
