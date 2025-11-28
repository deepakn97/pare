from __future__ import annotations

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.email_client import EmailClientApp
from are.simulation.apps.sandbox_file_system import Files, SandboxLocalFileSystem
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("email_to_filesystem_archival")
class EmailToFilesystemArchival(Scenario):
    """A scenario where the agent processes an incoming email report and organizes it locally with contact updates.

    This scenario tests the agent's ability to:
    - Read an incoming email and download attachments
    - Store the attachments in a sandbox file system
    - Update the contact record of the sender
    - Optionally, send a confirmation email back after user approval

    The agent must propose the archival action, receive user confirmation, and then execute it.
    All applications are used in this scenario.
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and populate all available apps with data and setup initial context."""
        aui = AgentUserInterface()
        email_app = EmailClientApp()
        contacts = ContactsApp()
        sandbox_fs = SandboxLocalFileSystem(name="sandbox", sandbox_dir=kwargs.get("sandbox_dir"))
        files_fs = Files(name="main_files", sandbox_dir=kwargs.get("sandbox_dir"))
        system = SystemApp(name="system_clock")

        # Setup contact list
        contacts.add_new_contact(
            first_name="Samuel",
            last_name="Hart",
            gender=Gender.MALE,
            age=35,
            email="samuel.hart@reports.com",
            job="Data Analyst",
            status=Status.EMPLOYED,
            description="Sends weekly data reports",
        )

        # Create directory structuring
        sandbox_fs.makedirs("InboxAttachments/Reports/", exist_ok=True)
        files_fs.makedirs("SharedReports/", exist_ok=True)

        # Simulate existing email in inbox
        email_app.send_email(
            recipients=["user@example.com"],
            subject="Weekly Sales Report",
            content="Please find attached the latest regional sales summary for this week.",
            attachment_paths=["SandboxData/reports/week42_sales.xlsx"],
        )

        self.apps = [aui, email_app, contacts, sandbox_fs, files_fs, system]

    def build_events_flow(self) -> None:
        """Defines the proactive interaction event flow of the scenario."""
        aui = self.get_typed_app(AgentUserInterface)
        email_app = self.get_typed_app(EmailClientApp)
        contacts = self.get_typed_app(ContactsApp)
        sandbox_fs = self.get_typed_app(SandboxLocalFileSystem)
        files_fs = self.get_typed_app(Files)
        system_app = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # Step 0: Time check before the workflow starts
            time_check = system_app.get_current_time().depends_on(None, delay_seconds=0.5)

            # Step 1: User requests archiving of attachments from specific reports
            user_request = aui.send_message_to_agent(
                content="Assistant, whenever I get reports from Samuel Hart, please store them locally in the reports folder and update his contact with timestamp info."
            ).depends_on(time_check, delay_seconds=0.5)

            # Step 2: Simulate new email arrival with attachment
            report_email = email_app.get_email_by_index(idx=0, folder_name="INBOX").depends_on(
                user_request, delay_seconds=2
            )

            # Step 3: Agent proposes to archive and record contact info
            agent_proposal = aui.send_message_to_user(
                content="I've received Samuel Hart's 'Weekly Sales Report' email with an attached spreadsheet. Should I download and store it in your 'Reports' folder and log the update for Samuel?"
            ).depends_on(report_email, delay_seconds=1)

            # Step 4: User approves the archival action
            user_approval = aui.send_message_to_agent(
                content="Yes, please download the attachment, save it under Reports, and note the contact update for Samuel."
            ).depends_on(agent_proposal, delay_seconds=1)

            # Step 5: Agent performs attachment download locally (oracle)
            download_action = (
                email_app.download_attachments(
                    email_id="inbox_report_0", folder_name="INBOX", path_to_save="InboxAttachments/Reports/"
                )
                .depends_on(user_approval, delay_seconds=1)
                .oracle()
            )

            # Step 6: Move downloaded report from sandbox to main files
            move_to_files = (
                sandbox_fs.mv(
                    path1="InboxAttachments/Reports/week42_sales.xlsx", path2="SharedReports/week42_sales.xlsx"
                )
                .depends_on(download_action, delay_seconds=0.5)
                .oracle()
            )

            # Step 7: Update contact record to reflect recent activity
            contact_update = (
                contacts.edit_contact(
                    contact_id="Samuel_Hart_id",
                    updates={
                        "last_updated": "2024-05-10 09:30:00",
                        "description": "Recent report archived successfully",
                    },
                )
                .depends_on(move_to_files, delay_seconds=1)
                .oracle()
            )

            # Step 8: Confirm by sending follow-up email
            send_confirmation = (
                email_app.send_email(
                    recipients=["samuel.hart@reports.com"],
                    subject="Report Archiving Confirmation",
                    content="Hello Samuel, your latest report has been archived successfully. Thank you.",
                )
                .depends_on(contact_update, delay_seconds=1)
                .oracle()
            )

            # Step 9: Verify directory tree and wait for notifications (full-loop)
            verify_fs_tree = sandbox_fs.tree(path="InboxAttachments/Reports/").depends_on(
                send_confirmation, delay_seconds=1
            )
            wait_sync = system_app.wait_for_notification(timeout=3).depends_on(verify_fs_tree, delay_seconds=0.2)

        self.events = [
            time_check,
            user_request,
            report_email,
            agent_proposal,
            user_approval,
            download_action,
            move_to_files,
            contact_update,
            send_confirmation,
            verify_fs_tree,
            wait_sync,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate success via email sent, file archived, and contact updated."""
        try:
            all_events = env.event_log.list_view()

            # Check that an attachment was downloaded and moved
            file_actions_success = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name in ["EmailClientApp", "SandboxLocalFileSystem"]
                and (e.action.function_name == "download_attachments" or e.action.function_name == "mv")
                for e in all_events
            )

            # Check that contact was edited to reflect updates
            contact_edit_logged = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ContactsApp"
                and e.action.function_name == "edit_contact"
                and "Samuel_Hart" in e.action.args.get("contact_id", "")
                for e in all_events
            )

            # Ensure confirmation email was sent back
            confirmation_email_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "EmailClientApp"
                and e.action.function_name == "send_email"
                and "Report Archiving Confirmation" in e.action.args.get("subject", "")
                for e in all_events
            )

            # Ensure the agent proposed the archival to user prior
            proposed_to_user = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "archive" in e.action.args.get("content", "").lower()
                for e in all_events
            )

            success = all([file_actions_success, contact_edit_logged, confirmation_email_sent, proposed_to_user])
            return ScenarioValidationResult(success=success)

        except Exception as err:
            return ScenarioValidationResult(success=False, exception=err)
