"""Scenario: Agent forwards note attachments via email based on incoming request."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps import SandboxLocalFileSystem
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

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

    The user has organized project documentation in a note titled "Q1 Budget Planning" stored
    in the "Work" folder, which includes financial spreadsheets and timeline documents attached
    to the note. A colleague (Sarah Chen) sends an email requesting these specific budget
    documents for an upcoming stakeholder meeting. The agent must:
    1. Detect the incoming email requesting Q1 Budget Planning documents
    2. Search notes to locate the requested note
    3. List the note's attachments to identify available files
    4. Propose to reply to Sarah with the attached documents
    5. Upon user acceptance, reply to Sarah's email with the attachment files

    This scenario exercises cross-app information retrieval (notes -> email), attachment handling
    across apps via the shared filesystem, and proactive email composition based on external requests.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with baseline data for the note attachment email forwarding scenario."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize SandboxLocalFileSystem for attachment handling
        self.files = SandboxLocalFileSystem(name="Files")

        # Initialize scenario specific apps
        self.note = StatefulNotesApp(name="Notes")
        self.email = StatefulEmailApp(name="Emails", user_email="alex.morgan@company.com")

        # Set internal_fs on apps that need filesystem access for attachments
        self.note.internal_fs = self.files
        self.email.internal_fs = self.files

        # Write attachment files to the filesystem
        with self.files.open("/Q1_Budget_2026.xlsx", "wb") as f:
            f.write(b"[Simulated Excel spreadsheet content for Q1 2026 budget projections and financial analysis]")
        with self.files.open("/Q1_Timeline.pdf", "wb") as f:
            f.write(
                b"[Simulated PDF document containing Q1 2026 project timeline, milestones, and resource allocation schedule]"
            )

        # Create the "Q1 Budget Planning" note in the Work folder (WITHOUT attachments - added in build_events_flow)
        self.budget_note_id = self.note.create_note_with_time(
            folder="Work",
            title="Q1 Budget Planning",
            content="Budget planning documents for Q1 2026:\n\n- Financial projections spreadsheet\n- Timeline and milestones\n- Resource allocation breakdown\n\nAttachments include detailed spreadsheets and timeline documents for the stakeholder meeting.",
            created_at="2025-11-10 14:30:00",
            updated_at="2025-11-15 16:45:00",
        )

        # Seed historical context - a previous email thread about Q1 planning
        self.email.create_and_add_email_with_time(
            sender="sarah.chen@company.com",
            recipients=[self.email.user_email],
            subject="Q1 Planning Meeting Scheduled",
            content="Hi Alex,\n\nJust confirming that our Q1 planning meeting with stakeholders is scheduled for next week. Looking forward to reviewing the budget documents.\n\nBest,\nSarah",
            email_time="2025-11-12 10:15:00",
            folder_name="INBOX",
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.files, self.note, self.email]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")

        # Add attachments to the note BEFORE capture_mode (after state serialization)
        # This avoids the bytes serialization issue while ensuring attachments exist before events run
        note_app.add_attachment_to_note(note_id=self.budget_note_id, attachment_path="/Q1_Budget_2026.xlsx")
        note_app.add_attachment_to_note(note_id=self.budget_note_id, attachment_path="/Q1_Timeline.pdf")

        with EventRegisterer.capture_mode():
            # ENV: Incoming email from Sarah requesting budget documents
            email_request_event = email_app.send_email_to_user_with_id(
                email_id="budget-request-email",
                sender="sarah.chen@company.com",
                subject="Request: Q1 Budget Documents",
                content="Hi Alex,\n\nCould you please send me the Q1 Budget Planning documents? I need the financial spreadsheet and timeline for the stakeholder meeting tomorrow morning.\n\nThanks!\nSarah",
            ).delayed(2)

            # Oracle: Agent searches for the requested note
            search_note_event = (
                note_app.search_notes(query="Q1 Budget Planning")
                .oracle()
                .depends_on(email_request_event, delay_seconds=3)
            )

            # Oracle: Agent lists attachments to see available files
            list_attachments_event = (
                note_app.list_attachments(note_id=self.budget_note_id)
                .oracle()
                .depends_on(search_note_event, delay_seconds=2)
            )

            # Oracle: Agent proposes to reply with the documents
            propose_event = (
                aui.send_message_to_user(
                    content="Sarah is requesting your Q1 Budget Planning documents. I found the note in your Work folder with two attachments: Q1_Budget_2026.xlsx and Q1_Timeline.pdf. Would you like me to reply to her email with these files attached?"
                )
                .oracle()
                .depends_on(list_attachments_event, delay_seconds=3)
            )

            # Oracle: User accepts the proposal
            accept_event = (
                aui.accept_proposal(content="Yes, please send them to Sarah.")
                .oracle()
                .depends_on(propose_event, delay_seconds=2)
            )

            # Oracle: Agent replies to Sarah's email with attachments
            reply_event = (
                email_app.reply_to_email(
                    email_id="budget-request-email",
                    folder_name="INBOX",
                    content="Hi Sarah,\n\nHere are the Q1 Budget Planning documents you requested. I've attached the financial spreadsheet and timeline for the stakeholder meeting.\n\nBest,\nAlex",
                    attachment_paths=["/Q1_Budget_2026.xlsx", "/Q1_Timeline.pdf"],
                )
                .oracle()
                .depends_on(accept_event, delay_seconds=3)
            )

        self.events = [
            email_request_event,
            search_note_event,
            list_attachments_event,
            propose_event,
            accept_event,
            reply_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent achieved the essential outcomes for this scenario.

        Essential outcomes (what we check):
        - Agent sent proposal to user about forwarding the documents
        - Agent replied to Sarah's email with both attachments

        Not checked (intermediate steps the agent might do differently):
        - How agent found the note (search_notes, search_notes_in_folder, list_notes, etc.)
        - How agent discovered attachments (list_attachments, get_note_by_id, etc.)
        """
        try:
            log_entries = env.event_log.list_view()

            # CHECK 1: Agent sent proposal to user
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # CHECK 2: Agent replied to Sarah's email with both attachments
            email_reply_found = False
            for e in log_entries:
                if e.event_type != EventType.AGENT or not isinstance(e.action, Action):
                    continue
                if e.action.class_name != "StatefulEmailApp" or e.action.function_name != "reply_to_email":
                    continue

                args = e.action.args if e.action.args else e.action.resolved_args
                if args.get("email_id") != "budget-request-email":
                    continue

                attachment_paths = args.get("attachment_paths", [])
                has_budget = any("Q1_Budget_2026.xlsx" in str(p) for p in attachment_paths)
                has_timeline = any("Q1_Timeline.pdf" in str(p) for p in attachment_paths)
                if has_budget and has_timeline:
                    email_reply_found = True
                    break

            success = proposal_found and email_reply_found

            if not success:
                failed_checks = []
                if not proposal_found:
                    failed_checks.append("agent did not send proposal to user")
                if not email_reply_found:
                    failed_checks.append(
                        "agent did not reply to Sarah with both attachments (Q1_Budget_2026.xlsx and Q1_Timeline.pdf)"
                    )
                rationale = "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
