from __future__ import annotations

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.sandbox_file_system import SandboxLocalFileSystem
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("team_report_summary_and_meeting")
class TeamReportSummaryAndMeeting(Scenario):
    """Scenario: A collaborative team workflow where the assistant helps coordinate report sharing and a follow-up meeting.

    Flow overview:
    1. The user asks the assistant to check the new project report.
    2. A teammate (Sophia) sends a summary file via message.
    3. The assistant proactively suggests sharing the file and scheduling a review meeting with another teammate (Daniel).
    4. The user confirms.
    5. The assistant creates a meeting in the calendar and shares the file.
    6. Validation checks that the correct actions were taken.

    This scenario demonstrates a multi-app ecosystem integration:
    - **Files**: Filesystem organization and displaying contents.
    - **ContactsApp**: Contact creation and management.
    - **MessagingApp**: Message exchanges and attachments.
    - **CalendarApp**: Scheduling a follow-up meeting.
    - **AgentUserInterface**: Communication with the user.
    - **SystemApp**: Gets current time for scheduling logic.
    """

    start_time: float | None = 0
    duration: float | None = 22

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and populate apps with realistic test data."""
        aui = AgentUserInterface()
        fs = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))
        contacts = ContactsApp()
        messaging = MessagingApp()
        calendar = CalendarApp()
        system = SystemApp()

        # Set up a reports directory
        fs.makedirs(path="Reports", exist_ok=True)

        # Create a test file: report summary text
        fs.open(path="Reports/project_summary.txt", mode="wb")
        # It's enough to mark file existence; content can be fetched later.

        # Add contacts
        contacts.add_new_contact(
            first_name="Sophia",
            last_name="Miller",
            gender=Gender.FEMALE,
            status=Status.EMPLOYED,
            job="Project Analyst",
            email="sophia.miller@company.com",
            city_living="Berlin",
            country="Germany",
        )
        contacts.add_new_contact(
            first_name="Daniel",
            last_name="Nguyen",
            gender=Gender.MALE,
            status=Status.EMPLOYED,
            job="Engineering Lead",
            email="daniel.nguyen@company.com",
            city_living="Munich",
            country="Germany",
        )

        # Initialize active conversation between user and Sophia
        conv_sophia = messaging.create_conversation(participants=["Sophia Miller"], title="Project Report Discussion")

        # Store in state
        self.apps = [aui, fs, contacts, messaging, calendar, system]
        self._conv_sophia_id = conv_sophia

    def build_events_flow(self) -> None:
        """Define proactive communication sequence and execution flow."""
        aui = self.get_typed_app(AgentUserInterface)
        messaging = self.get_typed_app(MessagingApp)
        files = self.get_typed_app(SandboxLocalFileSystem)
        contacts = self.get_typed_app(ContactsApp)
        calendar = self.get_typed_app(CalendarApp)
        system = self.get_typed_app(SystemApp)

        conversation_id = self._conv_sophia_id

        with EventRegisterer.capture_mode():
            # User starts the interaction
            user_start = aui.send_message_to_agent(
                content="Assistant, please help coordinate the new project report sharing and planning a review with Daniel."
            ).depends_on(None, delay_seconds=1)

            # Sophia sends summary file
            sophia_msg = messaging.send_attachment(
                conversation_id=conversation_id, filepath="Reports/project_summary.txt"
            ).depends_on(user_start, delay_seconds=2)

            # Agent reads file contents for preparation
            read_file = files.read_document(file_path="Reports/project_summary.txt", max_lines=5).depends_on(
                sophia_msg, delay_seconds=1
            )

            # Agent proactively proposes sharing and scheduling
            propose_share = aui.send_message_to_user(
                content="Sophia just sent the report summary. Would you like me to share it with Daniel and arrange a quick review meeting for tomorrow morning?"
            ).depends_on(read_file, delay_seconds=1)

            # User approves the plan
            user_approval = aui.send_message_to_agent(
                content="Yes, go ahead and share it with Daniel and set the meeting for 10 AM."
            ).depends_on(propose_share, delay_seconds=1)

            # Create meeting event in calendar upon approval
            current_time = system.get_current_time()
            meeting_event = (
                calendar.add_calendar_event(
                    title="Project Report Review",
                    start_datetime="1970-01-02 10:00:00",
                    end_datetime="1970-01-02 11:00:00",
                    tag="project",
                    location="Conference Room A",
                    description="Review of the updated project summary with Daniel and Sophia.",
                    attendees=["Sophia Miller", "Daniel Nguyen"],
                )
                .oracle()
                .depends_on(user_approval, delay_seconds=1)
            )

            # Agent shares file with Daniel over message
            create_conv_daniel = messaging.create_conversation(
                participants=["Daniel Nguyen"], title="Project Report Review Prep"
            ).depends_on(user_approval, delay_seconds=1)

            send_file_daniel = (
                messaging.send_attachment(conversation_id=create_conv_daniel, filepath="Reports/project_summary.txt")
                .oracle()
                .depends_on(create_conv_daniel, delay_seconds=1)
            )

        self.events = [
            user_start,
            sophia_msg,
            read_file,
            propose_share,
            user_approval,
            meeting_event,
            create_conv_daniel,
            send_file_daniel,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Check that the assistant successfully created a meeting and shared the file based on user approval."""
        try:
            events = env.event_log.list_view()
            # Validate proactive communication and corresponding actions
            user_asked = any(
                e.event_type == EventType.USER and "coordinate" in e.content.lower()
                for e in events
                if hasattr(e, "content")
            )
            proposed_action = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "would you like me" in e.action.args["content"].lower()
                for e in events
            )
            meeting_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Daniel Nguyen" in str(e.action.args.get("attendees", []))
                and "Project Report Review" in str(e.action.args.get("title", ""))
                for e in events
            )
            file_shared = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "MessagingApp"
                and e.action.function_name == "send_attachment"
                and "project_summary.txt" in e.action.args.get("filepath", "")
                for e in events
            )

            return ScenarioValidationResult(
                success=(user_asked and proposed_action and meeting_created and file_shared)
            )
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
