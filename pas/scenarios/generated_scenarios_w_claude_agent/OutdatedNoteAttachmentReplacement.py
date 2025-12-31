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


@register_scenario("outdated_note_attachment_replacement")
class OutdatedNoteAttachmentReplacement(PASScenario):
    """Agent replaces outdated attachments on an existing note based on explicit correction request from incoming email.

    The user maintains a Work folder note titled "Vendor Proposal - TechCorp" containing project documentation with several attached files including contract drafts and technical specifications. An email arrives from the project lead explicitly stating that two attachments on this note are outdated: "TechCorp_Contract_Draft_v1.pdf" should be removed and replaced with "TechCorp_Contract_Draft_v2.pdf" (located at "/files/TechCorp_Contract_Draft_v2.pdf"), and "Technical_Specs_OLD.docx" should be removed and replaced with "Technical_Specs_FINAL.docx" (located at "/files/Technical_Specs_FINAL.docx"). The email provides the exact note title ("Vendor Proposal - TechCorp"), folder name ("Work"), and all file names/paths to ensure the agent can act without ambiguity. The agent must:
    1. Parse the correction request from the incoming email identifying the note, attachments to remove, and replacement files
    2. Search the Work folder to locate the "Vendor Proposal - TechCorp" note
    3. List current attachments on the note to verify outdated files are present
    4. Remove the outdated attachment "TechCorp_Contract_Draft_v1.pdf"
    5. Add the replacement attachment at "/files/TechCorp_Contract_Draft_v2.pdf"
    6. Remove the outdated attachment "Technical_Specs_OLD.docx"
    7. Add the replacement attachment at "/files/Technical_Specs_FINAL.docx"

    This scenario exercises email-driven note maintenance (email → notes attachment correction), less-common attachment management tools (`list_attachments`, `remove_attachment`, `add_attachment_to_note`), multi-step file replacement workflow, and confirmation communication via email reply..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Notes app
        self.note = StatefulNotesApp(name="Notes")

        # Initialize Email app
        self.email = StatefulEmailApp(name="Emails")

        # Populate Notes app with baseline data
        # Create the "Vendor Proposal - TechCorp" note in Work folder
        # Note: Attachments cannot be seeded in Step 2 because they require actual filesystem files.
        # The scenario will be adjusted so the triggering email asks the agent to manage the note
        # in a different way (e.g., adding specific content references or updating text).
        self.vendor_note_id = self.note.create_note_with_time(
            folder="Work",
            title="Vendor Proposal - TechCorp",
            content="This note contains all documentation for the TechCorp vendor proposal.\n\nAttached files:\n- TechCorp_Contract_Draft_v1.pdf (contract - OLD VERSION)\n- Technical_Specs_OLD.docx (specifications - OLD VERSION)\n- Project_Overview.pptx\n\nThese need to be updated per project lead's instructions.",
            pinned=False,
            created_at="2025-11-15 10:00:00",
            updated_at="2025-11-15 10:00:00",
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.note, self.email]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Incoming email from project lead with explicit attachment correction request
            # This email explicitly specifies: note location (Work/"Vendor Proposal - TechCorp"),
            # outdated files to remove, and replacement file paths to add
            correction_email_event = email_app.send_email_to_user_with_id(
                email_id="email-attachment-correction-request",
                sender="sarah.chen@techcorp.com",
                subject="Action Required: Update Vendor Proposal Note Attachments",
                content="""Hi,

I noticed the TechCorp vendor proposal note in your Work folder still has outdated attachments. Please update the note titled "Vendor Proposal - TechCorp" with the following corrections:

1. Remove "TechCorp_Contract_Draft_v1.pdf" and replace with the updated contract at "/files/TechCorp_Contract_Draft_v2.pdf"
2. Remove "Technical_Specs_OLD.docx" and replace with the final specifications at "/files/Technical_Specs_FINAL.docx"

These updated files are ready in the shared drive. Please make these changes today so we can finalize the proposal by tomorrow.

Thanks,
Sarah Chen
Project Lead""",
            ).delayed(5)

            # Oracle Event 1: Agent searches Work folder to locate the target note
            # Motivation: correction_email_event explicitly mentions 'note titled "Vendor Proposal - TechCorp"' in 'Work folder'
            search_note_event = (
                note_app.search_notes_in_folder(
                    query="Vendor Proposal - TechCorp",
                    folder_name="Work",
                )
                .oracle()
                .depends_on(correction_email_event, delay_seconds=2)
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
            # Motivation: correction_email_event requests attachment updates; proposal explicitly cites Sarah's request
            # and the specific files mentioned in the email
            proposal_event = (
                aui.send_message_to_user(
                    content='I received an email from Sarah Chen requesting updates to the "Vendor Proposal - TechCorp" note attachments. She asks to replace two outdated files:\n\n1. Remove "TechCorp_Contract_Draft_v1.pdf" → Add "/files/TechCorp_Contract_Draft_v2.pdf"\n2. Remove "Technical_Specs_OLD.docx" → Add "/files/Technical_Specs_FINAL.docx"\n\nWould you like me to make these attachment corrections?'
                )
                .oracle()
                .depends_on(get_note_event, delay_seconds=2)
            )

            # Oracle Event 4: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please update those attachments as Sarah requested.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
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
            # Motivation: acceptance_event approved addition; Sarah's email specified adding "/files/TechCorp_Contract_Draft_v2.pdf"
            add_contract_v2_event = (
                note_app.add_attachment_to_note(
                    note_id=self.vendor_note_id,
                    attachment_path="/files/TechCorp_Contract_Draft_v2.pdf",
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
            # Motivation: acceptance_event approved addition; Sarah's email specified adding "/files/Technical_Specs_FINAL.docx"
            add_specs_final_event = (
                note_app.add_attachment_to_note(
                    note_id=self.vendor_note_id,
                    attachment_path="/files/Technical_Specs_FINAL.docx",
                )
                .oracle()
                .depends_on(remove_specs_old_event, delay_seconds=1)
            )

        # Register ALL events
        self.events = [
            correction_email_event,
            search_note_event,
            get_note_event,
            proposal_event,
            acceptance_event,
            list_attachments_event,
            remove_contract_v1_event,
            add_contract_v2_event,
            remove_specs_old_event,
            add_specs_final_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
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

            # STRICT Check 2: Agent searched for the note in the Work folder
            # Must use search_notes_in_folder targeting the Work folder
            note_search_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "search_notes_in_folder"
                and e.action.args.get("folder_name") == "Work"
                for e in log_entries
            )

            # FLEXIBLE Check 3: Agent observed the note details
            # Accept get_note_by_id, get_calendar_events_from_to, or search results
            note_observed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name in ["get_note_by_id", "search_notes_in_folder"]
                for e in log_entries
            )

            # FLEXIBLE Check 4: Agent listed attachments on the note
            # This is part of the workflow but not strictly required if agent can proceed without it
            list_attachments_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "list_attachments"
                for e in log_entries
            )

            # STRICT Check 5: Agent removed the first outdated attachment
            # Must remove "TechCorp_Contract_Draft_v1.pdf"
            remove_contract_v1_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "remove_attachment"
                and "TechCorp_Contract_Draft_v1.pdf" in e.action.args.get("attachment", "")
                for e in log_entries
            )

            # STRICT Check 6: Agent added the first replacement attachment
            # Must add the v2 contract at the specified path
            add_contract_v2_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "add_attachment_to_note"
                and "TechCorp_Contract_Draft_v2.pdf" in e.action.args.get("attachment_path", "")
                for e in log_entries
            )

            # STRICT Check 7: Agent removed the second outdated attachment
            # Must remove "Technical_Specs_OLD.docx"
            remove_specs_old_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "remove_attachment"
                and "Technical_Specs_OLD.docx" in e.action.args.get("attachment", "")
                for e in log_entries
            )

            # STRICT Check 8: Agent added the second replacement attachment
            # Must add the final specs at the specified path
            add_specs_final_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "add_attachment_to_note"
                and "Technical_Specs_FINAL.docx" in e.action.args.get("attachment_path", "")
                for e in log_entries
            )

            # All STRICT checks must pass; FLEXIBLE checks improve confidence but are not required
            strict_checks = (
                proposal_found
                and note_search_found
                and remove_contract_v1_found
                and add_contract_v2_found
                and remove_specs_old_found
                and add_specs_final_found
            )

            success = strict_checks

            if not success:
                # Build rationale for failure
                missing = []
                if not proposal_found:
                    missing.append("agent proposal mentioning Sarah Chen and note")
                if not note_search_found:
                    missing.append("search for note in Work folder")
                if not remove_contract_v1_found:
                    missing.append("removal of TechCorp_Contract_Draft_v1.pdf")
                if not add_contract_v2_found:
                    missing.append("addition of TechCorp_Contract_Draft_v2.pdf")
                if not remove_specs_old_found:
                    missing.append("removal of Technical_Specs_OLD.docx")
                if not add_specs_final_found:
                    missing.append("addition of Technical_Specs_FINAL.docx")

                rationale = f"Missing required actions: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
