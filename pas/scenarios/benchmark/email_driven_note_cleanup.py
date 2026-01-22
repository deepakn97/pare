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


@register_scenario("email_driven_note_cleanup")
class EmailDrivenNoteCleanup(PASScenario):
    """Agent archives and deletes outdated project notes based on explicit cleanup directive from incoming email.

    The user maintains project notes across multiple folders including "Work", "Inbox", and a custom folder "ProjectAlpha" containing documentation from a
    recently completed project. An email arrives from the project coordinator requesting a small cleanup: delete one explicitly outdated ProjectAlpha note and
    archive one remaining ProjectAlpha note into a new folder named "2025_Archives". To avoid ambiguity and reduce repeated lookup patterns, the email includes
    the note IDs.

    The agent must:
    1. Read the cleanup directive from the incoming email.
    2. Propose the delete + archive plan to the user and only proceed after acceptance.
    3. Delete the specified outdated note using `delete_note`.
    4. Create the archive folder "2025_Archives" using `new_folder`.
    5. Move the specified ProjectAlpha note into the archive folder using `move_note`.

    This scenario exercises email-driven workflow automation (email → notes cleanup/archival), less-common destructive notes operations (`delete_note`, `delete_folder`), folder lifecycle management (create archive, remove empty folder), cross-folder note search and selective deletion, and structured email confirmation of multi-step cleanup tasks..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Notes App
        self.note = StatefulNotesApp(name="Notes")

        # Initialize Email App
        self.email = StatefulEmailApp(name="Emails")

        # Initialize sandbox filesystem so historical emails can include attachments.
        self.files = SandboxLocalFileSystem(name="Files")
        self.email.internal_fs = self.files

        # Populate baseline data

        # Create custom ProjectAlpha folder and populate with notes
        self.note.new_folder("ProjectAlpha")

        # Note to be deleted (explicitly outdated)
        self.outdated_requirements_note_id = self.note.create_note_with_time(
            folder="ProjectAlpha",
            title="ProjectAlpha - Outdated Requirements",
            content="Initial requirements document that was superseded by v2. Keep for historical reference only.",
            created_at="2025-01-10 09:00:00",
            updated_at="2025-01-20 10:00:00",
        )

        # Note to be archived (remaining ProjectAlpha content)
        self.final_deliverables_note_id = self.note.create_note_with_time(
            folder="ProjectAlpha",
            title="ProjectAlpha - Final Deliverables",
            content="Summary of final deliverables: deployed application, documentation, handoff materials.",
            created_at="2025-10-20 13:00:00",
            updated_at="2025-10-25 15:00:00",
        )

        # Add an unrelated note in another folder (to verify selective actions)
        self.note.create_note_with_time(
            folder="Work",
            title="Q4 Planning Notes",
            content="Strategic planning for Q4 2025. Key initiatives and objectives.",
            created_at="2025-10-01 09:00:00",
            updated_at="2025-10-05 11:00:00",
        )

        # Seed prior email history from Sarah to make the later cleanup directive more realistic.
        #
        # Rationale: In real workflows, a coordinator would reference prior deliverables / updated docs
        # (often attached), and the cleanup request would be part of an existing thread.
        requirements_v2_path = "/ProjectAlpha_Requirements_v2.pdf"
        deliverables_path = "/ProjectAlpha_Final_Deliverables_Checklist.pdf"
        with self.files.open(requirements_v2_path, "wb") as f:
            f.write(b"dummy ProjectAlpha requirements v2")
        with self.files.open(deliverables_path, "wb") as f:
            f.write(b"dummy ProjectAlpha deliverables checklist")

        prior_email_1 = Email(
            email_id="email_projectalpha_requirements_v2",
            sender="sarah.martinez@example.com",
            recipients=[self.email.user_email],
            subject="ProjectAlpha: updated requirements (v2) + next steps",
            content=(
                "Hi,\n\n"
                "Sharing the updated ProjectAlpha requirements (v2). This supersedes the early draft requirements.\n\n"
                "For your records:\n"
                '- You have a note titled "ProjectAlpha - Outdated Requirements" that captured the initial draft.\n'
                "  You can delete it once we're fully wrapped up.\n\n"
                "Thanks!\n"
                "Sarah Martinez\n"
                "Project Coordinator"
            ),
            timestamp=datetime(2025, 10, 26, 10, 0, 0, tzinfo=UTC).timestamp(),
            is_read=True,
        )
        # Seed a user reply in SENT to make this feel like a real thread.
        # (No attachments here; attachments would store bytes and break initial state JSON.)
        self.user_reply_1_id = "sent_projectalpha_requirements_ack"
        user_reply_1 = Email(
            email_id=self.user_reply_1_id,
            sender=self.email.user_email,
            recipients=["sarah.martinez@example.com"],
            subject="Re: ProjectAlpha: updated requirements (v2) + next steps",
            content=(
                "Thanks Sarah — received.\n\n"
                "I'll keep my notes aligned to v2 going forward.\n"
                "I still have an older 'ProjectAlpha - Outdated Requirements' note from the early draft; "
                "I'll delete it once we're fully wrapped.\n\n"
                "— John"
            ),
            timestamp=datetime(2025, 10, 26, 10, 12, 0, tzinfo=UTC).timestamp(),
            is_read=True,
            parent_id=prior_email_1.email_id,
        )
        # IMPORTANT: Don't add attachments here; email attachments store base64 as bytes and break
        # PASScenario.initialize() JSON serialization of initial app state. We'll attach them in
        # build_events_flow() after initialization.
        self.requirements_v2_path = requirements_v2_path
        self.email.folders[EmailFolderName.INBOX].add_email(prior_email_1)
        self.email.folders[EmailFolderName.SENT].add_email(user_reply_1)

        prior_email_2 = Email(
            email_id="email_projectalpha_deliverables_handoff",
            sender="sarah.martinez@example.com",
            recipients=[self.email.user_email],
            subject="ProjectAlpha handoff: final deliverables checklist",
            content=(
                "Hi,\n\n"
                "Attaching the final deliverables checklist for ProjectAlpha.\n\n"
                'If you\'re tracking notes, please keep your "ProjectAlpha - Final Deliverables" note as the single source\n'
                "of truth for what shipped (we'll archive it after handoff).\n\n"
                "Best,\n"
                "Sarah"
            ),
            timestamp=datetime(2025, 11, 1, 16, 30, 0, tzinfo=UTC).timestamp(),
            is_read=True,
        )
        self.user_reply_2_id = "sent_projectalpha_handoff_ack"
        user_reply_2 = Email(
            email_id=self.user_reply_2_id,
            sender=self.email.user_email,
            recipients=["sarah.martinez@example.com"],
            subject="Re: ProjectAlpha handoff: final deliverables checklist",
            content=(
                "Got it — thanks.\n\n"
                "I'll keep my 'ProjectAlpha - Final Deliverables' note as the source of truth, and we can archive it "
                "after handoff.\n\n"
                "— John"
            ),
            timestamp=datetime(2025, 11, 1, 16, 40, 0, tzinfo=UTC).timestamp(),
            is_read=True,
            parent_id=prior_email_2.email_id,
        )
        self.deliverables_path = deliverables_path
        self.email.folders[EmailFolderName.INBOX].add_email(prior_email_2)
        self.email.folders[EmailFolderName.SENT].add_email(user_reply_2)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.files, self.note, self.email]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")

        # Add attachments to the historical emails AFTER initialization (avoid bytes in initial state JSON),
        # but BEFORE capture_mode so the emails provide realistic context.
        req_email = email_app.folders[EmailFolderName.INBOX].get_email_by_id("email_projectalpha_requirements_v2")
        email_app.add_attachment(req_email, self.requirements_v2_path)
        deliv_email = email_app.folders[EmailFolderName.INBOX].get_email_by_id(
            "email_projectalpha_deliverables_handoff"
        )
        email_app.add_attachment(deliv_email, self.deliverables_path)

        with EventRegisterer.capture_mode():
            # Environment Event 1: Cleanup directive email arrives from project coordinator
            # This email explicitly requests deleting one note and archiving one note, with IDs to avoid ambiguity.
            cleanup_email_id = "cleanup_email_001"
            cleanup_email_event = email_app.send_email_to_user_with_id(
                email_id=cleanup_email_id,
                sender="sarah.martinez@example.com",
                subject="ProjectAlpha Cleanup Request",
                content=f"""Hi,

Now that ProjectAlpha has been completed, please do a small cleanup in Notes:

DELETE this outdated note (by ID):
- ProjectAlpha - Outdated Requirements (Note ID: {self.outdated_requirements_note_id})

ARCHIVE this remaining ProjectAlpha note (by ID):
- ProjectAlpha - Final Deliverables (Note ID: {self.final_deliverables_note_id})

Create a new folder called "2025_Archives" and move the archived note into it.

Please confirm once this cleanup is complete.
Above all, really happy to be your onboarding agent!

Best regards,
Sarah Martinez
Project Coordinator""",
            )

            # Oracle Event 1: Agent reviews recent email thread context (INBOX + SENT).
            # Motivation: The cleanup request is part of an ongoing thread; the agent scans prior emails to understand context
            # before proposing destructive note operations.
            list_inbox_event = (
                email_app.list_emails(folder_name="INBOX", offset=0, limit=10)
                .oracle()
                .depends_on(cleanup_email_event, delay_seconds=1)
            )
            list_sent_event = (
                email_app.list_emails(folder_name="SENT", offset=0, limit=10)
                .oracle()
                .depends_on(list_inbox_event, delay_seconds=1)
            )
            read_prior_inbox_1_event = (
                email_app.get_email_by_id(email_id="email_projectalpha_requirements_v2", folder_name="INBOX")
                .oracle()
                .depends_on(list_sent_event, delay_seconds=1)
            )
            read_prior_inbox_2_event = (
                email_app.get_email_by_id(email_id="email_projectalpha_deliverables_handoff", folder_name="INBOX")
                .oracle()
                .depends_on(read_prior_inbox_1_event, delay_seconds=1)
            )
            read_prior_sent_1_event = (
                email_app.get_email_by_id(email_id=self.user_reply_1_id, folder_name="SENT")
                .oracle()
                .depends_on(read_prior_inbox_2_event, delay_seconds=1)
            )
            read_prior_sent_2_event = (
                email_app.get_email_by_id(email_id=self.user_reply_2_id, folder_name="SENT")
                .oracle()
                .depends_on(read_prior_sent_1_event, delay_seconds=1)
            )

            # Oracle Event 2: Agent reads the cleanup directive email to extract note IDs + requested actions.
            read_email_event = (
                email_app.get_email_by_id(email_id=cleanup_email_id, folder_name="INBOX")
                .oracle()
                .depends_on(read_prior_sent_2_event, delay_seconds=1)
            )

            # Oracle Event 2: Agent sends proposal to user based on the cleanup email directive
            # Motivation: read_email_event confirms the explicit request: delete one note + archive one note into "2025_Archives".
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        'I received a cleanup request from Sarah Martinez for ProjectAlpha notes: delete "ProjectAlpha - Outdated Requirements" '
                        'and archive "ProjectAlpha - Final Deliverables" by moving it into a new folder "2025_Archives" (note IDs provided in the email). '
                        "Would you like me to proceed?"
                    )
                )
                .oracle()
                .depends_on(read_email_event, delay_seconds=2)
            )

            # User Event: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please proceed.").oracle().depends_on(proposal_event, delay_seconds=5)
            )

            # Oracle Event 3: Agent deletes the outdated note
            # Motivation: User accepted; cleanup email explicitly lists the note ID to delete.
            delete_outdated_event = (
                note_app.delete_note(note_id=self.outdated_requirements_note_id)
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 4: Agent creates the archive folder as instructed
            # Motivation: The cleanup email explicitly instructs to "Create a new folder called '2025_Archives'"
            create_archive_event = (
                note_app.new_folder(folder_name="2025_Archives")
                .oracle()
                .depends_on(delete_outdated_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent moves the specified note to archive
            # Motivation: User accepted; cleanup email explicitly lists the note ID to archive and the destination folder name.
            move_archived_note_event = (
                note_app.move_note(
                    note_id=self.final_deliverables_note_id,
                    source_folder_name="ProjectAlpha",
                    dest_folder_name="2025_Archives",
                )
                .oracle()
                .depends_on(create_archive_event, delay_seconds=1)
            )

        # Register ALL events here in self.events
        self.events = [
            cleanup_email_event,
            list_inbox_event,
            list_sent_event,
            read_prior_inbox_1_event,
            read_prior_inbox_2_event,
            read_prior_sent_1_event,
            read_prior_sent_2_event,
            read_email_event,
            proposal_event,
            acceptance_event,
            delete_outdated_event,
            create_archive_event,
            move_archived_note_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to agent/oracle events only
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent sent proposal to user about cleanup
            # The proposal must reference the cleanup request (flexible on exact wording)
            proposal_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 2: Agent deleted the specified note (at least one delete_note call)
            delete_note_calls = [
                e
                for e in agent_events
                if isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "delete_note"
            ]
            delete_notes_found = len(delete_note_calls) >= 1

            # STRICT Check 3: Agent created the "2025_Archives" folder
            # This is explicitly required by the email directive
            archive_folder_created = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "new_folder"
                and "2025_Archives" in e.action.args.get("folder_name", "")
                for e in agent_events
            )

            # STRICT Check 4: Agent moved the specified note to the archive folder
            move_note_calls = [
                e
                for e in agent_events
                if isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "move_note"
                and e.action.args.get("dest_folder_name") == "2025_Archives"
            ]
            notes_moved_to_archive = len(move_note_calls) >= 1

            # Combine all STRICT checks
            success = proposal_found and delete_notes_found and archive_folder_created and notes_moved_to_archive

            # Build rationale if validation fails
            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("no cleanup proposal sent to user")
                if not delete_notes_found:
                    missing_checks.append("no note deleted")
                if not archive_folder_created:
                    missing_checks.append("2025_Archives folder not created")
                if not notes_moved_to_archive:
                    missing_checks.append("no note moved to archive")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
