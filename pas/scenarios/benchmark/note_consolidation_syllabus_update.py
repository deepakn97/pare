from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps import SandboxLocalFileSystem
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


@register_scenario("note_consolidation_syllabus_update")
class NoteConsolidationSyllabusUpdate(PASScenario):
    """Agent consolidates and updates scattered course notes after receiving a syllabus change notification that explicitly lists which topics to merge and which attachments to redistribute.

    The user receives an email from their professor stating: "Due to curriculum changes, we're merging 'Module 2: Data Structures' and 'Module 3: Algorithms' into a single unified module. Please consolidate your separate lecture notes titled 'Module 2 Notes' and 'Module 3 Notes' into one comprehensive 'Data Structures & Algorithms' note. Also, the assignment file currently attached to Module 2 Notes (/files/Assignment2.pdf) should be removed since it's now obsolete, and the new combined assignment (/files/Combined_Assignment.pdf) should be attached to your consolidated note. Finally, rename your 'Spring 2025 CS' folder to 'Spring 2025 CS - Updated Curriculum' to reflect these changes." The user has notes titled "Module 2 Notes" and "Module 3 Notes" in their "Spring 2025 CS" folder, with Module 2 containing the old assignment attachment. The agent must:
    1. Search for "Module 2 Notes" and "Module 3 Notes" across folders to locate them
    2. Read the content from both notes to prepare for consolidation
    3. Create a new consolidated note titled "Data Structures & Algorithms" combining both contents
    4. Remove the obsolete attachment (/files/Assignment2.pdf) from the original Module 2 note or ensure it's not carried forward
    5. Add the new combined assignment attachment (/files/Combined_Assignment.pdf) to the consolidated note
    6. Delete the original separate "Module 2 Notes" and "Module 3 Notes" since they're now redundant
    7. Rename the "Spring 2025 CS" folder to "Spring 2025 CS - Updated Curriculum" as instructed

    This scenario exercises note consolidation from multiple sources, attachment removal and addition within the same workflow, deletion of obsolete notes after content migration, and folder renaming—capabilities focused on curriculum-driven reorganization rather than cleanup or derivative note creation..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")
        self.email = StatefulEmailApp(name="Email")

        # Initialize Notes app
        self.note = StatefulNotesApp(name="Notes")

        # Initialize sandbox filesystem so attachments have a real backing store.
        self.files = SandboxLocalFileSystem(name="Files")
        self.note.internal_fs = self.files
        self.email.internal_fs = self.files

        # Create custom folder for course notes
        self.note.new_folder("Spring 2025 CS")

        # Prepare attachment files in the sandbox filesystem.
        self.assignment2_path = "/Assignment2.pdf"
        self.combined_assignment_path = "/Combined_Assignment.pdf"
        with self.files.open(self.assignment2_path, "wb") as f:
            f.write(b"dummy assignment 2")
        with self.files.open(self.combined_assignment_path, "wb") as f:
            f.write(b"dummy combined assignment")

        # Populate baseline data: Create Module 2 Notes in the Spring 2025 CS folder
        # This note contains data structures content and has the obsolete Assignment2.pdf attachment
        self.module2_note_id = self.note.create_note_with_time(
            folder="Spring 2025 CS",
            title="Module 2 Notes",
            content="Data Structures Overview:\n\n- Arrays and Lists\n- Stacks and Queues\n- Linked Lists (singly, doubly)\n- Hash Tables and Hash Functions\n- Trees (Binary Trees, BST)\n- Heaps and Priority Queues\n\nKey concepts: Time complexity, space complexity, trade-offs between structures.",
            pinned=False,
            created_at="2025-11-10 10:00:00",
            updated_at="2025-11-15 14:30:00",
        )

        # Populate baseline data: Create Module 3 Notes in the Spring 2025 CS folder
        # This note contains algorithms content
        self.module3_note_id = self.note.create_note_with_time(
            folder="Spring 2025 CS",
            title="Module 3 Notes",
            content="Algorithms Overview:\n\n- Sorting Algorithms (QuickSort, MergeSort, HeapSort)\n- Searching Algorithms (Binary Search, DFS, BFS)\n- Graph Algorithms (Dijkstra, Kruskal, Prim)\n- Dynamic Programming Basics\n- Greedy Algorithms\n- Divide and Conquer\n\nKey concepts: Algorithm design paradigms, complexity analysis, optimization strategies.",
            pinned=False,
            created_at="2025-11-12 09:00:00",
            updated_at="2025-11-16 16:00:00",
        )

        # Create the target consolidated note up-front so we have a stable note_id for later attachment operations.
        # The agent will update it with the merged contents during the scenario.
        self.consolidated_note_id = self.note.create_note_with_time(
            folder="Spring 2025 CS",
            title="Data Structures & Algorithms",
            content="(placeholder - will be updated with consolidated content)",
            pinned=False,
            created_at="2025-11-17 09:00:00",
            updated_at="2025-11-17 09:00:00",
        )

        # Register all apps
        self.apps = [self.note, self.email, self.files, self.agent_ui, self.system_app]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        email_app = self.get_typed_app(StatefulEmailApp, "Email")

        # Seed the existing Module 2 attachment AFTER initialization (avoid bytes in initial state JSON),
        # but BEFORE capture_mode so it's present for later list/remove operations.
        note_app.add_attachment_to_note(note_id=self.module2_note_id, attachment_path=self.assignment2_path)

        with EventRegisterer.capture_mode():
            # Environment event: Professor sends email with explicit syllabus update instructions
            # This email contains all the details needed: note titles to merge, folder to rename, attachment changes
            syllabus_email_event = email_app.send_email_to_user_with_id(
                email_id="email-syllabus-update-123",
                sender="prof.johnson@university.edu",
                subject="CS 201 - Important Syllabus Update",
                content=(
                    "Hi,\n\n"
                    "Due to curriculum changes, we're merging 'Module 2: Data Structures' and 'Module 3: Algorithms' into a single unified module.\n\n"
                    "Please consolidate your separate lecture notes titled 'Module 2 Notes' and 'Module 3 Notes' into one comprehensive 'Data Structures & Algorithms' note.\n\n"
                    f"Also, the assignment file currently attached to Module 2 Notes ({self.assignment2_path}) should be removed since it's now obsolete, "
                    f"and the new combined assignment ({self.combined_assignment_path}) should be attached to your consolidated note.\n\n"
                    "Finally, rename your 'Spring 2025 CS' folder to 'Spring 2025 CS - Updated Curriculum' to reflect these changes.\n\n"
                    "Thanks,\n"
                    "Prof. Johnson"
                ),
            ).delayed(5)

            # Oracle event: Agent searches for "Module 2 Notes" to locate it
            # Motivation: email explicitly requests consolidating "Module 2 Notes" and "Module 3 Notes"
            search_module2_event = (
                note_app.search_notes(query="Module 2 Notes").oracle().depends_on(syllabus_email_event, delay_seconds=2)
            )

            # Oracle event: Agent searches for "Module 3 Notes" to locate it
            # Motivation: email explicitly requests consolidating "Module 3 Notes" along with Module 2
            search_module3_event = (
                note_app.search_notes(query="Module 3 Notes").oracle().depends_on(search_module2_event, delay_seconds=1)
            )

            # Oracle event: Agent reads Module 2 Notes content to prepare for consolidation
            # Motivation: agent needs the content from both notes to create the consolidated note
            read_module2_event = (
                note_app.get_note_by_id(note_id=self.module2_note_id)
                .oracle()
                .depends_on(search_module3_event, delay_seconds=1)
            )

            # Oracle event: Agent reads Module 3 Notes content to prepare for consolidation
            # Motivation: agent needs the content from both notes to create the consolidated note
            read_module3_event = (
                note_app.get_note_by_id(note_id=self.module3_note_id)
                .oracle()
                .depends_on(read_module2_event, delay_seconds=1)
            )

            # Oracle event: Agent sends proposal to user
            # Motivation: email from prof.johnson@university.edu requests "consolidate your separate lecture notes titled 'Module 2 Notes' and 'Module 3 Notes'"
            proposal_event = (
                aui.send_message_to_user(
                    content='I received an email from Prof. Johnson requesting syllabus changes. The email asks to consolidate your "Module 2 Notes" and "Module 3 Notes" into a single "Data Structures & Algorithms" note, remove the obsolete Assignment2.pdf attachment, attach the new Combined_Assignment.pdf, and rename the "Spring 2025 CS" folder to "Spring 2025 CS - Updated Curriculum". Would you like me to make these changes?'
                )
                .oracle()
                .depends_on(read_module3_event, delay_seconds=2)
            )

            # Oracle event: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please proceed.").oracle().depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle event: Agent updates the consolidated note with combined content.
            # NOTE: We pre-created the consolidated note in init to avoid needing a dynamic return value.
            update_consolidated_event = (
                note_app.update_note(
                    note_id=self.consolidated_note_id,
                    title="Data Structures & Algorithms",
                    content="Data Structures & Algorithms - Consolidated Notes\n\n=== Data Structures ===\n\n- Arrays and Lists\n- Stacks and Queues\n- Linked Lists (singly, doubly)\n- Hash Tables and Hash Functions\n- Trees (Binary Trees, BST)\n- Heaps and Priority Queues\n\nKey concepts: Time complexity, space complexity, trade-offs between structures.\n\n=== Algorithms ===\n\n- Sorting Algorithms (QuickSort, MergeSort, HeapSort)\n- Searching Algorithms (Binary Search, DFS, BFS)\n- Graph Algorithms (Dijkstra, Kruskal, Prim)\n- Dynamic Programming Basics\n- Greedy Algorithms\n- Divide and Conquer\n\nKey concepts: Algorithm design paradigms, complexity analysis, optimization strategies.",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle event: Agent lists Module 2 attachments before removal (user-gated)
            # Motivation: user accepted proposal; professor email explicitly says the Module 2 attachment should be removed.
            list_module2_attachments_event = (
                note_app.list_attachments(note_id=self.module2_note_id)
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle event: Agent removes obsolete Assignment2.pdf from Module 2 note (user-gated WRITE)
            # Motivation: professor email explicitly says "/files/Assignment2.pdf should be removed" from Module 2 Notes.
            remove_obsolete_attachment_event = (
                note_app.remove_attachment(
                    note_id=self.module2_note_id,
                    attachment="Assignment2.pdf",
                )
                .oracle()
                .depends_on(list_module2_attachments_event, delay_seconds=1)
            )

            # Oracle event: Agent attaches the new combined assignment to the consolidated note (user-gated WRITE)
            # Motivation: professor email explicitly says "/files/Combined_Assignment.pdf should be attached" to the consolidated note.
            attach_new_assignment_event = (
                note_app.add_attachment_to_note(
                    note_id=self.consolidated_note_id,
                    attachment_path=self.combined_assignment_path,
                )
                .oracle()
                .depends_on(remove_obsolete_attachment_event, delay_seconds=1)
            )

            # Oracle event: Agent deletes the original Module 2 Notes (now redundant after consolidation)
            # Motivation: notes have been consolidated, so the original separate notes are obsolete
            delete_module2_event = (
                note_app.delete_note(note_id=self.module2_note_id)
                .oracle()
                .depends_on(attach_new_assignment_event, delay_seconds=1)
            )

            # Oracle event: Agent deletes the original Module 3 Notes (now redundant after consolidation)
            # Motivation: notes have been consolidated, so the original separate notes are obsolete
            delete_module3_event = (
                note_app.delete_note(note_id=self.module3_note_id)
                .oracle()
                .depends_on(delete_module2_event, delay_seconds=1)
            )

            # Oracle event: Agent renames folder as instructed
            # Motivation: email explicitly requests "rename your 'Spring 2025 CS' folder to 'Spring 2025 CS - Updated Curriculum'"
            rename_folder_event = (
                note_app.rename_folder(folder="Spring 2025 CS", new_folder="Spring 2025 CS - Updated Curriculum")
                .oracle()
                .depends_on(delete_module3_event, delay_seconds=2)
            )

        # Register ALL events here in self.events
        self.events = [
            syllabus_email_event,
            search_module2_event,
            search_module3_event,
            read_module2_event,
            read_module3_event,
            proposal_event,
            acceptance_event,
            update_consolidated_event,
            list_module2_attachments_event,
            remove_obsolete_attachment_event,
            attach_new_assignment_event,
            delete_module2_event,
            delete_module3_event,
            rename_folder_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only agent/oracle events (EventType.AGENT)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent sent proposal to the user
            # The proposal must come from PASAgentUserInterface.send_message_to_user
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 2: Agent created the consolidated note
            # Must update the pre-created consolidated note with the merged content.
            consolidated_note_updated = any(
                e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "update_note"
                and e.action.args.get("note_id") == self.consolidated_note_id
                for e in agent_events
            )

            # STRICT Check 3: Agent deleted both original notes
            # Must have at least 2 delete_note calls
            delete_events = [
                e
                for e in agent_events
                if e.action.class_name == "StatefulNotesApp" and e.action.function_name == "delete_note"
            ]
            both_notes_deleted = len(delete_events) >= 2

            # STRICT Check 4: Agent renamed the folder
            # Must be rename_folder with new_folder containing "Updated Curriculum"
            folder_renamed = any(
                e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "rename_folder"
                and "new_folder" in e.action.args
                and "updated curriculum" in e.action.args["new_folder"].lower()
                for e in agent_events
            )

            # STRICT Check 5: Agent removed the obsolete assignment attachment from Module 2
            removed_obsolete_attachment = any(
                e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "remove_attachment"
                and e.action.args.get("attachment") == "Assignment2.pdf"
                for e in agent_events
            )

            # STRICT Check 6: Agent attached the new combined assignment to the consolidated note
            attached_new_assignment = any(
                e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "add_attachment_to_note"
                and str(e.action.args.get("attachment_path", "")).endswith("Combined_Assignment.pdf")
                for e in agent_events
            )

            # Combine all strict checks
            success = (
                proposal_found
                and consolidated_note_updated
                and both_notes_deleted
                and folder_renamed
                and removed_obsolete_attachment
                and attached_new_assignment
            )

            # Build rationale for failures
            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("no proposal sent to user")
                if not consolidated_note_updated:
                    missing_checks.append("consolidated note 'Data Structures & Algorithms' not updated")
                if not both_notes_deleted:
                    missing_checks.append("both original notes not deleted")
                if not folder_renamed:
                    missing_checks.append("folder not renamed to 'updated curriculum'")
                if not removed_obsolete_attachment:
                    missing_checks.append("obsolete Assignment2.pdf attachment not removed")
                if not attached_new_assignment:
                    missing_checks.append("new Combined_Assignment.pdf not attached")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
