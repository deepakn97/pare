from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.contacts import Contact
from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulContactsApp,
    StatefulMessagingApp,
)
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("add_missing_group_contacts")
class AddMissingGroupContacts(PAREScenario):
    """Agent identifies and adds missing contacts from a frequently-used group conversation.

    The user actively participates in a group conversation titled "Book Club Monthly" with five participants: Alex Rivera, Jamie Thompson, Morgan Lee, Casey Jordan, and Taylor Kim. The user's contacts app contains entries for Alex Rivera, Morgan Lee, and Taylor Kim, but notably lacks Jamie Thompson and Casey Jordan despite dozens of messages exchanged in the group over the past three weeks. During a conversation about planning next month's meeting, Casey Jordan sends a message saying "I'll bring snacks! Email me your dietary restrictions at casey.jordan@email.com so I can plan ahead." The agent must: 1. Recognize that the user has been actively messaging with Casey Jordan (based on message frequency and recency) but Casey does not exist in the contacts app. 2. Extract Casey's email address from the message content. 3. Search the group conversation for additional context about Casey (past messages, any other identifying details like job or location if mentioned). 4. Propose creating a new contact entry for Casey Jordan with the discovered email address. 5. After user acceptance, create the contact and optionally scan the same group for Jamie Thompson to suggest a batch addition of all missing frequent contacts from this conversation.

    This scenario exercises contact gap detection through group conversation analysis, opportunistic information extraction from casual messages (email mentioned for a practical purpose, not as part of contact exchange), proactive contact creation (not update/merge), and message history mining to justify adding someone the user regularly communicates with but hasn't formally saved..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Contacts app with partial Book Club member entries
        self.contacts = StatefulContactsApp(name="Contacts")

        # Add the three existing contacts (Alex Rivera, Morgan Lee, Taylor Kim)
        alex = Contact(first_name="Alex", last_name="Rivera", email="alex.rivera@email.com", phone="555-0101")
        morgan = Contact(first_name="Morgan", last_name="Lee", email="morgan.lee@email.com", phone="555-0102")
        taylor = Contact(first_name="Taylor", last_name="Kim", email="taylor.kim@email.com", phone="555-0103")

        self.contacts.add_contact(alex)
        self.contacts.add_contact(morgan)
        self.contacts.add_contact(taylor)

        # Initialize Messaging app with Book Club group conversation
        self.messaging = StatefulMessagingApp(name="Messages")

        # Register all five Book Club participants in the messaging app's internal maps
        self.messaging.add_users(["Alex Rivera", "Jamie Thompson", "Morgan Lee", "Casey Jordan", "Taylor Kim"])

        # Create the Book Club group conversation with all five members
        alex_id = self.messaging.name_to_id["Alex Rivera"]
        jamie_id = self.messaging.name_to_id["Jamie Thompson"]
        morgan_id = self.messaging.name_to_id["Morgan Lee"]
        casey_id = self.messaging.name_to_id["Casey Jordan"]
        taylor_id = self.messaging.name_to_id["Taylor Kim"]

        # Build baseline conversation history (3 weeks of messages)
        base_timestamp = self.start_time - (21 * 24 * 3600)  # 3 weeks before start

        messages = [
            MessageV2(
                sender_id=alex_id,
                content="Hey everyone! Let's pick next month's book. Any suggestions?",
                timestamp=base_timestamp,
            ),
            MessageV2(
                sender_id=jamie_id,
                content="I heard great things about 'The Midnight Library'",
                timestamp=base_timestamp + 3600,
            ),
            MessageV2(
                sender_id=casey_id, content="That's a solid choice! I loved it.", timestamp=base_timestamp + 7200
            ),
            MessageV2(
                sender_id=morgan_id, content="Sounds good to me. When should we meet?", timestamp=base_timestamp + 10800
            ),
            MessageV2(
                sender_id=taylor_id,
                content="How about the first Saturday of next month?",
                timestamp=base_timestamp + 14400,
            ),
            MessageV2(
                sender_id=jamie_id,
                content="Works for me! Same location as last time?",
                timestamp=base_timestamp + (2 * 24 * 3600),
            ),
            MessageV2(
                sender_id=casey_id,
                content="Yes! The community center should be available.",
                timestamp=base_timestamp + (2 * 24 * 3600) + 1800,
            ),
            MessageV2(
                sender_id=alex_id, content="Perfect. I'll reserve the room.", timestamp=base_timestamp + (3 * 24 * 3600)
            ),
            MessageV2(
                sender_id=morgan_id, content="Looking forward to it!", timestamp=base_timestamp + (4 * 24 * 3600)
            ),
            MessageV2(
                sender_id=taylor_id,
                content="Same here. This is my favorite part of the month.",
                timestamp=base_timestamp + (5 * 24 * 3600),
            ),
            MessageV2(
                sender_id=casey_id, content="Agreed! See you all soon.", timestamp=base_timestamp + (6 * 24 * 3600)
            ),
            MessageV2(
                sender_id=jamie_id,
                content="Just finished the book. It's amazing!",
                timestamp=base_timestamp + (10 * 24 * 3600),
            ),
            MessageV2(
                sender_id=alex_id,
                content="I'm halfway through. So many great themes.",
                timestamp=base_timestamp + (12 * 24 * 3600),
            ),
            MessageV2(
                sender_id=morgan_id, content="Can't wait to discuss it!", timestamp=base_timestamp + (14 * 24 * 3600)
            ),
            MessageV2(
                sender_id=casey_id,
                content="Me too! I have so many thoughts.",
                timestamp=base_timestamp + (16 * 24 * 3600),
            ),
        ]

        book_club_conversation = ConversationV2(
            participant_ids=[alex_id, jamie_id, morgan_id, casey_id, taylor_id],
            messages=messages,
            title="Book Club Monthly",
            last_updated=messages[-1].timestamp,
        )

        self.messaging.add_conversation(book_club_conversation)

        # Store conversation_id for use in build_events_flow
        self.book_club_conversation_id = book_club_conversation.conversation_id

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.messaging]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PAREAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")

        # Get conversation_id and participant IDs from stored instance variables
        conversation_id = self.book_club_conversation_id
        casey_id = messaging_app.name_to_id["Casey Jordan"]

        with EventRegisterer.capture_mode():
            # Environment Event 1: Casey Jordan sends a message with email address
            # This is a non-oracle environment event representing an incoming message from the world
            casey_message_event = messaging_app.create_and_add_message(
                conversation_id=conversation_id,
                sender_id=casey_id,
                content="I'll bring snacks! Email me your dietary restrictions at casey.jordan@email.com so I can plan ahead.",
            ).delayed(10)

            # Oracle Event 1: Agent lists recent conversations to observe the Book Club conversation
            # This makes the conversation visible to the agent
            list_conversations_event = (
                messaging_app.list_recent_conversations(
                    offset=0,
                    limit=5,
                    offset_recent_messages_per_conversation=0,
                    limit_recent_messages_per_conversation=10,
                )
                .oracle()
                .depends_on(casey_message_event, delay_seconds=2)
            )

            # Oracle Event 2: Agent opens the Book Club conversation to read the full context
            # This reveals the conversation ID and participant structure
            open_conversation_event = (
                messaging_app.read_conversation(conversation_id=conversation_id, offset=0, limit=20)
                .oracle()
                .depends_on(list_conversations_event, delay_seconds=1)
            )

            # Oracle Event 3: Agent searches contacts to check if Casey Jordan already exists
            # This reveals the gap: Casey is not in contacts despite being an active participant
            search_casey_event = (
                contacts_app.search_contacts(query="Casey Jordan")
                .oracle()
                .depends_on(open_conversation_event, delay_seconds=1)
            )

            # Oracle Event 4: Agent sends proposal to user to add Casey Jordan as a contact
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed you've been actively messaging with Casey Jordan in the Book Club Monthly group, but Casey isn't in your contacts. Casey recently shared an email address (casey.jordan@email.com). Would you like me to add Casey as a contact?"
                )
                .oracle()
                .depends_on(search_casey_event, delay_seconds=2)
            )

            # Oracle Event 5: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please add Casey to my contacts.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent creates contact for Casey Jordan with extracted email
            create_casey_contact_event = (
                contacts_app.add_new_contact(first_name="Casey", last_name="Jordan", email="casey.jordan@email.com")
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 7: Agent sends confirmation message back to the group
            confirmation_event = (
                messaging_app.send_message_to_group_conversation(
                    conversation_id=conversation_id, content="Thanks Casey! I've saved your contact information."
                )
                .oracle()
                .depends_on(create_casey_contact_event, delay_seconds=2)
            )

        # Register ALL events
        self.events = [
            casey_message_event,
            list_conversations_event,
            open_conversation_event,
            search_casey_event,
            proposal_event,
            acceptance_event,
            create_casey_contact_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1 (STRICT): Agent sent proposal to user about adding Casey Jordan as contact
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PAREAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 2 (STRICT): Agent created new contact for Casey Jordan with correct email
            create_contact_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "add_new_contact"
                and e.action.args.get("email") == "casey.jordan@email.com"
                for e in log_entries
            )

            # Compute success: all strict checks must pass
            strict_checks = proposal_found and create_contact_found

            success = strict_checks

            # Build rationale for failures
            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal to user about adding Casey Jordan not found")
                if not create_contact_found:
                    missing_checks.append("agent did not create contact for Casey Jordan with correct email")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
