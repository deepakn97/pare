from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulEmailApp,
)
from pas.apps.note import StatefulNotesApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("note_attachment_email_forwarding")
class NoteAttachmentEmailForwarding(PASScenario):
    """Agent forwards note attachments via email based on incoming request.

    The user has organized project documentation in a note titled "Q1 Budget Planning" stored in the "Work" folder, which includes financial spreadsheets and timeline documents attached to the note. A colleague sends an email requesting these specific budget documents for an upcoming stakeholder meeting. The agent must:
    1. Parse the document request from the incoming email (identifies "Q1 Budget Planning" materials)
    2. Search notes in the Work folder to locate the requested note by title
    3. Open the note and list its attachments to identify relevant files
    4. Compose a reply email to the colleague
    5. Attach the files from the note to the email reply
    6. Send the email with confirmation message

    This scenario exercises cross-app information retrieval (notes → email), attachment handling across apps, contextual email composition with file transfers, and note search/navigation based on external requests..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with baseline data for the note attachment email forwarding scenario.

        Baseline state:
        - Notes: "Q1 Budget Planning" note in Work folder with two attachments (Q1_Budget_2026.xlsx, Q1_Timeline.pdf)
        - Email: Historical email from sarah.chen@company.com confirming the Q1 planning meeting
        """
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps here
        self.note = StatefulNotesApp(name="Notes")
        self.email = StatefulEmailApp(name="Emails")

        # Notes: Create the "Q1 Budget Planning" note in the Work folder with attachments
        self.q1_budget_note_id = self.note.create_note_with_time(
            folder="Work",
            title="Q1 Budget Planning",
            content="Budget planning documents for Q1 2026:\n\n- Financial projections spreadsheet\n- Timeline and milestones\n- Resource allocation breakdown\n\nAttachments include detailed spreadsheets and timeline documents for the stakeholder meeting.",
            created_at="2025-11-10 14:30:00",
            updated_at="2025-11-15 16:45:00",
        )

        # Add attachments to the note by directly modifying the note object
        import base64

        work_folder = self.note.folders["Work"]
        note = work_folder.get_note_by_id(self.q1_budget_note_id)
        if note:
            # Simulate attachments with base64-encoded placeholder data (store as bytes to match Note.attachments typing)
            note.attachments = {
                "Q1_Budget_2026.xlsx": base64.b64encode(
                    b"[Simulated Excel spreadsheet content for Q1 2026 budget projections and financial analysis]"
                ),
                "Q1_Timeline.pdf": base64.b64encode(
                    b"[Simulated PDF document containing Q1 2026 project timeline, milestones, and resource allocation schedule]"
                ),
            }

        # Email: Seed historical context - a previous email thread about Q1 planning
        self.email.create_and_add_email_with_time(
            sender="sarah.chen@company.com",
            recipients=[self.email.user_email],
            subject="Q1 Planning Meeting Scheduled",
            content="Hi Alex,\n\nJust confirming that our Q1 planning meeting with stakeholders is scheduled for next week. Looking forward to reviewing the budget documents.\n\nBest,\nSarah",
            email_time="2025-11-12 10:15:00",
            folder_name="INBOX",
        )

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.note, self.email]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")

        with EventRegisterer.capture_mode():
            # Environment event: Incoming email from Sarah requesting budget documents
            email_request_event = email_app.send_email_to_user_with_id(
                email_id="budget-request-email",
                sender="sarah.chen@company.com",
                subject="Request: Q1 Budget Documents",
                content="Hi Alex,\n\nCould you please send me the Q1 Budget Planning documents? I need the financial spreadsheet and timeline for the stakeholder meeting tomorrow morning. Maybe you've already saved them in your notes?\n\nThanks!\nSarah",
            ).delayed(2)

            # Agent searches Work folder for the requested note (motivated by email mentioning "Q1 Budget Planning")
            search_note_event = (
                note_app.search_notes_in_folder(query="Q1 Budget Planning", folder_name="Work")
                .oracle()
                .depends_on(email_request_event, delay_seconds=3)
            )

            # Agent retrieves the specific note to examine its contents and attachments
            # (motivated by search results showing matching note)
            get_note_event = (
                note_app.get_note_by_id(note_id=self.q1_budget_note_id)
                .oracle()
                .depends_on(search_note_event, delay_seconds=2)
            )

            # Agent lists attachments to confirm what files are available
            # (motivated by need to verify documents mentioned in Sarah's email are present)
            list_attachments_event = (
                note_app.list_attachments(note_id=self.q1_budget_note_id)
                .oracle()
                .depends_on(get_note_event, delay_seconds=2)
            )

            # Agent proposes to help by referencing the incoming email and the found documents
            propose_event = (
                aui.send_message_to_user(
                    content="I received an email from Sarah requesting your Q1 Budget Planning documents. I found the note in your Work folder with two attachments: Q1_Budget_2026.xlsx and Q1_Timeline.pdf. Would you like me to reply to Sarah confirming the documents are available?"
                )
                .oracle()
                .depends_on(list_attachments_event, delay_seconds=3)
            )

            # User accepts the proposal
            accept_event = (
                aui.accept_proposal(content="Yes, please reply to Sarah.")
                .oracle()
                .depends_on(propose_event, delay_seconds=2)
            )

            # Agent replies to Sarah's email
            # (motivated by user acceptance and prior observation of email request)
            reply_event = (
                email_app.reply_to_email(
                    email_id="budget-request-email",
                    folder_name="INBOX",
                    content="Hi Sarah,\n\nI have the Q1 Budget Planning documents ready. The files (Q1_Budget_2026.xlsx and Q1_Timeline.pdf) are organized in my Notes under the Work folder and attached to the email. I'll make sure to have them available for the stakeholder meeting tomorrow.\n\nBest,\nAlex",
                    attachment_paths=["Q1_Budget_2026.xlsx", "Q1_Timeline.pdf"],
                )
                .oracle()
                .depends_on(accept_event, delay_seconds=3)
            )

        # Register ALL events here in self.events
        self.events = [
            email_request_event,
            search_note_event,
            get_note_event,
            list_attachments_event,
            propose_event,
            accept_event,
            reply_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT events for validation
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent searched notes in Work folder
            # The agent must have used search_notes_in_folder to locate the requested note
            search_found = any(
                e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "search_notes_in_folder"
                and e.action.args.get("folder_name") == "Work"
                for e in agent_events
            )

            # STRICT Check 2: Agent retrieved the note by ID
            # The agent must have used get_note_by_id to examine the note contents
            get_note_found = any(
                e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "get_note_by_id"
                and e.action.args.get("note_id") is not None
                for e in agent_events
            )

            # STRICT Check 3: Agent listed attachments
            # The agent must have used list_attachments to see available files
            list_attachments_found = any(
                e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "list_attachments"
                and e.action.args.get("note_id") is not None
                for e in agent_events
            )

            # STRICT Check 4: Agent proposed help to user
            # The agent must have sent a message to the user (using PASAgentUserInterface.send_message_to_user)
            # We do NOT check the exact content, only that the proposal was made
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 5: Agent replied to Sarah's email
            # Equivalence class: reply_to_email OR send_email (both achieve the goal of responding)
            # We check for the presence of the email_id "budget-request-email" or recipient "sarah.chen@company.com"
            reply_found = any(
                e.action.class_name == "StatefulEmailApp"
                and e.action.function_name in ["reply_to_email", "send_email"]
                and (
                    e.action.args.get("email_id") == "budget-request-email"
                    or "sarah.chen@company.com" in str(e.action.args.get("recipients", []))
                )
                and any(str(p).endswith("Q1_Budget_2026.xlsx") for p in e.action.args.get("attachment_paths", []))
                and any(str(p).endswith("Q1_Timeline.pdf") for p in e.action.args.get("attachment_paths", []))
                for e in agent_events
            )

            # Determine success based on all STRICT checks
            success = search_found and get_note_found and list_attachments_found and proposal_found and reply_found

            # Build rationale if any check failed
            rationale = None
            if not success:
                missing = []
                if not search_found:
                    missing.append("note search in Work folder")
                if not get_note_found:
                    missing.append("note retrieval by ID")
                if not list_attachments_found:
                    missing.append("attachment listing")
                if not proposal_found:
                    missing.append("agent proposal to user")
                if not reply_found:
                    missing.append("email reply to Sarah")
                rationale = f"Missing critical actions: {', '.join(missing)}"

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
