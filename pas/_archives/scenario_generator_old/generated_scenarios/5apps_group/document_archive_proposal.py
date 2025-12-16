from __future__ import annotations

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.email_client import Email, EmailClientApp
from are.simulation.apps.sandbox_file_system import Files, SandboxLocalFileSystem
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("document_archive_proposal")
class DocumentArchiveProposal(Scenario):
    """Scenario: The agent manages a document archiving workflow.

    The user receives an email with a quarterly report attached.
    The agent downloads the attachment securely, organizes it into a sandbox archive,
    and proposes to share it with a colleague.
    Upon receiving user's explicit consent, the agent forwards the email.
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize all required apps and populate with example data."""
        aui = AgentUserInterface()
        email_client = EmailClientApp()
        system = SystemApp(name="system")
        sandbox_fs = SandboxLocalFileSystem(name="secure_sandbox", sandbox_dir=kwargs.get("sandbox_dir"))
        main_fs = Files(name="shared_drive", sandbox_dir=kwargs.get("sandbox_dir"))

        # Prepare directory structure in both file systems
        sandbox_fs.makedirs("secure_reports", exist_ok=True)
        main_fs.makedirs("team_archives/Q1", exist_ok=True)

        # Populate initial test email
        email_to_recv = Email(
            email_id="mail_001",
            sender="alex@corp.com",
            recipients=["user@company.com"],
            subject="Q1 Financial Report",
            content="Attached is the Q1 Financial Report document.",
            attachments={"Q1_Financial_Report.pdf": b"PDFDATA"},
        )
        email_client.receive_email(email=email_to_recv)

        self.apps = [aui, email_client, system, sandbox_fs, main_fs]

    def build_events_flow(self) -> None:
        """Defining event flow including proactive user interaction and follow-up actions."""
        aui = self.get_typed_app(AgentUserInterface)
        email_client = self.get_typed_app(EmailClientApp)
        sandbox_fs = self.get_typed_app(SandboxLocalFileSystem)
        main_fs = self.get_typed_app(Files)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # Initial message from user
            start_msg = aui.send_message_to_agent(
                content="Can you handle the financial report I just received safely?"
            ).depends_on(None, delay_seconds=1)

            # System retrieves the time when the message was received
            pull_time = system.get_current_time().depends_on(start_msg, delay_seconds=1)

            # Agent reads recent email in inbox
            read_mail = email_client.get_email_by_id(email_id="mail_001", folder_name="INBOX").depends_on(
                pull_time, delay_seconds=1
            )

            # Agent downloads attachment to secure sandbox location
            dl_attachment = email_client.download_attachments(
                email_id="mail_001", folder_name="INBOX", path_to_save="secure_sandbox/secure_reports/"
            ).depends_on(read_mail, delay_seconds=1)

            # Agent makes an archive copy in general team files
            cp_secure = sandbox_fs.ls(path="secure_reports", detail=False).depends_on(dl_attachment, delay_seconds=1)
            mv_to_main = main_fs.mv(
                path1="secure_sandbox/secure_reports/Q1_Financial_Report.pdf",
                path2="shared_drive/team_archives/Q1/Q1_Financial_Report.pdf",
            ).depends_on(cp_secure, delay_seconds=1)

            # Proactive proposal pattern
            propose_action = aui.send_message_to_user(
                content="The Q1 report has been archived. Would you like me to forward it to Sarah for team review?"
            ).depends_on(mv_to_main, delay_seconds=1)

            # User explicit detailed approval
            user_response = aui.send_message_to_agent(
                content="Yes, please share it with Sarah and note the action completion time."
            ).depends_on(propose_action, delay_seconds=1)

            # Agent executes proposed user-approved action (forward email)
            forward_mail = (
                email_client.forward_email(email_id="mail_001", recipients=["sarah@company.com"], folder_name="INBOX")
                .oracle()
                .depends_on(user_response, delay_seconds=1)
            )

            # Agent retrieves current time for logging completion
            confirm_time = system.get_current_time().depends_on(forward_mail, delay_seconds=1)

            # Agent sends summary confirmation to user
            completion_notify = (
                aui.send_message_to_user(content="I've shared the report with Sarah. Task completed and logged.")
                .oracle()
                .depends_on(confirm_time, delay_seconds=1)
            )

        self.events = [
            start_msg,
            pull_time,
            read_mail,
            dl_attachment,
            cp_secure,
            mv_to_main,
            propose_action,
            user_response,
            forward_mail,
            confirm_time,
            completion_notify,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Custom validation that confirms the mail has been forwarded and file archived."""
        try:
            events = env.event_log.list_view()

            forward_confirm = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "EmailClientApp"
                and event.action.function_name == "forward_email"
                and "sarah@company.com" in event.action.args.get("recipients", [])
                for event in events
            )

            proactive_check = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "AgentUserInterface"
                and "forward" in event.action.args.get("content", "").lower()
                for event in events
            )

            file_ops_check = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name in ["Files", "SandboxLocalFileSystem"]
                and event.action.function_name in ["mv", "ls"]
                for event in events
            )

            return ScenarioValidationResult(success=(forward_confirm and proactive_check and file_ops_check))
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
