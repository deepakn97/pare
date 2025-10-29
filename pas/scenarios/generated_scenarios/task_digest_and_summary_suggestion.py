from __future__ import annotations

import base64
import uuid
from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp, CalendarEvent
from are.simulation.apps.contacts import Contact, ContactsApp, Gender, Status
from are.simulation.apps.email_client import Email, EmailClientApp
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.sandbox_file_system import SandboxLocalFileSystem
from are.simulation.apps.system import SystemApp
from are.simulation.data.population_scripts.sandbox_file_system_population import default_fs_folders
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("task_digest_and_summary_suggestion")
class ScenarioAutoTaskDigestAndSummarySuggestion(Scenario):
    """Agent reads a weekly summary email, detects tasks, creates reminders, and proposes drafting a summary message."""

    start_time: float | None = 0
    duration: float | None = 50

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize applications and seed with sample data for this scenario."""
        aui = AgentUserInterface()
        email_app = EmailClientApp()
        calendar_app = CalendarApp()
        contacts_app = ContactsApp()
        messenger_app = MessagingApp()
        system_app = SystemApp()
        fs = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))
        default_fs_folders(fs)

        # Add relevant colleagues
        contacts_app.add_contact(
            Contact(
                first_name="Marta",
                last_name="Ionescu",
                email="marta@creativepulse.io",
                phone="+40 722 554 112",
                gender=Gender.FEMALE,
                status=Status.EMPLOYED,
                job="Marketing Specialist",
                city_living="Bucharest",
                country="Romania",
                age=30,
            )
        )
        contacts_app.add_contact(
            Contact(
                first_name="James",
                last_name="Wong",
                email="jwong@creativepulse.io",
                phone="+1 415 445 8823",
                gender=Gender.MALE,
                status=Status.EMPLOYED,
                job="Operations Analyst",
                city_living="San Francisco",
                country="USA",
                age=35,
            )
        )

        self.apps = [aui, email_app, calendar_app, contacts_app, messenger_app, system_app, fs]

    def build_events_flow(self) -> None:
        """Define interactions for digest recognition and follow-up automation."""
        aui = self.get_typed_app(AgentUserInterface)
        mail = self.get_typed_app(EmailClientApp)
        calendar = self.get_typed_app(CalendarApp)
        messaging = self.get_typed_app(MessagingApp)

        team_chat = messaging.create_conversation(
            participants=["Marta Ionescu", "James Wong"], title="Weekly Task Summary Collaboration"
        )

        encoded_attachment = base64.b64encode(b"Final report template for task summaries").decode("utf-8")

        with EventRegisterer.capture_mode():
            # Event 0: User asks the assistant to monitor incoming weekly summary reports
            setup_instruction = aui.send_message_to_agent(
                content="Assistant, please monitor any incoming weekly summary emails and help me create follow-up reminders."
            ).depends_on(None, delay_seconds=1)

            # Event 1: Marta sends a teamwork chat message hinting that she sent a weekly update
            note_in_messenger = messaging.add_message(
                conversation_id=team_chat,
                sender="Marta Ionescu",
                content="Hey team, I just sent the Weekly Progress Digest! Take a look when possible.",
            ).depends_on(setup_instruction, delay_seconds=3)

            # Event 2: Email with multiple tasks arrives
            tasks_email = mail.send_email_to_user(
                email=Email(
                    sender="marta@creativepulse.io",
                    recipients=[mail.user_email],
                    subject="CreativePulse Weekly Digest - Action Items",
                    content=(
                        "Hello,\nHere's our weekly update.\n"
                        "- Prepare Q3 marketing outline\n"
                        "- Review Ops report before Friday\n"
                        "- Send summary back to leadership by Monday.\n\nRegards,\nMarta"
                    ),
                    attachments={"Summary_Template.txt": encoded_attachment},
                    email_id=f"week_digest_{uuid.uuid4()}",
                )
            ).depends_on(note_in_messenger, delay_seconds=2)

            # Event 3: Agent detects actionable items and suggests creating reminders
            agent_suggests_reminders = aui.send_message_to_user(
                content="I've spotted actionable tasks in Marta's 'Weekly Digest'. Would you like me to set reminders for them?"
            ).depends_on(tasks_email, delay_seconds=2)

            # Event 4: User confirms reminder creation
            user_confirms = aui.send_message_to_agent(
                content="Yes, create reminders for each task mentioned."
            ).depends_on(agent_suggests_reminders, delay_seconds=2)

            # Event 5: Oracle actions - adding reminders as events
            reminder_event1 = (
                calendar.add_event(
                    CalendarEvent(
                        title="Prepare Q3 Marketing Outline",
                        start_time="2024-09-09T09:00:00",
                        end_time="2024-09-09T10:00:00",
                        description="From Weekly Digest task list.",
                    )
                )
                .oracle()
                .depends_on(user_confirms, delay_seconds=2)
            )

            reminder_event2 = (
                calendar.add_event(
                    CalendarEvent(
                        title="Review Operations Report",
                        start_time="2024-09-13T10:00:00",
                        end_time="2024-09-13T11:00:00",
                        description="Ensure review before Friday.",
                    )
                )
                .oracle()
                .depends_on(reminder_event1, delay_seconds=1)
            )

            reminder_event3 = (
                calendar.add_event(
                    CalendarEvent(
                        title="Send Leadership Summary",
                        start_time="2024-09-16T08:00:00",
                        end_time="2024-09-16T08:30:00",
                        description="Send weekly summary email to leadership on Monday.",
                    )
                )
                .oracle()
                .depends_on(reminder_event2, delay_seconds=1)
            )

            # Event 6: Assistant sends completion message back to user
            completion_ack = aui.send_message_to_user(
                content="I've created three reminders based on Marta's weekly digest tasks."
            ).depends_on(reminder_event3, delay_seconds=2)

            # Event 7: Agent optionally drafts a message in messenger to confirm task scheduling to Marta and James
            drafted_msg = messaging.send_message(
                conversation_id=team_chat,
                content="Reminders for digest tasks have been created. Everyone should be on track!",
            ).depends_on(completion_ack, delay_seconds=1)

        self.events = [
            setup_instruction,
            note_in_messenger,
            tasks_email,
            agent_suggests_reminders,
            user_confirms,
            reminder_event1,
            reminder_event2,
            reminder_event3,
            completion_ack,
            drafted_msg,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validation checks: Ensure reminders created, user notified, and follow-up posted in messenger."""
        try:
            logs = env.event_log.list_view()

            reminders_found = sum(
                1
                for ev in logs
                if ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "CalendarApp"
                and ev.action.function_name == "add_event"
                and any(word in ev.action.args.get("title", "").lower() for word in ["marketing", "report", "summary"])
            )

            confirmation_shown = any(
                ev.event_type == EventType.AGENT
                and ev.action.class_name == "AgentUserInterface"
                and "three reminders" in ev.action.args.get("content", "").lower()
                for ev in logs
            )

            messenger_followup = any(
                ev.event_type == EventType.AGENT
                and ev.action.class_name == "MessagingApp"
                and "digest tasks" in ev.action.args.get("content", "").lower()
                for ev in logs
            )

            success = reminders_found >= 3 and confirmation_shown and messenger_followup
            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
