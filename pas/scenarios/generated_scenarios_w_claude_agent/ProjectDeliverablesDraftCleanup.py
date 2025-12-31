"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulEmailApp,
)
from pas.apps.note import StatefulNotesApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("project_deliverables_draft_cleanup")
class ProjectDeliverablesDraftCleanup(PASScenario):
    """Agent consolidates project deliverables note attachments by removing draft versions and adding a manifest file.

    The user maintains a note titled "Q4 Website Redesign - Final Deliverables" in their Work folder containing six attachments: `/files/Homepage_Draft_v1.psd`, `/files/Homepage_Draft_v2.psd`, `/files/Homepage_Final.psd`, `/files/Navigation_Draft.sketch`, `/files/Navigation_Final.sketch`, and `/files/Wireframes_Draft.pdf`. The project manager sends an email stating: "Can you clean up the deliverables note for the website redesign project? Please remove all draft and intermediate versions from the attachments - we only need the final approved files for the client handoff. Also, add a deliverables manifest file documenting what's included." The agent must:
    1. Search notes to locate the "Q4 Website Redesign - Final Deliverables" note
    2. List all current attachments to identify which files are drafts
    3. Identify draft versions by filename patterns (files containing "Draft" or version numbers like "v1", "v2")
    4. Remove one representative draft attachment (`Homepage_Draft_v1.psd`) to demonstrate draft cleanup without repetitive loops
    5. Add a new manifest file `/files/Final_Deliverables_Manifest.txt` documenting the kept files
    6. Update the note content to reflect the consolidation with a timestamp and summary of the cleanup

    This scenario exercises email-triggered attachment cleanup workflows, attachment list inspection, a representative draft removal, manifest creation for documentation, and proactive workspace organization for client-facing deliverables.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        import base64

        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Notes app
        self.note = StatefulNotesApp(name="Notes")

        # Create the deliverables note in the Work folder
        self.deliverables_note_id = self.note.create_note_with_time(
            folder="Work",
            title="Q4 Website Redesign - Final Deliverables",
            content="Project deliverables for Q4 website redesign. Contains design files for homepage, navigation, and wireframes.",
            created_at="2025-11-10 10:00:00",
            updated_at="2025-11-15 14:30:00",
        )

        # Add six attachments to the note by directly modifying the note object
        # This approach bypasses filesystem checks and seeds baseline state
        work_folder = self.note.folders["Work"]
        note = work_folder.get_note_by_id(self.deliverables_note_id)
        if note:
            # Simulate attachments with base64-encoded placeholder data
            # 4 draft files (to be removed) + 2 final files (to be kept)
            note.attachments = {
                "Homepage_Draft_v1.psd": base64.b64encode(b"[Simulated PSD file: Homepage design draft version 1]"),
                "Homepage_Draft_v2.psd": base64.b64encode(b"[Simulated PSD file: Homepage design draft version 2]"),
                "Navigation_Draft.sketch": base64.b64encode(b"[Simulated Sketch file: Navigation design draft]"),
                "Wireframes_Draft.pdf": base64.b64encode(b"[Simulated PDF file: Wireframes draft document]"),
                "Homepage_Final.psd": base64.b64encode(b"[Simulated PSD file: Homepage final approved design]"),
                "Navigation_Final.sketch": base64.b64encode(
                    b"[Simulated Sketch file: Navigation final approved design]"
                ),
            }

        # Initialize Email app
        self.email = StatefulEmailApp(name="Emails")

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.note, self.email]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Project manager sends email requesting attachment cleanup
            # This email explicitly lists which draft files to remove and requests a manifest
            manager_email_event = email_app.send_email_to_user_with_id(
                email_id="pm_cleanup_request_001",
                sender="sarah.chen@company.com",
                subject="Q4 Website Redesign - Deliverables Cleanup",
                content="Hi! Can you clean up the deliverables note for the website redesign project? As a first pass, please remove the obvious draft file Homepage_Draft_v1.psd from the attachments. We only need the final approved files (Homepage_Final.psd and Navigation_Final.sketch) for the client handoff on Friday. Also, please add a deliverables manifest file documenting what's included so the client knows what they're receiving. Use the manifest at this path: /files/Final_Deliverables_Manifest.txt (filename: Final_Deliverables_Manifest.txt). It would be better to update the note with redesign info! Thanks!",
            ).delayed(15)

            # Oracle Event 1: Agent searches for the deliverables note
            # Motivation: manager email mentions "deliverables note for the website redesign project"
            search_note_event = (
                note_app.search_notes(query="Q4 Website Redesign")
                .oracle()
                .depends_on(manager_email_event, delay_seconds=2)
            )

            # Oracle Event 2: Agent retrieves the note details to get the note_id
            # Motivation: need note_id from search results to perform subsequent operations
            get_note_event = (
                note_app.get_note_by_id(note_id=self.deliverables_note_id)
                .oracle()
                .depends_on(search_note_event, delay_seconds=1)
            )

            # Oracle Event 3: Agent lists current attachments to verify what needs removal
            # Motivation: manager email lists specific files to remove; agent verifies they exist
            list_attachments_event = (
                note_app.list_attachments(note_id=self.deliverables_note_id)
                .oracle()
                .depends_on(get_note_event, delay_seconds=1)
            )

            # Oracle Event 4: Agent sends proposal to user citing the manager's request
            # Motivation: manager email explicitly requested "remove...draft files" and "add a manifest file"
            proposal_event = (
                aui.send_message_to_user(
                    content="I received a request from Sarah Chen to clean up the Q4 Website Redesign deliverables note. She asked me to remove the draft file Homepage_Draft_v1.psd and add a manifest file documenting the final files (using /files/Final_Deliverables_Manifest.txt). Also, she wants me to update the note with redesign info. Should I proceed?"
                )
                .oracle()
                .depends_on(list_attachments_event, delay_seconds=2)
            )

            # Oracle Event 5: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please proceed with the cleanup and update the note with redesign info."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent removes one representative draft attachment
            # Motivation: user accepted; manager email explicitly requested removing "Homepage_Draft_v1.psd".
            remove_draft_event = (
                note_app.remove_attachment(note_id=self.deliverables_note_id, attachment="Homepage_Draft_v1.psd")
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 7: Agent adds manifest file
            # Motivation: user accepted; manager email explicitly provided the manifest path "/files/Final_Deliverables_Manifest.txt".
            add_manifest_event = (
                note_app.add_attachment_to_note(
                    note_id=self.deliverables_note_id, attachment_path="/files/Final_Deliverables_Manifest.txt"
                )
                .oracle()
                .depends_on(remove_draft_event, delay_seconds=1)
            )

            # Oracle Event 8: Agent updates note content to document the cleanup
            # Motivation: user accepted; adding timestamp and summary as good practice after bulk modifications
            update_note_event = (
                note_app.update_note(
                    note_id=self.deliverables_note_id,
                    content="Project deliverables for Q4 website redesign. Contains design files for homepage, navigation, and wireframes.\n\n[Cleanup completed 2025-11-18: Removed draft file Homepage_Draft_v1.psd. Manifest added for client handoff. Note updated with redesign info.]",
                )
                .oracle()
                .depends_on(add_manifest_event, delay_seconds=1)
            )

        # Register ALL events
        self.events = [
            manager_email_event,
            search_note_event,
            get_note_event,
            list_attachments_event,
            proposal_event,
            acceptance_event,
            remove_draft_event,
            add_manifest_event,
            update_note_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent searched for the deliverables note
            # STRICT: Agent must locate the note to perform cleanup
            # FLEXIBLE: accept search_notes or get_note_by_id as equivalent ways to find the note
            note_search_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name in ["search_notes", "get_note_by_id"]
                for e in log_entries
            )

            # Check Step 2: Agent listed attachments to identify what needs removal
            # STRICT: Agent must inspect existing attachments before cleanup
            list_attachments_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "list_attachments"
                for e in log_entries
            )

            # Check Step 3: Agent sent proposal mentioning the cleanup operation
            # STRICT: Agent must inform user about cleanup plan and reference Sarah Chen's request
            # FLEXIBLE: wording details (exact file names, phrasing) can vary
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["sarah", "chen", "cleanup", "clean up"]
                )
                and any(keyword in e.action.args.get("content", "").lower() for keyword in ["draft", "deliverable"])
                for e in log_entries
            )

            # Check Step 4: Agent removed the representative draft attachment requested in the email
            # STRICT: Agent must remove Homepage_Draft_v1.psd (explicitly requested by the manager email).
            representative_draft_removed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "remove_attachment"
                and e.action.args.get("attachment") == "Homepage_Draft_v1.psd"
                for e in log_entries
            )

            # Check Step 5: Agent added the manifest file
            # STRICT: Agent must add the manifest file as requested by Sarah Chen
            # FLEXIBLE: exact filename path format can vary
            manifest_added = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "add_attachment_to_note"
                and "manifest" in e.action.args.get("attachment_path", "").lower()
                for e in log_entries
            )

            # Check Step 6: Agent updated the note content to reflect cleanup
            # STRICT: Agent must document the cleanup operation in the note
            note_updated = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "update_note"
                for e in log_entries
            )

            # Determine success and provide rationale for failures
            success = (
                note_search_found
                and list_attachments_found
                and proposal_found
                and representative_draft_removed
                and manifest_added
                and note_updated
            )

            if not success:
                failures = []
                if not note_search_found:
                    failures.append("agent did not search for deliverables note")
                if not list_attachments_found:
                    failures.append("agent did not list attachments")
                if not proposal_found:
                    failures.append("agent did not send cleanup proposal referencing Sarah Chen")
                if not representative_draft_removed:
                    failures.append("agent did not remove the draft file Homepage_Draft_v1.psd")
                if not manifest_added:
                    failures.append("agent did not add manifest file")
                if not note_updated:
                    failures.append("agent did not update note content")
                rationale = "; ".join(failures)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
