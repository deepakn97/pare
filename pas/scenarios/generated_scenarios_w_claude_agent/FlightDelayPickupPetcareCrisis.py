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
from are.simulation.types import AbstractEnvironment, Action, Event, EventRegisterer, EventType

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


@register_scenario("flight_delay_pickup_petcare_crisis")
class FlightDelayPickupPetcareCrisis(PASScenario):
    """The user receives an email notification from their airline that their return flight home has been delayed by six hours due to mechanical issues, pushing their arrival from 4 PM to 10 PM on Sunday evening. Their calendar shows their friend is scheduled to pick them up at the airport at 4:30 PM, and they have a dog boarding pickup appointment at the kennel for 5 PM the same day, with the kennel's contact notes indicating they close at 6 PM on Sundays and charge overtime fees after that. A messaging thread with their friend from two days ago mentions the friend has dinner plans Sunday night at 7 PM that they're really excited about. The user's contacts app contains an alternate emergency contact who lives near the kennel, the kennel manager's direct line, and their pet sitter who has keys to their home.

    The proactive agent detects the flight delay email and cross-references the new 10 PM arrival time against the calendar commitments, immediately recognizing a cascade of failures: the friend's pickup plan now conflicts with their dinner reservation, and more critically, the kennel pickup becomes impossible since the facility closes four hours before the user can arrive. The agent identifies from messaging context that asking the friend to wait six additional hours would ruin their evening plans, creating social friction. It recognizes the time-sensitive pet care obligation requires immediate alternative arrangements, as kennels enforce strict pickup policies and the dog cannot stay overnight without prior authorization.

    The agent proactively offers to send a message to the friend explaining the delay and releasing them from pickup duty while expressing appreciation, draft an email to the airline requesting meal vouchers or rebooking options, compose an urgent message to the emergency contact asking if they can pick up the dog from the kennel before 6 PM and either keep the dog overnight or meet the pet sitter to hand over keys, contact the pet sitter to arrange meeting the emergency contact and staying with the dog until the user arrives late that night, and update the calendar with the new flight time plus coordination checkpoints. The user accepts this multi-party crisis response, recognizing the agent understood the time-critical pet welfare priority, social relationship preservation, and the need to coordinate three different people to solve a problem the user cannot physically address while traveling..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with baseline data for flight delay scenario."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.contacts = StatefulContactsApp(name="Contacts")
        self.messaging = StatefulMessagingApp(name="Messages")
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.email = StatefulEmailApp(name="Emails")

        # Populate contacts: friend who will pick up user, emergency contact, pet sitter, kennel manager
        friend_contact = Contact(
            first_name="Alex",
            last_name="Chen",
            phone="+1-555-0101",
            email="alex.chen@email.com",
            description="Close friend, has dinner plans Sunday at 7 PM",
        )
        self.contacts.add_contact(friend_contact)

        emergency_contact = Contact(
            first_name="Jordan",
            last_name="Rivera",
            phone="+1-555-0202",
            email="jordan.rivera@email.com",
            description="Emergency contact, lives near Paws & Claws Kennel",
        )
        self.contacts.add_contact(emergency_contact)

        pet_sitter_contact = Contact(
            first_name="Sam",
            last_name="Taylor",
            phone="+1-555-0303",
            email="sam.taylor@petsitting.com",
            description="Professional pet sitter, has keys to user's home",
        )
        self.contacts.add_contact(pet_sitter_contact)

        kennel_contact = Contact(
            first_name="Morgan",
            last_name="Lee",
            phone="+1-555-0404",
            email="morgan@pawsandclaws.com",
            description="Manager at Paws & Claws Kennel, closes at 6 PM Sundays",
        )
        self.contacts.add_contact(kennel_contact)

        user_contact = Contact(
            first_name="User",
            last_name="Person",
            phone="+1-555-0000",
            email="user@email.com",
            is_user=True,
        )
        self.contacts.add_contact(user_contact)

        # Populate messaging: conversation with friend from two days ago mentioning dinner plans
        self.messaging.current_user_id = "+1-555-0000"
        self.messaging.current_user_name = "User Person"
        self.messaging.add_contacts([
            ("Alex Chen", "+1-555-0101"),
            ("Jordan Rivera", "+1-555-0202"),
            ("Sam Taylor", "+1-555-0303"),
        ])

        # Create conversation with friend about pickup, mentioning their dinner plans
        friend_conv = ConversationV2(
            participant_ids=["+1-555-0000", "+1-555-0101"],
            title="Alex Chen",
            conversation_id="conv_friend_pickup",
            last_updated=self.start_time - 172800,  # 2 days ago
        )
        friend_conv.messages.append(
            MessageV2(
                sender_id="+1-555-0000",
                content="Hey Alex! My flight gets in at 4 PM on Sunday. Could you pick me up at the airport around 4:30 PM?",
                timestamp=self.start_time - 172800,
            )
        )
        friend_conv.messages.append(
            MessageV2(
                sender_id="+1-555-0101",
                content="Absolutely! 4:30 works perfectly. I have dinner plans at 7 that evening but plenty of time to get you home first. Really excited about this new restaurant!",
                timestamp=self.start_time - 172500,
            )
        )
        friend_conv.messages.append(
            MessageV2(
                sender_id="+1-555-0000",
                content="Perfect, thank you so much! That should give you plenty of time.",
                timestamp=self.start_time - 172200,
            )
        )
        self.messaging.add_conversation(friend_conv)

        # Populate calendar: airport pickup appointment and kennel pickup appointment
        # Friend picking up user at 4:30 PM Sunday
        airport_pickup_event = CalendarEvent(
            event_id="event_airport_pickup",
            title="Alex picking me up from airport",
            start_datetime=self.start_time + 28800,  # Sunday 4:30 PM (9 AM + 7.5 hours)
            end_datetime=self.start_time + 30600,  # 30 min duration
            location="Airport Arrivals",
            description="Alex Chen picking me up, original flight arrival 4 PM",
            attendees=["Alex Chen"],
        )
        self.calendar.add_event(airport_pickup_event)

        # Dog pickup from kennel at 5 PM Sunday (closes at 6 PM)
        kennel_pickup_event = CalendarEvent(
            event_id="event_kennel_pickup",
            title="Pick up Max from Paws & Claws Kennel",
            start_datetime=self.start_time + 28800 + 1800,  # Sunday 5:00 PM
            end_datetime=self.start_time + 28800 + 3600,  # 30 min duration
            location="Paws & Claws Kennel, 123 Oak Street",
            description="Kennel closes at 6 PM on Sundays. Overtime fees after closing.",
            attendees=["Morgan Lee"],
        )
        self.calendar.add_event(kennel_pickup_event)

        # Populate email: no baseline emails needed (flight delay will arrive as environment event)
        self.email.user_email = "user@email.com"

        # Register all apps
        self.apps = [
            self.agent_ui,
            self.system_app,
            self.contacts,
            self.messaging,
            self.calendar,
            self.email,
        ]

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
            # Environment Event 1: Flight delay notification email arrives
            # Purpose: Trigger the cascade - user's arrival time changes from 4 PM to 10 PM
            flight_delay_event = email_app.send_email_to_user_with_id(
                email_id="email_flight_delay",
                sender="notifications@skylineairlines.com",
                subject="Flight Delay Notification - Flight SL2847",
                content="Dear Passenger,\n\nWe regret to inform you that your return flight SL2847 scheduled to arrive at 4:00 PM today has been delayed by 6 hours due to mechanical issues. Your new estimated arrival time is 10:00 PM.\n\nWe apologize for any inconvenience this may cause. Please contact us if you need assistance with connections or ground transportation.\n\nSkyline Airlines Customer Service",
            ).delayed(20)

            # Oracle Event 1: Agent checks calendar for conflicts with new arrival time
            # Purpose: Agent discovers two appointments that conflict with delayed arrival
            check_calendar_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-18 16:00:00",  # Original 4 PM arrival
                    end_datetime="2025-11-18 22:00:00",  # New 10 PM arrival window
                )
                .oracle()
                .depends_on(flight_delay_event, delay_seconds=2)
            )

            # Oracle Event 2: Agent checks messaging history with friend to understand constraints
            # Purpose: Agent reads conversation to see friend's 7 PM dinner plans
            check_messages_event = (
                messaging_app.read_conversation(conversation_id="conv_friend_pickup")
                .oracle()
                .depends_on(check_calendar_event, delay_seconds=1)
            )

            # Oracle Event 3: Agent sends comprehensive proposal to user
            # Purpose: Propose multi-party coordination plan to handle the crisis
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed your flight is delayed 6 hours (now arriving 10 PM instead of 4 PM). This creates a cascade of conflicts:\n\n"
                    "1. Alex can't pick you up at 4:30 PM anymore - and waiting until 10 PM would ruin their 7 PM dinner plans\n"
                    "2. You can't pick up Max from the kennel at 5 PM - they close at 6 PM and you won't arrive until 10 PM\n\n"
                    "I can help coordinate an alternative plan:\n"
                    "- Message Alex to release them from pickup duty (with appreciation)\n"
                    "- Contact Jordan (your emergency contact near the kennel) to pick up Max before 6 PM\n"
                    "- Arrange with Sam (your pet sitter) to meet Jordan and stay with Max until you get home\n"
                    "- Update your calendar with the new arrival time\n"
                    "- Draft an email to the airline requesting compensation\n\n"
                    "Would you like me to coordinate all of this?"
                )
                .oracle()
                .depends_on(check_messages_event, delay_seconds=3)
            )

            # Oracle Event 4: User accepts the comprehensive plan
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please do all of that! This is exactly what I need. Make sure Jordan and Sam can coordinate the dog handoff."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent messages friend to release them from pickup duty
            # Purpose: Preserve social relationship by being considerate of friend's plans
            message_friend_event = (
                messaging_app.send_message(
                    user_id="+1-555-0101",
                    content="Hi Alex! Bad news - my flight got delayed by 6 hours and won't arrive until 10 PM now. I know you have dinner plans at 7, so please don't worry about picking me up! I really appreciate you offering to help. Enjoy your dinner at that new restaurant!",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent messages emergency contact about urgent dog pickup
            # Purpose: Solve the critical pet care problem before kennel closes
            message_jordan_event = (
                messaging_app.send_message(
                    user_id="+1-555-0202",
                    content="Hi Jordan! I have an urgent favor to ask. My flight got delayed and I won't be back until 10 PM, but I need to pick up my dog Max from Paws & Claws Kennel by 6 PM (they close then). You're listed as my emergency contact and you live near the kennel. Could you possibly pick up Max for me? My pet sitter Sam will meet you to take Max to my place and stay with him until I get home. Please let me know ASAP!",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 7: Agent messages pet sitter to coordinate with emergency contact
            # Purpose: Ensure dog has proper care until user arrives home late
            message_petsitter_event = (
                messaging_app.send_message(
                    user_id="+1-555-0303",
                    content="Hi Sam! My flight is delayed until 10 PM tonight and I need your help. I've asked Jordan Rivera (emergency contact) to pick up Max from the kennel before 6 PM closing. Can you meet Jordan at the kennel around 5:30-6 PM to get Max, then stay with him at my place until I arrive around 11 PM? I'll pay you for the extra hours. Let me know if this works!",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 8: Agent updates calendar - edit airport pickup to new time
            # Purpose: Keep calendar accurate with new arrival time
            update_pickup_event = (
                calendar_app.edit_calendar_event(
                    event_id="event_airport_pickup",
                    start_datetime="2025-11-18 22:00:00",  # New 10 PM arrival
                    end_datetime="2025-11-18 22:30:00",
                    title="DELAYED: Arriving at airport (arrange ride)",
                )
                .oracle()
                .depends_on(message_friend_event, delay_seconds=1)
            )

            # Oracle Event 9: Agent updates calendar - edit kennel pickup to show Jordan handling it
            # Purpose: Reflect the alternate arrangement in calendar
            update_kennel_event = (
                calendar_app.edit_calendar_event(
                    event_id="event_kennel_pickup",
                    title="Jordan picking up Max from kennel (emergency backup)",
                    attendees=["Jordan Rivera", "Sam Taylor"],
                )
                .oracle()
                .depends_on(message_jordan_event, delay_seconds=1)
            )

            # Oracle Event 10: Agent drafts email to airline requesting compensation
            # Purpose: Help user get meal vouchers/rebooking options for the delay
            airline_compensation_event = (
                email_app.reply_to_email(
                    email_id="email_flight_delay",
                    content="Dear Skyline Airlines,\n\nThank you for notifying me about the 6-hour delay on Flight SL2847. This significant delay has caused multiple scheduling conflicts and I had to arrange emergency backup for pet care that I cannot personally handle due to being stranded at the airport.\n\nI would like to request:\n1. Meal vouchers for the extended wait time\n2. Information about rebooking options if earlier flights become available\n3. Compensation for the inconvenience as this delay exceeds your service guarantee\n\nPlease advise on what assistance you can provide.\n\nBest regards,\nUser Person\nConfirmation: SL2847",
                )
                .oracle()
                .depends_on(update_pickup_event, delay_seconds=2)
            )

        # Register ALL events here in self.events
        self.events: list[Event] = [
            flight_delay_event,
            check_calendar_event,
            check_messages_event,
            proposal_event,
            acceptance_event,
            message_friend_event,
            message_jordan_event,
            message_petsitter_event,
            update_pickup_event,
            update_kennel_event,
            airline_compensation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent sent comprehensive proposal to user
            # Strict check: must identify flight delay, cascade conflicts, and multi-party coordination plan
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "10 PM" in e.action.args.get("content", "")
                and "Alex" in e.action.args.get("content", "")
                and "Max" in e.action.args.get("content", "")
                and (
                    "Jordan" in e.action.args.get("content", "")
                    or "emergency contact" in e.action.args.get("content", "")
                )
                and "Sam" in e.action.args.get("content", "")
                for e in log_entries
            )

            # Check Step 2a: Agent detected calendar conflicts by querying calendar events
            # Flexible check: agent must retrieve calendar events in the affected time window
            calendar_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "get_calendar_events_from_to"
                for e in log_entries
            )

            # Check Step 2b: Agent checked messaging history to understand friend's constraints
            # Flexible check: agent must read the conversation with friend Alex
            message_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "read_conversation"
                and "conv_friend_pickup" in str(e.action.args.get("conversation_id", ""))
                for e in log_entries
            )

            # Check Step 3a: Agent messaged friend Alex to release them from pickup duty
            # Strict check: must mention delay and friend's dinner plans
            message_friend_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == "+1-555-0101"
                and "delay" in e.action.args.get("content", "").lower()
                and "10" in e.action.args.get("content", "")
                for e in log_entries
            )

            # Check Step 3b: Agent contacted emergency contact Jordan about urgent dog pickup
            # Strict check: must explain urgency and mention 6 PM closing time
            message_jordan_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == "+1-555-0202"
                and "Max" in e.action.args.get("content", "")
                and "6 PM" in e.action.args.get("content", "")
                for e in log_entries
            )

            # Check Step 3c: Agent coordinated with pet sitter Sam
            # Strict check: must mention meeting Jordan and staying with dog
            message_petsitter_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == "+1-555-0303"
                and "Jordan" in e.action.args.get("content", "")
                and "Max" in e.action.args.get("content", "")
                for e in log_entries
            )

            # Check Step 3d: Agent updated airport pickup calendar event with new arrival time
            # Strict check: must update event_airport_pickup to reflect 10 PM arrival
            update_pickup_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "edit_calendar_event"
                and e.action.args.get("event_id") == "event_airport_pickup"
                and "22:00:00" in str(e.action.args.get("start_datetime", ""))
                for e in log_entries
            )

            # Check Step 3e: Agent updated kennel pickup calendar event to reflect Jordan handling it
            # Flexible check: must edit the kennel pickup event
            update_kennel_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "edit_calendar_event"
                and e.action.args.get("event_id") == "event_kennel_pickup"
                for e in log_entries
            )

            # Check Step 3f: Agent drafted compensation email to airline
            # Flexible check: must reply to the flight delay email
            airline_email_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == "email_flight_delay"
                for e in log_entries
            )

            # Check Step 4: User accepted the proposal
            # Strict check: user must have explicitly accepted via accept_proposal
            acceptance_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "accept_proposal"
                for e in log_entries
            )

            # Success requires: proposal sent, calendar/message detection occurred,
            # core crisis actions (Jordan + Sam messages + calendar updates) executed, and user acceptance
            success = (
                proposal_found
                and calendar_check_found
                and message_check_found
                and message_jordan_found
                and message_petsitter_found
                and update_pickup_found
                and update_kennel_found
                and acceptance_found
            )

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
