from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.sandbox_file_system import Files, SandboxLocalFileSystem
from are.simulation.apps.system import SystemApp
from are.simulation.apps.virtual_file_system import VirtualFileSystem
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("storage_backup_proactive")
class StorageBackupProactive(Scenario):
    """Scenario: Demonstrates proactive file management across multiple storage systems.

    The agent checks sandbox files, copies data to a virtual file system, and creates backups using another file interface.
    Agent asks the user for permission before starting backup and sets a reminder after completion.
    """

    start_time: float | None = 0
    duration: float | None = 60

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize all available applications and prepopulate file systems."""
        aui = AgentUserInterface()
        system = SystemApp(name="system_controller")
        reminder = ReminderApp()
        sandbox_fs = SandboxLocalFileSystem(name="local_sandbox", sandbox_dir=kwargs.get("sandbox_dir"))
        virtual_fs = VirtualFileSystem(name="vfs_runtime")
        aux_files = Files(name="auxiliary_files", sandbox_dir=kwargs.get("sandbox_dir"))

        # Prepare file structures and content
        sandbox_fs.makedirs(path="project_data/reports", exist_ok=True)
        virtual_fs.mkdir(path="/cloud/backup", create_recursive=True)
        aux_files.makedirs(path="archive_logs", exist_ok=True)

        # In sandbox: simulate documents for user
        sandbox_fs.open(path="project_data/reports/summary.txt", mode="w")
        sandbox_fs.open(path="project_data/reports/design.docx", mode="w")
        sandbox_fs.open(path="project_data/config.yaml", mode="w")

        self.apps = [aui, system, reminder, sandbox_fs, virtual_fs, aux_files]

    def build_events_flow(self) -> None:
        """Construct the event flow: proactive prompt + user confirmation + backup workflow."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        reminder = self.get_typed_app(ReminderApp)
        sandbox_fs = self.get_typed_app(SandboxLocalFileSystem)
        virtual_fs = self.get_typed_app(VirtualFileSystem)
        files = self.get_typed_app(Files)

        with EventRegisterer.capture_mode():
            # Step 1: User asks the assistant to manage file backups
            user_request = aui.send_message_to_agent(
                content="I'd like you to manage my local project files and back them up somewhere safe."
            ).depends_on(None, delay_seconds=1)

            # Step 2: Agent checks current time for scheduling
            agent_time_check = system.get_current_time().depends_on(user_request, delay_seconds=1)

            # Step 3: Agent lists sandbox contents to inspect project folder
            sandbox_listing = sandbox_fs.ls(path="project_data", detail=True).depends_on(
                agent_time_check, delay_seconds=1
            )

            # Step 4: Agent requests user permission to back up all reports to the virtual system
            agent_propose = aui.send_message_to_user(
                content="I found the project files under 'project_data'. Would you like me to back them up to the cloud now?"
            ).depends_on(sandbox_listing, delay_seconds=1)

            # Step 5: User confirms the backup action
            user_response = aui.send_message_to_agent(
                content="Yes, please go ahead and create the backup now."
            ).depends_on(agent_propose, delay_seconds=2)

            # Step 6: Create a new directory in the VirtualFileSystem and move files
            create_backup_dir = virtual_fs.mkdir(path="/cloud/backup/project", create_recursive=True).depends_on(
                user_response, delay_seconds=1
            )

            move_reports = sandbox_fs.mv(
                path1="project_data/reports", path2="backup/tmp_reports", recursive=True
            ).depends_on(create_backup_dir, delay_seconds=2)

            # Step 7: Copy or simulate archive creation via Files app
            aux_copy = files.mv(path1="archive_logs", path2="archive_logs_backup", recursive=True).depends_on(
                move_reports, delay_seconds=1
            )

            # Step 8: Agent adds a reminder about storage cleanup after backup
            now_time = "1970-01-01 00:00:00"
            reminder_add = reminder.add_reminder(
                title="Cloud storage cleanup",
                due_datetime=now_time,
                description="Review and clean unnecessary files in backup storage.",
                repetition_unit=None,
            ).depends_on(aux_copy, delay_seconds=1)

            # Step 9: Agent notifies user that backup and reminder setup are complete
            agent_notify_done = (
                aui.send_message_to_user(
                    content="Backup completed successfully, and I've set a reminder for later cleanup."
                )
                .oracle()
                .depends_on(reminder_add, delay_seconds=1)
            )

        self.events = [
            user_request,
            agent_time_check,
            sandbox_listing,
            agent_propose,
            user_response,
            create_backup_dir,
            move_reports,
            aux_copy,
            reminder_add,
            agent_notify_done,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that backup operations and reminder creation were completed."""
        try:
            events = env.event_log.list_view()
            # Ensure proactive dialogue took place
            propose_present = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "AgentUserInterface"
                and "back them up" in event.action.args.get("content", "").lower()
                for event in events
            )

            # Validate that reminder has been added
            reminder_created = any(
                event.event_type == EventType.APP
                and isinstance(event.action, Action)
                and event.action.class_name == "ReminderApp"
                and event.action.function_name == "add_reminder"
                for event in events
            )

            # Ensure file operations across Sandbox and VirtualFS occurred
            sandbox_mv = any(
                event.event_type == EventType.APP
                and event.action.class_name == "SandboxLocalFileSystem"
                and event.action.function_name == "mv"
                for event in events
            )
            vfs_creation = any(
                event.event_type == EventType.APP
                and event.action.class_name == "VirtualFileSystem"
                and event.action.function_name == "mkdir"
                for event in events
            )

            all_conditions = propose_present and reminder_created and sandbox_mv and vfs_creation
            return ScenarioValidationResult(success=all_conditions)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
