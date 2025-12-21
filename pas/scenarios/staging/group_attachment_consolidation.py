"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
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


@register_scenario("group_attachment_consolidation")
class GroupAttachmentConsolidation(PASScenario):
    """Agent downloads and organizes multiple attachments shared across a group conversation for upcoming event planning.

    The user participates in a group conversation titled "Hiking Trip Planning" with three friends: Alex Rivera, Jordan Lee, and Casey Morgan. Over the course of an hour, different participants share reference materials for their planned weekend hike: Alex sends a trail map image, Jordan shares a PDF with camping regulations, and Casey forwards a photo of the weather forecast. The agent must: 1. Monitor the group conversation and detect that multiple attachments relate to the same upcoming event (the hiking trip). 2. Download all three attachments from their respective messages. 3. Recognize these scattered resources should be consolidated for the user's convenience. 4. Propose organizing the downloaded files and creating a summary of received materials. 5. After user acceptance, send a message back to the group confirming receipt and listing all received materials (trail map from Alex, regulations from Jordan, weather forecast from Casey).

    This scenario exercises multi-message attachment tracking within group conversations, proactive resource consolidation without explicit user request, download management across multiple senders, contextual understanding that related materials should be organized together, and group communication etiquette by acknowledging contributions from multiple participants in a single confirmation message..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize contacts app with hiking trip participants
        self.contacts = StatefulContactsApp(name="Contacts")

        # Add contacts for the three friends in the hiking group
        self.alex_contact_id = self.contacts.add_contact(
            Contact(
                first_name="Alex",
                last_name="Rivera",
                contact_id="contact-alex-rivera",
                phone="555-201-3001",
                email="alex.rivera@email.com",
            )
        )

        self.jordan_contact_id = self.contacts.add_contact(
            Contact(
                first_name="Jordan",
                last_name="Lee",
                contact_id="contact-jordan-lee",
                phone="555-201-3002",
                email="jordan.lee@email.com",
            )
        )

        self.casey_contact_id = self.contacts.add_contact(
            Contact(
                first_name="Casey",
                last_name="Morgan",
                contact_id="contact-casey-morgan",
                phone="555-201-3003",
                email="casey.morgan@email.com",
            )
        )

        # Initialize messaging app with group conversation
        self.messaging = StatefulMessagingApp(name="Messages")

        # Register user names to IDs for messaging
        self.messaging.add_users(["Alex Rivera", "Jordan Lee", "Casey Morgan"])

        # Get user IDs for participants
        alex_id = self.messaging.get_user_id("Alex Rivera")
        jordan_id = self.messaging.get_user_id("Jordan Lee")
        casey_id = self.messaging.get_user_id("Casey Morgan")

        # Create baseline group conversation with early planning messages (no attachments yet)
        # Conversation started a day before (2025-11-17 at 18:00 UTC)
        baseline_timestamp_1 = datetime(2025, 11, 17, 18, 0, 0, tzinfo=UTC).timestamp()
        baseline_timestamp_2 = datetime(2025, 11, 17, 18, 15, 0, tzinfo=UTC).timestamp()

        hiking_conversation = ConversationV2(
            conversation_id="conv-hiking-trip-planning",
            title="Hiking Trip Planning",
            participant_ids=[alex_id, jordan_id, casey_id, self.messaging.current_user_id],
            messages=[
                MessageV2(
                    sender_id=alex_id,
                    message_id="msg-baseline-1",
                    timestamp=baseline_timestamp_1,
                    content="Hey everyone! Excited for our hike this weekend. I found a great trail we should consider.",
                ),
                MessageV2(
                    sender_id=jordan_id,
                    message_id="msg-baseline-2",
                    timestamp=baseline_timestamp_2,
                    content="Awesome! Let me look up the camping regulations for that area.",
                ),
            ],
            last_updated=baseline_timestamp_2,
        )

        self.messaging.add_conversation(hiking_conversation)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.messaging]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")

        # Get user IDs for participants (matching how they were registered in init_and_populate_apps)
        alex_id = messaging_app.get_user_id("Alex Rivera")
        jordan_id = messaging_app.get_user_id("Jordan Lee")
        casey_id = messaging_app.get_user_id("Casey Morgan")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Alex shares trail map information
            message1_event = messaging_app.create_and_add_message(
                conversation_id="conv-hiking-trip-planning",
                sender_id=alex_id,
                content="Here's the trail map for Saturday's hike: Eagle Peak Trail. I've marked the parking coordinates and the summit viewpoint.",
            ).delayed(15)

            # Environment Event 2: Jordan shares camping regulations
            message2_event = messaging_app.create_and_add_message(
                conversation_id="conv-hiking-trip-planning",
                sender_id=jordan_id,
                content="Found the camping regulations PDF - no fires above 8000ft elevation, bear canisters required, and overnight permits available at ranger station.",
            ).delayed(25)

            # Environment Event 3: Casey shares weather forecast
            message3_event = messaging_app.create_and_add_message(
                conversation_id="conv-hiking-trip-planning",
                sender_id=casey_id,
                content="Weather forecast looks good! Clear skies Saturday, highs around 65F, lows 42F overnight. Sunday might have afternoon clouds.",
            ).delayed(20)

            # Oracle Event 1: Agent reads the conversation to review all shared materials
            read_conv_event = (
                messaging_app.read_conversation(
                    conversation_id="conv-hiking-trip-planning",
                    offset=0,
                    limit=20,
                )
                .oracle()
                .depends_on(message3_event, delay_seconds=3)
            )

            # Oracle Event 2: Agent proposes consolidating the shared information
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed your hiking group has shared several planning resources: trail map from Alex, camping regulations from Jordan, and weather forecast from Casey. Would you like me to send a summary confirmation to the group?"
                )
                .oracle()
                .depends_on(read_conv_event, delay_seconds=2)
            )

            # Oracle Event 3: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please send a confirmation to the group.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent sends consolidated confirmation to the group conversation
            confirmation_event = (
                messaging_app.send_message_to_group_conversation(
                    conversation_id="conv-hiking-trip-planning",
                    content="Thanks everyone for sharing the hiking trip materials! I've noted:\n- Trail map with coordinates (Alex)\n- Camping regulations & permit info (Jordan)\n- Weekend weather forecast (Casey)\n\nEverything is organized and ready for Saturday's hike!",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

        # Register ALL events
        self.events = [
            message1_event,
            message2_event,
            message3_event,
            read_conv_event,
            proposal_event,
            acceptance_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent sent proposal to the user about consolidating group information
            # STRICT: Must propose help related to the hiking group materials
            # FLEXIBLE: Exact wording can vary
            proposal_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check Step 2: Agent read the conversation to detect the shared materials
            # STRICT: Must call read_conversation on the hiking trip conversation
            # FLEXIBLE: offset/limit parameters can vary
            read_conversation_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "read_conversation"
                and e.action.args.get("conversation_id") == "conv-hiking-trip-planning"
                for e in log_entries
            )

            # Check Step 3: Agent sent confirmation message back to the group conversation
            # STRICT: Must use send_message_to_group_conversation on the correct conversation_id
            # FLEXIBLE: message content can vary as long as it's sent to the right group
            group_message_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message_to_group_conversation"
                and e.action.args.get("conversation_id") == "conv-hiking-trip-planning"
                for e in log_entries
            )

            # All critical checks must pass for success
            success = proposal_found and read_conversation_found and group_message_found

            if not success:
                # Build rationale explaining which checks failed
                failed_checks = []
                if not proposal_found:
                    failed_checks.append("agent proposal to user not found")
                if not read_conversation_found:
                    failed_checks.append("agent did not read the hiking conversation")
                if not group_message_found:
                    failed_checks.append("agent did not send confirmation to group")

                rationale = "Validation failed: " + ", ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
