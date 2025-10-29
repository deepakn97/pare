from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.sandbox_file_system import Files
from are.simulation.apps.system import SystemApp
from are.simulation.apps.virtual_file_system import VirtualFileSystem
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("dual_storage_sync_confirmation")
class DualStorageSyncConfirmation(Scenario):
    """Scenario: Demonstrates a dual-storage mirroring workflow.

    The Assistant helps the user synchronize folders between local (Files)
    and virtual (VirtualFileSystem) directories, asking for confirmation
    before proceeding.

    Apps used:
    - AgentUserInterface (interaction)
    - SystemApp (for current time and waiting)
    - Files (representing local/sandboxed storage)
    - VirtualFileSystem (representing cloud/remote storage)
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and populate the environment."""
        aui = AgentUserInterface()
        system = SystemApp(name="sys_ops")
        vfs = VirtualFileSystem(name="vremote")
        fstore = Files(name="localfiles", sandbox_dir=kwargs.get("sandbox_dir"))

        # Prepare base environment: simulate existing local folder with subfiles
        fstore.makedirs(path="projects/demo_local", exist_ok=True)
        fstore.open(path="projects/demo_local/notes.txt", mode="w")
        fstore.open(path="projects/demo_local/todo.md", mode="w")
        fstore.mkdir(path="projects/demo_local/assets", create_parents=True)
        fstore.open(path="projects/demo_local/assets/logo.png", mode="w")

        # Prepare VFS to mirror later
        vfs.mkdir(path="/mirror_zone", create_recursive=True)

        self.apps = [aui, system, vfs, fstore]

    def build_events_flow(self) -> None:
        """Build the sequence of scenario events."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        vfs = self.get_typed_app(VirtualFileSystem)
        fstore = self.get_typed_app(Files)

        with EventRegisterer.capture_mode():
            # 0. User asks agent to prepare synchronization plan.
            user_request = aui.send_message_to_agent(
                content="Hey assistant, I want to sync my local 'projects/demo_local' directory to the virtual system."
            ).depends_on(None, delay_seconds=1)

            # 1. Agent calls system time to timestamp sync session
            time_check = system.get_current_time().depends_on(user_request, delay_seconds=1)

            # 2. Agent lists all files locally to preview what will be synced
            scan_local = fstore.ls(path="projects/demo_local", detail=True).depends_on(time_check, delay_seconds=1)

            # 3. Agent asks user for confirmation to start mirroring (proactive proposal)
            proposal_msg = aui.send_message_to_user(
                content="I found 'notes.txt', 'todo.md', and an 'assets' folder inside 'projects/demo_local'. "
                "Would you like me to create a matching structure in the Virtual File System under '/mirror_zone/demo_local'?"
            ).depends_on(scan_local, delay_seconds=1)

            # 4. User confirms with contextual approval (proactive pattern)
            user_confirm = aui.send_message_to_agent(
                content="Yes, please go ahead and mirror it under '/mirror_zone/demo_local'."
            ).depends_on(proposal_msg, delay_seconds=1)

            # 5. Agent performs creation actions on VirtualFileSystem (oracle: expected correct execution)
            mk_root = (
                vfs.mkdir(path="/mirror_zone/demo_local", create_recursive=True)
                .oracle()
                .depends_on(user_confirm, delay_seconds=1)
            )
            mk_sub = (
                vfs.mkdir(path="/mirror_zone/demo_local/assets", create_recursive=True)
                .oracle()
                .depends_on(mk_root, delay_seconds=1)
            )

            # 6. Agent displays summary of file listing for the user after completion
            show_tree = fstore.tree(path="projects").depends_on(mk_sub, delay_seconds=1)
            confirm_msg = aui.send_message_to_user(
                content="Mirroring completed successfully. Both FileSystem and VirtualFileSystem are now in sync."
            ).depends_on(show_tree, delay_seconds=1)

            # 7. Wait for idle notification (simulates post-operation system state)
            _wait = system.wait_for_notification(timeout=2).depends_on(confirm_msg, delay_seconds=1)

        self.events = [
            user_request,
            time_check,
            scan_local,
            proposal_msg,
            user_confirm,
            mk_root,
            mk_sub,
            show_tree,
            confirm_msg,
            _wait,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the agent executed mirroring correctly."""
        try:
            events = env.event_log.list_view()
            # Check if VirtualFileSystem mkdir for correct destination was executed
            dir_created = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "VirtualFileSystem"
                and event.action.function_name == "mkdir"
                and "/mirror_zone/demo_local" in event.action.args["path"]
                for event in events
            )

            # Confirm that user was asked proactively before syncing
            proposal_sent = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "AgentUserInterface"
                and "Would you like me to create a matching structure" in event.action.args.get("content", "")
                for event in events
            )

            # Check that user confirmation exists
            user_confirmed = any(
                event.event_type == EventType.USER
                and isinstance(event.action, Action)
                and event.action.class_name == "AgentUserInterface"
                and "mirror" in event.action.args.get("content", "").lower()
                for event in events
            )

            # Verify final message acknowledging success was sent
            summary_message = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.function_name == "send_message_to_user"
                and "mirroring completed" in event.action.args.get("content", "").lower()
                for event in events
            )

            success = dir_created and proposal_sent and user_confirmed and summary_message
            return ScenarioValidationResult(success=success)
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
