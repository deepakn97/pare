from __future__ import annotations

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("daily_task_planner_proactive")
class DailyTaskPlannerProactive(Scenario):
    """A scenario where the agent helps the user organize daily tasks using reminders.

    The flow demonstrates:
    - Retrieving the current time (SystemApp)
    - Adding reminders for specific tasks (ReminderApp)
    - Waiting for next user message or timeout (SystemApp)
    - Proactive suggestion to the user and confirmation (AgentUserInterface)
    - Deletion and retrieval of reminders (ReminderApp)
    - Validation based on successful creation and confirmation of reminders

    Main goal: Show the agent assisting in setting a daily reminder list,
    confirming with the user whether to add a proposed reminder.
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize all required applications."""
        aui = AgentUserInterface()
        reminder_app = ReminderApp()
        system_app = SystemApp(name="core_system")

        # Register all apps for the scenario
        self.apps = [aui, reminder_app, system_app]

    def build_events_flow(self) -> None:
        """Define the event flow of the scenario including proactive confirmation."""
        aui = self.get_typed_app(AgentUserInterface)
        reminder_app = self.get_typed_app(ReminderApp)
        system_app = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # 1. Initial user request to organize daily tasks
            user_request = aui.send_message_to_agent(
                content=(
                    "Hi, I'd like help planning my tasks for today. Could you suggest and remind me about key items?"
                )
            ).depends_on(None, delay_seconds=1)

            # 2. Agent gets current time to anchor reminder schedule
            get_time_action = system_app.get_current_time().depends_on(user_request, delay_seconds=1).oracle()

            # 3. Agent processes and proactively proposes task reminders
            proactive_proposal = aui.send_message_to_user(
                content=(
                    "I suggest adding reminders for your afternoon report submission and your evening workout. "
                    "Would you like me to set them for you?"
                )
            ).depends_on(get_time_action, delay_seconds=1)

            # 4. User confirms with detailed response
            user_confirmation = aui.send_message_to_agent(
                content="Yes, please set both reminders — the report at 15:00 and the workout at 18:30."
            ).depends_on(proactive_proposal, delay_seconds=1)

            # 5. Agent creates two reminders based on user approval
            add_report_reminder = (
                reminder_app.add_reminder(
                    title="Submit Project Report",
                    due_datetime="1970-01-01 15:00:00",
                    description="Complete and send today's project report to the team.",
                    repetition_unit=None,
                )
                .depends_on(user_confirmation, delay_seconds=1)
                .oracle()
            )

            add_workout_reminder = (
                reminder_app.add_reminder(
                    title="Workout Session",
                    due_datetime="1970-01-01 18:30:00",
                    description="Do a 45-minute evening workout.",
                    repetition_unit=None,
                )
                .depends_on(add_report_reminder, delay_seconds=1)
                .oracle()
            )

            # 6. System waits to sync pending notifications
            idle_wait = system_app.wait_for_notification(timeout=5).depends_on(add_workout_reminder, delay_seconds=1)

            # 7. Agent retrieves all reminders to confirm creation and sends summary to user
            get_all_reminders = reminder_app.get_all_reminders().depends_on(idle_wait, delay_seconds=1)

            confirm_to_user = (
                aui.send_message_to_user(
                    content="I've created two reminders: one for your report and one for your workout. All set!"
                )
                .depends_on(get_all_reminders, delay_seconds=1)
                .oracle()
            )

        self.events = [
            user_request,
            get_time_action,
            proactive_proposal,
            user_confirmation,
            add_report_reminder,
            add_workout_reminder,
            idle_wait,
            get_all_reminders,
            confirm_to_user,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate scenario correctness by checking that reminders were added after user confirmation."""
        try:
            event_log = env.event_log.list_view()

            # Ensure the proactive proposal step happened (agent proposing something)
            proactive_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "would you like me to set them" in e.action.args.get("content", "").lower()
                for e in event_log
            )

            # Ensure both reminder creation actions occurred after confirmation
            reminders_created = [
                e
                for e in event_log
                if e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ReminderApp"
                and e.action.function_name == "add_reminder"
            ]

            # Ensure system time retrieval was performed
            system_time_called = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "SystemApp"
                and e.action.function_name == "get_current_time"
                for e in event_log
            )

            # Agent confirmed to user
            confirmation_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "i've created two reminders" in e.action.args.get("content", "").lower()
                for e in event_log
            )

            success = proactive_found and len(reminders_created) >= 2 and system_time_called and confirmation_sent
            return ScenarioValidationResult(success=success)
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
