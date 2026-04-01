from __future__ import annotations

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.calendar import CalendarApp
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.sandbox_file_system import Files, SandboxLocalFileSystem
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("project_brainstorm_management")
class ProjectBrainstormManagement(Scenario):
    """Scenario: Agent aids user in organizing a brainstorming session.

    The agent extracts info from files, proposing event and reminders, awaiting user confirmation, and then executing corresponding actions
    using all available apps.
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize all apps and seed with data."""
        # Instantiate all available applications
        aui = AgentUserInterface()
        calendar = CalendarApp()
        reminder = ReminderApp()
        system = SystemApp(name="system")
        files = SandboxLocalFileSystem(sandbox_dir=kwargs.get("sandbox_dir"))

        # Prepare some folders and sample documents
        files.makedirs(path="projects/brainstorm", exist_ok=True)
        files.open(path="projects/brainstorm/agenda.txt", mode="wb")
        # Simulate content with text document
        with open(f"{kwargs.get('sandbox_dir')}/projects/brainstorm/agenda.txt", "w") as fh:
            fh.write("Ideas:\n- New marketing campaign\n- Website redesign plan\nMeeting suggestion: Monday 10 am\n")

        # Aggregate all apps for the environment
        self.apps = [aui, calendar, reminder, system, files]

    def build_events_flow(self) -> None:
        """Event flow defining user-agent interaction for the productivity setup scenario.

        Includes a proactive proposal pattern:
        1. Agent proposes scheduling and reminders.
        2. User approves specifically.
        3. Agent executes the scheduling and adds relevant reminders.
        """
        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(CalendarApp)
        reminder = self.get_typed_app(ReminderApp)
        files = self.get_typed_app(Files)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # Step 1: User greets assistant and asks to check brainstorming files
            user_msg = aui.send_message_to_agent(
                content="Hey assistant, please review the brainstorming files and suggest how to organize the prep work."
            ).depends_on(None, delay_seconds=1)

            # Step 2: Agent checks current time
            get_time = system.get_current_time().depends_on(user_msg, delay_seconds=1)

            # Step 3: Agent reads the brainstorming agenda document to understand content
            read_doc = files.read_document(file_path="projects/brainstorm/agenda.txt", max_lines=10).depends_on(
                get_time, delay_seconds=1
            )

            # Step 4: Agent proactively proposes an action to the user
            agent_propose_action = aui.send_message_to_user(
                content=(
                    "I found details suggesting a meeting for the new marketing campaign "
                    "on Monday at 10 am. Shall I go ahead and schedule a 'Brainstorm Planning' session "
                    "in your calendar and add reminders for preparation?"
                )
            ).depends_on(read_doc, delay_seconds=1)

            # Step 5: User replies with contextual approval
            user_approval = aui.send_message_to_agent(
                content="Yes, go ahead and organize the brainstorming meeting and prep reminders."
            ).depends_on(agent_propose_action, delay_seconds=1)

            # Step 6: Agent adds a calendar event after approval
            add_event = (
                calendar.add_calendar_event(
                    title="Brainstorm Planning Session",
                    start_datetime="1970-01-05 10:00:00",
                    end_datetime="1970-01-05 11:30:00",
                    tag="brainstorming",
                    description="Session to discuss new marketing campaign ideas and website redesign plan",
                    location="Conference Room A",
                    attendees=["Alex Green", "Jamie Lee"],
                )
                .oracle()
                .depends_on(user_approval, delay_seconds=1)
            )

            # Step 7: Agent adds reminders for each participant about prep tasks
            add_reminder = (
                reminder.add_reminder(
                    title="Prepare Brainstorm Materials",
                    due_datetime="1970-01-05 09:00:00",
                    description="Collect and review marketing and website redesign materials before the meeting.",
                    repetition_unit=None,
                )
                .oracle()
                .depends_on(add_event, delay_seconds=1)
            )

            # Step 8: Agent lists today's events to confirm addition
            list_today = calendar.read_today_calendar_events().depends_on(add_reminder, delay_seconds=1)

            # Step 9: Agent lists existing reminder(s) to confirm creation
            list_reminders = reminder.get_all_reminders().depends_on(list_today, delay_seconds=1)

            # Step 10: Agent informs user success
            confirm_msg = (
                aui.send_message_to_user(
                    content="I've scheduled the brainstorming session and set reminders for preparation. You're all set!"
                )
                .oracle()
                .depends_on(list_reminders, delay_seconds=1)
            )

            # Step 11: System waits for any upcoming notifications before scenario ends
            wait_notif = system.wait_for_notification(timeout=2).depends_on(confirm_msg, delay_seconds=1)

        self.events = [
            user_msg,
            get_time,
            read_doc,
            agent_propose_action,
            user_approval,
            add_event,
            add_reminder,
            list_today,
            list_reminders,
            confirm_msg,
            wait_notif,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Custom scenario validation to confirm that meeting and reminders were created and user notified."""
        try:
            events = env.event_log.list_view()

            event_added = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Brainstorm Planning" in e.action.args.get("title", "")
                for e in events
            )
            reminder_added = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ReminderApp"
                and e.action.function_name == "add_reminder"
                and "Prepare" in e.action.args.get("title", "")
                for e in events
            )
            user_notified = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "scheduled" in e.action.args.get("content", "").lower()
                for e in events
            )
            all_tools_used = event_added and reminder_added and user_notified
            return ScenarioValidationResult(success=all_tools_used)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
