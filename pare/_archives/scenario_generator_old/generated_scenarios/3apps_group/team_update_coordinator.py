from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("team_update_coordinator")
class TeamUpdateCoordinator(Scenario):
    """Scenario where the agent helps a user coordinate a team update message across coworkers.

    The workflow involves:
    1. User asks the assistant to organize recent updates from messaging.
    2. The agent checks the day and proposes sharing a summary message with the team.
    3. User provides approval.
    4. The agent creates a team conversation, adds members, sends a summary, attaches a document, and waits for acknowledgment.

    Demonstrates usage of AgentUserInterface, SystemApp, and MessagingApp.
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate all applications with initial state."""
        aui = AgentUserInterface()
        system = SystemApp(name="SystemClock")
        messaging = MessagingApp()

        # Create a first conversation simulating existing private chats with teammates
        conv_alex = messaging.create_conversation(participants=["Alex Rivera"], title="Project Delta private chat")
        messaging.send_message(conversation_id=conv_alex, content="Reminder: Team update pending tomorrow.")
        messaging.send_message(conversation_id=conv_alex, content="Working on the new prototype, still debugging.")

        conv_jamie = messaging.create_conversation(participants=["Jamie Lee"], title="Jamie - quick notes")
        messaging.send_message(conversation_id=conv_jamie, content="Will send weekly report draft.")
        messaging.send_message(conversation_id=conv_jamie, content="Need feedback from Alex and you.")

        self.apps = [aui, system, messaging]

    def build_events_flow(self) -> None:
        """Define the chronological, proactive event sequence."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        messaging = self.get_typed_app(MessagingApp)

        # Setting up the flow of oracle events and interactions
        with EventRegisterer.capture_mode():
            # User triggers the process
            user_request = aui.send_message_to_agent(
                content="Can you prepare a summary message with updates from my chats for our team?"
            ).depends_on(None, delay_seconds=1)

            # Agent checks the current date/time
            get_time = system.get_current_time().depends_on(user_request, delay_seconds=1)

            # Agent searches for relevant conversations containing update information
            search_updates = messaging.search(query="update|report|prototype").depends_on(get_time, delay_seconds=1)

            # Agent proactively proposes sending a team update message
            propose_summary = aui.send_message_to_user(
                content="I found several conversations with project updates. Would you like me to draft and share a summary with Alex and Jamie?"
            ).depends_on(search_updates, delay_seconds=1)

            # User responds with approval
            user_approval = aui.send_message_to_agent(
                content="Yes, please send the summary to both Alex and Jamie."
            ).depends_on(propose_summary, delay_seconds=1)

            # Agent creates a team conversation
            create_team_chat = (
                messaging.create_conversation(
                    participants=["Alex Rivera", "Jamie Lee"], title="Weekly Team Summary Meeting"
                )
                .oracle()
                .depends_on(user_approval, delay_seconds=1)
            )

            # Agent sends compiled summary message
            send_summary = (
                messaging.send_message(
                    conversation_id=create_team_chat,
                    content="Here's the summary of this week's project updates:\n- Alex: debugging prototype\n- Jamie: report draft pending review.",
                )
                .oracle()
                .depends_on(create_team_chat, delay_seconds=1)
            )

            # Agent sends attachment (e.g., weekly_summary.txt)
            send_doc = (
                messaging.send_attachment(conversation_id=create_team_chat, filepath="Documents/weekly_summary.txt")
                .oracle()
                .depends_on(send_summary, delay_seconds=1)
            )

            # Agent adds a new participant (boss)
            add_manager = (
                messaging.add_participant_to_conversation(conversation_id=create_team_chat, participant="Morgan Chen")
                .oracle()
                .depends_on(send_doc, delay_seconds=1)
            )

            # Agent waits for a few seconds (simulate awaiting read receipt)
            wait_idle = system.wait_for_notification(timeout=5).depends_on(add_manager, delay_seconds=1)

            # Agent reads conversation after waiting
            read_team_chat = messaging.read_conversation(
                conversation_id=create_team_chat, offset=0, limit=5
            ).depends_on(wait_idle, delay_seconds=1)

        self.events = [
            user_request,
            get_time,
            search_updates,
            propose_summary,
            user_approval,
            create_team_chat,
            send_summary,
            send_doc,
            add_manager,
            wait_idle,
            read_team_chat,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validation: ensure the agent actually created the team chat and sent messages."""
        try:
            events = env.event_log.list_view()
            # Check if conversation creation occurred
            created_chat = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "MessagingApp"
                and event.action.function_name == "create_conversation"
                and "Jamie Lee" in str(event.action.args.get("participants", []))
                for event in events
            )
            # Check if a message was sent with summary content
            message_sent = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.function_name == "send_message"
                and "summary" in event.action.args.get("content", "").lower()
                for event in events
            )
            # Check that a proactive message offering to send was shown
            proactive_prompt = any(
                event.event_type == EventType.AGENT
                and event.action.class_name == "AgentUserInterface"
                and "draft and share" in event.action.args.get("content", "").lower()
                for event in events
            )
            success = created_chat and message_sent and proactive_prompt
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
