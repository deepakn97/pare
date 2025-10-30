from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.email_client import Email, EmailClientApp
from are.simulation.apps.sandbox_file_system import Files
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("document_organizer_proactive")
class DocumentOrganizerProactive(Scenario):
    """A proactive document organization scenario using all available applications.

    The agent receives an email with a project document attached, proposes to organize it
    into a categorized folder, and performs file operations accordingly after the user approves.

    The workflow demonstrates:
    - Email management and attachment handling (EmailClientApp)
    - File system organization and validation (Files)
    - Time awareness and waiting logic (SystemApp)
    - Proactive interaction with user (AgentUserInterface)
    """

    start_time: float | None = 0
    duration: float | None = 30

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and populate the applications with email and file system setup."""
        aui = AgentUserInterface()
        email_client = EmailClientApp()
        fs = Files(name="fs", sandbox_dir=kwargs.get("sandbox_dir", "./sandbox"))
        system = SystemApp(name="system")

        # Create base directory structure
        fs.makedirs("Downloads", exist_ok=True)
        fs.makedirs("Documents/Reports", exist_ok=True)

        # Simulate an incoming email with an attached report
        email_client.add_email_to_folder(
            folder_name="INBOX",
            email=Email(
                email_id="proj_report_123",
                sender="alice@team.com",
                recipients=["user@example.com"],
                subject="Q2 Project Documentation",
                content="Please find attached the final Q2 project report for your review.",
                attachments={"Q2_Project_Report.pdf": b"%PDF-1.4 content here"},
            ),
        )

        self.apps = [aui, email_client, fs, system]

    def build_events_flow(self) -> None:
        """Define the chronological interaction flow with proactive behavior."""
        aui = self.get_typed_app(AgentUserInterface)
        email_client = self.get_typed_app(EmailClientApp)
        fs = self.get_typed_app(Files)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # Step 0: User starts the assistance request
            user_request = aui.send_message_to_agent(
                content="Could you help me organize any new project documents I receive via email?"
            ).depends_on(None, delay_seconds=0)

            # Step 1: System retrieves current time (used for timestamp logging)
            get_time = system.get_current_time().depends_on(user_request, delay_seconds=1)

            # Step 2: Agent lists recent emails from INBOX
            list_inbox = email_client.list_emails(folder_name="INBOX", limit=3).depends_on(get_time, delay_seconds=1)

            # Step 3: Agent reads the first email (the one from Alice)
            read_email = email_client.get_email_by_index(idx=0, folder_name="INBOX").depends_on(
                list_inbox, delay_seconds=1
            )

            # Step 4: Agent downloads the attached report to Downloads
            download_attachment = email_client.download_attachments(
                email_id="proj_report_123", folder_name="INBOX", path_to_save="Downloads/"
            ).depends_on(read_email, delay_seconds=1)

            # Step 5: Agent proactively proposes to organize the file
            propose_action = aui.send_message_to_user(
                content="I've saved Alice's Q2 Project Report to Downloads. Would you like me to move it into the Documents/Reports folder for organization?"
            ).depends_on(download_attachment, delay_seconds=1)

            # Step 6: User approves with contextual confirmation
            user_approval = aui.send_message_to_agent(
                content="Yes, please move the report into Documents/Reports and show me the folder structure."
            ).depends_on(propose_action, delay_seconds=2)

            # Step 7: Agent moves the file based on approval (oracle truth)
            move_file = (
                fs.mv(
                    path1="Downloads/Q2_Project_Report.pdf",
                    path2="Documents/Reports/Q2_Project_Report.pdf",
                    recursive=False,
                )
                .oracle()
                .depends_on(user_approval, delay_seconds=1)
            )

            # Step 8: Agent displays the directory tree of Documents folder
            show_tree = fs.tree(path="Documents").oracle().depends_on(move_file, delay_seconds=1)

            # Step 9: Agent reports action completion and current weekday
            confirm_done = aui.send_message_to_user(
                content="The report has been moved successfully. Here's your updated Documents folder structure."
            ).depends_on(show_tree, delay_seconds=1)

            # Step 10: Agent waits for new notifications (simulate idle after task)
            idle_wait = system.wait_for_notification(timeout=5).depends_on(confirm_done, delay_seconds=1)

        self.events = [
            user_request,
            get_time,
            list_inbox,
            read_email,
            download_attachment,
            propose_action,
            user_approval,
            move_file,
            show_tree,
            confirm_done,
            idle_wait,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the document was organized and user was notified."""
        try:
            events = env.event_log.list_view()

            # Check if file move operation occurred to Reports
            file_moved = any(
                isinstance(ev.action, Action)
                and ev.action.function_name == "mv"
                and ev.action.class_name == "Files"
                and "Reports" in ev.action.args["path2"]
                for ev in events
            )

            # Check if agent proactively messaged the user
            proposal_detected = any(
                isinstance(ev.action, Action)
                and ev.action.function_name == "send_message_to_user"
                and "move it into the Documents/Reports" in ev.action.args.get("content", "")
                for ev in events
            )

            # Check if user approved action
            user_approval_sent = any(
                ev.event_type == EventType.USER
                and isinstance(ev.action, Action)
                and "please move the report" in ev.action.args.get("content", "").lower()
                for ev in events
            )

            # Ensure agent displayed final folder confirmation
            displayed_structure = any(
                isinstance(ev.action, Action) and ev.action.function_name == "tree" and ev.action.class_name == "Files"
                for ev in events
            )

            success = file_moved and proposal_detected and user_approval_sent and displayed_structure
            return ScenarioValidationResult(success=success)
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
