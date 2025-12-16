from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.cab import CabApp
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.sandbox_file_system import Files
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("team_field_meeting_coordination")
class TeamFieldMeetingCoordination(Scenario):
    """Scenario: The agent helps coordinate an on-site field meeting using messaging, files, reminders, and transportation booking.

    The workflow demonstrates:
    - reading a report file from the file system
    - messaging teammates
    - proactively proposing to arrange a cab ride
    - user confirmation
    - creating a reminder for the meeting
    - checking timing via the system clock
    """

    start_time: float | None = 0
    duration: float | None = 40

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate all required apps."""
        aui = AgentUserInterface()
        messaging = MessagingApp()
        reminders = ReminderApp()
        files = Files(name="demo_fs", sandbox_dir=kwargs.get("sandbox_dir"))
        system = SystemApp(name="system_base")
        cab = CabApp(name="city_cab")

        # Prepare the file system with a report file for the meeting
        files.makedirs("docs/meetings", exist_ok=True)
        self.report_path = "docs/meetings/project_alpha_summary.txt"
        with open(f"{kwargs.get('sandbox_dir')}/{self.report_path}", "w") as f:
            f.write("Project Alpha Report: Summary of field data collection tasks.")

        # Register all apps
        self.apps = [aui, messaging, reminders, files, system, cab]

    def build_events_flow(self) -> None:
        """Define the chronological flow of events: messages, proactive proposal, approval, and cab ordering."""
        aui = self.get_typed_app(AgentUserInterface)
        messaging = self.get_typed_app(MessagingApp)
        reminders = self.get_typed_app(ReminderApp)
        system = self.get_typed_app(SystemApp)
        cab = self.get_typed_app(CabApp)
        files = self.get_typed_app(Files)

        conv_id = messaging.create_conversation(participants=["Jordan Wells"], title="Field Visit Coordination")

        with EventRegisterer.capture_mode():
            # Step 1: User asks the assistant to prepare material for the next on-site meeting
            event0 = aui.send_message_to_agent(
                content="Hey Assistant, please prepare everything for our field meeting with Jordan tomorrow morning."
            ).depends_on(None, delay_seconds=1)

            # Step 2: The assistant checks the time
            event1 = system.get_current_time().depends_on(event0, delay_seconds=1)

            # Step 3: The assistant reads the project report file
            event2 = files.read_document(file_path=self.report_path, max_lines=10).depends_on(event1, delay_seconds=1)

            # Step 4: The assistant sends the summary report via message to Jordan
            event3 = messaging.send_message(
                conversation_id=conv_id, content="Hi Jordan, here's the summary for our upcoming field meeting."
            ).depends_on(event2, delay_seconds=1)
            event4 = messaging.send_attachment(conversation_id=conv_id, filepath=self.report_path).depends_on(
                event3, delay_seconds=1
            )

            # Step 5: Agent proactively proposes to book a cab
            proposal = aui.send_message_to_user(
                content="Would you like me to book a cab from your office to the research field site for tomorrow 9:00 AM?"
            ).depends_on(event4, delay_seconds=1)

            # Step 6: User approves the action
            user_response = aui.send_message_to_agent(
                content="Yes, please go ahead and arrange the cab ride for 9 AM."
            ).depends_on(proposal, delay_seconds=2)

            # Step 7: Assistant books the cab once confirmed
            book_cab = (
                cab.order_ride(
                    start_location="Downtown Office",
                    end_location="Field Research Site",
                    service_type="Van",
                    ride_time="2024-05-12 09:00:00",
                )
                .oracle()
                .depends_on(user_response, delay_seconds=1)
            )

            # Step 8: After booking, assistant sets a reminder for the meeting start time
            add_reminder = (
                reminders.add_reminder(
                    title="Field Meeting with Jordan",
                    due_datetime="2024-05-12 09:00:00",
                    description="Reminder: Depart by cab for the field meeting with Jordan.",
                    repetition_unit=None,
                )
                .oracle()
                .depends_on(book_cab, delay_seconds=1)
            )

            # Step 9: Assistant confirms completion to the user
            notify_user = (
                aui.send_message_to_user(
                    content="Cab booked successfully and reminder added for your 9 AM field meeting with Jordan."
                )
                .oracle()
                .depends_on(add_reminder, delay_seconds=1)
            )

        self.events = [
            event0,
            event1,
            event2,
            event3,
            event4,
            proposal,
            user_response,
            book_cab,
            add_reminder,
            notify_user,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate the scenario behavior succeeds."""
        try:
            events = env.event_log.list_view()

            # Check if a cab was ordered (main outcome)
            cab_order_done = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "CabApp"
                and e.action.function_name == "order_ride"
                for e in events
            )

            # Ensure a reminder was created for the meeting
            reminder_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ReminderApp"
                and e.action.function_name == "add_reminder"
                and "Jordan" in e.action.args.get("title", "")
                for e in events
            )

            # Confirm the proactive proposal to user existed
            proactive_check = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "AgentUserInterface"
                and "book a cab" in str(e.action.args.get("content", "")).lower()
                for e in events
            )

            # Confirm the user approval message occurred
            user_approval_found = any(
                e.event_type == EventType.USER
                and "go ahead and arrange the cab" in e.action.args.get("content", "").lower()
                for e in events
            )

            success = cab_order_done and reminder_created and proactive_check and user_approval_found
            return ScenarioValidationResult(success=success)
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
