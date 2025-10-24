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


@register_scenario("scenario_tutorial_proactive_file_summary")
class ScenarioTutorialProactiveFileSummary(Scenario):
    """Agent receives hint about a report attachment, downloads it, and offers to summarize it."""

    start_time: float | None = 0
    duration: float | None = 22

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate applications with minimal data."""
        agui = AgentUserInterface()
        email_client = EmailClientApp()
        calendar = CalendarApp()
        contacts = ContactsApp()
        fs = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))
        messaging = MessagingApp()
        system = SystemApp()

        default_fs_folders(fs)

        contacts.add_contact(
            Contact(
                first_name="Lara",
                last_name="Hughes",
                phone="+33 497 555 0011",
                email="lara.hughes@example.com",
                gender=Gender.FEMALE,
                status=Status.EMPLOYED,
                age=34,
            )
        )

        contacts.add_contact(
            Contact(
                first_name="James",
                last_name="Willow",
                phone="+33 597 002 8787",
                email="jwillow@example.com",
                gender=Gender.MALE,
                status=Status.EMPLOYED,
                age=40,
            )
        )

        self.apps = [agui, email_client, calendar, contacts, fs, messaging, system]

    def build_events_flow(self) -> None:
        """Create a multi-app proactive flow where the agent proposes summarizing a received document."""
        email_client = self.get_typed_app(EmailClientApp)
        messaging = self.get_typed_app(MessagingApp)
        aui = self.get_typed_app(AgentUserInterface)
        fs = self.get_typed_app(SandboxLocalFileSystem)

        conv_key = messaging.create_conversation(participants=["Lara Hughes"], title="Lara updates")

        with EventRegisterer.capture_mode():
            # Step 1: User instructs assistant
            user_pref = aui.send_message_to_agent(
                content="Assistant, please inform me when I receive any new project report attachments."
            ).depends_on(None, delay_seconds=1)

            # Step 2: Lara messages user about upcoming email
            notify_msg = messaging.add_message(
                conversation_id=conv_key,
                sender="Lara Hughes",
                content="Hi, I just sent you the Q1 project progress. It includes a PDF summary; please check and let me know your thoughts.",
            ).depends_on(user_pref, delay_seconds=3)

            # Step 3: Email with PDF arrives
            report_email = email_client.send_email_to_user(
                email=Email(
                    sender="lara.hughes@example.com",
                    recipients=[email_client.user_email],
                    subject="Quarterly Project Overview",
                    content="Find attached the Q1 project report in PDF. Awaiting your feedback!",
                    attachments={"Q1_report.pdf": base64.b64encode(b"This file contains Q1 data and updates.")},
                    email_id="lara_email_001",
                )
            ).depends_on(notify_msg, delay_seconds=2)

            # Step 4: Agent proactively proposes reading the file
            propose_sum = aui.send_message_to_user(
                content="Lara's report arrived with an attached PDF. Would you like me to summarize its key points?"
            ).depends_on(report_email, delay_seconds=2)

            # Step 5: User confirms
            user_accept = aui.send_message_to_agent(
                content="Yes, please summarize the contents of the PDF file."
            ).depends_on(propose_sum, delay_seconds=2)

            # Step 6: Oracle truth - agent downloads and reads report
            oracle_download = (
                email_client.download_attachments(
                    email_id="lara_email_001", folder_name="INBOX", path_to_save="Downloads/"
                )
                .oracle()
                .depends_on(user_accept, delay_seconds=1)
            )

            oracle_read = (
                fs.read_document(file_path="Downloads/Q1_report.pdf", max_lines=10)
                .oracle()
                .depends_on(oracle_download, delay_seconds=1)
            )

            oracle_notify_summary = (
                aui.send_message_to_user(content="I`ve read the Q1 report and summarized the key updates for you.")
                .oracle()
                .depends_on(oracle_read, delay_seconds=1)
            )

        self.events = [
            user_pref,
            notify_msg,
            report_email,
            propose_sum,
            user_accept,
            oracle_download,
            oracle_read,
            oracle_notify_summary,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate success: ensure the agent downloaded and read document, followed by a confirmation message."""
        try:
            event_log = env.event_log.list_view()
            downloaded = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.function_name == "download_attachments"
                and ev.action.class_name == "EmailClientApp"
                and "lara_email_001" in ev.action.args["email_id"]
                for ev in event_log
            )
            read_action = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "SandboxLocalFileSystem"
                and ev.action.function_name == "read_document"
                and "Q1_report.pdf" in ev.action.args.get("file_path", "")
                for ev in event_log
            )
            message_sent = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "AgentUserInterface"
                and "summary" in ev.action.args.get("content", "").lower()
                for ev in event_log
            )
            return ScenarioValidationResult(success=(downloaded and read_action and message_sent))
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
