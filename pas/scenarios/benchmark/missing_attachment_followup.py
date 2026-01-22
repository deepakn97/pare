"""Scenario: Agent detects missing attachment and follows up with sender."""

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

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulEmailApp,
    StatefulReminderApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("missing_attachment_followup")
class MissingAttachmentFollowup(PASScenario):
    """Agent detects missing attachment in document review request and proactively follows up with sender.

    The user receives an email from colleague Sarah Park requesting urgent review of a project proposal
    document by November 22nd. The email mentions an attached document ("please see the attached proposal"),
    but no attachment is actually present. The agent detects the missing attachment, proposes following up
    with Sarah, sends the follow-up email after user acceptance, waits for Sarah's reply with the attachment,
    creates a reminder for the November 22nd review deadline, and notifies the user.

    This scenario exercises attachment validation, proactive communication for incomplete requests,
    multi-turn email coordination, and reminder-based deadline tracking.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails", user_email="user@example.com")

        # Initialize reminder app for deadline tracking
        self.reminder = StatefulReminderApp(name="Reminders")

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.reminder]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")

        # Condition: Check if agent replied to Sarah's email asking for the attachment
        def agent_replied_to_sarah(env: AbstractEnvironment) -> bool:
            """Check if agent sent a reply to Sarah's email about the missing attachment."""
            for event in env.event_log.list_view():
                if (
                    event.event_type == EventType.AGENT
                    and isinstance(event.action, Action)
                    and event.action.class_name == "StatefulEmailApp"
                    and event.action.function_name == "reply_to_email"
                    and event.action.args.get("email_id") == "email-sarah-missing-attachment"
                ):
                    return True
            return False

        with EventRegisterer.capture_mode():
            # Environment Event 1: Initial email from Sarah mentioning attachment but without one
            initial_email_event = email_app.send_email_to_user_with_id(
                email_id="email-sarah-missing-attachment",
                sender="sarah.park@example.com",
                subject="Urgent: Project Proposal Review Needed",
                content="Hi! I need your review on the project proposal by November 22nd. Please see the attached proposal and let me know your thoughts by the deadline. This is time-sensitive for our client meeting.",
            ).delayed(20)

            # Oracle Event 1: Agent proposes following up about missing attachment
            proposal_event = (
                aui.send_message_to_user(
                    content="Sarah Park sent an email requesting review of a project proposal by November 22nd. The email mentions an attachment, but no file is attached. Would you like me to follow up with Sarah to request the missing document?"
                )
                .oracle()
                .depends_on(initial_email_event, delay_seconds=3)
            )

            # Oracle Event 2: User accepts proposal
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please ask Sarah to send the document, and add a reminder for the deadline."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent sends follow-up email to Sarah
            followup_email_event = (
                email_app.reply_to_email(
                    email_id="email-sarah-missing-attachment",
                    content="Hi Sarah, I'd be happy to review the proposal by November 22nd. However, I don't see any attachment in your email. Could you please resend the document?",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Condition Event: Wait for agent to actually reply to Sarah's email
            # This triggers when agent sends any reply to Sarah's email (works in non-oracle mode too)
            agent_replied_condition = ConditionCheckEvent.from_condition(agent_replied_to_sarah).depends_on(
                initial_email_event, delay_seconds=10
            )

            # Environment Event 2: Sarah's reply with the actual attachment
            # Depends on condition (agent replied) not oracle event
            sarah_reply_event = email_app.reply_to_email_from_user(
                sender="sarah.park@example.com",
                email_id="email-sarah-missing-attachment",
                content="Oh no, sorry about that! Here's the proposal document attached. Thanks for catching that!",
                attachment_paths=["proposal_document.pdf"],
            ).depends_on(agent_replied_condition, delay_seconds=30)

            # Oracle Event 4: Agent creates reminder for review deadline
            reminder_event = (
                reminder_app.add_reminder(
                    title="Review Project Proposal for Sarah Park",
                    due_datetime="2025-11-22 09:00:00",
                    description="Deadline to review project proposal from Sarah Park",
                )
                .oracle()
                .depends_on(sarah_reply_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent notifies user that document arrived and deadline is tracked
            completion_notification_event = (
                aui.send_message_to_user(
                    content="Sarah Park has sent the project proposal document. I've added a reminder for November 22nd to ensure you review it by the deadline."
                )
                .oracle()
                .depends_on(reminder_event, delay_seconds=1)
            )

        self.events = [
            initial_email_event,
            proposal_event,
            acceptance_event,
            followup_email_event,
            agent_replied_condition,
            sarah_reply_event,
            reminder_event,
            completion_notification_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects missing attachment and completes follow-up workflow."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1: Agent sent proposal about missing attachment
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 2: Agent sent follow-up email to Sarah
            followup_email_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == "email-sarah-missing-attachment"
                for e in log_entries
            )

            # Check 3: Agent created reminder for November 22nd deadline
            reminder_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulReminderApp"
                and e.action.function_name == "add_reminder"
                and "2025-11-22" in e.action.args.get("due_datetime", "")
                for e in log_entries
            )

            success = proposal_found and followup_email_found and reminder_found

            if not success:
                missing = []
                if not proposal_found:
                    missing.append("proposal about missing attachment")
                if not followup_email_found:
                    missing.append("follow-up email to Sarah")
                if not reminder_found:
                    missing.append("reminder for November 22nd deadline")
                return ScenarioValidationResult(success=False, rationale=f"Missing: {', '.join(missing)}")

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
