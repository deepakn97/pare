"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.calendar import CalendarEvent
from are.simulation.apps.contacts import Contact
from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Event, EventRegisterer

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
    StatefulContactsApp,
    StatefulEmailApp,
    StatefulMessagingApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("original_scenario_id_step2")
class ScenarioName(PASScenario):
    """<<scenario_description>>."""

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.email = StatefulEmailApp(name="Emails")
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.messaging = StatefulMessagingApp(name="Messages")
        self.contacts = StatefulContactsApp(name="Contacts")

        # Set user email for the email app
        self.email.user_email = "planner@eventpro.com"

        # Populate contacts with corporate client, catering partner, and existing clients
        corporate_client = Contact(
            first_name="Sarah",
            last_name="Mitchell",
            email="sarah.mitchell@techcorp.com",
            phone="+1-555-0101",
            job="HR Director",
            description="Corporate client - TechCorp Inc.",
        )

        catering_partner = Contact(
            first_name="Michael",
            last_name="Chen",
            email="michael@deluxecatering.com",
            phone="+1-555-0202",
            job="Catering Manager",
            description="Regular catering partner - Deluxe Catering",
        )

        existing_client_one = Contact(
            first_name="Jennifer",
            last_name="Adams",
            email="jennifer.adams@startup.io",
            phone="+1-555-0303",
            job="CEO",
            description="Client - quarterly team building",
        )

        existing_client_two = Contact(
            first_name="David",
            last_name="Rodriguez",
            email="david.r@supplier.net",
            phone="+1-555-0404",
            job="Sales Manager",
            description="Venue supplier",
        )

        self.contacts.add_contacts([corporate_client, catering_partner, existing_client_one, existing_client_two])

        # Populate calendar with existing commitments for Tuesday and Wednesday
        # Thursday is Nov 18, so Tuesday is Nov 23, Wednesday is Nov 24
        # Tuesday afternoon client meetings (2pm and 3:30pm)
        tuesday_meeting_1 = CalendarEvent(
            title="Client Meeting - Startup.io Q4 Planning",
            start_datetime=datetime(2025, 11, 23, 14, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 11, 23, 15, 0, 0, tzinfo=UTC).timestamp(),
            location="Office Conference Room A",
            attendees=["jennifer.adams@startup.io"],
            description="Quarterly planning session with Jennifer Adams",
        )

        tuesday_meeting_2 = CalendarEvent(
            title="Budget Review Meeting",
            start_datetime=datetime(2025, 11, 23, 15, 30, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 11, 23, 16, 30, 0, tzinfo=UTC).timestamp(),
            location="Office Conference Room B",
            description="Review Q4 budget and projections",
        )

        # Wednesday morning vendor site visit
        wednesday_site_visit = CalendarEvent(
            title="Vendor Site Visit - Riverside Venue",
            start_datetime=datetime(2025, 11, 24, 9, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 11, 24, 11, 0, 0, tzinfo=UTC).timestamp(),
            location="Riverside Event Venue, 123 River Rd",
            attendees=["david.r@supplier.net"],
            description="Site inspection for upcoming client event",
        )

        self.calendar.add_event(tuesday_meeting_1)
        self.calendar.add_event(tuesday_meeting_2)
        self.calendar.add_event(wednesday_site_visit)

        # Populate messaging app with catering partner thread
        # Initialize the catering partner contact in messaging
        self.messaging.add_contacts([("Michael Chen", "+1-555-0202")])

        # Create a conversation with the catering partner (existing thread from past collaborations)
        catering_conversation = ConversationV2(
            participant_ids=["+1-555-0202"],
            title="Michael Chen",
            last_updated=datetime(2025, 11, 17, 16, 30, 0, tzinfo=UTC).timestamp(),
        )

        # Add a previous message from past week
        previous_message = MessageV2(
            sender_id="+1-555-0202",
            content="Thanks for coordinating the corporate lunch event last week! Everything went smoothly.",
            timestamp=datetime(2025, 11, 11, 10, 0, 0, tzinfo=UTC).timestamp(),
        )
        catering_conversation.messages.append(previous_message)

        # Add the conversation to messaging app
        self.messaging.conversations[catering_conversation.conversation_id] = catering_conversation

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.calendar, self.messaging, self.contacts]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")

        with EventRegisterer.capture_mode():
            # TODO: Add environment events here

            # TODO: Add oracle events here
            # -- Agent will detect environment events, check App state changes(if necessary), send proposal to user via aui.send_message_to_user(...)
            # -- User will choose to accept the Agent proposal via aui.accept_proposal(...)
            # -- Agent will again detect environment events(if has), check App state changes(if necessary), and interacts with available methods in Apps based on its findings

            pass

        # TODO: Register ALL events here in self.events
        self.events: list[Event] = []

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # TODO: Check Step 1: Agent sent proposal to the user
            # example: proposal_found = ...

            # TODO: Check Step 2(contains one or more checks based on Agent detections): Agent detected one or more app states according to previous happened environment events
            # example: detect_action1_found = ...

            # TODO: Check Step 3(contains one or more checks based on Agent actions): Agent's actions -- Agent interacted with methods in Apps based on previous findings
            # example: execute_action1_found = ...

            # TODO: get the success result
            # example: success = (proposal_found and detect_action1_found and execute_action1_found and ...)
            success = True
            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
