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


@register_scenario("meeting_note_proposal")
class ScenarioProactiveMeetingNoteProposal(Scenario):
    """Proactive variant: agent detects meeting report email, proposes to summarize and store it."""

    start_time: float | None = 0
    duration: float | None = 30

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate applications with needed test data."""
        agui = AgentUserInterface()
        calendar = CalendarApp()
        email_client = EmailClientApp()
        contacts = ContactsApp()
        fs = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))
        messaging = MessagingApp()
        system = SystemApp()
        default_fs_folders(fs)

        # Populate contacts with relevant people
        contacts.add_contact(
            Contact(
                first_name="Clara",
                last_name="Stevens",
                phone="+33 445 987 0066",
                email="clara.stevens@corporate.com",
                gender=Gender.FEMALE,
                status=Status.EMPLOYED,
                age=32,
            )
        )
        contacts.add_contact(
            Contact(
                first_name="Robert",
                last_name="Nguyen",
                phone="+33 318 554 9292",
                email="robert.nguyen@corporate.com",
                gender=Gender.MALE,
                status=Status.EMPLOYED,
                age=29,
            )
        )

        self.apps = [agui, calendar, email_client, contacts, fs, messaging, system]

    def build_events_flow(self) -> None:
        """Build the series of events defining the proactive scenario."""
        aui = self.get_typed_app(AgentUserInterface)
        email_client = self.get_typed_app(EmailClientApp)
        fs = self.get_typed_app(SandboxLocalFileSystem)
        messaging = self.get_typed_app(MessagingApp)

        conv_key = messaging.create_conversation(participants=["Clara Stevens"], title="Project Sync")

        with EventRegisterer.capture_mode():
            # User message - instruct agent to monitor for meeting summaries
            event0 = aui.send_message_to_agent(
                content="Assistant, keep an eye on my emails and let me know if I get any meeting minutes that need saving."
            ).depends_on(None, delay_seconds=1)

            # Messaging from Clara - context for the meeting
            event1 = messaging.add_message(
                conversation_id=conv_key,
                sender="Clara Stevens",
                content="Hi! I'll send you the recap of our product sync meeting shortly by email.",
            ).depends_on(event0, delay_seconds=2)

            # Clara sends the meeting notes via email
            meeting_note_attachment = base64.b64encode(b"Project discussion notes: budget, next steps").decode("utf-8")
            event2 = email_client.send_email_to_user(
                email=Email(
                    sender="clara.stevens@corporate.com",
                    recipients=[email_client.user_email],
                    subject="Meeting Recap - Product Sync",
                    content="Please find attached the document summarizing today's discussion.",
                    attachments={"ProductSyncNotes.docx": meeting_note_attachment},
                    email_id="clara_meeting_email",
                )
            ).depends_on(event1, delay_seconds=3)

            # Agent proactively proposes to summarize and store notes
            proposal = aui.send_message_to_user(
                content=(
                    "I've received Clara's email with meeting notes. Would you like me to summarize and save this file to your meeting notes folder?"
                )
            ).depends_on(event2, delay_seconds=2)

            # User confirms the action
            user_confirm = aui.send_message_to_agent(
                content="Yes, please summarize and save it in my notes directory."
            ).depends_on(proposal, delay_seconds=2)

            # Oracle event: agent extracts and writes summary to notes file
            oracle_action = (
                fs.open(path="Documents/MeetingNotes/Summary_ProductSync.txt", mode="w")
                .oracle()
                .depends_on(user_confirm, delay_seconds=2)
            )

        self.events = [event0, event1, event2, proposal, user_confirm, oracle_action]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Ensure the scenario was completed correctly."""
        try:
            events = env.event_log.list_view()
            # detect file creation signal
            file_saved = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "SandboxLocalFileSystem"
                and event.action.function_name == "open"
                and "Documents/MeetingNotes" in event.action.args.get("path", "")
                for event in events
            )

            # agent proposed summarization proactively
            proposed_to_user = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "AgentUserInterface"
                and event.action.function_name == "send_message_to_user"
                and "summarize" in event.action.args["content"].lower()
                and "save" in event.action.args["content"].lower()
                for event in events
            )

            return ScenarioValidationResult(success=(file_saved and proposed_to_user))
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
