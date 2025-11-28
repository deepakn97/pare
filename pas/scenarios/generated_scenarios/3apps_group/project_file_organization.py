from __future__ import annotations

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.sandbox_file_system import SandboxLocalFileSystem
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("project_file_organization")
class ProjectFileOrganization(Scenario):
    """Proactive file organization scenario involving user confirmation and full app ecosystem usage.

    The objective:
    The agent detects unorganized project files in the sandbox file system,
    asks the user whether to organize them into a clean project folder,
    and upon approval, creates directories, moves files, and displays the result.

    This demonstrates use of:
    - AgentUserInterface for proactive confirmation and notification
    - SandboxLocalFileSystem for all file operations (list, mkdir, mv, info, display)
    - SystemApp for time and simulated waiting operations
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize the apps with sample unorganized files."""
        # Initialize applications
        aui = AgentUserInterface()
        fs = SandboxLocalFileSystem(name="local_fs", sandbox_dir=kwargs.get("sandbox_dir"))
        system = SystemApp(name="system_app")

        # Create base unorganized directory with mixed files
        fs.makedirs("Downloads", exist_ok=True)
        # Create dummy files for project content
        fs.open("Downloads/plan.txt", mode="wb", kwargs={})
        fs.open("Downloads/design.png", mode="wb", kwargs={})
        fs.open("Downloads/data.csv", mode="wb", kwargs={})
        # Create an unrelated file somewhere else
        fs.makedirs("Misc", exist_ok=True)
        fs.open("Misc/old_notes.docx", mode="wb", kwargs={})

        self.apps = [aui, fs, system]

    def build_events_flow(self) -> None:
        """Construct the oracle events flow."""
        aui = self.get_typed_app(AgentUserInterface)
        fs = self.get_typed_app(SandboxLocalFileSystem)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # 1. User begins scenario
            user_start = aui.send_message_to_agent(
                content="Hi, please check if my project files in the Downloads folder are properly organized."
            ).depends_on(None, delay_seconds=1)

            # 2. Agent checks current time to timestamp the organization
            get_time = system.get_current_time().depends_on(user_start, delay_seconds=1)

            # 3. Agent inspects the directory tree
            tree_snapshot = fs.tree(path="Downloads").depends_on(get_time, delay_seconds=1)

            # 4. Agent proposes to user a cleanup/organization action
            propose_action = aui.send_message_to_user(
                content=(
                    "I found several unorganized project files in 'Downloads'. "
                    "Would you like me to create a 'Project_Archive' folder with subfolders "
                    "for documents, images, and data, and move these files there?"
                )
            ).depends_on(tree_snapshot, delay_seconds=1)

            # 5. User approves with explicit consent
            user_approval = aui.send_message_to_agent(
                content="Yes, please go ahead and create the Project_Archive folder and move the files accordingly."
            ).depends_on(propose_action, delay_seconds=1)

            # 6. Agent performs organization if approved:
            # create project structure
            mkdir_root = (
                fs.mkdir(path="Project_Archive", create_parents=True)
                .oracle()
                .depends_on(user_approval, delay_seconds=1)
            )
            mkdir_docs = (
                fs.mkdir(path="Project_Archive/docs", create_parents=True)
                .oracle()
                .depends_on(mkdir_root, delay_seconds=1)
            )
            mkdir_images = (
                fs.mkdir(path="Project_Archive/images", create_parents=True)
                .oracle()
                .depends_on(mkdir_docs, delay_seconds=1)
            )
            mkdir_data = (
                fs.mkdir(path="Project_Archive/data", create_parents=True)
                .oracle()
                .depends_on(mkdir_images, delay_seconds=1)
            )

            # 7. Move files appropriately
            mv_plan = (
                fs.mv(path1="Downloads/plan.txt", path2="Project_Archive/docs/plan.txt")
                .oracle()
                .depends_on(mkdir_data, delay_seconds=1)
            )
            mv_design = (
                fs.mv(path1="Downloads/design.png", path2="Project_Archive/images/design.png")
                .oracle()
                .depends_on(mv_plan, delay_seconds=1)
            )
            mv_data = (
                fs.mv(path1="Downloads/data.csv", path2="Project_Archive/data/data.csv")
                .oracle()
                .depends_on(mv_design, delay_seconds=1)
            )

            # 8. Wait a bit for completion confirmation
            wait_sync = system.wait_for_notification(timeout=2).depends_on(mv_data, delay_seconds=1)

            # 9. Display organized file tree results to user
            display_tree = fs.display(path="Project_Archive").oracle().depends_on(wait_sync, delay_seconds=1)

            # 10. Agent notifies user that task is done, with timestamp from earlier
            notify_complete = (
                aui.send_message_to_user(
                    content="All project files have been successfully organized into 'Project_Archive'."
                )
                .oracle()
                .depends_on(display_tree, delay_seconds=1)
            )

        self.events = [
            user_start,
            get_time,
            tree_snapshot,
            propose_action,
            user_approval,
            mkdir_root,
            mkdir_docs,
            mkdir_images,
            mkdir_data,
            mv_plan,
            mv_design,
            mv_data,
            wait_sync,
            display_tree,
            notify_complete,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the files were organized and the user was notified."""
        try:
            events = env.event_log.list_view()

            # check for folder creation actions
            made_folders = [
                ev
                for ev in events
                if ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "SandboxLocalFileSystem"
                and ev.action.function_name == "mkdir"
                and "Project_Archive" in ev.action.args["path"]
            ]
            # files moved correctly
            moved_files = [
                ev
                for ev in events
                if ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "SandboxLocalFileSystem"
                and ev.action.function_name == "mv"
                and "Project_Archive" in ev.action.args["path2"]
            ]
            # user got final confirmation
            user_notified = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "AgentUserInterface"
                and ev.action.function_name == "send_message_to_user"
                and "organized" in ev.action.args["content"].lower()
                for ev in events
            )

            success = bool(made_folders and moved_files and user_notified)
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
