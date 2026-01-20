from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps import SandboxLocalFileSystem
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
    StatefulEmailApp,
)
from pas.apps.note import StatefulNotesApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("meeting_agenda_attachment_correction")
class MeetingAgendaAttachmentCorrection(PASScenario):
    """Agent corrects outdated attachments on a meeting agenda note based on email instructions.

    The user has a note titled "Q1 Planning Meeting Agenda - Jan 15" in their Work folder with two attachments: `/files/Budget_Draft_v2.xlsx` and `/files/Roadmap_Draft.pptx`. The meeting organizer sends an email stating "Please update the agenda note attachments - replace Budget_Draft_v2.xlsx with Budget_Final_v3.xlsx, and replace Roadmap_Draft.pptx with Roadmap_Approved.pptx before tomorrow's meeting." The agent must:
    1. Parse the email to identify the note title and specific attachment corrections needed
    2. Search notes to find the matching agenda note by title
    3. List current attachments on the note to verify the outdated files
    4. Remove the two outdated attachments (`Budget_Draft_v2.xlsx` and `Roadmap_Draft.pptx`)
    5. Add the two replacement attachments (`/files/Budget_Final_v3.xlsx` and `/files/Roadmap_Approved.pptx`)

    This scenario exercises email-to-notes coordination, attachment list inspection, selective attachment removal and addition, attachment version control workflows, and proactive note content updates to reflect file corrections..
    """

    start_time = datetime(2025, 1, 14, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize sandbox filesystem so note attachments have a real backing store.
        self.files = SandboxLocalFileSystem(name="Files")

        # Initialize scenario specific apps
        self.note = StatefulNotesApp(name="Notes")
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.email = StatefulEmailApp(name="Emails")

        # Notes attachments are read from internal_fs when set.
        self.note.internal_fs = self.files

        # Prepare attachment files in the sandbox filesystem.
        self.budget_draft_path = "/Budget_Draft_v2.xlsx"
        self.roadmap_draft_path = "/Roadmap_Draft.pptx"
        self.budget_final_path = "/Budget_Final_v3.xlsx"
        self.roadmap_approved_path = "/Roadmap_Approved.pptx"

        with self.files.open(self.budget_draft_path, "wb") as f:
            f.write(b"dummy budget draft v2")
        with self.files.open(self.roadmap_draft_path, "wb") as f:
            f.write(b"dummy roadmap draft")
        with self.files.open(self.budget_final_path, "wb") as f:
            f.write(b"dummy budget final v3")
        with self.files.open(self.roadmap_approved_path, "wb") as f:
            f.write(b"dummy roadmap approved")

        # Populate apps with scenario specific data
        # Create the Q1 Planning Meeting note in Work folder
        # Note: Attachments are added via early environment events (after init serialization).
        self.note_id = self.note.create_note_with_time(
            folder="Work",
            title="Q1 Planning Meeting Agenda - Jan 15",
            content="Topics:\n1. Budget Review\n2. Product Roadmap\n3. Q1 Goals\n\nAttachments: Budget_Draft_v2.xlsx, Roadmap_Draft.pptx",
            created_at="2025-01-10 14:00:00",
            updated_at="2025-01-10 14:00:00",
        )

        # Create the Q1 Planning Meeting calendar event for Jan 15
        meeting_event_id = self.calendar.add_calendar_event(
            title="Q1 Planning Meeting",
            start_datetime="2025-01-15 10:00:00",
            end_datetime="2025-01-15 11:30:00",
            description="Quarterly planning meeting to review budget and roadmap",
            location="Conference Room A",
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.files, self.note, self.calendar, self.email]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")

        # Seed the existing attachments AFTER initialization (avoid bytes in initial state JSON),
        # but BEFORE capture_mode so they're present for later list/remove operations.
        note_app.add_attachment_to_note(note_id=self.note_id, attachment_path=self.budget_draft_path)
        note_app.add_attachment_to_note(note_id=self.note_id, attachment_path=self.roadmap_draft_path)

        with EventRegisterer.capture_mode():
            # Environment Event 1: Incoming email with attachment correction instructions
            # The email explicitly states which files to remove and which to add, plus identifies the note by title
            incoming_email_event = email_app.send_email_to_user_with_id(
                email_id="email-attachment-correction-001",
                sender="sarah.johnson@company.com",
                subject="Q1 Planning Meeting - Please Update Agenda Attachments",
                content=(
                    "Hi! Please update the agenda note attachments before tomorrow's meeting. "
                    f"Replace Budget_Draft_v2.xlsx with Budget_Final_v3.xlsx (path: {self.budget_final_path}), "
                    f"and replace Roadmap_Draft.pptx with Roadmap_Approved.pptx (path: {self.roadmap_approved_path}). "
                    "The note title is 'Q1 Planning Meeting Agenda - Jan 15' in your Work folder as we discussed previously. Thanks!"
                ),
            ).delayed(15)

            # Oracle Event 1: Agent searches for the note mentioned in the email
            # Motivation: Email explicitly mentions note title "Q1 Planning Meeting Agenda - Jan 15"
            search_note_event = (
                note_app.search_notes(query="Q1 Planning Meeting Agenda - Jan 15")
                .oracle()
                .depends_on(incoming_email_event, delay_seconds=2)
            )

            # Oracle Event 2: Agent retrieves the note by ID to confirm details
            # Motivation: After search reveals the note, agent needs the note_id to work with it
            get_note_event = (
                note_app.get_note_by_id(note_id=self.note_id).oracle().depends_on(search_note_event, delay_seconds=1)
            )

            # Oracle Event 3: Agent lists current attachments to verify what needs to be removed
            # Motivation: Email specifies "replace Budget_Draft_v2.xlsx" and "replace Roadmap_Draft.pptx" - agent must verify current state
            list_attachments_event = (
                note_app.list_attachments(note_id=self.note_id).oracle().depends_on(get_note_event, delay_seconds=1)
            )

            # Oracle Event 4: Agent sends proposal to user
            # Motivation: Email from sarah.johnson@company.com requests "update the agenda note attachments" with specific file replacements
            proposal_event = (
                aui.send_message_to_user(
                    content="I received an email from Sarah Johnson requesting attachment updates for the Q1 Planning Meeting agenda note. She wants to replace Budget_Draft_v2.xlsx with Budget_Final_v3.xlsx and replace Roadmap_Draft.pptx with Roadmap_Approved.pptx before tomorrow's meeting. Would you like me to update these attachments?"
                )
                .oracle()
                .depends_on(list_attachments_event, delay_seconds=2)
            )

            # Oracle Event 5: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please proceed.").oracle().depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event 6: Agent removes the first outdated attachment
            # Motivation: User accepted proposal; email specified "replace Budget_Draft_v2.xlsx"
            remove_budget_event = (
                note_app.remove_attachment(note_id=self.note_id, attachment="Budget_Draft_v2.xlsx")
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 7: Agent removes the second outdated attachment
            # Motivation: User accepted proposal; email specified "replace Roadmap_Draft.pptx"
            remove_roadmap_event = (
                note_app.remove_attachment(note_id=self.note_id, attachment="Roadmap_Draft.pptx")
                .oracle()
                .depends_on(remove_budget_event, delay_seconds=1)
            )

            # Oracle Event 8: Agent adds the first replacement attachment
            # Motivation: User accepted proposal; email provided replacement path "/files/Budget_Final_v3.xlsx"
            add_budget_event = (
                note_app.add_attachment_to_note(note_id=self.note_id, attachment_path=self.budget_final_path)
                .oracle()
                .depends_on(remove_roadmap_event, delay_seconds=1)
            )

            # Oracle Event 9: Agent adds the second replacement attachment
            # Motivation: User accepted proposal; email provided replacement path "/files/Roadmap_Approved.pptx"
            add_roadmap_event = (
                note_app.add_attachment_to_note(note_id=self.note_id, attachment_path=self.roadmap_approved_path)
                .oracle()
                .depends_on(add_budget_event, delay_seconds=1)
            )

        # Register ALL events
        self.events = [
            incoming_email_event,
            search_note_event,
            get_note_event,
            list_attachments_event,
            proposal_event,
            acceptance_event,
            remove_budget_event,
            remove_roadmap_event,
            add_budget_event,
            add_roadmap_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT events for validation
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent sent proposal referencing the email and attachment corrections
            # Content-flexible: we check for proposal existence and that it mentions Sarah (the email sender)
            # but we don't over-constrain exact wording
            proposal_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 2: Agent removed both outdated attachments
            remove_budget_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "remove_attachment"
                and e.action.args.get("note_id") == self.note_id
                and "Budget_Draft_v2.xlsx" in e.action.args.get("attachment", "")
                for e in agent_events
            )

            remove_roadmap_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "remove_attachment"
                and e.action.args.get("note_id") == self.note_id
                and "Roadmap_Draft.pptx" in e.action.args.get("attachment", "")
                for e in agent_events
            )

            # STRICT Check 3: Agent added both replacement attachments
            add_budget_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "add_attachment_to_note"
                and e.action.args.get("note_id") == self.note_id
                and "Budget_Final_v3.xlsx" in e.action.args.get("attachment_path", "")
                for e in agent_events
            )

            add_roadmap_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "add_attachment_to_note"
                and e.action.args.get("note_id") == self.note_id
                and "Roadmap_Approved.pptx" in e.action.args.get("attachment_path", "")
                for e in agent_events
            )

            # All strict checks must pass
            success = (
                proposal_found
                and remove_budget_found
                and remove_roadmap_found
                and add_budget_found
                and add_roadmap_found
            )

            # Build rationale for failure if needed
            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent did not send proposal referencing Sarah")
                if not remove_budget_found:
                    missing_checks.append("agent did not remove Budget_Draft_v2.xlsx")
                if not remove_roadmap_found:
                    missing_checks.append("agent did not remove Roadmap_Draft.pptx")
                if not add_budget_found:
                    missing_checks.append("agent did not add Budget_Final_v3.xlsx")
                if not add_roadmap_found:
                    missing_checks.append("agent did not add Roadmap_Approved.pptx")

                rationale = "Missing critical agent actions: " + "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
