from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("teamfollowup_with_reminder")
class TeamFollowUpWithReminder(Scenario):
    """Scenario demonstrating coordinated productivity actions.

    - The agent reads a recent message conversation about a project follow-up.
    - Then proposes to the user to set a reminder to follow up.
    - Upon user approval, the agent sets that reminder and sends a confirmation via chat.

    This scenario uses ALL available apps:
    * AgentUserInterface — for user-agent communication
    * SystemApp — to get current time
    * MessagingApp — for project chat messaging
    * ReminderApp — to create reminders
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize all applications and populate with simulated state."""
        aui = AgentUserInterface()
        messaging = MessagingApp()
        reminder = ReminderApp()
        system = SystemApp(name="system")

        # Initial chat between "Me" and "Avery Lee"
        conv_id = messaging.create_conversation(participants=["Avery Lee"], title="Project Delta Discussion")

        # Add initial messages for context
        messaging.send_message(
            conversation_id=conv_id, content="Hi, I've reviewed the project report draft — will send feedback soon."
        )
        messaging.send_message(
            conversation_id=conv_id, content="Great! Please follow up by Thursday if we haven't finalized the budget."
        )

        self.apps = [aui, messaging, reminder, system]

    def build_events_flow(self) -> None:
        """Create the main event flow, demonstrating agent, user, and reminders."""
        aui = self.get_typed_app(AgentUserInterface)
        messaging = self.get_typed_app(MessagingApp)
        reminder_app = self.get_typed_app(ReminderApp)
        system = self.get_typed_app(SystemApp)

        conv_info = messaging.list_conversations_by_participant(participant="Avery Lee", offset=0, limit=1)
        conv_id = (
            conv_info[0].id
            if conv_info
            else messaging.create_conversation(participants=["Avery Lee"], title="Temp Chat for Follow-up")
        )

        current_time = system.get_current_time()
        timestamp_str = current_time["datetime"]

        with EventRegisterer.capture_mode():
            # Step 1: user initiates action request
            user_msg = aui.send_message_to_agent(
                content="Check the recent conversation with Avery and remind me to follow up if needed."
            ).depends_on(None, delay_seconds=1)

            # Step 2: system waits a moment simulating data fetch
            wait_action = system.wait_for_notification(timeout=3).depends_on(user_msg, delay_seconds=1)

            # Step 3: agent reads conversation to review last messages
            read_chat = messaging.read_conversation(conversation_id=conv_id, offset=0, limit=5).depends_on(
                wait_action, delay_seconds=1
            )

            # Step 4 (PROACTIVE INTERACTION): agent proposes setting a reminder
            propose_rem = aui.send_message_to_user(
                content=(
                    "Avery asked you to follow up by Thursday. Would you like me to create a reminder "
                    "for Thursday 9am titled 'Follow up with Avery about budget'?"
                )
            ).depends_on(read_chat, delay_seconds=1)

            # Step 5: user gives contextual confirmation
            user_approval = aui.send_message_to_agent(
                content="Yes, that would be great. Please set that reminder."
            ).depends_on(propose_rem, delay_seconds=1)

            # Step 6: agent adds a reminder (oracle)
            add_rem = (
                reminder_app.add_reminder(
                    title="Follow up with Avery about budget",
                    due_datetime="1970-01-01 09:00:00",
                    description="Reminder to message Avery Lee about the project budget status.",
                    repetition_unit=None,
                    repetition_value=1,
                )
                .oracle()
                .depends_on(user_approval, delay_seconds=1)
            )

            # Step 7: agent sends a follow-up confirmation message in chat (oracle)
            follow_chat = (
                messaging.send_message(
                    conversation_id=conv_id, content="I've created your follow-up reminder for Thursday 9am."
                )
                .oracle()
                .depends_on(add_rem, delay_seconds=1)
            )

        self.events = [user_msg, wait_action, read_chat, propose_rem, user_approval, add_rem, follow_chat]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Check that the agent correctly added reminder and interacted appropriately."""
        try:
            # Check event log for expected agent actions
            events = env.event_log.list_view()
            # Confirm a reminder was added with required title
            reminder_added = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ReminderApp"
                and e.action.function_name == "add_reminder"
                and "Avery" in e.action.args.get("title", "")
                for e in events
            )

            # Confirm proactive message about reminder proposal was sent
            proactive_prompt = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "reminder" in e.action.args.get("content", "").lower()
                for e in events
            )

            # Confirm messaging confirmation sent
            chat_confirmation = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "MessagingApp"
                and e.action.function_name == "send_message"
                and "follow-up reminder" in e.action.args.get("content", "").lower()
                for e in events
            )

            success = reminder_added and proactive_prompt and chat_confirmation
            return ScenarioValidationResult(success=success)
        except Exception as ex:
            return ScenarioValidationResult(success=False, exception=ex)
