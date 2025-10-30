from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import ApartmentListingApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("apartment_shared_visit_arrangement")
class ApartmentSharedVisitArrangement(Scenario):
    """Complex scenario: The agent helps user find an apartment, propose sharing details with a friend, and set a visit reminder.

    This scenario demonstrates:
    - Searching apartments using ApartmentListingApp
    - Managing contacts using ContactsApp
    - Setting a reminder for an upcoming apartment visit
    - Using SystemApp for time management
    - A proactive agent proposal with user confirmation
    """

    start_time: float | None = 0
    duration: float | None = 35

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize all apps with minimal data needed for simulation."""
        aui = AgentUserInterface()
        system = SystemApp(name="system_clock")
        contacts = ContactsApp()
        reminders = ReminderApp()
        apartments = ApartmentListingApp()

        # Add user personal details
        contacts.add_new_contact(
            first_name="Alice",
            last_name="Wong",
            gender=Gender.FEMALE,
            nationality="Canadian",
            country="Canada",
            city_living="Toronto",
            email="alice@example.com",
            status=Status.EMPLOYED,
            job="Designer",
            description="Primary user of the assistant",
        )

        # Add friend contact
        contacts.add_new_contact(
            first_name="Jordan",
            last_name="Lee",
            gender=Gender.MALE,
            nationality="Canadian",
            country="Canada",
            city_living="Toronto",
            email="jordan.lee@example.com",
            phone="+1-416-555-1299",
            status=Status.EMPLOYED,
            job="Architect",
            description="Friend interested in moving to a new apartment soon",
        )

        # Make apps available to the environment
        self.apps = [aui, system, contacts, reminders, apartments]

    def build_events_flow(self) -> None:
        """Define oracle event flow for the apartment search and sharing process."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        contacts = self.get_typed_app(ContactsApp)
        reminders = self.get_typed_app(ReminderApp)
        apartments = self.get_typed_app(ApartmentListingApp)

        with EventRegisterer.capture_mode():
            # User initiates a conversation about apartment search
            event0 = aui.send_message_to_agent(
                content="Hey Assistant, can you help me find an apartment in Toronto under 1500 CAD with 2 bedrooms?"
            ).depends_on(None, delay_seconds=1)

            # Agent queries ApartmentListingApp (oracle)
            event1 = (
                apartments.search_apartments(
                    location="Toronto",
                    min_price=700,
                    max_price=1500,
                    number_of_bedrooms=2,
                    property_type="Apartment",
                    furnished_status="Unfurnished",
                )
                .oracle()
                .depends_on(event0, delay_seconds=1)
            )

            # Agent retrieves the current date and time for context
            event2 = system.get_current_time().oracle().depends_on(event1, delay_seconds=1)

            # Agent proactively proposes to share the found apartment listing with Jordan
            event3 = aui.send_message_to_user(
                content="I found several suitable listings in Toronto under your criteria. Would you like me to share them with your friend Jordan Lee?"
            ).depends_on(event2, delay_seconds=1)

            # User approves the suggestion
            event4 = aui.send_message_to_agent(content="Yes, please share the listings with Jordan.").depends_on(
                event3, delay_seconds=2
            )

            # After approval, agent gets Jordan's contact info (oracle)
            event5 = contacts.search_contacts(query="Jordan").oracle().depends_on(event4, delay_seconds=1)

            # Agent saves one specific apartment as favorite to be shared later
            event6 = (
                apartments.save_apartment(apartment_id="apt_toronto_207").oracle().depends_on(event5, delay_seconds=1)
            )

            # Agent then sends a confirmation message to user
            event7 = aui.send_message_to_user(
                content="I've shared the apartment details with Jordan and saved it to your favorites. Would you also like me to set a reminder for visiting this apartment tomorrow?"
            ).depends_on(event6, delay_seconds=1)

            # User agrees to set a reminder
            event8 = aui.send_message_to_agent(
                content="Yes, please set a visit reminder for tomorrow afternoon."
            ).depends_on(event7, delay_seconds=1)

            # Agent gets current system time again (oracle)
            event9 = system.get_current_time().oracle().depends_on(event8, delay_seconds=1)

            # Agent creates the reminder for the visit (oracle)
            event10 = (
                reminders.add_reminder(
                    title="Toronto apartment viewing",
                    due_datetime="1970-01-02 14:00:00",
                    description="Visit the saved Toronto apartment (ID apt_toronto_207)",
                    repetition_unit=None,
                )
                .oracle()
                .depends_on(event9, delay_seconds=1)
            )

            # Agent final message confirming all actions done
            event11 = (
                aui.send_message_to_user(
                    content="The apartment visit reminder for tomorrow has been added, and Jordan has received the listing details."
                )
                .oracle()
                .depends_on(event10, delay_seconds=1)
            )

        self.events = [event0, event1, event2, event3, event4, event5, event6, event7, event8, event9, event10, event11]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validation ensuring all major steps occurred: search, save, reminder set, proactive messages."""
        try:
            events = env.event_log.list_view()
            # Check if reminder was successfully added by the agent
            reminder_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ReminderApp"
                and e.action.function_name == "add_reminder"
                and "Toronto apartment viewing" in e.action.args.get("title", "")
                for e in events
            )

            # Check if apartment was favorited
            apartment_saved = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ApartmentListingApp"
                and e.action.function_name == "save_apartment"
                and "apt_toronto_207" in e.action.args.get("apartment_id", "")
                for e in events
            )

            # Check that the agent proactively contacted the user
            proactive_msg = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "Jordan Lee" in e.action.args.get("content", "")
                for e in events
            )

            # Validation will succeed only if all 3 key actions completed
            success = reminder_created and apartment_saved and proactive_msg
            return ScenarioValidationResult(success)
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
