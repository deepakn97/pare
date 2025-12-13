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


@register_scenario("restaurant_booking_conflict")
class RestaurantBookingConflict(PASScenario):
    """The user has scheduled a dinner meeting with an important client on Thursday evening at 7 PM, confirmed via a calendar event that includes the client as an attendee and lists the restaurant name in the location field. Earlier that day, the user receives an email from the restaurant apologizing for a system error and explaining that their reservation was accidentally double-booked; the restaurant offers alternative time slots at 5:30 PM or 9 PM the same evening, or the original 7 PM slot on a different day. Meanwhile, a message thread with the client shows they have explicitly mentioned Thursday evening works best for their schedule and that they are flying out Friday morning.

    The proactive assistant should detect this conflict by correlating the calendar event details with the incoming email notification about the booking error. It should infer that the user needs to either reschedule the dinner to one of the offered alternative slots or find a different restaurant entirely, while considering the client's travel constraints revealed in the messaging app. The agent should proactively offer to help by suggesting it can check the client's availability for the 5:30 PM slot via the calendar, draft a message to the client proposing the time change, or search for alternative restaurants if neither backup slot works.

    The user is expected to accept the assistance, directing the agent to either propose the earlier time slot to the client or help identify a comparable restaurant that can accommodate the original 7 PM booking, demonstrating the value of cross-app reasoning that connects email disruptions, calendar commitments, and conversational context about stakeholder preferences.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps here
        self.contacts = StatefulContactsApp(name="Contacts")
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.email = StatefulEmailApp(name="Emails")
        self.messaging = StatefulMessagingApp(name="Messages")

        # Populate apps with scenario specific data here

        # Contacts: Client contact
        client_contact = Contact(
            first_name="Sarah",
            last_name="Chen",
            email="sarah.chen@techcorp.com",
            phone="+1-555-0123",
            job="VP of Product",
            description="Important client from TechCorp",
        )
        self.contacts.add_contact(client_contact)

        # Calendar: Thursday dinner meeting at 7 PM
        # Thursday is Nov 20, 2025 (2 days after start_time)
        dinner_start = datetime(2025, 11, 20, 19, 0, 0, tzinfo=UTC).timestamp()
        dinner_end = datetime(2025, 11, 20, 21, 0, 0, tzinfo=UTC).timestamp()
        dinner_event = CalendarEvent(
            title="Dinner Meeting with Sarah Chen",
            start_datetime=dinner_start,
            end_datetime=dinner_end,
            location="La Bella Vista Restaurant",
            attendees=["Sarah Chen"],
            description="Client dinner to discuss Q1 partnership opportunities",
        )
        self.calendar.set_calendar_event(dinner_event)

        # Messaging: Pre-existing conversation with client showing Thursday preference
        self.messaging.add_users(["Sarah Chen"])
        client_user_id = self.messaging.name_to_id["Sarah Chen"]

        # Create conversation with message history
        conversation = ConversationV2(
            participant_ids=[client_user_id, self.messaging.current_user_id], title="Sarah Chen"
        )

        # Earlier message from client about Thursday preference (3 days ago)
        msg1_time = datetime(2025, 11, 15, 14, 30, 0, tzinfo=UTC).timestamp()
        msg1 = MessageV2(
            sender_id=client_user_id,
            content="Looking forward to our dinner meeting! Thursday evening works perfectly for my schedule.",
            timestamp=msg1_time,
        )
        conversation.messages.append(msg1)
        conversation.update_last_updated(msg1_time)

        # User's response
        msg2_time = datetime(2025, 11, 15, 14, 45, 0, tzinfo=UTC).timestamp()
        msg2 = MessageV2(
            sender_id=self.messaging.current_user_id,
            content="Great! I've made a reservation at La Bella Vista for 7 PM on Thursday. See you then!",
            timestamp=msg2_time,
        )
        conversation.messages.append(msg2)
        conversation.update_last_updated(msg2_time)

        # Client's confirmation mentioning flight
        msg3_time = datetime(2025, 11, 15, 15, 0, 0, tzinfo=UTC).timestamp()
        msg3 = MessageV2(
            sender_id=client_user_id,
            content="Perfect! That timing is crucial since I'm flying out Friday morning. Really appreciate you accommodating my tight schedule.",
            timestamp=msg3_time,
        )
        conversation.messages.append(msg3)
        conversation.update_last_updated(msg3_time)

        self.messaging.add_conversation(conversation)

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.calendar, self.email, self.messaging]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")

        with EventRegisterer.capture_mode():
            # Environment Event: Restaurant sends email about double-booking on Thursday morning (Nov 20)
            # This happens on the day of the dinner, giving urgency to the situation
            restaurant_email_event = email_app.send_email_to_user_with_id(
                email_id="email-restaurant-booking-conflict",
                sender="reservations@labellavista.com",
                subject="Important: Reservation Conflict - La Bella Vista",
                content="""Dear Valued Guest,

We sincerely apologize for the inconvenience, but we've discovered a system error that resulted in a double-booking for your reservation tonight, Thursday, November 20th at 7:00 PM.

We deeply regret this mistake and would like to offer you the following alternative options:

1. Same evening at 5:30 PM (earlier slot)
2. Same evening at 9:00 PM (later slot)
3. Original 7:00 PM time slot on a different day this week

Please let us know which option works best for you, or if you'd prefer to cancel. Again, we apologize for this error and any inconvenience it may cause.

Best regards,
La Bella Vista Reservations Team
reservations@labellavista.com""",
            ).delayed(20)

            # Oracle Event 1: Agent detects the conflict by correlating email with calendar event
            # and messaging context, then sends proactive proposal to user
            agent_proposal_event = (
                aui.send_message_to_user(
                    content="""I've detected an issue with your dinner meeting tonight. La Bella Vista just emailed about a double-booking conflict for your 7 PM reservation with Sarah Chen.

**Context:**
- Calendar: "Dinner Meeting with Sarah Chen" scheduled for tonight at 7 PM at La Bella Vista
- Messages: Sarah mentioned Thursday evening is crucial because she's flying out Friday morning
- Restaurant offers: 5:30 PM or 9 PM tonight, or 7 PM on a different day

**Recommendation:**
Given Sarah's Friday morning flight constraint, I suggest the 5:30 PM slot tonight to keep the Thursday evening timing she needs. The 9 PM slot might be too late, and moving to a different day won't work with her travel schedule.

Would you like me to:
1. Check if Sarah is available at 5:30 PM via your calendar
2. Draft a message to Sarah proposing the earlier time
3. Confirm the 5:30 PM slot with the restaurant

Or would you prefer I search for alternative restaurants that can accommodate 7 PM tonight?"""
                )
                .oracle()
                .depends_on(restaurant_email_event, delay_seconds=3)
            )

            # Oracle Event 2: User accepts the agent's proposal and chooses the 5:30 PM option
            user_acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please go with option 1. Check her calendar availability for 5:30 PM and draft a message to Sarah proposing the time change. Let's keep it at La Bella Vista since I know the menu there."
                )
                .oracle()
                .depends_on(agent_proposal_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent checks calendar for conflicts around 5:30 PM on Thursday Nov 20
            agent_check_calendar_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-20 17:00:00", end_datetime="2025-11-20 19:00:00"
                )
                .oracle()
                .depends_on(user_acceptance_event, delay_seconds=1)
            )

            # Oracle Event 4: Agent sends message to client via messaging app proposing new time
            client_user_id = messaging_app.name_to_id["Sarah Chen"]
            agent_message_to_client_event = (
                messaging_app.send_message(
                    user_id=client_user_id,
                    content="Hi Sarah, I need to reach out about our dinner tonight at La Bella Vista. The restaurant had a booking system error and our 7 PM reservation was double-booked. They've offered us a 5:30 PM slot instead - would that work for you? I know you mentioned Thursday evening is important with your Friday morning flight, so I wanted to keep it tonight. Let me know!",
                )
                .oracle()
                .depends_on(agent_check_calendar_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent replies to restaurant confirming the 5:30 PM slot
            agent_reply_to_restaurant_event = (
                email_app.reply_to_email(
                    email_id="email-restaurant-booking-conflict",
                    folder_name="INBOX",
                    content="""Hello,

Thank you for reaching out about the booking conflict. I understand these things happen.

I would like to take the 5:30 PM slot this evening (Thursday, November 20th) for 2 guests under the same name.

I've contacted my dining companion to confirm the time change. Please confirm this reservation is secured.

Thank you for your flexibility.

Best regards""",
                )
                .oracle()
                .depends_on(agent_message_to_client_event, delay_seconds=1)
            )

        # TODO: Register ALL events here in self.events
        self.events: list[Event] = [
            restaurant_email_event,
            agent_proposal_event,
            user_acceptance_event,
            agent_check_calendar_event,
            agent_message_to_client_event,
            agent_reply_to_restaurant_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent sent proactive proposal to user about the restaurant booking conflict
            # Expected: PASAgentUserInterface.send_message_to_user containing correlation of email/calendar/messaging
            # Strict check: Agent must mention the restaurant conflict, calendar event, and client's travel constraint
            proposal_found = any(
                "send_message_to_user" in str(entry)
                and any(
                    keyword in str(entry).lower()
                    for keyword in ["la bella vista", "restaurant", "double-book", "conflict", "reservation"]
                )
                and any(keyword in str(entry).lower() for keyword in ["sarah", "client", "chen"])
                and any(keyword in str(entry).lower() for keyword in ["calendar", "dinner meeting", "7 pm"])
                for entry in log_entries
            )

            # Check Step 2: User accepted the agent's proposal
            # Expected: PASAgentUserInterface.accept_proposal indicating user wants agent to proceed
            # Strict check: This oracle event must exist to demonstrate user engagement
            acceptance_found = any(
                "accept_proposal" in str(entry)
                and any(keyword in str(entry).lower() for keyword in ["5:30", "calendar", "message", "sarah"])
                for entry in log_entries
            )

            # Check Step 3: Agent checked calendar for availability at the alternative time slot
            # Expected: StatefulCalendarApp.get_calendar_events_from_to for 5:30 PM slot verification
            # Flexible check: Agent may use various calendar query methods to verify availability
            calendar_check_found = any(
                ("get_calendar_events" in str(entry) or "calendar" in str(entry).lower())
                and any(time_keyword in str(entry) for time_keyword in ["17:00", "17:30", "5:30", "19:00"])
                for entry in log_entries
            )

            # Check Step 4: Agent sent message to client (Sarah Chen) proposing the time change
            # Expected: StatefulMessagingApp.send_message to the client's user_id
            # Strict check: Must send message and should mention the time change (5:30 PM)
            client_message_found = any(
                "send_message" in str(entry)
                and "Messages" in str(entry)
                and any(keyword in str(entry).lower() for keyword in ["sarah", "dinner", "restaurant"])
                and any(keyword in str(entry).lower() for keyword in ["5:30", "time", "slot", "reschedule"])
                for entry in log_entries
            )

            # Check Step 5: Agent replied to restaurant email confirming the new reservation
            # Expected: StatefulEmailApp.reply_to_email with email_id="email-restaurant-booking-conflict"
            # Strict check: Must reply to the specific restaurant email and confirm a time slot
            restaurant_reply_found = any(
                "reply_to_email" in str(entry)
                and "email-restaurant-booking-conflict" in str(entry)
                and any(
                    keyword in str(entry).lower() for keyword in ["5:30", "confirm", "reservation", "accept", "take"]
                )
                for entry in log_entries
            )

            # Success requires all critical steps: proposal, acceptance, and all three agent actions
            # All checks are required because this demonstrates full cross-app reasoning capability
            success = (
                proposal_found
                and acceptance_found
                and calendar_check_found
                and client_message_found
                and restaurant_reply_found
            )

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
