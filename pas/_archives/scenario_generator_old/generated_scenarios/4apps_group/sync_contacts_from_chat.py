from __future__ import annotations

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.contacts import ContactsApp
from are.simulation.apps.messaging import MessagingApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("sync_contacts_from_chat")
class SyncContactsFromChat(Scenario):
    """Scenario where the agent proposes adding a new chat participant to the user's Contacts list.

    This scenario demonstrates:
    - Messaging: managing conversations and participants
    - Contacts: adding and updating new contacts dynamically
    - System: using time and wait functionality
    - AgentUserInterface: proactive interaction with user approval

    Main objective:
    The agent notices the user is chatting with an unknown participant ("Alex Becker").
    The agent proactively proposes adding Alex Becker to Contacts.
    The user agrees, and the agent adds Alex to Contacts.
    """

    start_time: float | None = 0
    duration: float | None = 28

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize all applications with relevant data."""
        aui = AgentUserInterface()
        messaging = MessagingApp()
        contacts = ContactsApp()
        system = SystemApp(name="System")

        # Populate existing contacts
        contacts.add_new_contact(
            first_name="Mia",
            last_name="Lopez",
            email="mia.lopez@example.com",
            phone="+1 222-333-4444",
            job="Designer",
            city_living="New York",
            country="USA",
            description="Regular collaborator for graphic projects.",
        )

        # Create a messaging thread that will later trigger agent proposal
        conv_id = messaging.create_conversation(participants=["Alex Becker"], title="Discussing Marketing Plan")
        # add a chat message to simulate ongoing dialog
        messaging.send_message(
            conversation_id=conv_id,
            content="Hey, here are some points we can include in the next marketing presentation.",
        )

        # Store for later reference
        self.apps = [aui, messaging, contacts, system]

    def build_events_flow(self) -> None:
        """Define the timeline and proactive confirmation flow."""
        aui = self.get_typed_app(AgentUserInterface)
        messaging = self.get_typed_app(MessagingApp)
        contacts = self.get_typed_app(ContactsApp)
        system = self.get_typed_app(SystemApp)

        # Identify existing conversation for the proactive prompt
        conversation_ids = messaging.search(query="Alex Becker")
        target_conv_id = conversation_ids[0] if conversation_ids else "conv_alex"
        current_time_info = system.get_current_time()

        with EventRegisterer.capture_mode():
            # Event 0: simulate the user chatting with Alex
            event0 = messaging.send_message(
                conversation_id=target_conv_id, content="I'll get back to you after checking with the design team."
            ).depends_on(None, delay_seconds=1)

            # Event 1: Agent detects Alex Becker is not in current contacts
            # Agent proposes adding them to Contacts
            proposal = aui.send_message_to_user(
                content=(
                    "I noticed you're chatting with Alex Becker, "
                    "who isn't saved in your contacts. Would you like me to add Alex now?"
                )
            ).depends_on(event0, delay_seconds=1)

            # Event 2: The user approves the action with a contextual response
            approval = aui.send_message_to_agent(
                content="Yes, please add Alex Becker to my contacts and label as Marketing Manager."
            ).depends_on(proposal, delay_seconds=2)

            # Event 3: Upon user approval, the agent adds Alex Becker to Contacts
            oracle_add = (
                contacts.add_new_contact(
                    first_name="Alex",
                    last_name="Becker",
                    email="alex.becker@example.com",
                    phone="+1 555-888-9900",
                    job="Marketing Manager",
                    city_living="San Francisco",
                    country="USA",
                    description="New contact from recent messaging conversation.",
                )
                .oracle()
                .depends_on(approval, delay_seconds=1)
            )

            # Event 4: Agent confirms completion to the user
            confirm_msg = aui.send_message_to_user(
                content="I've added Alex Becker as a Marketing Manager in your contacts list."
            ).depends_on(oracle_add, delay_seconds=1)

            # Event 5: Simulate system waiting for next event (ensures use of SystemApp.wait)
            wait_event = system.wait_for_notification(timeout=3).depends_on(confirm_msg, delay_seconds=1)

        self.events = [event0, proposal, approval, oracle_add, confirm_msg, wait_event]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Confirm both proactive interaction and contact creation occurred."""
        try:
            logs = env.event_log.list_view()
            # Check the contact was actually added
            contact_added = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "ContactsApp"
                and event.action.function_name == "add_new_contact"
                and "Alex" in str(event.action.args.get("first_name", ""))
                and "Becker" in str(event.action.args.get("last_name", ""))
                for event in logs
            )
            # Check the proposal message was sent to the user
            proposal_sent = any(
                event.event_type == EventType.AGENT
                and isinstance(event.action, Action)
                and event.action.class_name == "AgentUserInterface"
                and "add" in str(event.action.args.get("content", "")).lower()
                and "alex becker" in str(event.action.args.get("content", "")).lower()
                for event in logs
            )
            # Validate user sent approval confirmation
            approval_found = any(
                event.event_type == EventType.USER
                and isinstance(event.action, Action)
                and "please add alex" in str(event.action.args.get("content", "")).lower()
                for event in logs
            )
            return ScenarioValidationResult(success=(contact_added and proposal_sent and approval_found))
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
