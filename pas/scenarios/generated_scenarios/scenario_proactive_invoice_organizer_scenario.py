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


@register_scenario("scenario_proactive_invoice_organizer")
class ScenarioProactiveInvoiceOrganizer(Scenario):
    """Agent identifies a new invoice email and offers to extract billing information, file it, and set a calendar reminder."""

    start_time: float | None = 0
    duration: float | None = 45

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the core applications for the invoice scenario."""
        aui = AgentUserInterface()
        calendar_app = CalendarApp()
        contacts_app = ContactsApp()
        email_app = EmailClientApp()
        messaging_app = MessagingApp()
        fs_app = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))
        system_app = SystemApp()
        default_fs_folders(fs_app)

        # Add sample contacts relevant to invoices
        contacts_app.add_contact(
            Contact(
                first_name="Raj",
                last_name="Mehta",
                phone="+91 99888 12345",
                email="raj.mehta@billsync.co",
                gender=Gender.MALE,
                status=Status.SELF_EMPLOYED,
                job="Freelance Consultant",
                age=38,
                city_living="Mumbai",
                country="India",
            )
        )
        contacts_app.add_contact(
            Contact(
                first_name="Nina",
                last_name="Lopez",
                phone="+1 415 555 0890",
                email="nina.lopez@greenenergy.org",
                gender=Gender.FEMALE,
                status=Status.EMPLOYED,
                job="Accounting Manager",
                age=40,
                city_living="San Francisco",
                country="USA",
            )
        )

        self.apps = [aui, calendar_app, contacts_app, email_app, messaging_app, fs_app, system_app]

    def build_events_flow(self) -> None:
        """Define event sequence: user enables smart invoice organization, invoice is received, agent reacts."""
        aui = self.get_typed_app(AgentUserInterface)
        email_app = self.get_typed_app(EmailClientApp)
        messaging_app = self.get_typed_app(MessagingApp)
        fs_app = self.get_typed_app(SandboxLocalFileSystem)
        calendar_app = self.get_typed_app(CalendarApp)

        chat_thread = messaging_app.create_conversation(participants=["Nina Lopez"], title="Work Expenses Coordination")

        with EventRegisterer.capture_mode():
            # Initial instruction
            ev0 = aui.send_message_to_agent(
                content="From now on, please help me organize any invoice emails and remind me about due dates."
            ).depends_on(None, delay_seconds=1)

            # Nina messages on chat saying she will send an invoice
            ev1 = messaging_app.add_message(
                conversation_id=chat_thread,
                sender="Nina Lopez",
                content="I just sent the latest renewable energy consulting invoice via email.",
            ).depends_on(ev0, delay_seconds=2)

            # Simulated incoming email with invoice attachment
            pdf_bytes = base64.b64encode(
                b"Invoice #33: GreenEnergy Consulting Services, Total: $1,250, Due: July 21st, 2024"
            ).decode("utf-8")

            ev2 = email_app.send_email_to_user(
                email=Email(
                    sender="nina.lopez@greenenergy.org",
                    recipients=[email_app.user_email],
                    subject="Invoice #33 for June Consulting Services",
                    content="Hello, attached is the invoice for June`s renewable consulting support.",
                    attachments={"Invoice33.pdf": pdf_bytes},
                    email_id="greenenergy_invoice_2024_06",
                )
            ).depends_on(ev1, delay_seconds=3)

            # Agent detects new invoice email and suggests extraction
            ev3 = aui.send_message_to_user(
                content=(
                    "I noticed an invoice email from Nina Lopez. Would you like me to extract total amount and due date, "
                    "store a text summary, and schedule a payment reminder?"
                )
            ).depends_on(ev2, delay_seconds=2)

            # User approval
            ev4 = aui.send_message_to_agent(
                content="Yes, extract and save it under my Financials directory, and add a payment reminder."
            ).depends_on(ev3, delay_seconds=2)

            # Oracle: file created
            ev5 = (
                fs_app.open(path="Documents/Financials/Invoice33_Summary.txt", mode="w")
                .oracle()
                .depends_on(ev4, delay_seconds=3)
            )

            # Oracle: reminder on calendar added
            ev6 = (
                calendar_app.add_event(
                    title="Pay GreenEnergy Invoice #33",
                    start_time="2024-07-20T09:00:00",
                    end_time="2024-07-20T09:15:00",
                    description="Payment reminder for consulting invoice.",
                )
                .oracle()
                .depends_on(ev5, delay_seconds=2)
            )

            # Confirmation message to communication channel
            ev7 = messaging_app.send_message(
                conversation_id=chat_thread,
                content="Hi Nina, I've logged your invoice and scheduled my payment reminder. Thanks!",
            ).depends_on(ev6, delay_seconds=2)

        self.events = [ev0, ev1, ev2, ev3, ev4, ev5, ev6, ev7]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate arrangement: agent detected invoice, created file, added calendar event, and confirmed communication."""
        try:
            logs = env.event_log.list_view()

            proactive_detection = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "AgentUserInterface"
                and "invoice" in ev.action.args.get("content", "").lower()
                and "extract" in ev.action.args.get("content", "").lower()
                for ev in logs
            )

            summary_created = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "SandboxLocalFileSystem"
                and ev.action.function_name == "open"
                and "Financials" in ev.action.args.get("path", "")
                for ev in logs
            )

            calendar_set = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "CalendarApp"
                and ev.action.function_name == "add_event"
                and "invoice" in ev.action.args.get("title", "").lower()
                for ev in logs
            )

            reply_sent = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "MessagingApp"
                and "logged your invoice" in ev.action.args.get("content", "").lower()
                for ev in logs
            )

            success = proactive_detection and summary_created and calendar_set and reply_sent
            return ScenarioValidationResult(success=success)

        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
