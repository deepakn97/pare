from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.sandbox_file_system import Files
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("project_feedback_share")
class ProjectFeedbackShare(Scenario):
    """Scenario: A project collaboration where the user asks the assistant to summarize a feedback document
    and share it via messaging with a teammate after confirmation.

    Demonstrates collaboration workflow:
    - Uses Files app to create and manage files
    - Uses MessagingApp to coordinate communication
    - Uses AgentUserInterface for natural user interaction
    Includes a proactive proposal → user confirmation → action execution pattern.
    """  # noqa: D205

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all applications and prepare test data."""
        # Initialize the apps available for the scenario
        aui = AgentUserInterface()
        fs = Files(name="work_files", sandbox_dir=kwargs.get("sandbox_dir"))
        messaging = MessagingApp()

        # Prepare a structure in the sandbox file system
        fs.makedirs(path="Documents/ProjectFeedback", exist_ok=True)
        # Create a dummy feedback file
        feedback_file = "Documents/ProjectFeedback/client_feedback.txt"

        content = (
            "Feedback Summary:\n"
            "1. Improve color consistency on main dashboard.\n"
            "2. Add loading indicators for data-heavy charts.\n"
            "3. Consider accessibility improvements for font size.\n"
        )
        fs.open(path=feedback_file, mode="wb")
        fs.cat(path=feedback_file)  # read the file once for context

        # List files for confirmation
        fs.ls(path="Documents/ProjectFeedback")

        # Create a messaging conversation with teammate "Jordan Lee"
        conv_id = messaging.create_conversation(participants=["Jordan Lee"], title="Project Feedback Discussion")

        # Store all apps for the environment
        self.apps = [aui, fs, messaging]

        # Save meta info for reuse
        self.feedback_file = feedback_file
        self.conversation_id = conv_id

    def build_events_flow(self) -> None:
        """Define sequence of ground-truth events."""
        aui = self.get_typed_app(AgentUserInterface)
        fs = self.get_typed_app(Files)
        messaging = self.get_typed_app(MessagingApp)
        feedback_path = self.feedback_file
        conv_id = self.conversation_id

        with EventRegisterer.capture_mode():
            # Step 1: User asks to review the feedback document
            user_request = aui.send_message_to_agent(
                content="Please summarize the latest client feedback document and prepare it to share with Jordan."
            ).depends_on(None, delay_seconds=1)

            # Step 2: Agent reads the file content (Files app)
            agent_reads = (
                fs.read_document(file_path=feedback_path, max_lines=10)
                .oracle()
                .depends_on(user_request, delay_seconds=1)
            )

            # Step 3: Agent proposes to share the summary with Jordan
            agent_propose = aui.send_message_to_user(
                content="I have summarized the feedback. Would you like me to send this summary to Jordan Lee in our project chat?"
            ).depends_on(agent_reads, delay_seconds=1)

            # Step 4: User confirms the agent's proposal
            user_confirm = aui.send_message_to_agent(
                content="Yes, please go ahead and share it with Jordan."
            ).depends_on(agent_propose, delay_seconds=1)

            # Step 5: Agent sends the summarized feedback message to Jordan
            feedback_summary = (
                "Summary:\n"
                "- Maintain consistent dashboard colors.\n"
                "- Add loading indicators for charts.\n"
                "- Enhance accessibility with larger fonts."
            )
            agent_share_message = (
                messaging.send_message(conversation_id=conv_id, content=feedback_summary)
                .oracle()
                .depends_on(user_confirm, delay_seconds=1)
            )

            # Step 6: Agent sends a confirmation back to user after sending
            agent_notify = (
                aui.send_message_to_user(content="I've shared the summarized feedback with Jordan Lee.")
                .oracle()
                .depends_on(agent_share_message, delay_seconds=1)
            )

        self.events = [user_request, agent_reads, agent_propose, user_confirm, agent_share_message, agent_notify]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Ensure that the agent read the feedback file and sent the summary message after confirmation."""
        try:
            events = env.event_log.list_view()

            # Validation: Did agent read the document?
            file_read = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "Files"
                and event.action.function_name == "read_document"
                and "client_feedback.txt" in event.action.args.get("file_path", "")
                for event in events
            )

            # Validation: Did agent send message in messaging app?
            msg_sent = any(
                (
                    event.event_type == EventType.AGENT
                    and isinstance(event.action, Action)
                    and event.action.class_name == "MessagingApp"
                    and event.action.function_name == "send_message"
                    and "Jordan" in str(event.action.args.get("conversation_id", ""))
                )
                or "feedback" in str(event.action.args.get("content", "")).lower()
                for event in events
            )

            # Validation: Did user approve before message sent?
            user_approved = any(
                event.event_type == EventType.USER
                and "share it with Jordan" in str(event.action.args.get("content", ""))
                for event in events
            )

            success = file_read and msg_sent and user_approved
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
