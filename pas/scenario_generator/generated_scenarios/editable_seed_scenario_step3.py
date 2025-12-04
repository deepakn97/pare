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


@register_scenario("original_scenario_id_step3")
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
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")

        # Get the conversation ID for the catering partner
        catering_conversation_id = None
        for conv_id, conv in messaging_app.conversations.items():
            if "+1-555-0202" in conv.participant_ids:
                catering_conversation_id = conv_id
                break

        with EventRegisterer.capture_mode():
            # Environment Event 1: Urgent email arrives from corporate client requesting retreat proposal
            event_1 = email_app.send_email_to_user_with_id(
                email_id="corp_retreat_request_001",
                sender="sarah.mitchell@techcorp.com",
                subject="URGENT: Team Building Retreat Proposal Needed - Nov 23-25",
                content="""Hi,

I hope this email finds you well. We have an urgent request for a team-building retreat for our engineering team.

Details:
- Dates: Tuesday, November 23 through Thursday, November 25
- Attendees: 12 people
- Dietary restrictions: 3 vegetarian, 1 vegan, 2 gluten-free
- Location: Within 50 miles of the city
- Budget: Flexible for quality venue and catering

Could you please send us a proposal with venue suggestions and estimated costs by end of day? We're eager to move forward quickly.

Best regards,
Sarah Mitchell
HR Director, TechCorp Inc.
sarah.mitchell@techcorp.com""",
            )

            # Environment Event 2: Message from catering partner about availability
            catering_message_event = messaging_app.create_and_add_message(
                conversation_id=catering_conversation_id,
                sender_id="+1-555-0202",
                content="Hey! Just wanted to reach out - we had a large event cancel for next week and now have unexpected availability Monday through Sunday. Do you have any upcoming events that need food services? Would love to work with you again!",
            ).delayed(30 * 60)

            # Oracle Event 1: Agent detects the conflict and opportunity, sends proposal to user
            oracle_proposal = aui.send_message_to_user(
                content="""I've noticed an urgent retreat request from TechCorp that conflicts with your existing schedule:

**Conflict Analysis:**
- Requested dates: Tue Nov 23 - Thu Nov 25
- Your conflicts:
  • Tuesday 2:00 PM - Client Meeting (Startup.io)
  • Tuesday 3:30 PM - Budget Review Meeting
  • Wednesday 9:00 AM - Vendor Site Visit (Riverside Venue)

**Opportunity:**
- Your catering partner Michael just messaged about unexpected availability next week

**Proposed Solution:**
I can draft a response to Sarah Mitchell proposing alternative dates (Fri Nov 26 - Sun Nov 28) that avoid your conflicts, while simultaneously confirming availability with Michael for the adjusted dates. This maintains professionalism and leverages the timely catering opportunity.

Would you like me to prepare both messages?"""
            ).delayed(5 * 60)

            # Oracle Event 2: User accepts the proposal
            oracle_acceptance = aui.accept_proposal(
                content="Yes, please draft both messages. For the client email, also mention that I can suggest Lakeview Lodge and Mountain Retreat Center as venue options within their 50-mile radius."
            ).delayed(2 * 60)

            # Oracle Event 3: Agent drafts and sends reply to corporate client
            agent_reply_to_client = email_app.reply_to_email(
                email_id="corp_retreat_request_001",
                folder_name="INBOX",
                content="""Dear Sarah,

Thank you for reaching out about the team-building retreat for your engineering team. I appreciate the detailed information about your requirements.

After reviewing my calendar, I have existing client commitments on Tuesday afternoon (November 23) and Wednesday morning (November 24) that would impact my ability to provide full on-site coordination during those dates.

I'd like to propose alternative dates that would allow me to give your retreat my complete attention: Friday, November 26 through Sunday, November 28. This weekend timeframe often works well for team-building activities and would ensure seamless coordination.

For venues within 50 miles that can accommodate your group of 12 with the dietary requirements you specified, I recommend:
- Lakeview Lodge: Excellent facilities with full catering kitchen
- Mountain Retreat Center: Beautiful setting with experienced dietary accommodation

I have confirmed availability with my trusted catering partner who can expertly handle the vegetarian, vegan, and gluten-free requirements for your team.

Would these alternative dates work for your team? I can provide detailed proposals with pricing for both venues by tomorrow morning.

Best regards,
Event Planning Professional""",
            ).delayed(3 * 60)

            # Oracle Event 4: Agent sends message to catering partner
            agent_message_to_caterer = messaging_app.send_message(
                user_id="+1-555-0202",
                content="Perfect timing! I have a potential corporate retreat for 12 people, Friday Nov 26 through Sunday Nov 28. Dietary needs: 3 vegetarian, 1 vegan, 2 gluten-free. Can you confirm your availability for those dates? Will send more details once client confirms.",
            ).delayed(2 * 60)

        # TODO: Register ALL events here in self.events
        self.events: list[Event] = [
            event_1,
            catering_message_event,
            oracle_proposal,
            oracle_acceptance,
            agent_reply_to_client,
            agent_message_to_caterer,
        ]

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
