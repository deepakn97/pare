from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.sandbox_file_system import Files
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("office_report_review_and_archive")
class OfficeReportReviewAndArchive(Scenario):
    """Scenario where an agent handles office reports.

    The workflow includes:
    1. The system logs the current time.
    2. The agent reads a report document from a folder.
    3. The agent proactively offers to archive it for the user.
    4. Upon user approval, the agent creates an archive directory and moves the file.
    5. The agent validates that the file exists in the right place afterward.
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate apps with sandbox content."""
        # Instantiate the applications we will use
        aui = AgentUserInterface()
        system = SystemApp(name="system")
        fs = Files(name="docs_fs", sandbox_dir=kwargs.get("sandbox_dir"))

        # Prepare document folders
        fs.makedirs(path="team_reports", exist_ok=True)
        fs.makedirs(path="archive", exist_ok=True)

        # Populate a report document
        report_file = "team_reports/Q4_financial_report.txt"
        fs.open(path=report_file, mode="w", kwargs={})
        # Write simulated text content
        with open(fs.sandbox_dir + "/" + report_file, "w") as f:
            f.write("Quarter 4 Financial Report\nRevenue Growth: 18%\nNet Profit: 12%")

        self.apps = [aui, system, fs]

    def build_events_flow(self) -> None:
        """Build the sequence of events, including a proactive agent-user interaction."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        fs = self.get_typed_app(Files)

        with EventRegisterer.capture_mode():
            # User triggers the workflow
            event0 = aui.send_message_to_agent(
                content="Can you show me the contents of the Q4 report and suggest what to do next?"
            ).depends_on(None, delay_seconds=1)

            # System logs current time
            sys_time = system.get_current_time().depends_on(event0, delay_seconds=1)

            # Agent reads the document content
            read_report = fs.read_document(file_path="team_reports/Q4_financial_report.txt", max_lines=10).depends_on(
                sys_time, delay_seconds=1
            )

            # Agent proactively proposes archiving after reading
            propose_archive = aui.send_message_to_user(
                content="I've reviewed the Q4 Financial Report. Would you like me to archive it in the 'archive' directory for record keeping?"
            ).depends_on(read_report, delay_seconds=1)

            # User approves the action
            user_approval = aui.send_message_to_agent(
                content="Yes, please move the report into the archive folder so it's properly stored."
            ).depends_on(propose_archive, delay_seconds=1)

            # Agent creates the folder if needed
            create_archive_dir = fs.mkdir(path="archive", create_parents=True).depends_on(
                user_approval, delay_seconds=1
            )

            # Agent moves the file into archive
            archive_action = (
                fs.mv(
                    path1="team_reports/Q4_financial_report.txt",
                    path2="archive/Q4_financial_report.txt",
                    recursive=False,
                )
                .oracle()
                .depends_on(create_archive_dir, delay_seconds=1)
            )

            # Agent confirms the operation back to the user
            confirm_action = aui.send_message_to_user(
                content="The Q4 Financial Report has been successfully archived."
            ).depends_on(archive_action, delay_seconds=1)

            # Agent waits for any further notification or timeout (demonstrate system waiting)
            wait_close = system.wait_for_notification(timeout=5).depends_on(confirm_action, delay_seconds=1)

        self.events = [
            event0,
            sys_time,
            read_report,
            propose_archive,
            user_approval,
            create_archive_dir,
            archive_action,
            confirm_action,
            wait_close,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Check if the report has been archived and notifications occurred."""
        try:
            events = env.event_log.list_view()
            # Verify the file was moved
            moved_file_action = any(
                evt.event_type == EventType.AGENT
                and isinstance(evt.action, Action)
                and evt.action.class_name == "Files"
                and evt.action.function_name == "mv"
                and evt.action.args["path1"] == "team_reports/Q4_financial_report.txt"
                and evt.action.args["path2"] == "archive/Q4_financial_report.txt"
                for evt in events
            )

            # Verify the agent proposed before acting
            proposed_step = any(
                evt.event_type == EventType.AGENT
                and isinstance(evt.action, Action)
                and evt.action.class_name == "AgentUserInterface"
                and evt.action.function_name == "send_message_to_user"
                and "archive" in evt.action.args.get("content", "").lower()
                for evt in events
            )

            # Verify confirmation message was sent
            confirmation_sent = any(
                evt.event_type == EventType.AGENT
                and isinstance(evt.action, Action)
                and evt.action.class_name == "AgentUserInterface"
                and evt.action.function_name == "send_message_to_user"
                and "successfully archived" in evt.action.args.get("content", "").lower()
                for evt in events
            )

            return ScenarioValidationResult(success=(moved_file_action and proposed_step and confirmation_sent))
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
