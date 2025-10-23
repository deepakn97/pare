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


@register_scenario("scenario_proactive_file_summary_share")
class ScenarioProactiveFileSummaryShare(Scenario):
    """Proactive file handling and sharing scenario.

    The agent detects a new report email with an attached file, summarizes content, and proposes to share it with a colleague.
    Upon user confirmation, it sends the summary as a message to the colleague.
    """

    start_time: float | None = 0
    duration: float | None = 30

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Setup environment: user interface, email, messaging, and contacts."""
        aui = AgentUserInterface()
        email_client = EmailClientApp()
        contacts = ContactsApp()
        messaging = MessagingApp()
        fs = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))
        calendar = CalendarApp()
        system = SystemApp()

        default_fs_folders(fs)

        # Populate contacts with different individuals
        contacts.add_contact(
            Contact(
                first_name="Lena",
                last_name="Owens",
                phone="+44 987 654 321",
                email="lena.owens@example.com",
                gender=Gender.FEMALE,
                status=Status.EMPLOYED,
                age=32,
            )
        )

        contacts.add_contact(
            Contact(
                first_name="Carlos",
                last_name="Vega",
                phone="+34 938 111 222",
                email="carlos.vega@example.com",
                gender=Gender.MALE,
                status=Status.EMPLOYED,
                age=41,
            )
        )

        self.apps = [aui, email_client, contacts, messaging, fs, calendar, system]

    def build_events_flow(self) -> None:
        """Define scenario flow: receive report email → propose → confirm → share summary."""
        aui = self.get_typed_app(AgentUserInterface)
        email_client = self.get_typed_app(EmailClientApp)
        messaging = self.get_typed_app(MessagingApp)

        conv_carlos = messaging.create_conversation(["Carlos Vega"], title="Report Discussion")

        with EventRegisterer.capture_mode():
            # Event: user asks agent to monitor incoming reports
            evt_intro = aui.send_message_to_agent(
                content="Assistant, please monitor my emails and alert me when a project report arrives."
            ).depends_on(None, delay_seconds=2)

            # Event: receive the report email with an attachment
            evt_mail = email_client.send_email_to_user(
                email=Email(
                    sender="lena.owens@example.com",
                    recipients=[email_client.user_email],
                    subject="Quarterly Project Update",
                    content="Attached is the new quarterly report with performance details.",
                    attachments={"report_q1.pdf": base64.b64encode(b"Q1 metrics summary and charts.")},
                    email_id="q1_report_mail",
                )
            ).depends_on(evt_intro, delay_seconds=5)

            # Agent proactively proposes to summarize and share it
            evt_propose = aui.send_message_to_user(
                content="A new project report arrived from Lena Owens. Would you like me to summarize it and share with Carlos Vega?"
            ).depends_on(evt_mail, delay_seconds=2)

            # User approves the sharing
            evt_user_confirm = aui.send_message_to_agent(
                content="Yes, please summarize and share it with Carlos."
            ).depends_on(evt_propose, delay_seconds=1)

            # Oracle: agent reads document & sends summary message to Carlos
            evt_oracle_msg = (
                messaging.send_message(
                    conversation_id=conv_carlos,
                    content="Summary of the Q1 report from Lena Owens: strong performance in metrics, charts indicate positive growth.",
                )
                .oracle()
                .depends_on(evt_user_confirm, delay_seconds=2)
            )

        self.events = [evt_intro, evt_mail, evt_propose, evt_user_confirm, evt_oracle_msg]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate agent behavior: must both propose and share summary."""
        try:
            events = env.event_log.list_view()

            # Check proposal message
            proposed_summary = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "report" in e.action.args.get("content", "").lower()
                and "share" in e.action.args.get("content", "").lower()
                for e in events
            )

            # Check oracle communication with Carlos Vega
            shared_message = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "MessagingApp"
                and e.action.function_name == "send_message"
                and "summary" in e.action.args.get("content", "").lower()
                and "carlos" in e.action.args.get("content", "").lower()
                for e in events
            )

            return ScenarioValidationResult(success=proposed_summary and shared_message)
        except Exception as ex:
            return ScenarioValidationResult(success=False, exception=ex)
