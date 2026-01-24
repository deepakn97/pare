"""Scenario for cleaning up project deliverables note attachments and updating content."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps import SandboxLocalFileSystem
from are.simulation.apps.email_client import Email, EmailFolderName
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

# Draft files to be removed
DRAFT_FILES = [
    "Homepage_Draft_v1.psd",
    "Homepage_Draft_v2.psd",
    "Navigation_Draft.sketch",
    "Wireframes_Draft.pdf",
]


@register_scenario("project_deliverables_draft_cleanup")
class ProjectDeliverablesDraftCleanup(PASScenario):
    """Agent cleans up project deliverables note after boss requests changes.

    Story:
    1. User has a note "Q4 Website Redesign - Final Deliverables" with design files
    2. User previously sent an email to their boss (Sarah Chen) sharing the deliverables
    3. Boss replies requesting cleanup: remove draft attachments and update note content
    4. Agent proposes to make the requested changes
    5. User accepts
    6. Agent removes all draft attachments, adds manifest file, and updates note content

    This scenario exercises email-triggered attachment cleanup, cross-app coordination
    (email -> notes), and proactive workspace organization for client-facing deliverables.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    additional_system_prompt = """You shared your Q4 Website Redesign deliverables note with your boss Sarah Chen.

ACCEPT proposals that:
- Offer to clean up the deliverables note as requested by Sarah
- Mention removing draft files and adding the manifest
- Mention updating the note content

REJECT proposals that:
- Don't explain what changes will be made
- Don't reference Sarah's request"""

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize SandboxLocalFileSystem for attachment handling
        self.files = SandboxLocalFileSystem(name="Files")

        # Initialize Notes app
        self.note = StatefulNotesApp(name="Notes")
        self.note.internal_fs = self.files

        # Initialize Email app
        self.email = StatefulEmailApp(name="Emails")
        self.email.internal_fs = self.files

        # Create the deliverables note in the Work folder (WITHOUT attachments - added in build_events_flow)
        self.deliverables_note_id = self.note.create_note_with_time(
            folder="Work",
            title="Q4 Website Redesign - Final Deliverables",
            content=(
                "Project deliverables for Q4 website redesign.\n\n"
                "Design Files:\n"
                "- Homepage designs (draft and final versions)\n"
                "- Navigation designs (draft and final versions)\n"
                "- Wireframes (draft and final)\n\n"
                "Status: Ready for review"
            ),
            created_at="2025-11-10 10:00:00",
            updated_at="2025-11-15 14:30:00",
        )

        # User previously sent email to boss sharing the deliverables
        user_email_to_boss = Email(
            email_id="email_deliverables_share",
            sender=self.email.user_email,
            recipients=["sarah.chen@company.com"],
            subject="Q4 Website Redesign - Final Deliverables for Review",
            content=(
                "Hi Sarah,\n\n"
                "I've compiled all the deliverables for the Q4 website redesign project. "
                "The note contains:\n"
                "- Homepage designs (drafts v1, v2 and final)\n"
                "- Navigation designs (draft and final)\n"
                "- Wireframes (draft and final)\n\n"
                "Please let me know if you need any changes before the client handoff.\n\n"
                "Thanks!"
            ),
            timestamp=self.start_time - 86400,  # Sent yesterday
            is_read=True,
        )
        self.email.add_email(user_email_to_boss, folder_name=EmailFolderName.SENT)

        self.apps = [self.agent_ui, self.system_app, self.files, self.note, self.email]

    def build_events_flow(self) -> None:
        """Build event flow for deliverables cleanup."""
        aui = self.get_typed_app(PASAgentUserInterface)
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        files_app = self.get_typed_app(SandboxLocalFileSystem, "Files")

        # Create all the design files in the sandbox filesystem (before capture mode)
        # Draft files
        with files_app.open("/Homepage_Draft_v1.psd", "wb") as f:
            f.write(b"[Simulated PSD: Homepage design draft version 1]")
        with files_app.open("/Homepage_Draft_v2.psd", "wb") as f:
            f.write(b"[Simulated PSD: Homepage design draft version 2]")
        with files_app.open("/Navigation_Draft.sketch", "wb") as f:
            f.write(b"[Simulated Sketch: Navigation design draft]")
        with files_app.open("/Wireframes_Draft.pdf", "wb") as f:
            f.write(b"[Simulated PDF: Wireframes draft]")

        # Final files
        with files_app.open("/Homepage_Final.psd", "wb") as f:
            f.write(b"[Simulated PSD: Homepage final approved design]")
        with files_app.open("/Navigation_Final.sketch", "wb") as f:
            f.write(b"[Simulated Sketch: Navigation final approved design]")
        with files_app.open("/Wireframes_Final.pdf", "wb") as f:
            f.write(b"[Simulated PDF: Wireframes final version]")

        # Manifest file (already exists, agent just needs to attach it)
        with files_app.open("/Final_Deliverables_Manifest.txt", "wb") as f:
            f.write(
                b"Q4 Website Redesign - Final Deliverables Manifest\n\n"
                b"1. Homepage_Final.psd - Final homepage design\n"
                b"2. Navigation_Final.sketch - Final navigation design\n"
                b"3. Wireframes_Final.pdf - Final wireframes document\n"
            )

        # Add attachments to the note (before capture mode)
        # 4 draft files + 3 final files
        note_app.add_attachment_to_note(
            note_id=self.deliverables_note_id,
            attachment_path="/Homepage_Draft_v1.psd",
        )
        note_app.add_attachment_to_note(
            note_id=self.deliverables_note_id,
            attachment_path="/Homepage_Draft_v2.psd",
        )
        note_app.add_attachment_to_note(
            note_id=self.deliverables_note_id,
            attachment_path="/Homepage_Final.psd",
        )
        note_app.add_attachment_to_note(
            note_id=self.deliverables_note_id,
            attachment_path="/Navigation_Draft.sketch",
        )
        note_app.add_attachment_to_note(
            note_id=self.deliverables_note_id,
            attachment_path="/Navigation_Final.sketch",
        )
        note_app.add_attachment_to_note(
            note_id=self.deliverables_note_id,
            attachment_path="/Wireframes_Draft.pdf",
        )
        note_app.add_attachment_to_note(
            note_id=self.deliverables_note_id,
            attachment_path="/Wireframes_Final.pdf",
        )

        with EventRegisterer.capture_mode():
            # ENV: Boss replies to the user's email (same thread) requesting cleanup
            boss_reply_event = email_app.reply_to_email_from_user(
                sender="sarah.chen@company.com",
                email_id="email_deliverables_share",
                content=(
                    "Thanks for putting this together!\n\n"
                    "Before the client handoff on Friday, can you please:\n"
                    "1. Remove all the draft files - we only need the final versions\n"
                    "2. Add the deliverables manifest file (/files/Final_Deliverables_Manifest.txt) "
                    "so the client knows what they're receiving\n"
                    "3. Update the note content to say 'Ready for client handoff' instead of "
                    "'Ready for review'\n\n"
                    "Thanks!\n"
                    "Sarah"
                ),
            ).delayed(10)

            # Oracle: Agent searches for the deliverables note
            search_note_event = (
                note_app.search_notes(query="Q4 Website Redesign")
                .oracle()
                .depends_on(boss_reply_event, delay_seconds=2)
            )

            # Oracle: Agent retrieves the note to see current state
            get_note_event = (
                note_app.get_note_by_id(note_id=self.deliverables_note_id)
                .oracle()
                .depends_on(search_note_event, delay_seconds=1)
            )

            # Oracle: Agent lists current attachments
            list_attachments_event = (
                note_app.list_attachments(note_id=self.deliverables_note_id)
                .oracle()
                .depends_on(get_note_event, delay_seconds=1)
            )

            # Oracle: Agent proposes cleanup
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "Sarah replied to your deliverables email requesting some changes before "
                        "the client handoff. She'd like me to:\n"
                        "1. Remove all draft files (Homepage_Draft_v1.psd, Homepage_Draft_v2.psd, "
                        "Navigation_Draft.sketch, Wireframes_Draft.pdf)\n"
                        "2. Add the deliverables manifest file\n"
                        "3. Update the note to say 'Ready for client handoff'\n\n"
                        "Should I proceed with these changes?"
                    )
                )
                .oracle()
                .depends_on(list_attachments_event, delay_seconds=2)
            )

            # Oracle: User accepts
            acceptance_event = (
                aui.accept_proposal(content="Yes, please make those changes.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle: Agent removes all draft attachments
            remove_draft1_event = (
                note_app.remove_attachment(
                    note_id=self.deliverables_note_id,
                    attachment="Homepage_Draft_v1.psd",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            remove_draft2_event = (
                note_app.remove_attachment(
                    note_id=self.deliverables_note_id,
                    attachment="Homepage_Draft_v2.psd",
                )
                .oracle()
                .depends_on(remove_draft1_event, delay_seconds=1)
            )

            remove_draft3_event = (
                note_app.remove_attachment(
                    note_id=self.deliverables_note_id,
                    attachment="Navigation_Draft.sketch",
                )
                .oracle()
                .depends_on(remove_draft2_event, delay_seconds=1)
            )

            remove_draft4_event = (
                note_app.remove_attachment(
                    note_id=self.deliverables_note_id,
                    attachment="Wireframes_Draft.pdf",
                )
                .oracle()
                .depends_on(remove_draft3_event, delay_seconds=1)
            )

            # Oracle: Agent adds manifest file
            add_manifest_event = (
                note_app.add_attachment_to_note(
                    note_id=self.deliverables_note_id,
                    attachment_path="/Final_Deliverables_Manifest.txt",
                )
                .oracle()
                .depends_on(remove_draft4_event, delay_seconds=1)
            )

            # Oracle: Agent updates note content
            update_note_event = (
                note_app.update_note(
                    note_id=self.deliverables_note_id,
                    content=(
                        "Project deliverables for Q4 website redesign.\n\n"
                        "Final Design Files:\n"
                        "- Homepage_Final.psd\n"
                        "- Navigation_Final.sketch\n"
                        "- Wireframes_Final.pdf\n\n"
                        "Status: Ready for client handoff\n\n"
                        "See Final_Deliverables_Manifest.txt for complete list."
                    ),
                )
                .oracle()
                .depends_on(add_manifest_event, delay_seconds=1)
            )

        self.events = [
            boss_reply_event,
            search_note_event,
            get_note_event,
            list_attachments_event,
            proposal_event,
            acceptance_event,
            remove_draft1_event,
            remove_draft2_event,
            remove_draft3_event,
            remove_draft4_event,
            add_manifest_event,
            update_note_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate essential outcomes.

        Checks:
        1. Agent sent proposal to user
        2. Agent removed all 4 draft attachments
        3. Agent added manifest file
        4. Agent updated note content
        """
        try:
            log_entries = env.event_log.list_view()
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # Check 1: Proposal sent to user
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # Check 2: All draft files removed
            removed_attachments = {
                e.action.args.get("attachment")
                for e in agent_events
                if e.action.class_name == "StatefulNotesApp" and e.action.function_name == "remove_attachment"
            }
            all_drafts_removed = all(draft in removed_attachments for draft in DRAFT_FILES)

            # Check 3: Manifest file added
            manifest_added = any(
                e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "add_attachment_to_note"
                and "manifest" in str(e.action.args.get("attachment_path", "")).lower()
                for e in agent_events
            )

            # Check 4: Note content updated
            note_updated = any(
                e.action.class_name == "StatefulNotesApp" and e.action.function_name == "update_note"
                for e in agent_events
            )

            success = proposal_found and all_drafts_removed and manifest_added and note_updated

            if not success:
                missing = []
                if not proposal_found:
                    missing.append("proposal to user")
                if not all_drafts_removed:
                    missing_drafts = [d for d in DRAFT_FILES if d not in removed_attachments]
                    missing.append(f"draft removal (missing: {missing_drafts})")
                if not manifest_added:
                    missing.append("manifest file added")
                if not note_updated:
                    missing.append("note content update")
                return ScenarioValidationResult(
                    success=False,
                    rationale=f"Missing: {', '.join(missing)}",
                )

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
