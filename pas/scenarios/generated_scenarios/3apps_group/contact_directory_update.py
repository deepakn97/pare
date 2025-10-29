from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.contacts import Contact, ContactsApp, Gender, Status
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("contact_directory_update")
class ContactDirectoryUpdate(Scenario):
    """Scenario demonstrating proactive contact management.

    The user wants to keep the contact list updated and consistent. The agent will:
    1. Check the current time and ask whether to update a specific contact.
    2. Propose to correct or complete missing contact information.
    3. After user approval, execute the contact edit.
    4. Search for an additional contact and show query-based updates.

    This scenario uses:
      - AgentUserInterface: for communication and message proposals.
      - ContactsApp: for searching, editing, getting, and adding contacts.
      - SystemApp: for obtaining current time and waiting for notifications.
    """

    start_time: float | None = 0
    duration: float | None = 30

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and populate the environment with the necessary data."""
        aui = AgentUserInterface()
        contacts = ContactsApp()
        system = SystemApp(name="system")

        # Populate with several contacts for realistic search and edit operations
        contact_anna = Contact(
            first_name="Anna",
            last_name="Richards",
            gender=Gender.FEMALE,
            status=Status.EMPLOYED,
            age=34,
            email="anna.richards@oldmail.com",
            phone="+1 555 0101",
            city_living="Chicago",
            country="USA",
        )

        contact_lee = Contact(
            first_name="Lee",
            last_name="Chen",
            gender=Gender.MALE,
            status=Status.EMPLOYED,
            age=29,
            email="lee.chen@work.org",
            phone="+86 189 9200 3030",
            city_living="Shanghai",
            country="China",
        )

        contact_unknown = Contact(
            first_name="Sam",
            last_name="White",
            gender=Gender.UNKNOWN,
            status=Status.UNKNOWN,
            email=None,
            phone=None,
            city_living=None,
            country=None,
        )

        contacts._contacts.extend([contact_anna, contact_lee, contact_unknown])

        self.apps = [aui, contacts, system]

    def build_events_flow(self) -> None:
        """Define the event flow including proactive interaction and validation steps."""
        aui = self.get_typed_app(AgentUserInterface)
        contacts = self.get_typed_app(ContactsApp)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # Step 1: User asks the assistant to check contact updates
            user_start = aui.send_message_to_agent(
                content="Assistant, please check who in my contact list might need an update or missing info."
            ).depends_on(None, delay_seconds=1)

            # Step 2: Agent retrieves system time to timestamp the proposed update
            fetch_time = system.get_current_time().depends_on(user_start, delay_seconds=1)

            # Step 3: Agent proactively proposes to update Sam's missing email
            propose_action = aui.send_message_to_user(
                content="It's currently business hours. I found Sam White has missing details. Would you like me to add an email and update their city?"
            ).depends_on(fetch_time, delay_seconds=1)

            # Step 4: User approves the proposal
            user_approval = aui.send_message_to_agent(
                content="Yes, please update Sam White with email sam.white@email.com in New York."
            ).depends_on(propose_action, delay_seconds=1)

            # Step 5: Agent updates the contact information as approved (oracle action)
            oracle_update = (
                contacts.edit_contact(
                    contact_id="Sam White",
                    updates={
                        "email": "sam.white@email.com",
                        "city_living": "New York",
                        "country": "USA",
                        "status": Status.EMPLOYED,
                    },
                )
                .oracle()
                .depends_on(user_approval, delay_seconds=2)
            )

            # Step 6: Agent searches for "Lee" to confirm another valid contact exists
            search_contact = contacts.search_contacts(query="Lee").depends_on(oracle_update, delay_seconds=1)

            # Step 7: Agent informs the user that the update was successful
            final_message = (
                aui.send_message_to_user(
                    content="I've updated Sam White as requested and verified Lee Chen's contact remains correct."
                )
                .oracle()
                .depends_on(search_contact, delay_seconds=1)
            )

            # Step 8: System app demonstration - wait after updates to mimic idle state
            idle_wait = system.wait_for_notification(timeout=5).depends_on(final_message, delay_seconds=1)

        # register all the expected event chain
        self.events = [
            user_start,
            fetch_time,
            propose_action,
            user_approval,
            oracle_update,
            search_contact,
            final_message,
            idle_wait,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate if contact editing and user notification were completed."""
        try:
            all_events = env.event_log.list_view()

            edited = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ContactsApp"
                and e.action.function_name == "edit_contact"
                and "Sam White" in e.action.args["contact_id"]
                and e.action.args["updates"].get("email") == "sam.white@email.com"
                for e in all_events
            )

            notified_user_after_edit = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "updated" in e.action.args["content"].lower()
                for e in all_events
            )

            time_checked = any(
                e.action.class_name == "SystemApp" and e.action.function_name == "get_current_time" for e in all_events
            )

            return ScenarioValidationResult(success=(edited and notified_user_after_edit and time_checked))
        except Exception as err:
            return ScenarioValidationResult(success=False, exception=err)
