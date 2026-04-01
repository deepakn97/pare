from __future__ import annotations

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.sandbox_file_system import SandboxLocalFileSystem
from are.simulation.apps.system import SystemApp
from are.simulation.apps.virtual_file_system import VirtualFileSystem
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("asset_sync_and_share")
class AssetSyncAndShare(Scenario):
    """Scenario: Agent helps user synchronize a project file, preview it, and share it via messaging.

    With a proactive confirmation step.

    Workflow:
    - User asks assistant to ensure all digital assets from local project folder are backed up.
    - Agent inspects local sandbox folder, synchronizes files to virtual file system.
    - Agent proposes to share one key file via messaging with a collaborator.
    - User approves.
    - Agent sends the file through messaging.
    - System time and waits used for realistic simulation.
    """

    start_time: float | None = 0
    duration: float | None = 30

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and populate all available applications."""
        # Required applications
        aui = AgentUserInterface()
        system = SystemApp(name="System")
        messaging = MessagingApp()
        local_fs = SandboxLocalFileSystem(name="LocalFS", sandbox_dir=kwargs.get("sandbox_dir"))
        vfs = VirtualFileSystem(name="CloudStorage")

        # Populate local sandbox with "project assets"
        local_fs.makedirs("ProjectAssets", exist_ok=True)
        local_fs.open("ProjectAssets/design_notes.txt", mode="wb")
        local_fs.open("ProjectAssets/mockup_image.png", mode="wb")

        # Virtual file system: create a sync folder
        vfs.mkdir("SyncedAssets", create_recursive=True)

        # Store apps
        self.apps = [aui, system, messaging, local_fs, vfs]

    def build_events_flow(self) -> None:
        """Build the flow of events including proactive interaction and subsequent actions."""
        # Get references
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        messaging = self.get_typed_app(MessagingApp)
        local_fs = self.get_typed_app(SandboxLocalFileSystem)
        vfs = self.get_typed_app(VirtualFileSystem)

        # Start building oracle / expected sequence of events
        with EventRegisterer.capture_mode():
            # User starts by requesting sync
            event0 = aui.send_message_to_agent(
                content="Could you sync all project files from my local assets folder to cloud storage?"
            ).depends_on(None, delay_seconds=1)

            # Agent gets current time to log sync start
            event1 = system.get_current_time().oracle().depends_on(event0, delay_seconds=1)

            # Agent lists the contents of local project folder
            event2 = local_fs.ls(path="ProjectAssets").oracle().depends_on(event1, delay_seconds=1)

            # Agent creates corresponding folder in virtual storage
            event3 = vfs.mkdir(path="SyncedAssets", create_recursive=True).oracle().depends_on(event2, delay_seconds=1)

            # Agent moves (simulates synchronization) the file from local to virtual storage
            event4 = (
                vfs.mv(path1="SyncedAssets", path2="SyncedAssets_backup_folder")
                .oracle()
                .depends_on(event3, delay_seconds=1)
            )

            # Agent waits a short time to simulate sync delay
            event5 = system.wait_for_notification(timeout=3).oracle().depends_on(event4, delay_seconds=1)

            # Agent reviews synced content (tree for presentation)
            event6 = vfs.tree(path="SyncedAssets").oracle().depends_on(event5, delay_seconds=1)

            # Agent shows the user the local project folder tree before sync
            event7 = local_fs.tree(path="ProjectAssets").oracle().depends_on(event6, delay_seconds=1)

            # Agent proactively proposes sharing a synced file
            proactive_proposal = aui.send_message_to_user(
                content=(
                    "Synchronization complete. Would you like me to share the mockup image file "
                    "with Alex via messaging for a quick review?"
                )
            ).depends_on(event7, delay_seconds=1)

            # User explicitly approves the sharing
            approval = aui.send_message_to_agent(
                content="Yes, please send the mockup image to Alex in a new chat titled 'Design Review'."
            ).depends_on(proactive_proposal, delay_seconds=1)

            # Based on approval, the agent creates a new conversation
            new_conversation = (
                messaging.create_conversation(participants=["Alex"], title="Design Review")
                .oracle()
                .depends_on(approval, delay_seconds=1)
            )

            # The agent previews the file before sending to Alex
            preview_action = (
                local_fs.display(path="ProjectAssets/mockup_image.png")
                .oracle()
                .depends_on(new_conversation, delay_seconds=1)
            )

            # The agent sends that same file as an attachment via messaging
            send_file = (
                messaging.send_attachment(conversation_id=new_conversation, filepath="ProjectAssets/mockup_image.png")
                .oracle()
                .depends_on(preview_action, delay_seconds=1)
            )

        # Register events
        self.events = [
            event0,
            event1,
            event2,
            event3,
            event4,
            event5,
            event6,
            event7,
            proactive_proposal,
            approval,
            new_conversation,
            preview_action,
            send_file,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validation logic ensuring full pipeline success."""
        try:
            events = env.event_log.list_view()
            # Validate messaging of attachment occurred
            attachment_sent = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "MessagingApp"
                and event.action.function_name == "send_attachment"
                and "mockup_image.png" in event.action.args.get("filepath", "")
                for event in events
            )
            # Validate proactive proposal sent to user
            proposal_sent = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "AgentUserInterface"
                and event.action.function_name == "send_message_to_user"
                and "share the mockup image" in event.action.args.get("content", "").lower()
                for event in events
            )
            # Validate local FS and VFS usage
            vfs_used = any(
                event.action.class_name == "VirtualFileSystem" for event in events if isinstance(event.action, Action)
            )
            fs_read = any(
                event.action.class_name == "SandboxLocalFileSystem"
                for event in events
                if isinstance(event.action, Action)
            )
            # Validation success if all critical systems participated and file shared
            return ScenarioValidationResult(success=(attachment_sent and proposal_sent and vfs_used and fs_read))
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
