from __future__ import annotations

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.sandbox_file_system import Files, SandboxLocalFileSystem
from are.simulation.apps.system import SystemApp
from are.simulation.apps.virtual_file_system import VirtualFileSystem
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("secure_doc_sync")
class SecureDocumentSync(Scenario):
    """Secure document synchronization scenario across multiple file systems with calendar-linked version control.

    This scenario simulates a secure document workflow where:
    - The agent detects a newly uploaded report in a sandbox file system.
    - The agent proposes to archive it into a virtual file system and schedule a version review reminder.
    - The user approves the action.
    - The agent then archives the document, creates a version tracking event in the calendar,
      and organizes directories in both the sandbox and shared file contexts.
    """

    start_time: float | None = 0
    duration: float | None = 24

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and populate all available applications."""
        # Initialize all applications required by scenario
        self.aui = AgentUserInterface()
        self.calendar = CalendarApp()
        self.system = SystemApp(name="system")
        self.local_fs = SandboxLocalFileSystem(name="sandbox_fs", sandbox_dir=kwargs.get("sandbox_dir"))
        self.shared_fs = Files(name="files_fs", sandbox_dir=kwargs.get("sandbox_dir"))
        self.virtual_fs = VirtualFileSystem(name="vfs")

        # Populate the file systems with initial directories and placeholder files
        self.local_fs.makedirs(path="reports/current", exist_ok=True)
        self.local_fs.mkdirs = self.local_fs.makedirs  # alias pattern in some examples
        self.local_fs.mkdir(path="archives", create_parents=True)
        self.shared_fs.makedirs(path="shared/team_docs", exist_ok=True)
        self.virtual_fs.mkdir(path="/secure_archive", create_recursive=True)

        # Add a placeholder document file to sandbox local file system
        # Simulate the presence of a newly generated report to trigger the interaction
        self.local_fs.open(path="reports/current/monthly_summary.docx", mode="wb")

        # Register all apps
        self.apps = [self.aui, self.calendar, self.system, self.local_fs, self.shared_fs, self.virtual_fs]

    def build_events_flow(self) -> None:
        """Construct the event flow including the proactive interaction pattern."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        calendar = self.get_typed_app(CalendarApp)
        sandbox_fs = self.get_typed_app(SandboxLocalFileSystem)
        virtual_fs = self.get_typed_app(VirtualFileSystem)
        shared_fs = self.get_typed_app(Files)

        with EventRegisterer.capture_mode():
            # User notifies the agent that a new report has been generated
            event0 = aui.send_message_to_agent(
                content="Hi Assistant, a new financial report has been saved in the sandbox under reports/current. Please manage it securely."
            ).depends_on(None, delay_seconds=1)

            # Agent checks system time before making a decision
            event1 = system.get_current_time().depends_on(event0, delay_seconds=1)

            # Agent proposes proactive action to archive & schedule
            proposal = aui.send_message_to_user(
                content=(
                    "I noticed the 'monthly_summary.docx' in reports/current. "
                    "Would you like me to archive this document securely in the virtual file system "
                    "and schedule a review meeting next Monday?"
                )
            ).depends_on(event1, delay_seconds=1)

            # User confirms the proposed proactive action
            confirmation = aui.send_message_to_agent(
                content="Yes, go ahead and move it to secure archive and set that review meeting."
            ).depends_on(proposal, delay_seconds=1)

            # Agent moves the file into virtual secure archive after confirmation
            move_to_secure = (
                virtual_fs.mv(
                    path1="/sandbox/reports/current/monthly_summary.docx",
                    path2="/secure_archive/monthly_summary_v1.docx",
                )
                .oracle()
                .depends_on(confirmation, delay_seconds=1)
            )

            # Agent also creates a shared folder for the team in sandbox filesystem (example of FS manipulation)
            create_team_dir = (
                sandbox_fs.mkdir(path="team_share", create_parents=True)
                .oracle()
                .depends_on(move_to_secure, delay_seconds=0)
            )

            # Agent adds a new calendar event for version review
            event3 = (
                calendar.add_calendar_event(
                    title="Report Version Review",
                    start_datetime="2024-05-06 10:00:00",
                    end_datetime="2024-05-06 10:30:00",
                    tag="version_control",
                    description="Team review for version v1 of monthly_summary.docx archived securely.",
                    location="Online Meeting",
                    attendees=["Finance Team"],
                )
                .oracle()
                .depends_on(create_team_dir, delay_seconds=1)
            )

            # Agent creates a corresponding directory on shared filesystem as backup copy
            event4 = (
                shared_fs.makedirs(path="shared/backups/reports", exist_ok=True)
                .oracle()
                .depends_on(event3, delay_seconds=0)
            )

            # Agent waits for acknowledgment or next user instruction
            idle_wait = system.wait_for_notification(timeout=3).depends_on(event4, delay_seconds=0)

        self.events = [
            event0,
            event1,
            proposal,
            confirmation,
            move_to_secure,
            create_team_dir,
            event3,
            event4,
            idle_wait,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate the outcome of the scenario workflow."""
        try:
            events = env.event_log.list_view()

            # Check if the proactive message was sent by agent
            proactive_message = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.function_name == "send_message_to_user"
                and "securely" in event.action.args.get("content", "").lower()
                for event in events
            )

            # Check if user confirmation was captured
            user_confirmation = any(
                event.event_type == EventType.USER
                and isinstance(event.action, Action)
                and "secure archive" in event.action.args.get("content", "").lower()
                for event in events
            )

            # Check if the file move action occurred in virtual file system
            moved_file = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "VirtualFileSystem"
                and event.action.function_name == "mv"
                and "/secure_archive/" in str(event.action.args.get("path2", ""))
                for event in events
            )

            # Check if a calendar event was created with correct title and tag
            calendar_event_created = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "CalendarApp"
                and event.action.function_name == "add_calendar_event"
                and "Report Version Review" in event.action.args.get("title", "")
                and event.action.args.get("tag", "") == "version_control"
                for event in events
            )

            success = proactive_message and user_confirmation and moved_file and calendar_event_created
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
