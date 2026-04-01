from __future__ import annotations

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.sandbox_file_system import Files
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("team_file_share_collaboration")
class TeamFileShareCollaboration(Scenario):
    """A scenario demonstrating file collaboration and proactive sharing confirmation.

    The agent reads a team meeting summary file from the file system, proposes to share it
    with a colleague through a messaging app, waits for user confirmation, and then sends it
    upon approval. The scenario uses all available apps: AgentUserInterface, Files,
    MessagingApp, and SystemApp.
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize apps and populate the sandboxed environment."""
        # Instantiate all available applications
        aui = AgentUserInterface()
        file_system = Files(name="project_fs", sandbox_dir=kwargs.get("sandbox_dir", "/sandbox/team_project"))
        messaging = MessagingApp()
        system = SystemApp(name="sys")

        # Create a directory for the team project and place a report file there
        file_system.makedirs(path="team_reports", exist_ok=True)
        # Simulate a team report file
        with open("team_reports/meeting_notes.txt", "w", encoding="utf-8") as f:
            f.write(
                "Team Meeting Summary:\n"
                "- Discussed new product design adjustments.\n"
                "- Assigned marketing strategy to Clara.\n"
                "- Next sprint planning scheduled for next Monday."
            )

        # Store apps for later reference in event flow
        self.apps = [aui, file_system, messaging, system]

    def build_events_flow(self) -> None:
        """Define the event sequence, including proactive interaction and user confirmation."""
        aui = self.get_typed_app(AgentUserInterface)
        files = self.get_typed_app(Files)
        messaging = self.get_typed_app(MessagingApp)
        system = self.get_typed_app(SystemApp)

        # Prepare a conversation for the collaboration
        conv_id = messaging.create_conversation(participants=["Clara Jenkins"], title="Product Strategy Discussion")

        with EventRegisterer.capture_mode():
            # 1. User requests assistance
            e0 = aui.send_message_to_agent(
                content="Can you help me share the new meeting notes with Clara?"
            ).depends_on(None, delay_seconds=1)

            # 2. Agent checks current time to tag note sharing appropriately
            e1 = system.get_current_time().depends_on(e0, delay_seconds=1)

            # 3. Agent reads the meeting notes file content for context
            e2 = files.read_document(file_path="team_reports/meeting_notes.txt", max_lines=10).depends_on(
                e1, delay_seconds=1
            )

            # 4. Agent proactively asks for confirmation before sharing
            e3 = aui.send_message_to_user(
                content="I found the meeting_notes.txt file in the project folder. Would you like me to share it with Clara Jenkins in our chat?"
            ).depends_on(e2, delay_seconds=1)

            # 5. User provides contextual approval
            e4 = aui.send_message_to_agent(
                content="Yes, please share the file with Clara in the project chat."
            ).depends_on(e3, delay_seconds=2)

            # 6. Agent sends the file as an attachment in the conversation after approval
            e5 = (
                messaging.send_attachment(conversation_id=conv_id, filepath="team_reports/meeting_notes.txt")
                .oracle()
                .depends_on(e4, delay_seconds=1)
            )

            # 7. Agent notifies the user of successful sharing
            e6 = aui.send_message_to_user(content="The meeting notes have been sent to Clara successfully!").depends_on(
                e5, delay_seconds=1
            )

            # 8. Agent lists recent messages for validation (simulate final action)
            e7 = messaging.list_recent_conversations(offset=0, limit=3).depends_on(e6, delay_seconds=1)

            # 9. System waits for any new notifications (simulate idle wait)
            e8 = system.wait_for_notification(timeout=5).depends_on(e7, delay_seconds=1)

        self.events = [e0, e1, e2, e3, e4, e5, e6, e7, e8]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the scenario objectives were met (file shared after approval)."""
        try:
            events = env.event_log.list_view()

            # Check if the proactive message was sent to the user
            proactive_prompt_sent = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "AgentUserInterface"
                and event.action.function_name == "send_message_to_user"
                and "meeting_notes.txt" in event.action.args.get("content", "")
                for event in events
            )

            # Check if the attachment was sent after confirmation
            file_shared_correctly = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "MessagingApp"
                and event.action.function_name == "send_attachment"
                and "meeting_notes.txt" in event.action.args.get("filepath", "")
                for event in events
            )

            # Check if user approval message came before sending attachment
            approvals = [
                i
                for i, event in enumerate(events)
                if event.event_type == EventType.USER
                and isinstance(event.action, Action)
                and event.action.class_name == "AgentUserInterface"
                and "share" in event.action.args.get("content", "").lower()
            ]
            share_events = [
                i
                for i, event in enumerate(events)
                if event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "MessagingApp"
                and event.action.function_name == "send_attachment"
            ]
            approval_before_share = approvals and share_events and approvals[0] < share_events[0]

            success = proactive_prompt_sent and file_shared_correctly and approval_before_share
            return ScenarioValidationResult(success=success)
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
