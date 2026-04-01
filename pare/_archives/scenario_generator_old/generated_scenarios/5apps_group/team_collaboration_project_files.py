from __future__ import annotations

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.sandbox_file_system import Files
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("team_collaboration_project_files")
class TeamCollaborationProjectFiles(Scenario):
    """Scenario that demonstrates teamwork via messaging, file sharing, reminders, and time management.

    This scenario involves the agent assisting the user with collaborating on a project draft.
    It will show the agent proposing to share the latest draft file with a collaborator after
    summarizing the file content and then setting a reminder for a team review.
    All available apps are used as part of an integrated collaboration workflow.
    """

    start_time: float | None = 0
    duration: float | None = 50

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and populate all required applications for the team collaboration scenario."""
        aui = AgentUserInterface()
        messaging = MessagingApp()
        reminder = ReminderApp()
        system = SystemApp(name="system_main")
        fs = Files(name="fs_team", sandbox_dir=kwargs.get("sandbox_dir", "sandbox"))

        # Create the shared project directory and add a draft document
        fs.makedirs("ProjectAlpha", exist_ok=True)
        fs.open("ProjectAlpha/draft_v1.docx", mode="wb")
        fs.open("ProjectAlpha/review_notes.txt", mode="wb")

        # Create a conversation with team member
        conv_id = messaging.create_conversation(participants=["Jordan Lee"], title="Project Alpha Discussion")

        # Store initialized apps
        self.apps = [aui, messaging, reminder, fs, system]

        # Store the conversation id for subsequent actions
        self.conv_id = conv_id

    def build_events_flow(self) -> None:
        """Build event flow demonstrating proactive collaboration and cross-app interactions."""
        aui = self.get_typed_app(AgentUserInterface)
        messaging = self.get_typed_app(MessagingApp)
        reminder = self.get_typed_app(ReminderApp)
        fs = self.get_typed_app(Files)
        system = self.get_typed_app(SystemApp)

        conv_id = self.conv_id

        with EventRegisterer.capture_mode():
            # Step 1: User requests project assistance
            user_msg = aui.send_message_to_agent(
                content="Can you check if the latest draft of our report is ready to send to Jordan?"
            ).depends_on(None, delay_seconds=1)

            # Step 2: Agent examines file system content and reports findings
            agent_check_fs = fs.ls(path="ProjectAlpha", detail=False).depends_on(user_msg, delay_seconds=1)
            agent_read_doc = fs.read_document(file_path="ProjectAlpha/draft_v1.docx", max_lines=10).depends_on(
                agent_check_fs, delay_seconds=1
            )

            # Step 3: Agent proposes to user sharing the draft with teammate
            propose_share = aui.send_message_to_user(
                content=(
                    "I found 'draft_v1.docx' in the ProjectAlpha folder. "
                    "Would you like me to share it with Jordan Lee in our conversation?"
                )
            ).depends_on(agent_read_doc, delay_seconds=1)

            # Step 4: User approval (proactive confirmation pattern)
            user_approval = aui.send_message_to_agent(
                content="Yes, please share the draft file with Jordan and set a reminder for review tomorrow."
            ).depends_on(propose_share, delay_seconds=1)

            # Step 5: Agent sends the file via messaging
            oracle_attachment = (
                messaging.send_attachment(conversation_id=conv_id, filepath="ProjectAlpha/draft_v1.docx")
                .oracle()
                .depends_on(user_approval, delay_seconds=1)
            )

            # Step 6: Agent sets reminder after sending the draft
            current_time_data = system.get_current_time().depends_on(oracle_attachment, delay_seconds=1)
            add_reminder_action = (
                reminder.add_reminder(
                    title="Team review for Project Alpha",
                    due_datetime="2024-06-20 10:00:00",
                    description="Review draft with Jordan before submission.",
                    repetition_unit=None,
                )
                .oracle()
                .depends_on(current_time_data, delay_seconds=1)
            )

            # Step 7: Agent notifies completion to user and shows reminder setup
            completion_notice = (
                aui.send_message_to_user(
                    content="I've shared the draft with Jordan and added a reminder for your team review."
                )
                .oracle()
                .depends_on(add_reminder_action, delay_seconds=1)
            )

        self.events = [
            user_msg,
            agent_check_fs,
            agent_read_doc,
            propose_share,
            user_approval,
            oracle_attachment,
            current_time_data,
            add_reminder_action,
            completion_notice,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Custom validation that checks if all apps were interacted with correctly."""
        try:
            events = env.event_log.list_view()

            # Validation of message sent with correct file attachment
            attachment_sent = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "MessagingApp"
                and event.action.function_name == "send_attachment"
                and "draft_v1.docx" in event.action.args["filepath"]
                for event in events
            )

            # Validation of reminder creation
            reminder_created = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "ReminderApp"
                and event.action.function_name == "add_reminder"
                and "Project Alpha" in event.action.args["title"]
                for event in events
            )

            # Validation that user confirmation and proposal interaction exists
            proactive_dialogue = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "AgentUserInterface"
                and "Would you like me to share" in event.action.args.get("content", "")
                for event in events
            ) and any(
                event.event_type == EventType.USER
                and isinstance(event.action, Action)
                and "please share the draft" in event.action.args.get("content", "").lower()
                for event in events
            )

            # Check file system usage
            fs_access = any(isinstance(event.action, Action) and event.action.class_name == "Files" for event in events)

            # Check system clock retrieval usage
            system_used = any(
                isinstance(event.action, Action)
                and event.action.class_name == "SystemApp"
                and event.action.function_name == "get_current_time"
                for event in events
            )

            success_all = all([attachment_sent, reminder_created, proactive_dialogue, fs_access, system_used])
            return ScenarioValidationResult(success=success_all)
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
