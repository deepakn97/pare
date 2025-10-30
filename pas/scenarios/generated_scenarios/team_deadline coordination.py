from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("team_deadline coordination")
class TeamDeadlineCoordination(Scenario):
    """Proactive scenario: agent checks contacts, proposes to message teammates about deadlines, waits for user confirmation, sends group message and sets reminder."""

    start_time: float | None = 0
    duration: float | None = 50

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate applications."""
        aui = AgentUserInterface()
        contacts = ContactsApp()
        reminders = ReminderApp()
        messages = self._init_stateful_messaging_app()
        system = SystemApp(name="sys")

        # Populate contacts
        contacts.add_new_contact(
            first_name="Liam",
            last_name="Turner",
            gender=Gender.MALE,
            status=Status.EMPLOYED,
            email="liam.turner@example.com",
            job="Designer",
            description="Colleague from product design",
            phone="+3333345566",
        )
        contacts.add_new_contact(
            first_name="Nora",
            last_name="James",
            gender=Gender.FEMALE,
            status=Status.EMPLOYED,
            email="nora.james@example.com",
            job="Engineer",
            description="Backend engineer",
            phone="+3337788990",
        )

        # also simulate current user detail retrieval usage
        _ = contacts.get_current_user_details()

        # Validate retrieval + search
        _ = contacts.get_contacts(offset=0)
        _ = contacts.search_contacts(query="Nora")

        self.apps = [aui, contacts, reminders, messages, system]

    def _init_stateful_messaging_app(self) -> Any:  # noqa: ANN401
        """Mock initializer for messaging app within the scenario."""
        from are.simulation.apps.app import App

        class DummyMessagingApp(App):
            pass

        return DummyMessagingApp("stateful_messaging")

    def build_events_flow(self) -> None:
        """Describe the event flow."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        reminders = self.get_typed_app(ReminderApp)
        contacts = self.get_typed_app(ContactsApp)
        stmsg = self.get_typed_app_by_name("stateful_messaging")

        with EventRegisterer.capture_mode():
            # Step 1: user initial request
            user_msg = aui.send_message_to_agent(
                content="Hey Assistant, please check who's on the project team for the mobile app redesign and help me remind them about the proposal deadline."
            ).depends_on(None, delay_seconds=1)

            # Step 2: Agent uses contacts and system time to prepare
            sys_time = system.get_current_time().depends_on(user_msg, delay_seconds=1)

            # Step 3: Agent informs the user proactively asking permission to message teammates
            agent_propose = aui.send_message_to_user(
                content="I found Liam Turner and Nora James are on the redesign project team. Would you like me to send them both a reminder message about the proposal deadline and add a reminder for you tomorrow morning?"
            ).depends_on(sys_time, delay_seconds=1)

            # Step 4: User confirms
            user_approval = aui.send_message_to_agent(
                content="Yes, please message Liam and Nora, and also remind me tomorrow at 9am."
            ).depends_on(agent_propose, delay_seconds=1)

            # Step 5: Agent confirms it will execute the approved action
            stmsg_lookup_liam = stmsg.lookup_user_id(user_name="Liam").depends_on(user_approval, delay_seconds=1)
            stmsg_lookup_nora = stmsg.lookup_user_id(user_name="Nora").depends_on(user_approval, delay_seconds=1)

            # Step 6: Create group conversation
            conversation_create = (
                stmsg.create_group_conversation(user_ids=["U_LIAM", "U_NORA"], title="Proposal Deadline Coordination")
                .oracle()
                .depends_on([stmsg_lookup_liam, stmsg_lookup_nora], delay_seconds=1)
            )

            # Step 7: Send message to that conversation
            group_notify = (
                stmsg.send_message_to_group_conversation(
                    conversation_id="GP_DeadlineTeam",
                    content="Hi team! A quick reminder that the project proposal is due by tomorrow evening. Let's ensure all drafts are finalized before noon!",
                )
                .oracle()
                .depends_on(conversation_create, delay_seconds=1)
            )

            # Step 8: Add a reminder via ReminderApp for tomorrow
            reminder_add = (
                reminders.add_reminder(
                    title="Finalize Proposal Submission",
                    due_datetime="1970-01-02 09:00:00",
                    description="Complete and review mobile redesign proposal before sending.",
                    repetition_unit=None,
                )
                .oracle()
                .depends_on(group_notify, delay_seconds=1)
            )

            # Step 9: Wait for notification to simulate time passage
            pause = system.wait_for_notification(timeout=5).depends_on(reminder_add, delay_seconds=1)

            # Step 10: Agent gently reaffirms task done
            done_notif = (
                aui.send_message_to_user(
                    content="I sent a deadline reminder to Liam and Nora and scheduled your personal reminder for 9am tomorrow."
                )
                .oracle()
                .depends_on(pause, delay_seconds=1)
            )

        self.events = [
            user_msg,
            sys_time,
            agent_propose,
            user_approval,
            stmsg_lookup_liam,
            stmsg_lookup_nora,
            conversation_create,
            group_notify,
            reminder_add,
            pause,
            done_notif,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the proactive action was executed and reminders/messages created."""
        try:
            logs = env.event_log.list_view()
            sent_msgs = [
                ev
                for ev in logs
                if ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "stateful_messaging"
                and "send_message_to_group_conversation" in ev.action.function_name
            ]
            reminders_set = [
                ev
                for ev in logs
                if ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "ReminderApp"
                and ev.action.function_name == "add_reminder"
            ]
            proposal_proposed = any(
                ev.action.class_name == "AgentUserInterface"
                and "Would you like me to send" in ev.action.args.get("content", "")
                for ev in logs
                if ev.event_type == EventType.AGENT
            )
            user_confirmed = any(
                ev.event_type == EventType.USER and "please message Liam" in ev.action.args.get("content", "")
                for ev in logs
            )
            success = len(sent_msgs) > 0 and len(reminders_set) > 0 and proposal_proposed and user_confirmed
            return ScenarioValidationResult(success=success)
        except Exception as ex:
            return ScenarioValidationResult(success=False, exception=ex)
