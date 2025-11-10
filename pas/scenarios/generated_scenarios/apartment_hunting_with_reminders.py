from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import ApartmentListingApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("apartment_hunting_with_reminders")
class ApartmentHuntingWithReminders(Scenario):
    """Scenario: Agent helps the user organize apartment viewings with reminders and contact sharing.

    This scenario demonstrates the use of all apps:
    - Uses SystemApp to get current time
    - Uses ApartmentListingApp to find and save apartments
    - Uses ReminderApp to create follow-up reminders
    - Uses ContactsApp to manage and share the landlord's details
    - Uses AgentUserInterface for proactive interaction with the user

    The agent will proactively suggest to the user that they share a found apartment's details
    with their friend and create a reminder to schedule a visit.
    """

    start_time: float | None = 0
    duration: float | None = 30

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps and populate with demo contacts and reference data."""
        self.aui = AgentUserInterface()
        self.contacts = ContactsApp()
        self.reminders = ReminderApp()
        self.system = SystemApp(name="system_main")
        self.apts = ApartmentListingApp()

        # Add example contacts: user and friend
        self.contacts.add_new_contact(
            first_name="Sophia",
            last_name="Green",
            gender=Gender.FEMALE,
            age=29,
            nationality="British",
            city_living="London",
            country="United Kingdom",
            status=Status.EMPLOYED,
            job="Marketing Manager",
            email="sophia.green@example.com",
            phone="+44 07707 123456",
            description="Close friend from work",
        )

        self.contacts.add_new_contact(
            first_name="Lucas",
            last_name="Gray",
            gender=Gender.MALE,
            age=31,
            nationality="British",
            city_living="London",
            country="United Kingdom",
            status=Status.EMPLOYED,
            job="Software Engineer",
            email="lucas.gray@example.com",
            phone="+44 07707 654321",
            description="Current user",
        )

        self.apps = [self.aui, self.contacts, self.reminders, self.system, self.apts]

    def build_events_flow(self) -> None:
        """Define the sequence of events in apartment searching and reminders workflow."""
        aui = self.get_typed_app(AgentUserInterface)
        contacts = self.get_typed_app(ContactsApp)
        reminders = self.get_typed_app(ReminderApp)
        system = self.get_typed_app(SystemApp)
        apts = self.get_typed_app(ApartmentListingApp)

        with EventRegisterer.capture_mode():
            # Step 1: User requests help searching for an apartment
            user_request = aui.send_message_to_agent(
                content="Can you help me find a 2-bedroom apartment in central London under £2000?"
            ).depends_on(None, delay_seconds=1)

            # Step 2: Agent searches for apartments matching criteria
            apt_search = apts.search_apartments(
                location="London",
                max_price=2000,
                number_of_bedrooms=2,
                property_type="Apartment",
                furnished_status="Furnished",
            ).depends_on(user_request, delay_seconds=1)

            # Step 3: Agent gets current time to use later for scheduling reminder
            current_time = system.get_current_time().depends_on(apt_search, delay_seconds=1)

            # Step 4: Agent proactively proposes to user to share and schedule a visit reminder
            propose_action = aui.send_message_to_user(
                content=(
                    "I found a few options matching your request. "
                    "Would you like me to share the best one with Sophia Green and set a reminder "
                    "for you to contact the landlord about arranging a viewing?"
                )
            ).depends_on(current_time, delay_seconds=1)

            # Step 5: User responds approving the agent's suggestion
            user_confirms = aui.send_message_to_agent(
                content="Yes, please share it with Sophia and set the reminder."
            ).depends_on(propose_action, delay_seconds=1)

            # Step 6: Agent retrieves Sophia's contact details
            sophia_contact = contacts.search_contacts(query="Sophia Green").depends_on(user_confirms, delay_seconds=1)

            # Step 7: Agent saves the top apartment to favorites and gets its details
            all_apartments = apts.list_all_apartments().depends_on(sophia_contact, delay_seconds=1)
            save_apartment = (
                apts.save_apartment(apartment_id="A101").oracle().depends_on(all_apartments, delay_seconds=1)
            )
            chosen_apartment_detail = apts.get_apartment_details(apartment_id="A101").depends_on(
                save_apartment, delay_seconds=1
            )

            # Step 8: Agent adds a reminder for contacting the landlord
            reminder_create = (
                reminders.add_reminder(
                    title="Contact landlord for viewing",
                    due_datetime="2024-06-12 18:00:00",
                    description="Reach out to the landlord to schedule viewing of apartment A101 in London",
                    repetition_unit=None,
                )
                .oracle()
                .depends_on(chosen_apartment_detail, delay_seconds=1)
            )

            # Step 9: Agent final message summarizing the completed steps
            summary_to_user = (
                aui.send_message_to_user(
                    content="I've shared the apartment details with Sophia and set your reminder for June 12th at 6 PM."
                )
                .oracle()
                .depends_on(reminder_create, delay_seconds=1)
            )

        self.events = [
            user_request,
            apt_search,
            current_time,
            propose_action,
            user_confirms,
            sophia_contact,
            all_apartments,
            save_apartment,
            chosen_apartment_detail,
            reminder_create,
            summary_to_user,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that apartments were searched, reminder was added, and user interaction succeeded."""
        try:
            events = env.event_log.list_view()

            # Check that the reminder was created
            reminder_made = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ReminderApp"
                and e.action.function_name == "add_reminder"
                and "Contact landlord" in e.action.args["title"]
                for e in events
            )

            # Check that the agent queried the apartment listing app
            apt_search_done = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ApartmentListingApp"
                and e.action.function_name == "search_apartments"
                for e in events
            )

            # Confirm proactive user proposal and confirmation exist
            proposal_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "share" in e.action.args["content"].lower()
                for e in events
            )

            user_approval = any(
                e.event_type == EventType.USER
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "please share" in e.action.args["content"].lower()
                for e in events
            )

            return ScenarioValidationResult(
                success=(reminder_made and apt_search_done and proposal_sent and user_approval)
            )
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
