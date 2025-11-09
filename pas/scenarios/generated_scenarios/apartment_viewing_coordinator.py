from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import ApartmentListingApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("apartment_viewing_coordinator")
class ApartmentViewingCoordinator(Scenario):
    """A scenario where the agent helps coordinate apartment viewings with proactive confirmation.

    The scenario demonstrates integration across:
    - ApartmentListingApp for finding an apartment
    - ContactsApp for sharing contact details
    - ReminderApp for scheduling upcoming appointments
    - SystemApp for time awareness
    - AgentUserInterface for user interaction
    """

    start_time: float | None = 0
    duration: float | None = 30

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and populate all apps used in the scenario."""
        aui = AgentUserInterface()
        contacts = ContactsApp()
        reminder = ReminderApp()
        apartment_app = ApartmentListingApp()
        system = SystemApp(name="core_system")

        # Prepare contacts information
        realtor_id = contacts.add_new_contact(
            first_name="Sophia",
            last_name="Keller",
            gender=Gender.FEMALE,
            email="sophia.keller@homespot.com",
            phone="+1 234 555 0192",
            city_living="Denver",
            country="USA",
            status=Status.EMPLOYED,
            job="Real Estate Agent",
            description="Friendly and responsive realtor from HomeSpot Realty.",
        )

        # Add a potential roommate contact
        roommate_id = contacts.add_new_contact(
            first_name="Emma",
            last_name="Stone",
            gender=Gender.FEMALE,
            email="emma.stone@example.com",
            phone="+1 987 234 9988",
            city_living="Denver",
            country="USA",
            status=Status.STUDENT,
            job="Graduate Student",
            description="Looking for a 2-bedroom apartment with me.",
        )

        self.apps = [aui, contacts, reminder, apartment_app, system]

    def build_events_flow(self) -> None:
        """Construct the event flow that defines the scenario logic."""
        aui = self.get_typed_app(AgentUserInterface)
        contacts = self.get_typed_app(ContactsApp)
        reminder = self.get_typed_app(ReminderApp)
        apartment_app = self.get_typed_app(ApartmentListingApp)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # User initiates the interaction
            start_event = aui.send_message_to_agent(
                content=(
                    "Hey assistant, can you find an affordable 2-bedroom apartment in Denver and set up a viewing with the realtor?"
                )
            ).depends_on(None, delay_seconds=1)

            # System gets the current time
            check_time = system.get_current_time().depends_on(start_event, delay_seconds=1)

            # Apartment app searches listings
            search_apartments = apartment_app.search_apartments(
                location="Denver", number_of_bedrooms=2, max_price=1500, furnished_status="Unfurnished"
            ).depends_on(check_time, delay_seconds=1)

            # Agent proposes an apartment choice to user
            propose_action = aui.send_message_to_user(
                content="I found 'Pine View Apartments' that matches your criteria. Would you like me to contact the realtor Sophia Keller and schedule a viewing?"
            ).depends_on(search_apartments, delay_seconds=1)

            # User approves the proposal explicitly
            user_approval = aui.send_message_to_agent(
                content="Yes, please contact Sophia and also remind me to review the apartment details tomorrow morning."
            ).depends_on(propose_action, delay_seconds=1)

            # Get realtor contact information
            get_realtor = contacts.search_contacts(query="Sophia Keller").depends_on(user_approval, delay_seconds=1)

            # Save the found apartment to favorites
            list_all = apartment_app.list_all_apartments().depends_on(get_realtor, delay_seconds=1)
            save_one = (
                apartment_app.save_apartment(apartment_id="pine_view_apartment")
                .oracle()
                .depends_on(list_all, delay_seconds=1)
            )

            # Add a reminder to follow up
            add_recall = reminder.add_reminder(
                title="Check Pine View Apartment details",
                due_datetime="1970-01-02 09:00:00",
                description="Review apartment details and confirm visit with Sophia Keller.",
            ).depends_on(save_one, delay_seconds=1)

            # Confirm setup to user
            final_confirm = (
                aui.send_message_to_user(
                    content="I've scheduled a reminder and saved Sophia's contact. You'll be reminded tomorrow morning to review Pine View Apartments."
                )
                .oracle()
                .depends_on(add_recall, delay_seconds=1)
            )

            # Wait for next notification (simulate background state)
            wait_state = system.wait_for_notification(timeout=5).depends_on(final_confirm, delay_seconds=1)

        self.events = [
            start_event,
            check_time,
            search_apartments,
            propose_action,
            user_approval,
            get_realtor,
            list_all,
            save_one,
            add_recall,
            final_confirm,
            wait_state,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that the apartment was processed, contact found, and reminder created."""
        try:
            events = env.event_log.list_view()

            # Validation 1: The user was prompted with a question about scheduling a viewing
            proactive_prompt = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "Would you like me to contact" in e.action.args.get("content", "")
                for e in events
            )

            # Validation 2: A reminder was created
            reminder_added = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ReminderApp"
                and e.action.function_name == "add_reminder"
                for e in events
            )

            # Validation 3: Apartment saving oracle event exists
            apartment_saved = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ApartmentListingApp"
                and e.action.function_name == "save_apartment"
                and e.is_oracle
                for e in events
            )

            # Validation 4: Contact search was attempted for the realtor
            contact_search_done = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ContactsApp"
                and e.action.function_name == "search_contacts"
                and "Sophia Keller" in e.action.args.get("query", "")
                for e in events
            )

            return ScenarioValidationResult(
                success=proactive_prompt and reminder_added and apartment_saved and contact_search_done
            )

        except Exception as ex:
            return ScenarioValidationResult(success=False, exception=ex)
