"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.contacts import Contact
from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulContactsApp,
    StatefulMessagingApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("group_chat_name_change_sync")
class GroupChatNameChangeSync(PASScenario):
    """Agent updates contact name and syncs changes to group conversation after detecting formal name change announcement.

    The user has a contact saved as "Robert Kim" and participates in a group message thread called "Book Club Planning" that includes Robert, Sarah Chen, and Emma Martinez. Robert sends a message to his individual conversation with the user stating "Hey! Just wanted to let you know I've legally changed my name to Robin Kim and will be going by Robin from now on." The agent must: 1. Parse the name change announcement from the individual conversation. 2. Search contacts and locate the existing "Robert Kim" contact record. 3. Update the contact's first name from "Robert" to "Robin". 4. Identify group conversations where this contact participates as a member. 5. Send a brief message in the Book Club Planning group conversation addressing Robin by the new name to acknowledge the change and help other participants adapt.

    This scenario exercises identity continuity across contact updates, cross-conversation participant tracking to find affected group chats, contact record modification triggered by natural language announcements in messaging, and proactive group communication to propagate name changes without requiring the user to manually notify each shared group.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Contacts App
        self.contacts = StatefulContactsApp(name="Contacts")

        # Create contacts for the scenario
        robert_contact = Contact(
            first_name="Robert", last_name="Kim", phone="+1-555-0101", email="robert.kim@email.com"
        )
        sarah_contact = Contact(first_name="Sarah", last_name="Chen", phone="+1-555-0102", email="sarah.chen@email.com")
        emma_contact = Contact(
            first_name="Emma", last_name="Martinez", phone="+1-555-0103", email="emma.martinez@email.com"
        )

        # Add contacts to the contacts app
        self.contacts.add_contact(robert_contact)
        self.contacts.add_contact(sarah_contact)
        self.contacts.add_contact(emma_contact)

        # Store contact IDs for use in messaging
        self.robert_id = robert_contact.contact_id
        self.sarah_id = sarah_contact.contact_id
        self.emma_id = emma_contact.contact_id

        # Initialize Messaging App
        self.messaging = StatefulMessagingApp(name="Messages")

        # Register users in messaging app by mapping names to contact IDs
        self.messaging.name_to_id["Robert Kim"] = self.robert_id
        self.messaging.id_to_name[self.robert_id] = "Robert Kim"
        self.messaging.name_to_id["Sarah Chen"] = self.sarah_id
        self.messaging.id_to_name[self.sarah_id] = "Sarah Chen"
        self.messaging.name_to_id["Emma Martinez"] = self.emma_id
        self.messaging.id_to_name[self.emma_id] = "Emma Martinez"

        # Create group conversation: Book Club Planning
        # Participants: user + Robert + Sarah + Emma
        group_conversation = ConversationV2(
            participant_ids=[self.robert_id, self.sarah_id, self.emma_id], title="Book Club Planning"
        )

        # Add some baseline message history to the group conversation
        baseline_timestamp = self.start_time - (24 * 3600)  # 1 day before start_time
        group_conversation.messages.append(
            MessageV2(
                sender_id=self.sarah_id,
                content="Hey everyone! Should we meet next week to discuss the next book?",
                timestamp=baseline_timestamp,
            )
        )
        group_conversation.messages.append(
            MessageV2(
                sender_id=self.emma_id,
                content="Sounds good to me! I'm free on Tuesday evening.",
                timestamp=baseline_timestamp + 1800,  # 30 minutes later
            )
        )
        group_conversation.messages.append(
            MessageV2(
                sender_id=self.robert_id,
                content="Tuesday works for me too. Looking forward to it!",
                timestamp=baseline_timestamp + 3600,  # 1 hour later
            )
        )
        group_conversation.update_last_updated(baseline_timestamp + 3600)

        # Add the group conversation to messaging app
        self.messaging.add_conversation(group_conversation)
        self.group_conversation_id = group_conversation.conversation_id

        # Create individual conversation with Robert (initially empty - message will arrive as event)
        individual_conversation = ConversationV2(participant_ids=[self.robert_id], title="Robert Kim")
        self.messaging.add_conversation(individual_conversation)
        self.robert_conversation_id = individual_conversation.conversation_id

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.messaging]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Robert sends name change announcement in individual conversation
            message_event = messaging_app.create_and_add_message(
                conversation_id=self.robert_conversation_id,
                sender_id=self.robert_id,
                content="Hey! Just wanted to let you know I've legally changed my name to Robin Kim and will be going by Robin from now on.",
            ).delayed(20)

            # Oracle Event 1: Agent proposes contact update
            proposal_event = (
                aui.send_message_to_user(
                    content="I received a message from Robert Kim stating that they've legally changed their name to Robin Kim. Would you like me to update their contact and notify the group chats they're in?"
                )
                .oracle()
                .depends_on(message_event, delay_seconds=2)
            )

            # Oracle Event 2: User accepts proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please update Robert's name to Robin.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent searches for existing contact to verify
            search_event = (
                contacts_app.search_contacts(query="Robert Kim").oracle().depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 4: Agent updates contact first name from Robert to Robin
            update_event = (
                contacts_app.edit_contact(contact_id=self.robert_id, updates={"first_name": "Robin"})
                .oracle()
                .depends_on(search_event, delay_seconds=1)
            )

            # Oracle Event 5: Agent lists conversations by participant to find group chats
            list_convs_event = (
                messaging_app.list_conversations_by_participant(user_id=self.robert_id, offset=0, limit=5)
                .oracle()
                .depends_on(update_event, delay_seconds=1)
            )

            # Oracle Event 6: Agent sends acknowledgment message in group chat
            group_message_event = (
                messaging_app.send_message_to_group_conversation(
                    conversation_id=self.group_conversation_id,
                    content="Hi everyone! Just a quick note that Robin (formerly Robert) has updated their name. Looking forward to our next book club meeting!",
                )
                .oracle()
                .depends_on(list_convs_event, delay_seconds=2)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            message_event,
            proposal_event,
            acceptance_event,
            search_event,
            update_event,
            list_convs_event,
            group_message_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent sent proposal to the user about the name change
            # STRICT: Must mention Robert/Robin and name change concept
            # FLEXIBLE: Exact wording can vary
            proposal_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check Step 2: Agent searched for existing contact to locate Robert Kim
            # STRICT: Must search for the contact using some variant of the name
            # FLEXIBLE: Query string can vary (Robert, Kim, Robert Kim, etc.)
            search_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "search_contacts"
                and "query" in e.action.args
                and len(e.action.args.get("query", "")) > 0
                for e in log_entries
            )

            # Check Step 3: Agent updated contact first name from Robert to Robin
            # STRICT: Must update the specific contact with first_name = "Robin"
            # FLEXIBLE: Other fields in updates dict can vary
            update_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "edit_contact"
                and e.action.args.get("contact_id") == self.robert_id
                and "updates" in e.action.args
                and e.action.args.get("updates", {}).get("first_name") == "Robin"
                for e in log_entries
            )

            # Check Step 4: Agent listed conversations by participant to find group chats
            # STRICT: Must call list_conversations_by_participant with the contact's ID
            # FLEXIBLE: offset and limit parameters can vary
            list_conversations_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "list_conversations_by_participant"
                and e.action.args.get("user_id") == self.robert_id
                for e in log_entries
            )

            # Check Step 5: Agent sent message to group chat acknowledging the name change
            # STRICT: Must send to the correct group conversation and use new name "Robin"
            # FLEXIBLE: Message content can vary as long as it mentions Robin
            group_message_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message_to_group_conversation"
                and e.action.args.get("conversation_id") == self.group_conversation_id
                for e in log_entries
            )

            success = (
                proposal_found and search_found and update_found and list_conversations_found and group_message_found
            )

            # Build rationale for failure
            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal about name change")
                if not search_found:
                    missing_checks.append("contact search")
                if not update_found:
                    missing_checks.append("contact update with first_name=Robin")
                if not list_conversations_found:
                    missing_checks.append("list conversations by participant")
                if not group_message_found:
                    missing_checks.append("group message mentioning Robin")

                rationale = f"Missing critical checks: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
