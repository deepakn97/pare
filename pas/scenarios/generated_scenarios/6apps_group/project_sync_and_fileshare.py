from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.email_client import Email, EmailClientApp
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.sandbox_file_system import SandboxLocalFileSystem
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("project_sync_and_fileshare")
class ProjectSyncAndFileshare(Scenario):
    """A comprehensive proactive scenario.

    The agent helps the user coordinate a project status meeting by integrating email updates,
    team chat messages, shared summary files, and calendar events.

    Workflow Summary:
    1. The user receives an email update from Morgan with an attachment.
    2. The agent proposes to share the attachment with the team's chat and schedule a sync meeting.
    3. The user confirms.
    4. The agent moves the attachment to a shared folder, shares it in chat,
       and adds a project sync event to the calendar.
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize environment with necessary apps and data."""
        aui = AgentUserInterface()
        system = SystemApp(name="system_time")
        email_client = EmailClientApp()
        calendar = CalendarApp()
        messaging = MessagingApp()
        fs = SandboxLocalFileSystem(name="sandbox_files", sandbox_dir=kwargs.get("sandbox_dir"))

        # Create shared directories
        fs.makedirs(path="Projects/Shared", exist_ok=True)
        fs.makedirs(path="Downloads", exist_ok=True)

        # Add an email to the inbox
        email_client.list_emails(folder_name="INBOX")
        sample_email = Email(
            sender="morgan@company.com",
            recipients=["me@company.com"],
            subject="Weekly Project Update",
            content="Here's the latest project summary report. Please review and share.",
            attachments={"report_summary.docx": b"Report summary data"},
            email_id="email_001",
        )

        email_client._emails = {"INBOX": [sample_email]}
        self.apps = [aui, system, email_client, calendar, messaging, fs]

    def build_events_flow(self) -> None:
        """Define event flow for the proactive scenario."""
        aui = self.get_typed_app(AgentUserInterface)
        email_client = self.get_typed_app(EmailClientApp)
        calendar = self.get_typed_app(CalendarApp)
        messaging = self.get_typed_app(MessagingApp)
        fs = self.get_typed_app(SandboxLocalFileSystem)
        system = self.get_typed_app(SystemApp)

        team_conv_id = messaging.create_conversation(
            participants=["Sam Taylor", "Jamie Lee"], title="Project Sync Team"
        )

        with EventRegisterer.capture_mode():
            user_request = aui.send_message_to_agent(
                content="Assistant, please monitor for any project updates coming from Morgan."
            ).depends_on(None, delay_seconds=1)

            new_email_event = email_client.get_email_by_index(idx=0, folder_name="INBOX").depends_on(
                user_request, delay_seconds=2
            )

            download_event = email_client.download_attachments(
                email_id="email_001", folder_name="INBOX", path_to_save="Downloads/"
            ).depends_on(new_email_event, delay_seconds=1)

            # Agent proposes action (PROACTIVE STEP)
            proactive_proposal = aui.send_message_to_user(
                content="I just received Morgan's project update with a report. "
                "Would you like me to move it to the shared folder, post it to the team chat, "
                "and add a calendar event for a review session?"
            ).depends_on(download_event, delay_seconds=1)

            # User provides contextual approval
            user_approval = aui.send_message_to_agent(
                content="Yes, please share the report with Sam and Jamie and schedule the review tomorrow morning."
            ).depends_on(proactive_proposal, delay_seconds=2)

            # Agent executes multi-app actions
            move_file_event = (
                fs.mv(path1="Downloads/report_summary.docx", path2="Projects/Shared/report_summary.docx")
                .oracle()
                .depends_on(user_approval, delay_seconds=1)
            )

            send_to_chat = (
                messaging.send_attachment(conversation_id=team_conv_id, filepath="Projects/Shared/report_summary.docx")
                .oracle()
                .depends_on(move_file_event, delay_seconds=1)
            )

            # Get system time and use it to set meeting
            fetch_time = system.get_current_time().depends_on(send_to_chat, delay_seconds=1)

            calendar_event = (
                calendar.add_calendar_event(
                    title="Project Summary Review",
                    start_datetime="2024-06-25 09:00:00",
                    end_datetime="2024-06-25 09:30:00",
                    description="Review the latest report with Sam and Jamie.",
                    location="Conference Room B",
                    attendees=["Sam Taylor", "Jamie Lee"],
                    tag="project_review",
                )
                .oracle()
                .depends_on(fetch_time, delay_seconds=1)
            )

        self.events = [
            user_request,
            new_email_event,
            download_event,
            proactive_proposal,
            user_approval,
            move_file_event,
            send_to_chat,
            fetch_time,
            calendar_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validation: Check actions across different apps to confirm task completion."""
        try:
            events = env.event_log.list_view()

            # Check agent proposed to user
            did_propose = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "project update" in e.action.args["content"].lower()
                for e in events
            )

            # Confirm shared file moved
            file_moved = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "Files"
                and e.action.function_name == "mv"
                and "Projects/Shared" in e.action.args["path2"]
                for e in events
            )

            # Confirm message sent in chat
            chat_shared = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "MessagingApp"
                and e.action.function_name == "send_attachment"
                for e in events
            )

            # Confirm calendar event created
            meeting_added = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "CalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Project Summary Review" in e.action.args["title"]
                for e in events
            )

            return ScenarioValidationResult(success=(did_propose and file_moved and chat_shared and meeting_added))
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
