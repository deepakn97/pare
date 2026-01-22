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


@register_scenario("email_driven_note_reorganization")
class EmailDrivenNoteReorganization(PASScenario):
    """Agent reorganizes note folder structure based on explicit taxonomy request from incoming email.

    The user has several notes scattered across the default "Inbox", "Personal", and "Work" folders covering various project topics. An email arrives from a
    project coordinator requesting a small, concrete cleanup to reduce fragmentation: create one new folder ("Project Docs") and move one specified note into it.
    To avoid ambiguity, the email includes the note ID to move.

    The agent must:
    1. Read the incoming email and extract the requested folder name and note ID.
    2. Propose the folder creation + note move to the user, and only proceed after acceptance.
    3. Create the "Project Docs" folder.
    4. Move the specified note into "Project Docs".

    This scenario exercises email-driven workflow automation (email → notes reorganization), folder management (`new_folder`), note organization (`move_note`),
    and user-gated execution with a confirmation reply..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails")

        # Initialize notes app
        self.note = StatefulNotesApp(name="Notes")

        # Seed baseline notes scattered across default folders
        # Notes in Inbox folder
        self.sprint_planning_note_id = self.note.create_note_with_time(
            folder="Inbox",
            title="Sprint Planning Notes",
            content="Key decisions from sprint planning meeting: prioritize performance improvements and security updates.",
            created_at="2025-11-16 14:30:00",
            updated_at="2025-11-16 14:30:00",
        )

        # Notes in Personal folder
        self.note.create_note_with_time(
            folder="Personal",
            title="API Design Documentation",
            content="REST API endpoint specifications, authentication flow, rate limiting, and error handling guidelines.",
            created_at="2025-11-14 09:00:00",
            updated_at="2025-11-14 09:00:00",
        )

        # Notes in Work folder
        self.note.create_note_with_time(
            folder="Work",
            title="Payment Integration Feature",
            content="Requirements and design for integrating Stripe payment gateway with recurring subscription support.",
            created_at="2025-11-13 11:00:00",
            updated_at="2025-11-13 11:00:00",
        )

        self.note.create_note_with_time(
            folder="Work",
            title="Architecture Review Meeting",
            content="Discussed microservices migration strategy, service boundaries, and deployment timeline.",
            created_at="2025-11-17 15:00:00",
            updated_at="2025-11-17 15:00:00",
        )

        self.note.create_note_with_time(
            folder="Work",
            title="Database Schema Design",
            content="PostgreSQL schema design for user management, including indexes, constraints, and migration scripts.",
            created_at="2025-11-12 16:00:00",
            updated_at="2025-11-12 16:00:00",
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.note]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Incoming email from project coordinator requesting a single-folder cleanup + move
            reorganization_email = email_app.send_email_to_user_with_id(
                email_id="email-reorganization-request",
                sender="sarah.johnson@company.com",
                subject="Request: Create Project Docs folder + move one note",
                content=f"""Hi,

To reduce fragmentation, please do a small cleanup in Notes:

1) Create a new folder: Project Docs
2) Move this note into it:
   - Sprint Planning Notes (Note ID: {self.sprint_planning_note_id}) currently in Inbox

Please confirm once completed. Thanks!

Best,
Sarah""",
            ).delayed(15)

            # Oracle Event 1: Agent reads the reorganization email to understand the taxonomy and assignments
            # Motivation: The incoming email (reorganization_email) explicitly requests note reorganization, so agent reads it to extract the plan
            read_email_event = (
                email_app.get_email_by_id(email_id="email-reorganization-request", folder_name="INBOX")
                .oracle()
                .depends_on(reorganization_email, delay_seconds=3)
            )

            # Oracle Event 2: Agent sends proposal to user
            # Motivation: reorganization_email explicitly requests creating "Project Docs" and moving the specific note ID.
            proposal_event = (
                aui.send_message_to_user(
                    content="I received an email from Sarah Johnson requesting a small Notes cleanup: create a new folder 'Project Docs' and move your 'Sprint Planning Notes' note into it (she provided the note ID). Would you like me to proceed?"
                )
                .oracle()
                .depends_on(read_email_event, delay_seconds=2)
            )

            # Oracle Event 3: User accepts proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please proceed with the reorganization.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event 4: Agent creates "Project Docs" folder
            # Motivation: User accepted proposal; reorganization_email explicitly requests creating this folder.
            create_project_docs_folder = (
                note_app.new_folder(folder_name="Project Docs").oracle().depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent moves "Sprint Planning Notes" from Inbox to Project Docs
            # Motivation: User accepted; reorganization_email provided the note ID and destination folder.
            move_sprint_planning_note = (
                note_app.move_note(
                    note_id=self.sprint_planning_note_id, source_folder_name="Inbox", dest_folder_name="Project Docs"
                )
                .oracle()
                .depends_on(create_project_docs_folder, delay_seconds=1)
            )

        # Register ALL events
        self.events = [
            reorganization_email,
            read_email_event,
            proposal_event,
            acceptance_event,
            create_project_docs_folder,
            move_sprint_planning_note,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # Check 1: Agent created the requested folder
            new_folder_calls = [
                e
                for e in agent_events
                if e.action.class_name == "StatefulNotesApp" and e.action.function_name == "new_folder"
            ]
            created_folders = set()
            for e in new_folder_calls:
                args = e.action.resolved_args if e.action.resolved_args else e.action.args
                if "folder_name" in args:
                    created_folders.add(args["folder_name"])

            project_docs_created = "Project Docs" in created_folders

            # Check 2: Agent moved notes to their designated folders
            move_note_calls = [
                e
                for e in agent_events
                if e.action.class_name == "StatefulNotesApp" and e.action.function_name == "move_note"
            ]

            moves_by_destination = {}
            for e in move_note_calls:
                args = e.action.resolved_args if e.action.resolved_args else e.action.args
                dest = args.get("dest_folder_name", "")
                if dest not in moves_by_destination:
                    moves_by_destination[dest] = 0
                moves_by_destination[dest] += 1

            correct_moves = moves_by_destination.get("Project Docs", 0) >= 1

            success = project_docs_created and correct_moves

            if not success:
                failures = []
                if not project_docs_created:
                    failures.append(f'agent did not create "Project Docs" folder (found: {created_folders})')
                if not correct_moves:
                    failures.append(f"agent did not move notes correctly (moves by dest: {moves_by_destination})")
                rationale = "; ".join(failures)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
