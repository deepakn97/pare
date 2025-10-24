from __future__ import annotations

import base64
from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.contacts import Contact, ContactsApp, Gender, Status
from are.simulation.apps.email_client import Email, EmailClientApp
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.sandbox_file_system import SandboxLocalFileSystem
from are.simulation.apps.system import SystemApp
from are.simulation.data.population_scripts.sandbox_file_system_population import default_fs_folders
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("scenario_proactive_followup_documents")
class ScenarioProactiveFollowupDocuments(Scenario):
    """Scenario where the agent proactively helps organize team documents from emails and file system."""

    start_time: float | None = 0
    duration: float | None = 22

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Set up all applications and populate with data."""
        aui = AgentUserInterface()
        email_client = EmailClientApp()
        fs = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))
        contacts = ContactsApp()
        messaging = MessagingApp()
        calendar = CalendarApp()
        system = SystemApp()

        default_fs_folders(fs)

        # Add work contacts
        contacts.add_contact(
            Contact(
                first_name="Samantha",
                last_name="Green",
                email="samantha.green@company.com",
                phone="+1 654 222 1299",
                gender=Gender.FEMALE,
                status=Status.EMPLOYED,
                job="Project Manager",
            )
        )
        contacts.add_contact(
            Contact(
                first_name="Alex",
                last_name="Perez",
                email="alex.perez@company.com",
                phone="+1 654 118 3312",
                gender=Gender.MALE,
                status=Status.EMPLOYED,
                job="Developer",
            )
        )
        contacts.add_contact(
            Contact(
                first_name="Kim",
                last_name="Patel",
                email="kim.patel@company.com",
                phone="+1 654 441 8821",
                gender=Gender.FEMALE,
                status=Status.EMPLOYED,
                job="Designer",
            )
        )

        # Add some existing files
        fs.makedirs("Documents/Reports", exist_ok=True)
        fs.makedirs("Documents/SharedDocs", exist_ok=True)
        fs.makedirs("Downloads", exist_ok=True)
        fs.open("Documents/Reports/old_summary.docx", "wb").close()

        self.apps = [aui, email_client, contacts, fs, messaging, calendar, system]

    def build_events_flow(self) -> None:
        """Define the events of the proactive document organization scenario."""
        aui = self.get_typed_app(AgentUserInterface)
        email_client = self.get_typed_app(EmailClientApp)
        fs = self.get_typed_app(SandboxLocalFileSystem)
        messaging = self.get_typed_app(MessagingApp)

        # conversation for context
        conv_id = messaging.create_conversation(participants=["Samantha Green"], title="Weekly Deliverables Thread")

        with EventRegisterer.capture_mode():
            # Initial user setup message
            e0 = aui.send_message_to_agent(
                content="Assistant, please watch my inbox for project documents and help organize them in the shared folder."
            ).depends_on(None, delay_seconds=1)

            # Samantha sends a related message
            e1 = messaging.add_message(
                conversation_id=conv_id,
                sender="Samantha Green",
                content="Hey, I just sent the new project reports via email. Please make sure Alex and Kim can view them.",
            ).depends_on(e0, delay_seconds=2)

            # Email with attachments arrives
            e2 = email_client.send_email_to_user(
                email=Email(
                    sender="samantha.green@company.com",
                    recipients=[email_client.user_email],
                    subject="Updated Project Reports",
                    content="Hi, here are the new reports for this week. Please upload them to the SharedDocs folder.",
                    attachments={
                        "weekly_update.pdf": base64.b64encode(b"Some project report data"),
                        "design_notes.txt": base64.b64encode(b"Initial design outline"),
                    },
                    email_id="report_email",
                )
            ).depends_on(e1, delay_seconds=2)

            # Agent proactively proposes organizing the files
            propose_event = aui.send_message_to_user(
                content=(
                    "I received Samantha's email with attachments. Would you like me to "
                    "save the files into Documents/SharedDocs?"
                )
            ).depends_on(e2, delay_seconds=1)

            # User confirms
            confirm_event = aui.send_message_to_agent(content="Yes, please sort them into SharedDocs.").depends_on(
                propose_event, delay_seconds=1
            )

            # Oracle file move operations: download attachments then move them
            oracle_download = (
                email_client.download_attachments(
                    email_id="report_email", folder_name="INBOX", path_to_save="Downloads/"
                )
                .oracle()
                .depends_on(confirm_event, delay_seconds=1)
            )

            oracle_move1 = (
                fs.mv(path1="Downloads/weekly_update.pdf", path2="Documents/SharedDocs/weekly_update.pdf")
                .oracle()
                .depends_on(oracle_download, delay_seconds=1)
            )

            oracle_move2 = (
                fs.mv(path1="Downloads/design_notes.txt", path2="Documents/SharedDocs/design_notes.txt")
                .oracle()
                .depends_on(oracle_move1, delay_seconds=1)
            )

        self.events = [e0, e1, e2, propose_event, confirm_event, oracle_download, oracle_move1, oracle_move2]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Verify that the files were placed correctly and the agent confirmed the organization."""
        try:
            event_log = env.event_log.list_view()
            # Check that files were moved to the SharedDocs folder
            correct_moves = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "SandboxLocalFileSystem"
                and e.action.function_name == "mv"
                and "SharedDocs" in e.action.args["path2"]
                for e in event_log
            )
            # Check agent communication
            proactive_message_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "attachments" in e.action.args.get("content", "").lower()
                for e in event_log
            )
            return ScenarioValidationResult(success=(correct_moves and proactive_message_sent))
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
