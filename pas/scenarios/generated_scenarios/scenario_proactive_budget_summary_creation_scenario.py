from __future__ import annotations

import base64
import uuid
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


@register_scenario("scenario_proactive_budget_summary_creation")
class ScenarioProactiveBudgetSummaryCreation(Scenario):
    """Proactive variant: the agent detects a financial summary email and offers to store an annual report file."""

    start_time: float | None = 0
    duration: float | None = 40

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize applications and load contextual data."""
        aui = AgentUserInterface()
        calendar = CalendarApp()
        email_app = EmailClientApp()
        contacts_app = ContactsApp()
        messenger = MessagingApp()
        fs_app = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))
        sys_app = SystemApp()
        default_fs_folders(fs_app)

        # Create relevant company contacts
        contacts_app.add_contact(
            Contact(
                first_name="Sanjay",
                last_name="Patel",
                phone="+1 760 444 6677",
                email="sanjay.patel@financeplus.com",
                gender=Gender.MALE,
                status=Status.EMPLOYED,
                age=40,
            )
        )
        contacts_app.add_contact(
            Contact(
                first_name="Diana",
                last_name="Miller",
                phone="+1 760 555 8723",
                email="diana.miller@financeplus.com",
                gender=Gender.FEMALE,
                status=Status.EMPLOYED,
                age=35,
            )
        )

        self.apps = [aui, calendar, email_app, contacts_app, messenger, fs_app, sys_app]

    def build_events_flow(self) -> None:
        """Define all relevant events for the proactive finance report scenario."""
        aui = self.get_typed_app(AgentUserInterface)
        email_app = self.get_typed_app(EmailClientApp)
        fs_app = self.get_typed_app(SandboxLocalFileSystem)
        messenger = self.get_typed_app(MessagingApp)

        chat_finance = messenger.create_conversation(participants=["Diana Miller"], title="Finance Reports Discussion")

        file_token = str(uuid.uuid4())
        encoded_data = base64.b64encode(b"Consolidated Q1-Q4 financial report with revenue highlights").decode("utf-8")

        with EventRegisterer.capture_mode():
            # User instructs assistant to keep tabs on financial updates
            start_event = aui.send_message_to_agent(
                content="Assistant, please monitor for yearly financial report emails and help store summaries securely."
            ).depends_on(None, delay_seconds=1)

            # Diana sends instant message
            message_event = messenger.add_message(
                conversation_id=chat_finance,
                sender="Diana Miller",
                content="Hi, I'm sending you the annual report file via email right now.",
            ).depends_on(start_event, delay_seconds=3)

            # Email from Diana arrives with attachment
            email_event = email_app.send_email_to_user(
                email=Email(
                    sender="diana.miller@financeplus.com",
                    recipients=[email_app.user_email],
                    subject="2024 Financial Summary - Confidential",
                    content="Attached is the yearly summary document. Please handle with care.",
                    attachments={f"Finance_Report_{file_token}.pdf": encoded_data},
                    email_id="annual_financial_email",
                )
            ).depends_on(message_event, delay_seconds=3)

            # Agent proactively proposes an organized action based on detected attachment
            propose_event = aui.send_message_to_user(
                content=(
                    "I've noticed an incoming mail with the annual financial summary from Diana. "
                    "Would you like me to place a summarized copy into your Finance/Reports folder?"
                )
            ).depends_on(email_event, delay_seconds=2)

            # User confirms the organization proposal
            confirmation_event = aui.send_message_to_agent(
                content="Yes, please generate a summarized report and save it in my finance reports directory."
            ).depends_on(propose_event, delay_seconds=2)

            # Agent (oracle) performs file creation in sandbox
            oracle_write_event = (
                fs_app.open(path="Documents/Finance/Reports/Annual_Summary_2024.txt", mode="w")
                .oracle()
                .depends_on(confirmation_event, delay_seconds=2)
            )

            # Agent replies to user confirming completion
            done_event = aui.send_message_to_user(
                content="I`ve generated and placed the summarized financial report under Documents/Finance/Reports."
            ).depends_on(oracle_write_event, delay_seconds=2)

        self.events = [
            start_event,
            message_event,
            email_event,
            propose_event,
            confirmation_event,
            oracle_write_event,
            done_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Check if proactive summary suggestion and file creation occurred."""
        try:
            log_entries = env.event_log.list_view()

            # Proactive suggestion check
            suggestion_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "financial" in e.action.args.get("content", "").lower()
                and "summary" in e.action.args.get("content", "").lower()
                for e in log_entries
            )

            # File generation check
            file_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "SandboxLocalFileSystem"
                and e.action.function_name == "open"
                and "Finance/Reports/Annual_Summary_2024.txt" in e.action.args.get("path", "")
                for e in log_entries
            )

            return ScenarioValidationResult(success=(suggestion_found and file_created))
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
