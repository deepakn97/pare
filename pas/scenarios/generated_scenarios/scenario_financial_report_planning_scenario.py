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
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType


@register_scenario("scenario_financial_report_planning")
class ScenarioFinancialReportPlanning(Scenario):
    """Scenario: The agent helps the user organize financial report attachments from an email.

    and adds a related planning meeting on the calendar.
    """

    start_time: float | None = 0
    duration: float | None = 35

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize applications and create sample setup."""
        aui = AgentUserInterface()
        calendar = CalendarApp()
        contacts = ContactsApp()
        email_client = EmailClientApp()
        messaging = MessagingApp()
        filesystem = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))
        system = SystemApp()
        default_fs_folders(filesystem)

        # Add a finance manager and colleague
        contacts.add_contact(
            Contact(
                first_name="Renee",
                last_name="Hartman",
                email="renee.hartman@finwise.org",
                phone="+1 714 990 4581",
                status=Status.EMPLOYED,
                job="Finance Manager",
                gender=Gender.FEMALE,
            )
        )
        contacts.add_contact(
            Contact(
                first_name="Leo",
                last_name="Burke",
                email="leo.burke@finwise.org",
                phone="+1 714 734 6655",
                status=Status.EMPLOYED,
                job="Accountant",
                gender=Gender.MALE,
            )
        )

        self.apps = [aui, calendar, contacts, email_client, messaging, filesystem, system]

    def build_events_flow(self) -> None:
        """Construct the sequence of actions for the financial report scenario."""
        aui = self.get_typed_app(AgentUserInterface)
        email_client = self.get_typed_app(EmailClientApp)
        filesystem = self.get_typed_app(SandboxLocalFileSystem)
        calendar = self.get_typed_app(CalendarApp)

        finance_folder = f"FinanceReport_{uuid.uuid4().hex[:6]}"

        with EventRegisterer.capture_mode():
            # 1. User instructs the assistant to highlight reports from Renee
            start_cmd = aui.send_message_to_agent(
                content="Assistant, please notify me if Renee sends this month's financial reports."
            ).depends_on(None, delay_seconds=1)

            # 2. Renee sends the financial email with multiple files
            report_email = email_client.send_email_to_user(
                email=Email(
                    sender="renee.hartman@finwise.org",
                    recipients=[email_client.user_email],
                    subject="Monthly Financials - May Summary Attached",
                    content=(
                        "Here are the May financial documents. Please review them before our planning call. "
                        "Include Leo if you have questions."
                    ),
                    attachments={
                        "May_Report.pdf": base64.b64encode(b"Confidential May results").decode("utf-8"),
                        "Expense_Breakdown.xlsx": base64.b64encode(b"Raw spending data for May").decode("utf-8"),
                    },
                    email_id="email_" + uuid.uuid4().hex[:5],
                )
            ).depends_on(start_cmd, delay_seconds=2)

            # 3. The agent observes the mail and offers organizational help
            agent_proposes = aui.send_message_to_user(
                content=(
                    "Renee just sent the May financial documents. "
                    "Would you like me to create a 'FinanceReport' folder in your workspace "
                    "and schedule a planning meeting on Friday at 4 PM?"
                )
            ).depends_on(report_email, delay_seconds=2)

            # 4. User approves assistant`s proposal
            user_accepts = aui.send_message_to_agent(
                content="Yes, that sounds good. Please prepare that folder and meeting."
            ).depends_on(agent_proposes, delay_seconds=1)

            # 5. Oracle actions - create folder and copy attachments
            make_dir = (
                filesystem.makedirs(path=finance_folder, exist_ok=True)
                .oracle()
                .depends_on(user_accepts, delay_seconds=1)
            )
            copy_first = (
                filesystem.cp(path1="Downloads/May_Report.pdf", path2=f"{finance_folder}/May_Report.pdf")
                .oracle()
                .depends_on(make_dir, delay_seconds=1)
            )
            copy_second = (
                filesystem.cp(
                    path1="Downloads/Expense_Breakdown.xlsx", path2=f"{finance_folder}/Expense_Breakdown.xlsx"
                )
                .oracle()
                .depends_on(copy_first, delay_seconds=1)
            )

            # 6. Oracle actions - add planning meeting to the calendar
            create_meeting = (
                calendar.add_calendar_event(
                    title="May Financial Planning Review",
                    start_datetime="1970-01-09 16:00:00",
                    end_datetime="1970-01-09 17:00:00",
                    description="Discuss May results and next month`s budget with Renee and Leo.",
                    tag="finance",
                )
                .oracle()
                .depends_on(copy_second, delay_seconds=2)
            )

        self.events = [
            start_cmd,
            report_email,
            agent_proposes,
            user_accepts,
            make_dir,
            copy_first,
            copy_second,
            create_meeting,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Ensure the financial folder and meeting were created as planned."""
        try:
            logs = env.event_log.list_view()

            # Folder creation evidence
            dir_created = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "SandboxLocalFileSystem"
                and e.action.function_name == "makedirs"
                for e in logs
            )

            # Check that both files were copied
            pdf_copied = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "SandboxLocalFileSystem"
                and "May_Report.pdf" in str(e.action.args)
                for e in logs
            )
            xlsx_copied = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "SandboxLocalFileSystem"
                and "Expense_Breakdown.xlsx" in str(e.action.args)
                for e in logs
            )

            # Verify meeting creation
            meeting_added = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "CalendarApp"
                and "Financial Planning Review" in str(e.action.args)
                for e in logs
            )

            # Verify assistant suggested both folder and meeting
            assistant_prompt = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "AgentUserInterface"
                and "folder" in e.action.args.get("content", "").lower()
                and "meeting" in e.action.args.get("content", "").lower()
                for e in logs
            )

            success = dir_created and pdf_copied and xlsx_copied and meeting_added and assistant_prompt
            return ScenarioValidationResult(success=success)

        except Exception as err:
            return ScenarioValidationResult(success=False, exception=err)
