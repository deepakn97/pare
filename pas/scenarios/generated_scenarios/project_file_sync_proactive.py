from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.sandbox_file_system import Files, SandboxLocalFileSystem
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer


@register_scenario("project_file_sync_proactive")
class ProjectFileSyncProactive(Scenario):
    """A scenario demonstrating file synchronization between a local sandbox and a mounted file system.

    Coordinated through user confirmation and proactive agent behavior.

    The workflow includes:
    - The agent checking system time and file structure
    - Reading and displaying local project information
    - Proactively suggesting a synchronization action between sandbox and Files storage
    - Executing the sync upon user approval

    All available applications (AgentUserInterface, SandboxLocalFileSystem, Files, SystemApp)
    are used across the flow.
    """

    start_time: float | None = 0
    duration: float | None = 40

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize environment and populate filesystems with directory structures and files."""
        aui = AgentUserInterface()
        sandbox_fs = SandboxLocalFileSystem(
            name="sandbox_fs",
            sandbox_dir=kwargs.get("sandbox_dir"),
            state_directory="/tmp/sandbox_state",  # noqa: S108
        )
        files_fs = Files(name="cloud_drive", sandbox_dir="/tmp/files_state")  # noqa: S108
        sys_app = SystemApp(name="core_system")

        # Prepopulate sandbox with a 'project' folder containing temporary design files
        sandbox_fs.makedirs(path="/sandbox/projects/alpha_design", exist_ok=True)
        sandbox_fs.makedirs(path="/sandbox/projects/beta_notes", exist_ok=True)

        # Simulate some dummy files in sandbox (would exist on agent's drive)
        sandbox_fs.open(
            path="/sandbox/projects/alpha_design/spec_summary.txt", mode="wb", kwargs={"data": b"Initial design spec"}
        )
        sandbox_fs.open(
            path="/sandbox/projects/alpha_design/report_draft.md",
            mode="wb",
            kwargs={"data": b"Beta draft pending approval"},
        )

        # Prepare remote Files system minimal structure
        files_fs.makedirs(path="/cloud/archives", exist_ok=True)
        files_fs.makedirs(path="/cloud/synced_projects", exist_ok=True)

        # Register all apps for this scenario
        self.apps = [aui, sandbox_fs, files_fs, sys_app]

    def build_events_flow(self) -> None:
        """Define the event flow: agent proposes a proactive file sync, waits for user confirmation, then executes transfer."""
        aui = self.get_typed_app(AgentUserInterface)
        sandbox_fs = self.get_typed_app(SandboxLocalFileSystem)
        files_fs = self.get_typed_app(Files)
        sys_app = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # User message to start the process
            user_start = (
                aui.send_message_to_agent(content="Let's make sure my latest project reports are backed up properly.")
                .depends_on(None, delay_seconds=1)
                .with_id("user_start")
            )

            # System: fetch the current time for logging
            current_time = sys_app.get_current_time().depends_on(user_start, delay_seconds=1)

            # Agent: inspect local file structure
            sandbox_tree = sandbox_fs.tree(path="/sandbox/projects").depends_on(current_time, delay_seconds=1)

            # Agent proposes an action to the user (MANDATORY proactive pattern)
            propose_sync = (
                aui.send_message_to_user(
                    content=(
                        "I found 'alpha_design' and 'beta_notes' in your sandbox. "
                        "Would you like me to synchronize them to your `/cloud/synced_projects` folder now?"
                    )
                )
                .depends_on(sandbox_tree, delay_seconds=1)
                .with_id("agent_propose_sync")
            )

            # User approves the proposed sync action
            user_approve = (
                aui.send_message_to_agent(
                    content="Yes, please go ahead and sync both project folders to the cloud drive."
                )
                .depends_on(propose_sync, delay_seconds=1)
                .with_id("user_approval")
            )

            # Agent performs synchronization - moves/copies the relevant directory
            sandbox_info = sandbox_fs.info(path="/sandbox/projects/alpha_design").depends_on(
                user_approve, delay_seconds=1
            )

            # Agent performs move in the Files system (oracle truth)
            sync_transfer_oracle = (
                files_fs.mv(
                    path1="/sandbox/projects/alpha_design",
                    path2="/cloud/synced_projects/alpha_design_backup",
                    recursive=True,
                )
                .oracle()
                .depends_on(sandbox_info, delay_seconds=2)
            )

            # System waits before next sync confirmation
            system_pause = sys_app.wait_for_notification(timeout=2).depends_on(sync_transfer_oracle, delay_seconds=1)

            # Agent displays confirmation to user
            report_back = (
                aui.send_message_to_user(
                    content="The `alpha_design` project has been securely synced to your cloud drive."
                )
                .depends_on(system_pause, delay_seconds=1)
                .oracle()
            )

        self.events = [
            user_start,
            current_time,
            sandbox_tree,
            propose_sync,
            user_approve,
            sandbox_info,
            sync_transfer_oracle,
            system_pause,
            report_back,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the sync was proposed, approved, performed, and confirmed properly."""
        try:
            actions = [e for e in env.event_log.list_view() if isinstance(e.action, Action)]

            # Verify agent proposed synchronization and got approval
            proposal_event = any(
                a.action.function_name == "send_message_to_user" and "sync" in a.action.args.get("content", "").lower()
                for a in actions
            )
            approval_event = any(
                a.action.function_name == "send_message_to_agent" and "sync" in a.action.args.get("content", "").lower()
                for a in actions
            )

            # Verify the file move operation was executed correctly
            sync_performed = any(
                a.action.class_name == "Files"
                and a.action.function_name == "mv"
                and "/cloud/synced_projects/alpha_design_backup" in a.action.args.get("path2", "")
                for a in actions
            )

            # Agent should confirm completion to user
            confirmation_msg = any(
                a.action.class_name == "AgentUserInterface"
                and a.action.function_name == "send_message_to_user"
                and "synced" in a.action.args.get("content", "").lower()
                for a in actions
            )

            success = proposal_event and approval_event and sync_performed and confirmation_msg
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
