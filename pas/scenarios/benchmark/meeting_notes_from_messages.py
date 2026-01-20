from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.contacts import Contact
from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulContactsApp,
    StatefulMessagingApp,
)
from pas.apps.note import StatefulNotesApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("meeting_notes_from_messages")
class MeetingNotesFromMessages(PASScenario):
    """Agent organizes meeting notes from messages into structured notes app entries.

    The user receives a series of messages from their colleague Sarah Martinez containing meeting notes, action items, and decisions from a project planning session. The messages arrive fragmented across multiple texts with different pieces of information: attendees, decisions made, deadlines, and follow-up tasks. The agent must:
    1. Detect incoming messages containing meeting-related information
    2. Parse and extract structured information (attendees, decisions, action items, deadlines)
    3. Search for or create a "Work - Project Planning" folder in Notes
    4. Create a new note titled with the meeting date/topic containing the organized information
    5. Extract any new contact details mentioned (if Sarah shares a new team member's phone/email)
    6. Update or create contact entries for mentioned participants

    This scenario exercises cross-app information synthesis (messaging → notes → contacts), natural language parsing of unstructured meeting content, knowledge organization with folder management, and proactive information capture with user confirmation..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Contacts app with pre-existing contact data
        self.contacts = StatefulContactsApp(name="Contacts")

        # Add the user's own contact details
        user_contact = Contact(
            first_name="Alex",
            last_name="Chen",
            is_user=True,
            phone="+1-555-0100",
            email="alex.chen@company.com",
            job="Product Manager",
        )
        self.contacts.add_contact(user_contact)

        # Add Sarah Martinez - the colleague who will send the meeting notes
        sarah_contact = Contact(
            first_name="Sarah",
            last_name="Martinez",
            phone="+1-555-0101",
            email="sarah.martinez@company.com",
            job="Senior Designer",
        )
        self.contacts.add_contact(sarah_contact)

        # Add other team members who might be mentioned in the meeting
        david_contact = Contact(
            first_name="David",
            last_name="Park",
            phone="+1-555-0102",
            email="david.park@company.com",
            job="Engineering Lead",
        )
        self.contacts.add_contact(david_contact)

        # Initialize Messaging app with conversation history
        self.messaging = StatefulMessagingApp(name="Messages")
        self.messaging.current_user_name = "Alex Chen"

        # Register contacts in messaging app
        self.messaging.add_contacts([("Sarah Martinez", sarah_contact.phone), ("David Park", david_contact.phone)])

        # Create an existing conversation with Sarah (older message history)
        self.sarah_conversation = ConversationV2(
            participant_ids=[user_contact.phone, sarah_contact.phone], title="Sarah Martinez"
        )
        # Add a prior message from a few days ago
        prior_timestamp = datetime(2025, 11, 15, 14, 30, 0, tzinfo=UTC).timestamp()
        prior_message = MessageV2(
            sender_id=sarah_contact.phone,
            content="Hey Alex, looking forward to our project planning meeting on Monday!",
            timestamp=prior_timestamp,
        )
        self.sarah_conversation.messages.append(prior_message)
        self.sarah_conversation.update_last_updated(prior_timestamp)
        self.messaging.add_conversation(self.sarah_conversation)

        # Initialize Notes app with existing folder structure
        self.note = StatefulNotesApp(name="Notes")

        # Create a "Work - Project Planning" folder (baseline state before the scenario begins)
        # This folder already exists but is empty
        self.note.new_folder("Work - Project Planning")

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.messaging, self.note]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")

        # Get the conversation_id for the existing Sarah conversation BEFORE entering capture mode
        sarah_phone = "+1-555-0101"
        user_phone = "+1-555-0100"
        conversation_ids = messaging_app.get_existing_conversation_ids([sarah_phone])
        if len(conversation_ids) > 0:
            sarah_conversation_id = conversation_ids[0]
        else:
            # Fallback: use the conversation_id from the seeded conversation
            sarah_conversation_id = self.sarah_conversation.conversation_id

        with EventRegisterer.capture_mode():
            # Environment events: Sarah sends fragmented meeting notes across multiple messages

            # Message 1: Attendees and high-level summary
            msg1 = messaging_app.create_and_add_message(
                conversation_id=sarah_conversation_id,
                sender_id=sarah_phone,
                content="Hey Alex! Quick recap from our project planning meeting today. Attendees: you, me, David Park, and Emily Wong (new marketing lead, if you haven't save her info to your contact please save it now - emily.wong@company.com, +1-555-0103).",
            )

            # Message 2: Key decisions
            msg2 = messaging_app.create_and_add_message(
                conversation_id=sarah_conversation_id,
                sender_id=sarah_phone,
                content="Key decisions: 1) Launch date moved to Jan 15th. 2) We're going with the minimalist design approach. 3) Budget approved for additional dev resources.",
            ).delayed(2)

            # Message 3: Action items and deadlines
            msg3 = messaging_app.create_and_add_message(
                conversation_id=sarah_conversation_id,
                sender_id=sarah_phone,
                content="Action items: David to finalize backend architecture by Nov 25. You need to draft product specs by Nov 22. Emily will prepare marketing materials by Dec 1. I'll handle design mockups by Nov 28. It's always a good habit to save those important info into your notes!",
            ).delayed(4)

            # Oracle events: Agent detects messages and takes action
            # Agent reads the conversation to see the new messages (motivated by incoming message notifications)
            read_conv = (
                messaging_app.read_conversation(conversation_id=sarah_conversation_id, offset=0, limit=10)
                .oracle()
                .depends_on([msg3], delay_seconds=2)
            )

            # Agent searches for the Work - Project Planning folder to confirm it exists (motivated by the meeting context in Sarah's messages)
            search_folders = note_app.list_folders().oracle().depends_on(read_conv, delay_seconds=1)

            # Agent searches contacts to check if Emily Wong already exists (motivated by the mention of a new contact in msg1)
            search_emily = (
                contacts_app.search_contacts(query="Emily Wong").oracle().depends_on(read_conv, delay_seconds=1)
            )

            # Agent sends a proposal to the user summarizing what was captured (motivated by the incoming messages and completed organization work)
            proposal = (
                aui.send_message_to_user(
                    content="I noticed Sarah sent fragmented meeting notes across three messages. Do you want me to organize the information into a structured note in your 'Work - Project Planning' folder, including attendees, decisions, and action items with deadlines? I also noticed there is a new member mentioned -- Emily Wong (new marketing lead), do you want to add her to your contacts?"
                )
                .oracle()
                .depends_on(search_emily, delay_seconds=2)
            )

            # User accepts the proposal
            acceptance = (
                aui.accept_proposal(
                    content="Yes, please organize the information into 'Work - Project Planning' folder and create a new contact."
                )
                .oracle()
                .depends_on(proposal, delay_seconds=3)
            )

            # Agent adds Emily Wong as a new contact (motivated by the contact info provided in msg1 and empty search results)
            add_emily = (
                contacts_app.add_new_contact(
                    first_name="Emily",
                    last_name="Wong",
                    phone="+1-555-0103",
                    email="emily.wong@company.com",
                    job="Marketing Lead",
                )
                .oracle()
                .depends_on(acceptance, delay_seconds=2)
            )

            # Agent creates a note with the organized meeting information (motivated by the fragmented meeting notes in messages)
            create_note = (
                note_app.create_note(
                    folder="Work - Project Planning",
                    title="Project Planning Meeting - Nov 18, 2025",
                    content="""Meeting Recap - November 18, 2025

Attendees:
- Alex Chen (Product Manager)
- Sarah Martinez (Senior Designer)
- David Park (Engineering Lead)
- Emily Wong (Marketing Lead)

Key Decisions:
1. Launch date: January 15th
2. Design approach: Minimalist
3. Budget: Approved for additional dev resources

Action Items & Deadlines:
- David Park: Finalize backend architecture (Due: Nov 25)
- Alex Chen: Draft product specs (Due: Nov 22)
- Emily Wong: Prepare marketing materials (Due: Dec 1)
- Sarah Martinez: Complete design mockups (Due: Nov 28)""",
                )
                .oracle()
                .depends_on(add_emily, delay_seconds=3)
            )

        # Register ALL events
        self.events = [
            msg1,
            msg2,
            msg3,
            read_conv,
            search_folders,
            search_emily,
            proposal,
            acceptance,
            add_emily,
            create_note,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1: Agent sent proposal to the user (STRICT - content flexible, presence strict)
            # Must mention organizing meeting notes/information
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 2: Agent read the conversation to detect the meeting notes (STRICT)
            read_conversation_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "read_conversation"
                for e in log_entries
            )

            # Check 3: Agent created a note in the Work - Project Planning folder (STRICT)
            note_created_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "create_note"
                for e in log_entries
            )

            # Check 4: Agent added Emily Wong as a new contact (STRICT - action required, exact details flexible)
            # Accept add_new_contact or create_contact (if both exist in API)
            emily_contact_added = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name in ["add_new_contact", "create_contact"]
                and "emily" in str(e.action.args.get("first_name", "")).lower()
                and "wong" in str(e.action.args.get("last_name", "")).lower()
                for e in log_entries
            )

            # All checks are strict and required for success
            success = proposal_found and read_conversation_found and note_created_found and emily_contact_added

            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal to user")
                if not read_conversation_found:
                    missing_checks.append("read conversation with Sarah")
                if not note_created_found:
                    missing_checks.append("create note in Work - Project Planning folder")
                if not emily_contact_added:
                    missing_checks.append("add Emily Wong to contacts")

                rationale = f"Missing required actions: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
