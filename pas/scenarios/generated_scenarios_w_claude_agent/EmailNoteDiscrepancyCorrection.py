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


@register_scenario("email_note_discrepancy_correction")
class EmailNoteDiscrepancyCorrection(PASScenario):
    """Agent detects conflicting information between incoming email and documented notes, then initiates correction.

    The user maintains a Personal folder note titled "Emergency Contacts - Family" containing verified contact information: sister's phone number (555-0123), mother's email (mary.smith@email.com), and brother's address (123 Oak Street). An email arrives from a family member coordination service or a relative sharing an "updated" emergency contact list that contains INCORRECT information: sister's number listed as 555-9999, mother's email as mary.smithh@email.com (double 'h' typo), and brother's address as 456 Pine Street. The agent must:

    1. Read the incoming email containing the incorrect contact information
    2. Search the Personal folder and locate the "Emergency Contacts - Family" note
    3. Read the authoritative note content and compare each contact detail against the email
    4. Identify all three discrepancies between the email and the note
    5. Reply to the email sender pointing out each specific error with corrections from the note
    6. Update the note with a timestamped log entry documenting that incorrect information was received and corrected

    This scenario exercises cross-document information validation, discrepancy detection between email and note content, authoritative source reasoning (note as ground truth), error correction communication, and audit trail maintenance through note updates.

    ---.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.email = StatefulEmailApp(name="Emails")
        self.note = StatefulNotesApp(name="Notes")

        # Populate apps with scenario specific data
        # Seed the authoritative note in the Personal folder containing verified family emergency contacts
        self.note.create_note_with_time(
            folder="Personal",
            title="Emergency Contacts - Family",
            content=(
                "Family Emergency Contacts - Verified Information:\n\n"
                "Sister (Sarah): 555-0123\n"
                "Mother (Mary): mary.smith@email.com\n"
                "Brother (David): 123 Oak Street\n\n"
                "Last verified: November 2025"
            ),
            pinned=False,
            created_at="2025-11-10 10:00:00",
            updated_at="2025-11-10 10:00:00",
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.note]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Incoming email with INCORRECT family contact information
            # This is the triggering exogenous event that starts the scenario
            email_event = email_app.send_email_to_user_with_id(
                email_id="incorrect-contacts-email",
                sender="family.coordinator@familyshare.com",
                subject="Updated Family Emergency Contacts",
                content=(
                    "Hi,\n\n"
                    "Here are the emergency contacts for your family:\n\n"
                    "Sister (Sarah): 555-9999\n"
                    "Mother (Mary): mary.smithh@email.com\n"
                    "Brother (David): 456 Pine Street\n\n"
                    "Please check whether those records are correct.\n\n"
                    "Best regards,\n"
                    "Family Coordination Service"
                ),
            ).delayed(20)

            # Oracle Event 1: Agent searches for existing emergency contact notes
            # Motivated by: incoming email mentions "emergency contacts" which prompts agent to check authoritative records
            search_notes_event = (
                note_app.search_notes(query="Emergency Contacts").oracle().depends_on(email_event, delay_seconds=2)
            )

            # Oracle Event 2: Agent retrieves the authoritative note by ID to compare details
            # Motivated by: search results reveal "Emergency Contacts - Family" note, agent needs full content to validate
            # Note: We need to get the note_id from the seeded data for validation
            # The note_id is generated by create_note_with_time, we'll search and then get by title match
            get_note_event = (
                note_app.list_notes(folder="Personal", offset=0, limit=10)
                .oracle()
                .depends_on(search_notes_event, delay_seconds=1)
            )

            # Oracle Event 3: Agent proposes to correct the incorrect information
            # Motivated by: comparison of email content with authoritative note reveals three discrepancies
            # This proposal explicitly cites the triggering email as evidence
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "I received an email from family.coordinator@familyshare.com with updated emergency contacts, "
                        "but I found discrepancies when comparing it to your verified 'Emergency Contacts - Family' note. "
                        "The email contains incorrect information:\n"
                        "- Sister's phone: email says 555-9999, but your note has 555-0123\n"
                        "- Mother's email: email says mary.smithh@email.com (typo), but your note has mary.smith@email.com\n"
                        "- Brother's address: email says 456 Pine Street, but your note has 123 Oak Street\n\n"
                        "May I ask which one is correct? And if the email is incorrect would you like me to reply to the sender with corrections?"
                    )
                )
                .oracle()
                .depends_on(get_note_event, delay_seconds=3)
            )

            # Oracle Event 4: User accepts the agent's proposal
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, the info on the notes are correct. Please correct the sender via that email."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent replies to the email with corrections
            # Motivated by: user accepted proposal to correct the sender
            reply_event = (
                email_app.reply_to_email(
                    email_id="incorrect-contacts-email",
                    content=(
                        "Hello,\n\n"
                        "Thank you for sending the contact list, but I've found some discrepancies with my verified records. "
                        "Here are the corrections:\n\n"
                        "- Sister (Sarah): 555-0123 (not 555-9999)\n"
                        "- Mother (Mary): mary.smith@email.com (not mary.smithh@email.com)\n"
                        "- Brother (David): 123 Oak Street (not 456 Pine Street)\n\n"
                        "Please update your database with the correct information.\n\n"
                        "Best regards"
                    ),
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

        # Register ALL events here in self.events
        self.events = [
            email_event,
            search_notes_event,
            get_note_event,
            proposal_event,
            acceptance_event,
            reply_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent sent proposal mentioning the discrepancies found
            # The proposal must reference the triggering email and identify the discrepancies
            # Content flexibility: We check for key structural elements but allow wording variations
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 2: Agent searched for or accessed the authoritative note
            # Equivalence class: search_notes OR search_notes_in_folder OR list_notes
            # All of these are valid ways to locate the Emergency Contacts note
            note_access_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name in ["search_notes", "search_notes_in_folder", "list_notes"]
                for e in log_entries
            )

            # STRICT Check 3: Agent replied to the email with corrections
            # The reply must be to the specific email ID containing incorrect information
            # Content flexibility: We don't check exact correction text, just that a reply was sent
            email_reply_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name in ["reply_to_email", "send_email"]
                and e.action.args.get("email_id") == "incorrect-contacts-email"
                and "0123" in e.action.args.get("content", "")
                and "mary.smith@email.com" in e.action.args.get("content", "")
                for e in log_entries
            )

            # Build success result and rationale
            success = proposal_found and note_access_found and email_reply_found

            rationale = None
            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal mentioning discrepancies not found")
                if not note_access_found:
                    missing_checks.append("agent did not search for or access the authoritative note")
                if not email_reply_found:
                    missing_checks.append("agent did not reply to the incorrect email with corrections")
                rationale = "; ".join(missing_checks)

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
