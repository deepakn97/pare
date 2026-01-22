"""Scenario: Agent sends personalized follow-up messages triggered by a reminder."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulMessagingApp,
)
from pas.apps.note import StatefulNotesApp
from pas.apps.reminder import StatefulReminderApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("reminder_triggered_followup_batch")
class ReminderTriggeredFollowupBatch(PASScenario):
    """Agent sends personalized follow-up messages to multiple contacts based on a task note when triggered by a reminder.

    The user has a note titled "Project Follow-ups" in the Work folder containing a task list with
    three contacts and their associated topics. A reminder triggers to send follow-up messages.
    The agent reads the note, identifies the contacts, and sends personalized messages to each.

    Flow:
    1. Reminder becomes due (triggers agent attention)
    2. Agent proposes to send follow-up messages based on the note content
    3. User accepts
    4. Agent sends personalized messages to Sarah Kim, Alex Chen, and Jordan Martinez
    5. Agent confirms completion

    This scenario exercises reminder-triggered proactive action, cross-app task extraction from
    notes to drive messaging workflows, and personalized multi-recipient outbound communication.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    additional_system_prompt = """You have a reminder set to send follow-up messages and a note titled 'Project Follow-ups' with three tasks.

BEFORE the reminder notification arrives:
- Navigate to the Messages app to check your conversations
- Do NOT accept any proposals from the agent

AFTER the reminder notification arrives:

ACCEPT proposals that:
- Identify all three contacts: Sarah Kim, Alex Chen, and Jordan Martinez
- Associate the correct topic with each contact (Sarah: Q1 roadmap, Alex: API integration timeline, Jordan: design mockups)

REJECT proposals that:
- Arrive before you receive the reminder notification
- Miss any of the three contacts
- Associate wrong topics with contacts (e.g., asking Sarah about design mockups)
- Offer to send a generic message to all contacts instead of personalized ones"""

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize ReminderApp with follow-up reminder due shortly after start_time
        self.reminder = StatefulReminderApp(name="Reminders")
        self.reminder.add_reminder(
            title="Send follow-up messages",
            due_datetime="2025-11-18 09:01:00",
            description="Follow up with Sarah, Alex, and Jordan about their project items",
        )

        # Initialize NotesApp with the follow-up task list
        self.notes = StatefulNotesApp(name="Notes")
        self.notes.create_note_with_time(
            folder="Work",
            title="Project Follow-ups",
            content="Follow up with Sarah Kim about the Q1 roadmap, Alex Chen about the API integration timeline, and Jordan Martinez about the design mockups.",
            created_at="2025-11-17 10:00:00",
            updated_at="2025-11-17 10:00:00",
        )

        # Initialize MessagingApp with the contacts
        self.messaging = StatefulMessagingApp(name="Messages")
        self.messaging.add_users(["Sarah Kim", "Alex Chen", "Jordan Martinez"])

        # Store user IDs for use in build_events_flow and validation
        self.sarah_id = self.messaging.name_to_id["Sarah Kim"]
        self.alex_id = self.messaging.name_to_id["Alex Chen"]
        self.jordan_id = self.messaging.name_to_id["Jordan Martinez"]

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.reminder, self.notes, self.messaging]

    def build_events_flow(self) -> None:
        """Build event flow - reminder-triggered follow-up messaging."""
        aui = self.get_typed_app(PASAgentUserInterface)
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")

        with EventRegisterer.capture_mode():
            # Oracle Event 1: Agent proposes to send follow-up messages after reminder becomes due
            proposal_event = (
                aui.send_message_to_user(
                    content="Your reminder to send follow-up messages is due. I found your 'Project Follow-ups' note with three tasks: contacting Sarah Kim about the Q1 roadmap, Alex Chen about the API integration timeline, and Jordan Martinez about the design mockups. Would you like me to send these follow-up messages now?"
                )
                .oracle()
                .delayed(80)
            )

            # Oracle Event 2: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please send all three follow-up messages.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent sends message to Sarah Kim
            send_sarah_event = (
                messaging_app.send_message(
                    user_id=self.sarah_id,
                    content="Hi Sarah, just following up on the Q1 roadmap. Do you have any updates you can share?",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent sends message to Alex Chen
            send_alex_event = (
                messaging_app.send_message(
                    user_id=self.alex_id,
                    content="Hi Alex, checking in on the API integration timeline. How is progress looking?",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent sends message to Jordan Martinez
            send_jordan_event = (
                messaging_app.send_message(
                    user_id=self.jordan_id,
                    content="Hi Jordan, following up on the design mockups. Are they ready for review?",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent confirms completion to user
            completion_event = (
                aui.send_message_to_user(
                    content="All three follow-up messages have been sent successfully to Sarah, Alex, and Jordan."
                )
                .oracle()
                .depends_on([send_sarah_event, send_alex_event, send_jordan_event], delay_seconds=3)
            )

        self.events = [
            proposal_event,
            acceptance_event,
            send_sarah_event,
            send_alex_event,
            send_jordan_event,
            completion_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent sends follow-up messages after user approval."""
        try:
            log_entries = env.event_log.list_view()

            # Essential outcome 1: Agent sent proposal to user
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Essential outcome 2: Agent sent message to Sarah Kim about Q1 roadmap
            sarah_message_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == self.sarah_id
                and "roadmap" in e.action.args.get("content", "").lower()
                for e in log_entries
            )

            # Essential outcome 3: Agent sent message to Alex Chen about API integration
            alex_message_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == self.alex_id
                and "api" in e.action.args.get("content", "").lower()
                for e in log_entries
            )

            # Essential outcome 4: Agent sent message to Jordan Martinez about design mockups
            jordan_message_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == self.jordan_id
                and (
                    "design" in e.action.args.get("content", "").lower()
                    or "mockup" in e.action.args.get("content", "").lower()
                )
                for e in log_entries
            )

            success = proposal_found and sarah_message_sent and alex_message_sent and jordan_message_sent

            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("proposal to user")
                if not sarah_message_sent:
                    missing_checks.append("message to Sarah Kim about roadmap")
                if not alex_message_sent:
                    missing_checks.append("message to Alex Chen about API")
                if not jordan_message_sent:
                    missing_checks.append("message to Jordan Martinez about design/mockups")
                rationale = f"Missing: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
