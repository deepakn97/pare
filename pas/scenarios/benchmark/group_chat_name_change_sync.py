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
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("group_chat_name_change_sync")
class GroupChatNameChangeSync(PASScenario):
    """Agent updates contact name after detecting formal name change announcement.

    The user has a contact saved as "Robert Kim" and participates in a group message thread
    called "Book Club Planning" that includes Robert, Sarah Chen, and Emma Martinez. Robert
    sends a message to his individual conversation with the user stating that he has legally
    changed his name to Robin Kim.

    The agent must:
    1. Parse the name change announcement from the individual conversation
    2. Search contacts and locate the existing "Robert Kim" contact record
    3. Propose updating the contact's first name from "Robert" to "Robin"
    4. After user approval, update the contact

    This scenario exercises contact record modification triggered by natural language
    announcements in messaging, and identity continuity across contact updates.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    additional_system_prompt = """You are receiving a name change notification from a contact.
The agent should only update the contact information, NOT send messages to group chats.
If the agent proposes to send messages to group conversations on your behalf, REJECT that part.
Only accept proposals that update the contact name."""

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
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

        # Store contact ID for validation
        self.robert_id = robert_contact.contact_id

        # Initialize Messaging App
        self.messaging = StatefulMessagingApp(name="Messages")

        # Add users to messaging app using proper method
        self.messaging.add_users(["Robert Kim", "Sarah Chen", "Emma Martinez"])

        # Get messaging user IDs
        self.robert_msg_id = self.messaging.name_to_id["Robert Kim"]
        self.sarah_msg_id = self.messaging.name_to_id["Sarah Chen"]
        self.emma_msg_id = self.messaging.name_to_id["Emma Martinez"]
        self.user_id = self.messaging.current_user_id

        # Create group conversation: Book Club Planning
        # Participants: user + Robert + Sarah + Emma
        group_conversation = ConversationV2(
            participant_ids=[self.user_id, self.robert_msg_id, self.sarah_msg_id, self.emma_msg_id],
            title="Book Club Planning",
        )

        # Add some baseline message history to the group conversation
        baseline_timestamp = self.start_time - (24 * 3600)  # 1 day before start_time
        group_conversation.messages.append(
            MessageV2(
                sender_id=self.sarah_msg_id,
                content="Hey everyone! Should we meet next week to discuss the next book?",
                timestamp=baseline_timestamp,
            )
        )
        group_conversation.messages.append(
            MessageV2(
                sender_id=self.emma_msg_id,
                content="Sounds good to me! I'm free on Tuesday evening.",
                timestamp=baseline_timestamp + 1800,  # 30 minutes later
            )
        )
        group_conversation.messages.append(
            MessageV2(
                sender_id=self.robert_msg_id,
                content="Tuesday works for me too. Looking forward to it!",
                timestamp=baseline_timestamp + 3600,  # 1 hour later
            )
        )
        group_conversation.update_last_updated(baseline_timestamp + 3600)

        # Add the group conversation to messaging app
        self.messaging.add_conversation(group_conversation)
        self.group_conversation_id = group_conversation.conversation_id

        # Create individual conversation with Robert (initially empty - message will arrive as event)
        individual_conversation = ConversationV2(participant_ids=[self.robert_msg_id], title="Robert Kim")
        self.messaging.add_conversation(individual_conversation)
        self.robert_conversation_id = individual_conversation.conversation_id

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.messaging]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Robert sends name change announcement in individual conversation
            message_event = messaging_app.create_and_add_message(
                conversation_id=self.robert_conversation_id,
                sender_id=self.robert_msg_id,
                content="Hey! Just wanted to let you know I've legally changed my name to Robin Kim and will be going by Robin from now on.",
            ).delayed(20)

            # Oracle Event 2: Agent proposes contact update
            proposal_event = (
                aui.send_message_to_user(
                    content="I received a message from Robert Kim stating that they've legally changed their name to Robin Kim. Would you like me to update their contact?"
                )
                .oracle()
                .depends_on(message_event, delay_seconds=2)
            )

            # Oracle Event 3: User accepts proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please update Robert's name to Robin.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent searches for existing contact to verify
            search_event = (
                contacts_app.search_contacts(query="Robert Kim").oracle().depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 5: Agent updates contact first name from Robert to Robin
            update_event = (
                contacts_app.edit_contact(contact_id=self.robert_id, updates={"first_name": "Robin"})
                .oracle()
                .depends_on(search_event, delay_seconds=1)
            )

            # Oracle Event 6: Agent confirms completion to user
            confirmation_event = (
                aui.send_message_to_user(content="I've updated Robert Kim's contact to Robin Kim.")
                .oracle()
                .depends_on(update_event, delay_seconds=1)
            )

        self.events = [
            message_event,
            proposal_event,
            acceptance_event,
            search_event,
            update_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1: Agent sent proposal to the user about the name change
            proposal_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 2: Agent searched for existing contact to locate Robert Kim
            search_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "search_contacts"
                and "query" in e.action.args
                and len(e.action.args.get("query", "")) > 0
                for e in log_entries
            )

            # Check 3: Agent updated contact first name from Robert to Robin
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

            success = proposal_found and search_found and update_found

            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal about name change")
                if not search_found:
                    missing_checks.append("contact search")
                if not update_found:
                    missing_checks.append("contact update with first_name=Robin")

                rationale = f"Missing critical checks: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
