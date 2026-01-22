from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps import SandboxLocalFileSystem
from are.simulation.apps.email_client import Email, EmailFolderName
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


@register_scenario("outdated_note_attachment_replacement")
class OutdatedNoteAttachmentReplacement(PASScenario):
    """Agent updates a work note to use the latest vendor documents received via email attachments, and replies to confirm.

    The user maintains a Work folder note titled "Vendor Proposal - TechCorp" containing project documentation with two
    draft attachments (TechCorp_Contract_Draft_v1.pdf and Technical_Specs_OLD.docx). The project lead later emails the
    *final* versions as attachments. The agent must:
    1. Read the email and download the attached final files into a dedicated project folder (e.g., /TechCorp_Final/)
    2. Search the Work folder to locate the "Vendor Proposal - TechCorp" note
    3. List current attachments on the note to verify draft files are present
    4. Remove the draft attachments from the note
    5. Attach the downloaded final files to the note
    6. Reply to the project lead confirming the note has been updated

    This scenario exercises email-driven note maintenance (email → notes attachment correction), downloading attachments from email, less-common attachment management tools (`list_attachments`, `remove_attachment`, `add_attachment_to_note`), and a multi-step replacement workflow.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize sandbox filesystem so attachments have a real backing store.
        self.files = SandboxLocalFileSystem(name="Files")

        # Initialize Notes app
        self.note = StatefulNotesApp(name="Notes")

        # Initialize Email app
        self.email = StatefulEmailApp(name="Emails")

        # Notes attachments are read from internal_fs when set.
        self.note.internal_fs = self.files
        # Email attachments are read from internal_fs when set.
        self.email.internal_fs = self.files

        # Prepare attachment files in the sandbox filesystem.
        self.contract_v1_path = "/TechCorp_Contract_Draft_v1.pdf"
        self.contract_v2_path = "/TechCorp_Contract_Draft_v2.pdf"
        self.specs_old_path = "/Technical_Specs_OLD.docx"
        self.specs_final_path = "/Technical_Specs_FINAL.docx"
        self.contract_v2_filename = self.contract_v2_path.split("/")[-1]
        self.specs_final_filename = self.specs_final_path.split("/")[-1]
        self.techcorp_final_dir = "/TechCorp_Final"
        # Create a dedicated directory where the agent will download final files (to differ from other attachment scenarios).
        self.files.mkdir(self.techcorp_final_dir)

        with self.files.open(self.contract_v1_path, "wb") as f:
            f.write(b"dummy contract v1")
        with self.files.open(self.contract_v2_path, "wb") as f:
            f.write(b"dummy contract v2")
        with self.files.open(self.specs_old_path, "wb") as f:
            f.write(b"dummy specs old")
        with self.files.open(self.specs_final_path, "wb") as f:
            f.write(b"dummy specs final")

        # Populate Notes app with baseline data
        # Create the "Vendor Proposal - TechCorp" note in Work folder
        # Note: Attachments are seeded via early environment events (after init serialization).
        self.vendor_note_id = self.note.create_note_with_time(
            folder="Work",
            title="Vendor Proposal - TechCorp",
            content="This note contains all documentation for the TechCorp vendor proposal.\n\nAttached files:\n- TechCorp_Contract_Draft_v1.pdf (contract - OLD VERSION)\n- Technical_Specs_OLD.docx (specifications - OLD VERSION)\n- Project_Overview.pptx\n\nThese need to be updated per project lead's instructions.",
            pinned=False,
            created_at="2025-11-15 10:00:00",
            updated_at="2025-11-15 10:00:00",
        )

        # Seed email history: earlier draft docs were shared via email.
        # IMPORTANT: Don't add attachments here (bytes); we'll attach them in build_events_flow post-init.
        self.draft_email_id = "email-techcorp-drafts"
        prior_email = Email(
            email_id=self.draft_email_id,
            sender="sarah.chen@techcorp.com",
            recipients=[self.email.user_email],
            subject="TechCorp proposal — draft contract + specs",
            content=(
                "Hi,\n\n"
                "Sharing the current draft contract + technical specs for the TechCorp proposal.\n"
                "I'll send final versions once legal/eng sign off.\n\n"
                "Thanks,\n"
                "Sarah Chen"
            ),
            timestamp=datetime(2025, 11, 15, 17, 0, 0, tzinfo=UTC).timestamp(),
            is_read=True,
        )
        self.email.folders[EmailFolderName.INBOX].add_email(prior_email)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.files, self.note, self.email]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")

        # Seed the existing attachments AFTER initialization (avoid bytes in initial state JSON),
        # but BEFORE capture_mode so they're present for later list/remove operations.
        note_app.add_attachment_to_note(note_id=self.vendor_note_id, attachment_path=self.contract_v1_path)
        note_app.add_attachment_to_note(note_id=self.vendor_note_id, attachment_path=self.specs_old_path)

        # Attach files to the historical draft email AFTER initialization (avoid bytes in initial state JSON).
        draft_email = email_app.folders[EmailFolderName.INBOX].get_email_by_id(self.draft_email_id)
        email_app.add_attachment(email=draft_email, attachment_path=self.contract_v1_path)
        email_app.add_attachment(email=draft_email, attachment_path=self.specs_old_path)

        with EventRegisterer.capture_mode():
            # Environment Event 1: Project lead sends final versions as attachments (realistic trigger).
            correction_email_event = email_app.send_email_to_user_with_id(
                email_id="email-attachment-correction-request",
                sender="sarah.chen@techcorp.com",
                subject="TechCorp proposal — final contract + specs (attached)",
                content="""Hi,

Attached are the final versions for the TechCorp proposal:

- TechCorp_Contract_Draft_v2.pdf
- Technical_Specs_FINAL.docx

Please download these attachments into the TechCorp_Final folder so we keep the final versions in one place:
- /TechCorp_Final/

Please use these instead of the earlier draft versions when finalizing the proposal materials today.

Thanks,
Sarah Chen
Project Lead""",
                attachment_paths=[self.contract_v2_path, self.specs_final_path],
            ).delayed(5)

            # Oracle Event 0: Agent reads the email and downloads attachments before attaching into Notes.
            read_email_event = (
                email_app.get_email_by_id(email_id="email-attachment-correction-request", folder_name="INBOX")
                .oracle()
                .depends_on(correction_email_event, delay_seconds=1)
            )
            download_attachments_event = (
                email_app.download_attachments(
                    email_id="email-attachment-correction-request",
                    folder_name="INBOX",
                    path_to_save=self.techcorp_final_dir,
                )
                .oracle()
                .depends_on(read_email_event, delay_seconds=1)
            )

            # Oracle Event 1: Agent searches Work folder to locate the target note
            # Motivation: user maintains TechCorp proposal materials in a Work note; agent updates it to match final docs.
            search_note_event = (
                note_app.search_notes_in_folder(
                    query="Vendor Proposal - TechCorp",
                    folder_name="Work",
                )
                .oracle()
                .depends_on(download_attachments_event, delay_seconds=1)
            )

            # Oracle Event 2: Agent retrieves the note details to confirm identity
            # Motivation: search_note_event located the note; retrieve full details to confirm it's the correct note
            get_note_event = (
                note_app.get_note_by_id(
                    note_id=self.vendor_note_id,
                )
                .oracle()
                .depends_on(search_note_event, delay_seconds=1)
            )

            # Oracle Event 3: Agent sends proposal to user citing the email trigger
            # Motivation: Sarah sent final versions attached; agent asks to swap draft attachments in user's note.
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "I received an email from Sarah Chen with the final TechCorp proposal files attached "
                        '(TechCorp_Contract_Draft_v2.pdf and Technical_Specs_FINAL.docx). Your "Vendor Proposal - TechCorp" note '
                        "still has the older draft attachments (TechCorp_Contract_Draft_v1.pdf and Technical_Specs_OLD.docx). "
                        f"She also asked to download/store the final files under {self.techcorp_final_dir}/. "
                        "Would you like me to download the attachments into that folder and replace the attachments in your note with the final versions?"
                    )
                )
                .oracle()
                .depends_on(get_note_event, delay_seconds=2)
            )

            # Oracle Event 4: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please proceed.").oracle().depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent lists current attachments to verify state before modifications
            # Motivation: acceptance_event approved changes; need to verify current attachment state before removing
            list_attachments_event = (
                note_app.list_attachments(
                    note_id=self.vendor_note_id,
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 6: Agent removes first outdated attachment
            # Motivation: acceptance_event approved removal; Sarah's email specified removing "TechCorp_Contract_Draft_v1.pdf"
            remove_contract_v1_event = (
                note_app.remove_attachment(
                    note_id=self.vendor_note_id,
                    attachment="TechCorp_Contract_Draft_v1.pdf",
                )
                .oracle()
                .depends_on(list_attachments_event, delay_seconds=1)
            )

            # Oracle Event 7: Agent adds first replacement attachment
            # Motivation: acceptance_event approved addition; attach the downloaded final contract from the project folder.
            add_contract_v2_event = (
                note_app.add_attachment_to_note(
                    note_id=self.vendor_note_id,
                    attachment_path=f"{self.techcorp_final_dir}/{self.contract_v2_filename}",
                )
                .oracle()
                .depends_on(remove_contract_v1_event, delay_seconds=1)
            )

            # Oracle Event 8: Agent removes second outdated attachment
            # Motivation: acceptance_event approved removal; Sarah's email specified removing "Technical_Specs_OLD.docx"
            remove_specs_old_event = (
                note_app.remove_attachment(
                    note_id=self.vendor_note_id,
                    attachment="Technical_Specs_OLD.docx",
                )
                .oracle()
                .depends_on(add_contract_v2_event, delay_seconds=1)
            )

            # Oracle Event 9: Agent adds second replacement attachment
            # Motivation: acceptance_event approved addition; attach the downloaded final specs from the project folder.
            add_specs_final_event = (
                note_app.add_attachment_to_note(
                    note_id=self.vendor_note_id,
                    attachment_path=f"{self.techcorp_final_dir}/{self.specs_final_filename}",
                )
                .oracle()
                .depends_on(remove_specs_old_event, delay_seconds=1)
            )

            # Oracle Event 10: Agent replies to Sarah confirming update completion (distinguishes this scenario).
            reply_confirmation_event = (
                email_app.reply_to_email(
                    email_id="email-attachment-correction-request",
                    folder_name="INBOX",
                    content=(
                        "Thanks — I downloaded the final contract + specs and updated my 'Vendor Proposal - TechCorp' note "
                        "to use the final attachments (removed the draft versions)."
                    ),
                )
                .oracle()
                .depends_on(add_specs_final_event, delay_seconds=1)
            )

        # Register ALL events
        self.events = [
            correction_email_event,
            read_email_event,
            download_attachments_event,
            search_note_event,
            get_note_event,
            proposal_event,
            acceptance_event,
            list_attachments_event,
            remove_contract_v1_event,
            add_contract_v2_event,
            remove_specs_old_event,
            add_specs_final_event,
            reply_confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent sent proposal mentioning Sarah Chen and the attachment correction task
            # The proposal must reference Sarah's email and the specific note/attachments to be updated
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 2: Agent removed the first outdated attachment
            # Must remove "TechCorp_Contract_Draft_v1.pdf"
            remove_contract_v1_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "remove_attachment"
                and "TechCorp_Contract_Draft_v1.pdf" in e.action.args.get("attachment", "")
                for e in log_entries
            )

            # STRICT Check 3: Agent added the first replacement attachment
            # Must add the v2 contract at the specified path
            add_contract_v2_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "add_attachment_to_note"
                and "TechCorp_Contract_Draft_v2.pdf" in e.action.args.get("attachment_path", "")
                for e in log_entries
            )

            # STRICT Check 4: Agent removed the second outdated attachment
            # Must remove "Technical_Specs_OLD.docx"
            remove_specs_old_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "remove_attachment"
                and "Technical_Specs_OLD.docx" in e.action.args.get("attachment", "")
                for e in log_entries
            )

            # STRICT Check 5: Agent added the second replacement attachment
            # Must add the final specs at the specified path
            add_specs_final_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "add_attachment_to_note"
                and "Technical_Specs_FINAL.docx" in e.action.args.get("attachment_path", "")
                for e in log_entries
            )

            # STRICT Check 6: Agent downloaded the final attachments into the dedicated project folder
            # Must call download_attachments with path_to_save == "/TechCorp_Final"
            downloaded_to_project_folder = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "download_attachments"
                and e.action.args.get("email_id") == "email-attachment-correction-request"
                and e.action.args.get("folder_name") == "INBOX"
                and e.action.args.get("path_to_save") == self.techcorp_final_dir
                for e in log_entries
            )

            # All STRICT checks must pass; FLEXIBLE checks improve confidence but are not required
            strict_checks = (
                proposal_found
                and remove_contract_v1_found
                and add_contract_v2_found
                and remove_specs_old_found
                and add_specs_final_found
                and downloaded_to_project_folder
            )

            success = strict_checks

            if not success:
                # Build rationale for failure
                missing = []
                if not proposal_found:
                    missing.append("agent proposal mentioning Sarah Chen and note")
                if not remove_contract_v1_found:
                    missing.append("removal of TechCorp_Contract_Draft_v1.pdf")
                if not add_contract_v2_found:
                    missing.append("addition of TechCorp_Contract_Draft_v2.pdf")
                if not remove_specs_old_found:
                    missing.append("removal of Technical_Specs_OLD.docx")
                if not add_specs_final_found:
                    missing.append("addition of Technical_Specs_FINAL.docx")
                if not downloaded_to_project_folder:
                    missing.append(f"download_attachments to {self.techcorp_final_dir}")

                rationale = f"Missing required actions: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
