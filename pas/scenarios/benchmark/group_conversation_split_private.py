"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulMessagingApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("group_conversation_split_private")
class GroupConversationSplitPrivate(PASScenario):
    """Agent detects sensitive discussion in group chat and proactively suggests moving to private conversation.

    The user participates in a group conversation titled "Project Team" with colleagues Alex Rivera, Jordan Lee, and Casey Morgan. During a casual work discussion, Jordan messages: "Hey, can someone review the salary data I sent for the new hires?" followed by "Want to make sure the compensation packages are competitive before we finalize." The agent recognizes that salary and compensation information is sensitive and should not be discussed in a group setting with multiple participants. The agent must: 1. Detect the sensitive topic (salary/compensation) mentioned in the group chat. 2. Identify the specific participant (Jordan Lee) who initiated the sensitive discussion. 3. Propose creating a private 1:1 conversation with Jordan to discuss this matter appropriately. 4. After user acceptance, open or create a direct conversation with Jordan Lee. 5. Send an initial message to Jordan in the private thread suggesting they continue the compensation discussion there instead of the group chat. 6. Optionally send a brief message in the group chat redirecting the topic without revealing details.

    This scenario exercises content sensitivity detection across messaging contexts, privacy-aware conversation routing, appropriate communication channel selection based on topic classification, and graceful topic redirection from group to individual conversations without exposing the sensitive nature of the original request..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        # Initialize core apps
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")
        self.messaging = StatefulMessagingApp(name="Messages")

        # Add users to messaging app
        self.messaging.add_users(["Alex Rivera", "Jordan Lee", "Casey Morgan"])

        # Get user IDs for participants
        self.user_id = self.messaging.current_user_id
        self.alex_id = self.messaging.get_user_id("Alex Rivera")
        self.jordan_id = self.messaging.get_user_id("Jordan Lee")
        self.casey_id = self.messaging.get_user_id("Casey Morgan")

        # Create group conversation "Project Team" with baseline history
        # This conversation already exists before the scenario starts
        self.group_conversation = ConversationV2(
            participant_ids=[self.user_id, self.alex_id, self.jordan_id, self.casey_id],
            title="Project Team",
            conversation_id="conv-project-team",
            last_updated=self.start_time - 86400,  # Last updated 1 day ago
        )

        # Add some baseline messages from the past (non-sensitive work discussion)
        baseline_timestamp_1 = self.start_time - 3600  # 1 hour ago
        baseline_timestamp_2 = self.start_time - 1800  # 30 minutes ago

        self.group_conversation.messages.append(
            MessageV2(
                sender_id=self.alex_id,
                content="Good morning everyone! Ready for this week's sprint?",
                timestamp=baseline_timestamp_1,
            )
        )

        self.group_conversation.messages.append(
            MessageV2(
                sender_id=self.casey_id,
                content="Yes! Looking forward to wrapping up the Q4 deliverables.",
                timestamp=baseline_timestamp_2,
            )
        )

        # Add the group conversation to messaging app
        self.messaging.add_conversation(self.group_conversation)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.messaging]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")

        # Use stable participant IDs computed during init (avoid calling get_user_id in capture_mode, which can return an Event)
        jordan_id = self.jordan_id

        with EventRegisterer.capture_mode():
            # Environment Event 1: Jordan sends first sensitive message to group chat
            # This message contains salary-related information that should be private
            message1_event = messaging_app.create_and_add_message(
                conversation_id=self.group_conversation.conversation_id,
                sender_id=jordan_id,
                content="Hey, can someone review the salary data I sent for the new hires?",
            ).delayed(10)

            # Environment Event 2: Jordan follows up with more sensitive compensation details
            message2_event = messaging_app.create_and_add_message(
                conversation_id=self.group_conversation.conversation_id,
                sender_id=jordan_id,
                content="Want to make sure the compensation packages are competitive before we finalize.",
            ).depends_on(message1_event, delay_seconds=3)

            # Environment Event 3: Casey flags the topic as sensitive and requests moving it off the group chat
            # This provides an explicit observable cue (not just policy inference) to move the discussion to a private thread.
            message3_event = messaging_app.create_and_add_message(
                conversation_id=self.group_conversation.conversation_id,
                sender_id=self.casey_id,
                content=(
                    "Quick note: salary/comp details are sensitive—let's move this to a 1:1 thread instead of the group chat. "
                    "Could you DM Jordan directly to continue that discussion?"
                ),
            ).depends_on(message2_event, delay_seconds=2)

            # Oracle Event 1: Agent detects sensitive topic and proposes moving to private conversation
            # Motivation: Casey explicitly flagged salary/comp as sensitive and asked the user to DM Jordan directly.
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed Jordan is discussing salary information in the Project Team group chat. This sensitive topic should be discussed privately. Would you like me to help move this conversation to a private thread with Jordan?"
                )
                .oracle()
                .depends_on(message3_event, delay_seconds=3)
            )

            # Oracle Event 2: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, that's a good idea. Please handle it.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent searches for or identifies Jordan's user ID
            # This step makes the agent explicitly observe Jordan's identity
            lookup_event = (
                messaging_app.lookup_user_id(user_name="Jordan Lee")
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 4: Agent sends private message to Jordan
            # This creates or uses existing 1:1 conversation with Jordan
            private_message_event = (
                messaging_app.send_message(
                    user_id=jordan_id,
                    content="Hi Jordan, I noticed you were discussing salary and compensation details in the Project Team group chat. These topics are better suited for a private conversation. Feel free to continue the discussion here, and I can help coordinate if needed.",
                )
                .oracle()
                .depends_on(lookup_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent optionally sends a brief redirect in group chat
            # This is a polite redirect without revealing details
            group_redirect_event = (
                messaging_app.send_message_to_group_conversation(
                    conversation_id=self.group_conversation.conversation_id,
                    content="I've reached out to Jordan separately to discuss the staffing details.",
                )
                .oracle()
                .depends_on(private_message_event, delay_seconds=1)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            message1_event,
            message2_event,
            message3_event,
            proposal_event,
            acceptance_event,
            lookup_event,
            private_message_event,
            group_redirect_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:  # noqa: C901
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only agent/oracle events
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # Check Step 1: Agent sent proposal to user about moving sensitive conversation
            # STRICT: Agent must detect sensitivity and propose the privacy-protecting action
            proposal_found = False
            for event in agent_events:
                if (
                    event.action.class_name == "PASAgentUserInterface"
                    and event.action.function_name == "send_message_to_user"
                ):
                    proposal_found = True
                    break

            # Check Step 2: Agent looked up Jordan's user ID
            # STRICT: Agent must identify the specific participant to message privately
            lookup_found = False
            for event in agent_events:
                if event.action.class_name == "StatefulMessagingApp" and event.action.function_name == "lookup_user_id":
                    args = event.get_args()
                    if "jordan" in args.get("user_name", "").lower():
                        lookup_found = True
                        break

            # Check Step 3: Agent sent private message to Jordan
            # STRICT: Agent must send a message to Jordan privately
            # FLEXIBLE: Content can vary; we only check that the correct tool was called with Jordan's ID
            private_message_found = False
            jordan_id = self.messaging.get_user_id("Jordan Lee")
            for event in agent_events:
                if event.action.class_name == "StatefulMessagingApp" and event.action.function_name == "send_message":
                    args = event.get_args()
                    if args.get("user_id") == jordan_id:
                        private_message_found = True
                        break

            # Success requires all STRICT checks to pass
            # The group redirect is optional and does not affect success
            success = proposal_found and lookup_found and private_message_found

            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal to move sensitive conversation")
                if not lookup_found:
                    missing_checks.append("lookup of Jordan Lee's user ID")
                if not private_message_found:
                    missing_checks.append("private message to Jordan Lee")

                rationale = f"Missing required agent actions: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
