from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.system import SystemApp
from are.simulation.apps.virtual_file_system import VirtualFileSystem
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("file_organization_proactive_backup")
class FileOrganizationProactiveBackup(Scenario):
    """Scenario: The agent proactively proposes organizing and backing up files.

    This scenario demonstrates the integration of:
    - VirtualFileSystem for manipulating directories and files
    - SystemApp for time-based event handling
    - AgentUserInterface for proactive task proposals and user confirmations

    Flow:
    - SystemApp provides the timestamp.
    - The agent inspects a VirtualFileSystem folder.
    - The agent proposes to the user to back up a project directory.
    - The user approves with a contextual message.
    - The agent creates a backup folder, moves project files, and confirms completion.
    """

    start_time: float | None = 0
    duration: float | None = 30

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate applications with directories and files."""
        # Create necessary application instances.
        aui = AgentUserInterface()
        sys_app = SystemApp(name="system_app")
        vfs = VirtualFileSystem(name="virtual_fs")

        # Build a small directory tree for demonstration.
        # /projects/alpha and /projects/beta with some files.
        vfs.mkdir("/projects")
        vfs.mkdir("/projects/alpha")
        vfs.mkdir("/projects/beta")
        vfs.open("/projects/alpha/plan.txt", mode="wb")
        vfs.open("/projects/alpha/data.csv", mode="wb")
        vfs.open("/projects/beta/notes.txt", mode="wb")

        # Also create a target backup directory for later
        vfs.mkdir("/backups")

        # Register apps in the environment
        self.apps = [aui, sys_app, vfs]

    def build_events_flow(self) -> None:
        """Set up the flow of interactions and actions."""
        aui = self.get_typed_app(AgentUserInterface)
        sys_app = self.get_typed_app(SystemApp)
        vfs = self.get_typed_app(VirtualFileSystem)

        with EventRegisterer.capture_mode():
            # Event 0: System provides the current time
            system_time = sys_app.get_current_time().depends_on(None, delay_seconds=0)

            # Event 1: User initiates conversation asking for file organization assistance
            user_start = aui.send_message_to_agent(
                content="Can you check what project files I have and propose a cleanup?"
            ).depends_on(system_time, delay_seconds=1)

            # Event 2: Agent lists the current projects directory
            list_dirs = vfs.ls(path="/projects", detail=True).depends_on(user_start, delay_seconds=1)

            # Event 3: Agent proposes an action — to back up the /projects/alpha folder to /backups/alpha_backup
            propose_backup = aui.send_message_to_user(
                content="I found multiple files in /projects/alpha. Would you like me to back up that folder into /backups/alpha_backup?"
            ).depends_on(list_dirs, delay_seconds=1)

            # Event 4: User provides contextual approval for the backup action
            user_approval = aui.send_message_to_agent(
                content="Yes, please create the backup for the alpha project folder."
            ).depends_on(propose_backup, delay_seconds=1)

            # Oracle Section (agent's ideal behavior):

            # Event 5: Create the backup directory if not existing
            create_backup_dir = (
                vfs.mkdir(path="/backups/alpha_backup", create_recursive=True)
                .oracle()
                .depends_on(user_approval, delay_seconds=1)
            )

            # Event 6: Move the contents to backup directory
            move_files = (
                vfs.mv(path1="/projects/alpha", path2="/backups/alpha_backup")
                .oracle()
                .depends_on(create_backup_dir, delay_seconds=1)
            )

            # Event 7: Verify existence of backup (check folder)
            check_backup = vfs.exists(path="/backups/alpha_backup").oracle().depends_on(move_files, delay_seconds=1)

            # Event 8: Agent sends confirmation to user that backup completed
            confirm_msg = (
                aui.send_message_to_user(
                    content="The alpha project folder has been successfully backed up to /backups/alpha_backup."
                )
                .oracle()
                .depends_on(check_backup, delay_seconds=1)
            )

            # Event 9: System waits for a small interval before idle
            wait_idle = sys_app.wait_for_notification(timeout=3).depends_on(confirm_msg, delay_seconds=1)

            # Event 10: Agent prints the final directory tree for verification
            dir_tree = vfs.tree(path="/").oracle().depends_on(wait_idle, delay_seconds=1)

        self.events = [
            system_time,
            user_start,
            list_dirs,
            propose_backup,
            user_approval,
            create_backup_dir,
            move_files,
            check_backup,
            confirm_msg,
            wait_idle,
            dir_tree,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the backup directory was created and agent interacted properly."""
        try:
            events = env.event_log.list_view()
            # Backup creation verified by oracle mkdir/mv actions.
            mkdir_done = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.function_name == "mkdir"
                and e.action.class_name == "VirtualFileSystem"
                and "/backups/alpha_backup" in e.action.args.get("path", "")
                for e in events
            )
            mv_done = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.function_name == "mv"
                and e.action.class_name == "VirtualFileSystem"
                and "/projects/alpha" in e.action.args.get("path1", "")
                and "/backups/alpha_backup" in e.action.args.get("path2", "")
                for e in events
            )
            user_notified = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "backed up" in (e.action.args.get("content", "").lower())
                for e in events
            )
            return ScenarioValidationResult(success=(mkdir_done and mv_done and user_notified))
        except Exception as err:
            return ScenarioValidationResult(success=False, exception=err)
