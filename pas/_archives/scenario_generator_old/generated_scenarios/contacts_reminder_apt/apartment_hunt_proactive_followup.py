from __future__ import annotations

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import ApartmentListingApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("apartment_hunt_proactive_followup")
class ApartmentHuntProactiveFollowup(Scenario):
    """Scenario where the agent searches for an apartment, adds a contact.

    Proactively offers to set a reminder, and follows up based on user confirmation.
    """

    start_time: float | None = 0
    duration: float | None = 32

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize and populate applications with test data."""
        aui = AgentUserInterface()
        apartment_listing = ApartmentListingApp()
        contacts = ContactsApp()
        reminders = ReminderApp()
        system = SystemApp(name="core_system")

        # Add a few contacts including an agent contact
        contacts.add_new_contact(
            first_name="Elena",
            last_name="Morales",
            gender=Gender.FEMALE,
            status=Status.EMPLOYED,
            phone="+1 555 098 3456",
            email="elena.morales@homesphere.com",
            job="Real Estate Agent",
            city_living="Madrid",
            country="Spain",
        )
        contacts.add_new_contact(
            first_name="Lucas",
            last_name="Nguyen",
            gender=Gender.MALE,
            status=Status.EMPLOYED,
            phone="+1 555 777 2234",
            email="lucas.nguyen@example.com",
            job="Friend",
            city_living="Madrid",
            country="Spain",
        )

        self.apps = [aui, apartment_listing, contacts, reminders, system]

    def build_events_flow(self) -> None:
        """Define the scenario's interaction flow using all available applications."""
        aui = self.get_typed_app(AgentUserInterface)
        apartment_listing = self.get_typed_app(ApartmentListingApp)
        contacts = self.get_typed_app(ContactsApp)
        reminders = self.get_typed_app(ReminderApp)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # User initiates request
            event0 = aui.send_message_to_agent(
                content=(
                    "Hey Assistant, I'm looking for a one-bedroom apartment near Madrid city center, budget around 1500 euros."
                )
            ).depends_on(None, delay_seconds=1)

            # Agent uses apartment listing to find listings
            search_apartments = apartment_listing.search_apartments(
                location="Madrid", number_of_bedrooms=1, max_price=1500
            ).depends_on(event0, delay_seconds=1)

            # Agent fetches system time (used for scheduling later)
            current_time = system.get_current_time().depends_on(search_apartments, delay_seconds=1)

            # Agent proposes to user that they found a suitable place
            propose_message = aui.send_message_to_user(
                content=(
                    "I found several apartments under 1500€ in Madrid. One from 'Elena Morales' looks promising. "
                    "Would you like me to save it and set a reminder to follow up with her?"
                )
            ).depends_on(current_time, delay_seconds=1)

            # User confirms proactively with a contextual message
            user_confirm = aui.send_message_to_agent(
                content=("Yes, go ahead and save that apartment and remind me to call Elena tomorrow morning.")
            ).depends_on(propose_message, delay_seconds=1)

            # Agent saves the apartment and confirms contact
            save_apartment = (
                apartment_listing.save_apartment(apartment_id="apt001")
                .oracle()
                .depends_on(user_confirm, delay_seconds=1)
            )

            # Agent retrieves Elena's contact info to ensure follow-up
            get_contact = contacts.search_contacts(query="Elena Morales").depends_on(save_apartment, delay_seconds=1)

            # Add a reminder for tomorrow morning (uses current_date + 1)
            add_reminder = (
                reminders.add_reminder(
                    title="Call real estate agent Elena",
                    due_datetime="1970-01-02 09:00:00",
                    description="Follow up about apartment viewing with Elena Morales.",
                )
                .oracle()
                .depends_on(get_contact, delay_seconds=1)
            )

            # Wait for system notification (simulate passage of time)
            wait_system = system.wait_for_notification(timeout=2).depends_on(add_reminder, delay_seconds=1)

            # Agent checks upcoming reminders
            due_check = reminders.get_all_reminders().depends_on(wait_system, delay_seconds=1)

            # Agent informs user that the reminder has been created
            notify_user = (
                aui.send_message_to_user(
                    content="I've saved the apartment and set a reminder to call Elena Morales tomorrow morning."
                )
                .oracle()
                .depends_on(due_check, delay_seconds=1)
            )

        self.events = [
            event0,
            search_apartments,
            current_time,
            propose_message,
            user_confirm,
            save_apartment,
            get_contact,
            add_reminder,
            wait_system,
            due_check,
            notify_user,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Verify that the agent saved the apartment, scheduled a reminder, and notified the user."""
        try:
            events = env.event_log.list_view()
            apartment_saved = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ApartmentListingApp"
                and e.action.function_name == "save_apartment"
                for e in events
            )
            reminder_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ReminderApp"
                and e.action.function_name == "add_reminder"
                and "Elena" in e.action.args.get("description", "")
                for e in events
            )
            user_notified = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "reminder" in e.action.args.get("content", "").lower()
                for e in events
            )
            return ScenarioValidationResult(success=(apartment_saved and reminder_created and user_notified))
        except Exception as exc:
            return ScenarioValidationResult(success=False, exception=exc)
