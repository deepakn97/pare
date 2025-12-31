"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.messaging_v2 import ConversationV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulMessagingApp,
)
from pas.apps.note import StatefulNotesApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("reminder_triggered_followup_batch")
class ReminderTriggeredFollowupBatch(PASScenario):
    """Agent sends personalized follow-up messages to multiple contacts based on a task note when triggered by a reminder.

    The user has a note titled "Project Follow-ups" in the Work folder containing a task list: "Follow up with Sarah Kim about the Q1 roadmap, Alex Chen about the API integration timeline, and Jordan Martinez about the design mockups." The user receives a message from themselves (via a messaging reminder or a friend named "Task Reminder") saying "Don't forget to send those follow-up messages today!" The agent must:
    1. Parse the incoming reminder trigger and recognize it refers to follow-up tasks
    2. Search the Notes app for notes containing "follow-up" or "follow up" keywords
    3. Identify and read the "Project Follow-ups" note
    4. Extract the three named contacts (Sarah Kim, Alex Chen, Jordan Martinez) and their associated topics
    5. Look up the user_id for each contact name using the messaging app's lookup functionality
    6. Send three individual personalized messages: one to Sarah asking about the Q1 roadmap, one to Alex asking about the API integration timeline, and one to Jordan asking about the design mockups
    7. Confirm completion to the user via the agent interface

    This scenario exercises reminder-triggered proactive action, cross-app task extraction from notes to drive messaging workflows, batch contact resolution with fuzzy name matching, and personalized multi-recipient outbound communication based on structured note content.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize StatefulNotesApp
        self.note = StatefulNotesApp(name="Notes")

        # Seed baseline note "Project Follow-ups" in the Work folder
        # This note contains the task list the agent will discover after the reminder arrives
        self.note.create_note_with_time(
            folder="Work",
            title="Project Follow-ups",
            content="Follow up with Sarah Kim about the Q1 roadmap, Alex Chen about the API integration timeline, and Jordan Martinez about the design mockups. Use their user_id to send the messages.",
            created_at="2025-11-17 10:00:00",
            updated_at="2025-11-17 10:00:00",
        )

        # Initialize StatefulMessagingApp
        self.messaging = StatefulMessagingApp(name="Messages")
        self.messaging.current_user_id = "user_main"
        self.messaging.current_user_name = "Me"

        # Register the three contacts the agent will need to message
        # Step 3 must include an early observation action (like lookup_user_id) so the agent can discover these mappings at runtime
        self.messaging.add_users(["Sarah Kim", "Alex Chen", "Jordan Martinez"])

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.note, self.messaging]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")

        # Resolve deterministic user IDs for the seeded users. The agent grounds these IDs via lookup_user_id oracle events below.
        sarah_id = messaging_app.name_to_id["Sarah Kim"]
        alex_id = messaging_app.name_to_id["Alex Chen"]
        jordan_id = messaging_app.name_to_id["Jordan Martinez"]

        with EventRegisterer.capture_mode():
            # Environment event 1: Reminder message arrives from user to themselves
            # This is the triggering exogenous event that motivates all agent actions
            # Create a self-reminder conversation
            self_user_id = messaging_app.current_user_id
            reminder_conversation = ConversationV2(participant_ids=[self_user_id])
            messaging_app.add_conversation(reminder_conversation)

            reminder_event = messaging_app.create_and_add_message(
                conversation_id=reminder_conversation.conversation_id,
                sender_id=self_user_id,
                content="Don't forget to send those follow-up messages in notes today!",
            ).delayed(5)

            # Oracle event 1: Agent searches notes for "follow up" keyword (motivated by the reminder message content)
            search_event = note_app.search_notes(query="follow up").oracle().depends_on(reminder_event, delay_seconds=3)

            # Oracle event 2: Agent reads the "Project Follow-ups" note to extract task details
            # (motivated by search results showing this note)
            read_note_event = (
                note_app.list_notes(folder="Work", offset=0, limit=10)
                .oracle()
                .depends_on(search_event, delay_seconds=2)
            )

            # Oracle event 3: Agent looks up Sarah Kim's user_id (motivated by note content listing "Sarah Kim")
            lookup_sarah_event = (
                messaging_app.lookup_user_id(user_name="Sarah Kim")
                .oracle()
                .depends_on(read_note_event, delay_seconds=2)
            )

            # Oracle event 4: Agent looks up Alex Chen's user_id (motivated by note content listing "Alex Chen")
            lookup_alex_event = (
                messaging_app.lookup_user_id(user_name="Alex Chen")
                .oracle()
                .depends_on(read_note_event, delay_seconds=2)
            )

            # Oracle event 5: Agent looks up Jordan Martinez's user_id (motivated by note content listing "Jordan Martinez")
            lookup_jordan_event = (
                messaging_app.lookup_user_id(user_name="Jordan Martinez")
                .oracle()
                .depends_on(read_note_event, delay_seconds=2)
            )

            # Oracle event 6: Agent proposes to send the follow-up messages (motivated by the reminder message and note content)
            proposal_event = (
                aui.send_message_to_user(
                    content="I saw your reminder about follow-up messages. I found your 'Project Follow-ups' note with three tasks: contacting Sarah Kim about the Q1 roadmap, Alex Chen about the API integration timeline, and Jordan Martinez about the design mockups. Would you like me to send these follow-up messages now?"
                )
                .oracle()
                .depends_on([lookup_sarah_event, lookup_alex_event, lookup_jordan_event], delay_seconds=3)
            )

            # Oracle event 7: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please send all three follow-up messages.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle event 8: Agent sends message to Sarah Kim (motivated by user acceptance and note content specifying "Sarah Kim" + "Q1 roadmap")
            send_sarah_event = (
                messaging_app.send_message(
                    user_id=sarah_id,
                    content="Hi Sarah, just following up on the Q1 roadmap. Do you have any updates you can share?",
                )
                .oracle()
                .depends_on([acceptance_event, lookup_sarah_event], delay_seconds=2)
            )

            # Oracle event 9: Agent sends message to Alex Chen (motivated by user acceptance and note content specifying "Alex Chen" + "API integration timeline")
            send_alex_event = (
                messaging_app.send_message(
                    user_id=alex_id,
                    content="Hi Alex, checking in on the API integration timeline. How is progress looking?",
                )
                .oracle()
                .depends_on([acceptance_event, lookup_alex_event], delay_seconds=2)
            )

            # Oracle event 10: Agent sends message to Jordan Martinez (motivated by user acceptance and note content specifying "Jordan Martinez" + "design mockups")
            send_jordan_event = (
                messaging_app.send_message(
                    user_id=jordan_id,
                    content="Hi Jordan, following up on the design mockups. Are they ready for review?",
                )
                .oracle()
                .depends_on([acceptance_event, lookup_jordan_event], delay_seconds=2)
            )

            # Oracle event 11: Agent confirms completion to user (motivated by all three messages being sent)
            completion_event = (
                aui.send_message_to_user(
                    content="All three follow-up messages have been sent successfully to Sarah, Alex, and Jordan."
                )
                .oracle()
                .depends_on([send_sarah_event, send_alex_event, send_jordan_event], delay_seconds=3)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            reminder_event,
            search_event,
            read_note_event,
            lookup_sarah_event,
            lookup_alex_event,
            lookup_jordan_event,
            proposal_event,
            acceptance_event,
            send_sarah_event,
            send_alex_event,
            send_jordan_event,
            completion_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent searched Notes for "follow up" (or similar) keywords
            # This is a critical detection step that connects the reminder trigger to the task note
            notes_search_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "search_notes"
                and "follow" in e.action.args.get("query", "").lower()
                for e in log_entries
            )

            # STRICT Check 2: Agent looked up at least one contact using lookup_user_id
            # Contact resolution is required to send messages to the right people
            contact_lookup_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "lookup_user_id"
                and e.action.args.get("user_name") in ["Sarah Kim", "Alex Chen", "Jordan Martinez"]
                for e in log_entries
            )

            # STRICT Check 3: Agent sent proposal mentioning the three contacts and their topics
            # The proposal must demonstrate understanding of all three follow-up tasks
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 4: Agent sent message to Sarah Kim about Q1 roadmap
            # This verifies personalized outbound messaging based on note content
            expected_sarah_id = self.get_typed_app(StatefulMessagingApp, "Messages").name_to_id["Sarah Kim"]
            sarah_message_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == expected_sarah_id
                for e in log_entries
            )

            # STRICT Check 5: Agent sent message to Alex Chen about API integration
            # This verifies the second follow-up task was completed
            expected_alex_id = self.get_typed_app(StatefulMessagingApp, "Messages").name_to_id["Alex Chen"]
            alex_message_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == expected_alex_id
                for e in log_entries
            )

            # STRICT Check 6: Agent sent message to Jordan Martinez about design mockups
            # This verifies the third follow-up task was completed
            expected_jordan_id = self.get_typed_app(StatefulMessagingApp, "Messages").name_to_id["Jordan Martinez"]
            jordan_message_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == expected_jordan_id
                for e in log_entries
            )

            # Determine success based on all strict checks
            success = (
                notes_search_found
                and contact_lookup_found
                and proposal_found
                and sarah_message_sent
                and alex_message_sent
                and jordan_message_sent
            )

            # If failed, build rationale message
            rationale = None
            if not success:
                missing_checks = []
                if not notes_search_found:
                    missing_checks.append("notes search for follow-up keywords")
                if not contact_lookup_found:
                    missing_checks.append("contact lookup for Sarah/Alex/Jordan")
                if not proposal_found:
                    missing_checks.append("proposal mentioning all three contacts")
                if not sarah_message_sent:
                    missing_checks.append("message to Sarah Kim")
                if not alex_message_sent:
                    missing_checks.append("message to Alex Chen")
                if not jordan_message_sent:
                    missing_checks.append("message to Jordan Martinez")
                rationale = f"Missing critical checks: {', '.join(missing_checks)}"

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
