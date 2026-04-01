from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.apartment_listing import ApartmentListingApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("apartment_hunting_followup")
class ApartmentHuntingFollowup(Scenario):
    """Scenario demonstrating coordinated use of contact, apartment listing, reminder, and system tools.

    Objective:
        The user asks the assistant to help find a pet-friendly apartment, proposes sharing one with a friend “Jordan”.
        The agent proactively suggests saving the apartment and creating a reminder for follow-up, then executes that
        after user approval.
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps and populate them with data."""
        # Initialize all required apps
        self.agui = AgentUserInterface()
        self.system = SystemApp(name="system")
        self.contacts = ContactsApp()
        self.reminder = ReminderApp()
        self.apartments = ApartmentListingApp()

        # Add a friend contact "Jordan" to contacts
        self.contacts.add_new_contact(
            first_name="Jordan",
            last_name="Parker",
            gender=Gender.OTHER,
            status=Status.EMPLOYED,
            age=29,
            city_living="Seattle",
            country="USA",
            description="Close friend interested in sharing a pet-friendly apartment",
            email="jordan.parker@example.com",
            phone="+1 206 555 2345",
        )

        # Also ensure the current user is identified
        self.contacts.get_current_user_details()

        # Ensure list/retrieve operations of other apps
        self.apartments.list_all_apartments()
        self.reminder.get_all_reminders()

        # Required list of all apps
        self.apps = [self.agui, self.system, self.contacts, self.reminder, self.apartments]

    def build_events_flow(self) -> None:
        """Define the flow of user-agent interaction."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        contacts = self.get_typed_app(ContactsApp)
        reminder = self.get_typed_app(ReminderApp)
        apartment_list = self.get_typed_app(ApartmentListingApp)

        # Start temporal context from system clock
        current = system.get_current_time()
        base_time = current["datetime"]

        with EventRegisterer.capture_mode():
            # User initiates
            e0 = aui.send_message_to_agent(
                content=(
                    "I'm looking for a pet-friendly 2-bedroom apartment in Seattle under $1800. "
                    "Can you find one for me, and maybe let Jordan know once we find something good?"
                )
            ).depends_on(None, delay_seconds=1)

            # Agent uses apartment listing to search
            e1 = apartment_list.search_apartments(
                location="Seattle", number_of_bedrooms=2, max_price=1800, pet_policy="Pets allowed"
            ).depends_on(e0, delay_seconds=1)

            # Agent reviews details of one search result
            e2 = apartment_list.get_apartment_details(apartment_id="apt001").depends_on(e1, delay_seconds=1)

            # Agent proposes action to user (PROACTIVE STEP)
            e3 = aui.send_message_to_user(
                content=(
                    "I found a 2-bedroom apartment in Seattle under your budget that allows pets. "
                    "Would you like me to save this apartment and create a follow-up reminder for tomorrow, "
                    "so we can review it together with Jordan?"
                )
            ).depends_on(e2, delay_seconds=1)

            # User approves explicitly
            e4 = aui.send_message_to_agent(
                content="Yes, please save it and add a reminder to review it with Jordan tomorrow."
            ).depends_on(e3, delay_seconds=1)

            # Agent acts upon confirmation: save the apartment
            e5 = apartment_list.save_apartment(apartment_id="apt001").oracle().depends_on(e4, delay_seconds=1)

            # Agent also adds a reminder for the next day
            e6 = (
                reminder.add_reminder(
                    title="Discuss apartment with Jordan",
                    due_datetime=base_time,
                    description="Review the saved Seattle apartment in favorites with Jordan.",
                    repetition_unit=None,
                )
                .oracle()
                .depends_on(e5, delay_seconds=1)
            )

            # Simulate waiting for notification time
            e7 = system.wait_for_notification(timeout=5).depends_on(e6, delay_seconds=1)

            # Agent searches contacts to verify Jordan
            e8 = contacts.search_contacts(query="Jordan Parker").depends_on(e7, delay_seconds=1)

            # Agent finishes by confirming reminder creation to user
            e9 = (
                aui.send_message_to_user(
                    content=(
                        "I've saved the apartment and scheduled a reminder to review it with Jordan tomorrow. "
                        "You can find it under your saved listings."
                    )
                )
                .oracle()
                .depends_on(e8, delay_seconds=1)
            )

        # Register all events to scenario timeline
        self.events = [e0, e1, e2, e3, e4, e5, e6, e7, e8, e9]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Check if apartment was saved and reminder created after user approval."""
        try:
            events = env.event_log.list_view()

            # Ensure save_apartment called on agent side
            saved_action = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ApartmentListingApp"
                and e.action.function_name == "save_apartment"
                for e in events
            )

            # Check that reminder was created
            reminder_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "ReminderApp"
                and e.action.function_name == "add_reminder"
                for e in events
            )

            # Verify agent proactively proposed before user approval
            proactive_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and "save" in e.action.args.get("content", "").lower()
                and "reminder" in e.action.args.get("content", "").lower()
                for e in events
            )

            # Validation passes only if all 3 conditions hold
            success = saved_action and reminder_created and proactive_found
            return ScenarioValidationResult(success=success)

        except Exception as err:
            return ScenarioValidationResult(success=False, exception=err)
