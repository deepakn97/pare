from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.cab import CabApp
from are.simulation.apps.contacts import ContactsApp, Gender, Status
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer


@register_scenario("conference_trip_coordination")
class ConferenceTripCoordination(Scenario):
    """Scenario: The user is traveling to a tech conference and wants help coordinating the ride and reminders.

    The agent will:
    1. Record the current time
    2. Proactively propose scheduling a cab
    3. Upon user approval, book the ride
    4. Add a relevant reminder
    5. Confirm or update contacts for information sharing

    All apps are used: SystemApp (for time), CabApp (for ride operations),
    ReminderApp (for trip reminders), ContactsApp (contact management),
    and AgentUserInterface (for rich proactive user interaction).
    """

    start_time: float | None = 0
    duration: float | None = 40

    def init_and_populate_apps(self, *args: object, **kwargs: object) -> None:
        """Initialize all apps with dummy but consistent data."""
        self.aui = AgentUserInterface()
        self.system = SystemApp(name="system_time_keeper")
        self.contacts = ContactsApp()
        self.reminder = ReminderApp()
        self.cab = CabApp()

        # Add some contacts for later interaction
        self.contacts.add_new_contact(
            first_name="Jordan",
            last_name="Lee",
            gender=Gender.MALE,
            age=31,
            nationality="Canadian",
            city_living="Toronto",
            country="Canada",
            status=Status.EMPLOYED,
            job="Engineer",
            description="Tech conference attendee",
            phone="+1 222 555 7889",
            email="jordan.lee@example.com",
        )

        self.contacts.add_new_contact(
            first_name="Naomi",
            last_name="Parker",
            gender=Gender.FEMALE,
            age=28,
            nationality="American",
            city_living="New York",
            country="USA",
            status=Status.EMPLOYED,
            job="Event Manager",
            description="Conference coordinator",
            phone="+1 333 209 4530",
            email="naomi.parker@example.com",
        )

        self.apps = [self.aui, self.system, self.contacts, self.reminder, self.cab]

    def build_events_flow(self) -> None:
        """Define the chronological flow of this proactive interaction scenario."""
        aui = self.get_typed_app(AgentUserInterface)
        system = self.get_typed_app(SystemApp)
        contacts = self.get_typed_app(ContactsApp)
        reminder = self.get_typed_app(ReminderApp)
        cab = self.get_typed_app(CabApp)

        with EventRegisterer.capture_mode():
            # Step 0: User requests help for conference travel
            user_initial = aui.send_message_to_agent(
                content="Assistant, I need to get to the GreenTech Conference venue tomorrow morning."
            ).depends_on(None, delay_seconds=1)

            # Step 1: Agent checks current time to plan appropriately
            check_time = system.get_current_time().oracle().depends_on(user_initial, delay_seconds=1)

            # Step 2: Agent looks for or verifies contact of the coordinator (Naomi)
            find_contact = contacts.search_contacts(query="Naomi").oracle().depends_on(check_time, delay_seconds=1)

            # Step 3: Agent proposes a specific cab booking action
            propose_action = aui.send_message_to_user(
                content=(
                    "Would you like me to schedule a cab from your hotel to the conference center at 8:00 AM tomorrow? "
                    "I can also share your ETA with Jordan Lee once it's booked."
                )
            ).depends_on(find_contact, delay_seconds=1)

            # Step 4: User grants detailed approval
            user_approval = aui.send_message_to_agent(
                content="Yes, please schedule that morning cab and share the details with Jordan Lee."
            ).depends_on(propose_action, delay_seconds=2)

            # Step 5: Agent calculates the cab quote before booking
            get_quote = (
                cab.get_quotation(
                    start_location="Sunrise Hotel, Downtown",
                    end_location="GreenTech Conference Center",
                    service_type="Premium",
                    ride_time="2024-06-12 08:00:00",
                )
                .oracle()
                .depends_on(user_approval, delay_seconds=1)
            )

            # Step 6: Agent books the ride after obtaining quotation
            book_ride = (
                cab.order_ride(
                    start_location="Sunrise Hotel, Downtown",
                    end_location="GreenTech Conference Center",
                    service_type="Premium",
                    ride_time="2024-06-12 08:00:00",
                )
                .oracle()
                .depends_on(get_quote, delay_seconds=1)
            )

            # Step 7: Agent adds a reminder for the user
            add_trip_reminder = (
                reminder.add_reminder(
                    title="Cab Ride to GreenTech",
                    due_datetime="2024-06-12 07:45:00",
                    description="Meet your cab in front of Sunrise Hotel. Notify Jordan Lee once you depart.",
                    repetition_unit=None,
                )
                .oracle()
                .depends_on(book_ride, delay_seconds=1)
            )

            # Step 8: Agent confirms back with user
            final_confirm = (
                aui.send_message_to_user(
                    content=(
                        "Your ride to the GreenTech Conference has been booked, and a reminder added for 15 minutes before departure. "
                        "I have also updated your itinerary shared with Jordan Lee."
                    )
                )
                .oracle()
                .depends_on(add_trip_reminder, delay_seconds=2)
            )

            # Step 9: Agent waits passively afterward
            idle_wait = system.wait_for_notification(timeout=10).depends_on(final_confirm, delay_seconds=1)

        self.events = [
            user_initial,
            check_time,
            find_contact,
            propose_action,
            user_approval,
            get_quote,
            book_ride,
            add_trip_reminder,
            final_confirm,
            idle_wait,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Check if the scenario resulted in a booked ride and a reminder."""
        try:
            events = env.event_log.list_view()

            has_booking = any(
                isinstance(e.action, Action)
                and e.action.class_name == "CabApp"
                and e.action.function_name == "order_ride"
                for e in events
            )

            has_reminder = any(
                isinstance(e.action, Action)
                and e.action.class_name == "ReminderApp"
                and e.action.function_name == "add_reminder"
                and "Cab Ride" in e.action.args.get("title", "")
                for e in events
            )

            proactive_dialogue_present = any(
                e.action.class_name == "AgentUserInterface"
                and "Would you like me to schedule a cab" in e.action.args.get("content", "")
                for e in events
                if isinstance(e.action, Action)
            )

            return ScenarioValidationResult(success=(has_booking and has_reminder and proactive_dialogue_present))
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
