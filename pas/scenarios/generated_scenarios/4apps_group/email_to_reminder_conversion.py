from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.email_client import Email, EmailClientApp
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("email_to_reminder_conversion")
class EmailToReminderConversion(Scenario):
    """Scenario: The agent helps the user convert an important email request into a reminder.

    Context:
    - The user receives several emails.
    - One of them is a work-related email asking for a report submission.
    - The agent proactively offers to create a reminder for the report.
    - The user approves the action.
    - The agent adds the reminder using ReminderApp.

    This scenario demonstrates the interaction among all available applications:
    - EmailClientApp: To read and search emails.
    - ReminderApp: To create and later list reminders.
    - AgentUserInterface: For proactive proposal and user confirmation.
    - SystemApp: To get current date/time and wait before next actions.
    """

    start_time: float | None = 0
    duration: float | None = 40

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all available apps and populate them with starting data."""
        aui = AgentUserInterface()
        email_client = EmailClientApp()
        reminders = ReminderApp()
        system = SystemApp(name="sys_time")

        # Populate inbox with several emails, one relevant
        email_client._inbox = [
            Email(
                email_id="em001",
                sender="promotion@shoppingworld.com",
                recipients=["user@example.com"],
                subject="Exclusive Offer Just For You",
                content="Get 50% off on electronics this weekend.",
            ),
            Email(
                email_id="em002",
                sender="alex.brown@officecorp.com",
                recipients=["user@example.com"],
                subject="Monthly Report Submission",
                content="Please share the updated project report by tomorrow at 3 PM.",
            ),
            Email(
                email_id="em003",
                sender="newsletter@fitnessdaily.com",
                recipients=["user@example.com"],
                subject="Stay Fit with These 5 Morning Exercises",
                content="Check out our guide for a healthier lifestyle.",
            ),
        ]

        self.apps = [aui, email_client, reminders, system]

    def build_events_flow(self) -> None:
        """Define the sequence of events for the scenario."""
        aui = self.get_typed_app(AgentUserInterface)
        email_client = self.get_typed_app(EmailClientApp)
        reminder_app = self.get_typed_app(ReminderApp)
        system_app = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # User asks agent to check for important tasks in email inbox
            event0 = aui.send_message_to_agent(
                content="Hey Assistant, could you check if I have any important work emails that need action?"
            ).depends_on(None, delay_seconds=1)

            # Agent searches for keywords like 'report' in emails
            event1 = email_client.search_emails(query="report").depends_on(event0, delay_seconds=1)

            # Agent reads the matched email
            event2 = email_client.get_email_by_id(email_id="em002", folder_name="INBOX").depends_on(
                event1, delay_seconds=1
            )

            # Agent retrieves system time for reminder datetime
            event3 = system_app.get_current_time().depends_on(event2, delay_seconds=1)

            # Agent proactively proposes creating a reminder for the report
            agent_proposal = aui.send_message_to_user(
                content=(
                    "I found an email from Alex Brown asking for a report submission by tomorrow. "
                    "Would you like me to create a reminder for this task?"
                )
            ).depends_on(event3, delay_seconds=1)

            # User approves the action
            user_approval = aui.send_message_to_agent(
                content="Yes, please set a reminder for tomorrow noon to finish the report."
            ).depends_on(agent_proposal, delay_seconds=1)

            # Agent adds the reminder based on approved action
            add_reminder_oracle = (
                reminder_app.add_reminder(
                    title="Submit Monthly Report",
                    due_datetime="1970-01-02 12:00:00",
                    description="Reminder to submit the project report to Alex Brown before the deadline.",
                )
                .oracle()
                .depends_on(user_approval, delay_seconds=1)
            )

            # Agent confirms completion to the user
            event_confirm = (
                aui.send_message_to_user(
                    content="Got it. A reminder for 'Submit Monthly Report' has been added for tomorrow noon."
                )
                .oracle()
                .depends_on(add_reminder_oracle, delay_seconds=1)
            )

            # System waits after completion, representing pause until next activity
            event_wait = system_app.wait_for_notification(timeout=3).depends_on(event_confirm, delay_seconds=1)

        self.events = [
            event0,
            event1,
            event2,
            event3,
            agent_proposal,
            user_approval,
            add_reminder_oracle,
            event_confirm,
            event_wait,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the scenario ends successfully with a new reminder created."""
        try:
            events = env.event_log.list_view()
            reminder_created = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "ReminderApp"
                and event.action.function_name == "add_reminder"
                and "Report" in event.action.args["title"]
                for event in events
            )

            user_notified = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "AgentUserInterface"
                and event.action.function_name == "send_message_to_user"
                and "reminder" in event.action.args.get("content", "").lower()
                for event in events
            )

            # Check if system time retrieval happened (SystemApp usage)
            system_used = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "SystemApp"
                and event.action.function_name == "get_current_time"
                for event in events
            )

            return ScenarioValidationResult(success=reminder_created and user_notified and system_used)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
