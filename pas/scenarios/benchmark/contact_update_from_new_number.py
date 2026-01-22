"""Proactive contact update from messages received from a new/unknown number."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.contacts import Contact
from are.simulation.apps.messaging_v2 import ConversationV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import HomeScreenSystemApp, PASAgentUserInterface, StatefulContactsApp, StatefulMessagingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("contact_update_from_new_number")
class ContactUpdateFromNewNumber(PASScenario):
    """Agent updates contact information from messages received from unknown number.

    The user has an existing contact for "Michael Chen" with old phone and email.
    Messages arrive from an unknown number claiming to be Michael Chen with updated
    contact information. The agent must:
    1. Parse identity claim from unknown number
    2. Match to existing contact
    3. Extract new phone number (sender's number) and email from messages
    4. Update existing contact record
    5. Send confirmation to the new number

    This scenario exercises cross-app correlation (messaging -> contacts), identity
    verification, information synthesis across multiple messages, and contact update tools.
    """

    # Scenario starts on 2025-11-11 at 9:00 AM UTC (ecologically valid timestamp)
    start_time = datetime(2025, 11, 11, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        # Initialize apps
        self.messaging = StatefulMessagingApp(name="Messages")
        self.contacts = StatefulContactsApp(name="Contacts")
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Populate contacts - Add existing contact for Michael Chen with OLD information
        self.michael_chen_contact_id = self.contacts.add_contact(
            Contact(
                first_name="Michael",
                last_name="Chen",
                contact_id="contact-michael-chen",
                phone="555-123-4567",  # Old phone number
                email="michael.chen@oldcompany.com",  # Old email
            )
        )
        self.messaging.add_users(["John Doe", "Michael Chen"])
        self.user_id = self.messaging.current_user_id
        # Store Michael Chen's user_id for messaging
        self.michael_chen_user_id = self.messaging.name_to_id["Michael Chen"]
        self.unknown_conversation = ConversationV2(participant_ids=[self.user_id, "555-6787-897"])
        self.messaging.add_conversation(self.unknown_conversation)

        # Register all apps
        self.apps = [self.messaging, self.contacts, self.agent_ui, self.system_app]

    def build_events_flow(self) -> None:
        """Build event flow - messages from unknown number trigger contact update."""
        aui = self.get_typed_app(PASAgentUserInterface)
        messaging = self.get_typed_app(StatefulMessagingApp, "Messages")
        contacts = self.get_typed_app(StatefulContactsApp, "Contacts")

        with EventRegisterer.capture_mode():
            # Event 1: First message from unknown number - identity claim and phone update request
            message1_event = messaging.create_and_add_message(
                conversation_id=self.unknown_conversation.conversation_id,
                sender_id="555-6787-897",
                content="Hey, this is Michael Chen. I got a new phone number - please update my contact to this number.",
            ).delayed(20)

            # Event 2: Second message from same unknown number - email update
            message2_event = messaging.create_and_add_message(
                conversation_id=self.unknown_conversation.conversation_id,
                sender_id="555-6787-897",
                content="Also using a new email now: michael.chen@newcompany.com",
            ).delayed(3)

            # Event 3: Agent proposes contact update (oracle)
            proposal_event = (
                aui.send_message_to_user(
                    content="I received messages from a new number (555-987-6543) claiming to be Michael Chen with updated contact information. Would you like me to update Michael's contact with this new phone number and email (michael.chen@newcompany.com)?"
                )
                .oracle()
                .depends_on(message2_event, delay_seconds=2)
            )

            # Event 4: User accepts proposal (oracle)
            acceptance_event = (
                aui.accept_proposal(content="Yes, please update Michael's contact information.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Event 5: Agent searches for existing contact (oracle)
            search_event = (
                contacts.search_contacts(query="Michael Chen").oracle().depends_on(acceptance_event, delay_seconds=1)
            )

            # Event 6: Agent updates contact with new phone and email (oracle)
            update_event = (
                contacts.edit_contact(
                    contact_id="contact-michael-chen",
                    updates={
                        "phone": "555-987-6543",
                        "email": "michael.chen@newcompany.com",
                    },
                )
                .oracle()
                .depends_on(search_event, delay_seconds=1)
            )

            # Event 7: Agent sends confirmation to new number (oracle)
            # Send message to Michael Chen using his user_id in messaging app
            confirmation_event = (
                messaging.send_message(
                    user_id=self.michael_chen_user_id,
                    content="Thanks Michael! I've updated your contact information.",
                )
                .oracle()
                .depends_on(update_event, delay_seconds=2)
            )

        # Register ALL events
        self.events = [
            message1_event,
            message2_event,
            proposal_event,
            acceptance_event,
            search_event,
            update_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent updated contact with new information."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1: Agent sent proposal mentioning Michael Chen, new number, and contact update
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(name in e.action.args.get("content", "") for name in ["Michael Chen", "Michael"])
                and any(
                    keyword in e.action.args.get("content", "")
                    for keyword in ["555-987-6543", "new number", "new phone"]
                )
                and any(keyword in e.action.args.get("content", "") for keyword in ["contact", "update", "information"])
                for e in log_entries
            )

            # Check 2: Agent searched for existing contact
            search_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "search_contacts"
                and any(name in e.action.args.get("query", "") for name in ["Michael", "Chen", "Michael Chen"])
                for e in log_entries
            )

            # Check 3: Agent updated contact with correct new phone and email (STRICT)
            update_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "edit_contact"
                and e.action.args.get("contact_id") == "contact-michael-chen"
                and e.action.args.get("updates").get("phone") == "555-987-6543"
                and e.action.args.get("updates").get("email") == "michael.chen@newcompany.com"
                for e in log_entries
            )

            # Check 4: Agent sent confirmation message back to Michael Chen
            confirmation_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == self.michael_chen_user_id
                and any(
                    keyword in e.action.args.get("content", "")
                    for keyword in ["update", "thank", "Thanks", "saved", "confirmed"]
                )
                for e in log_entries
            )

            success = proposal_found and search_found and update_found and confirmation_found
            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
