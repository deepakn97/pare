"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.calendar import CalendarEvent
from are.simulation.apps.contacts import Contact
from are.simulation.apps.messaging import Conversation, Message
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


@register_scenario("package_delivery_access_coordination")
class PackageDeliveryAccessCoordination(PASScenario):
    """The user receives an email notification from a shipping carrier stating that a high-value package requiring signature confirmation will arrive on Tuesday between 1-5 PM at their home address. The user's calendar shows they have an all-day offsite work meeting on Tuesday located 45 minutes away from home, with no breaks scheduled. Their contacts app contains their building superintendent who holds spare keys, a trusted neighbor who has previously accepted packages for them, and the sender (their elderly parent) whose contact notes mention this package contains important estate documents that cannot be left unattended or rescheduled beyond this week due to legal deadlines. A messaging thread with the neighbor from last month shows they work from home on Tuesdays and Wednesdays.

    The proactive agent correlates the delivery window with the user's calendar absence and recognizes the signature requirement prevents standard drop-off solutions. It identifies from the email content and contact notes that the package has both high value and time sensitivity, making it critical to arrange authorized reception. By reviewing the messaging history, the agent discovers the neighbor's Tuesday work-from-home pattern aligns perfectly with the delivery window and recalls their previous willingness to help with package acceptance. The agent understands this requires coordination across multiple parties: authorizing the neighbor with the carrier, informing the sender that alternative arrangements are being made, and confirming the neighbor's availability.

    The agent proactively offers to draft a message to the neighbor asking if they can accept the signature-required delivery on Tuesday afternoon, compose an email to the shipping carrier providing the neighbor's name for authorized delivery release, send a reply to the parent explaining the secure reception arrangement to ease their concern about the documents, and add a calendar reminder to retrieve the package from the neighbor Tuesday evening. The user accepts this multi-party coordination plan, recognizing the agent successfully connected delivery logistics, legal urgency, trusted relationship context, and scheduling conflicts into a practical solution that ensures the time-sensitive documents are received securely despite their unavoidable absence..
    """

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
        self.contacts = StatefulContactsApp(name="Contacts")
        self.messaging = StatefulMessagingApp(name="Messages")

        # Populate contacts with parent (sender), neighbor (helper), and building superintendent
        # Parent - elderly, sender of the estate documents package
        self.contacts.add_contact(
            Contact(
                first_name="Margaret",
                last_name="Thompson",
                contact_id="contact-parent-margaret",
                email="margaret.thompson@email.com",
                phone="555-234-5678",
                age=72,
                description="Mom - sending important estate documents that must arrive this week due to legal deadlines. High priority package.",
            )
        )

        # Trusted neighbor - works from home on Tuesdays and Wednesdays
        self.contacts.add_contact(
            Contact(
                first_name="David",
                last_name="Chen",
                contact_id="contact-neighbor-david",
                email="david.chen@email.com",
                phone="555-345-6789",
                description="Neighbor in Apt 4B. Works from home Tuesdays and Wednesdays. Has previously helped with package deliveries.",
            )
        )

        # Building superintendent (additional backup contact)
        self.contacts.add_contact(
            Contact(
                first_name="Robert",
                last_name="Martinez",
                contact_id="contact-super-robert",
                email="robert.martinez@buildingmgmt.com",
                phone="555-456-7890",
                job="Building Superintendent",
                description="Building superintendent with spare keys to apartments. Available during business hours.",
            )
        )

        # Populate calendar with all-day offsite meeting on Tuesday, November 25th
        # User is away from home all day, 45 minutes away, no breaks
        tuesday_meeting_start = datetime(2025, 11, 25, 8, 0, 0, tzinfo=UTC).timestamp()
        tuesday_meeting_end = datetime(2025, 11, 25, 18, 0, 0, tzinfo=UTC).timestamp()

        self.calendar.events["event-offsite-meeting"] = CalendarEvent(
            event_id="event-offsite-meeting",
            title="Offsite Strategy Meeting - All Day",
            start_datetime=tuesday_meeting_start,
            end_datetime=tuesday_meeting_end,
            location="Downtown Conference Center (45 min from home)",
            description="Mandatory all-day offsite meeting with executive team. No breaks scheduled.",
            attendees=["Executive Team", "Department Heads"],
        )

        # Populate messaging with conversation history with David (neighbor)
        # Shows David works from home on Tuesdays/Wednesdays and has helped before
        neighbor_conversation_id = "conv-neighbor-david"

        # Create conversation with neighbor from last month
        last_month_timestamp = datetime(2025, 10, 15, 14, 30, 0, tzinfo=UTC).timestamp()

        neighbor_conversation = Conversation(
            conversation_id=neighbor_conversation_id,
            participants=["David Chen", "User"],
            title="David Chen",
            last_updated=last_month_timestamp,
            messages=[
                Message(
                    sender="User",
                    message_id="msg-user-1",
                    timestamp=datetime(2025, 10, 15, 14, 30, 0, tzinfo=UTC).timestamp(),
                    content="Hey David! I have a package coming tomorrow but I'll be at work. Would you be able to grab it if they leave it by my door?",
                ),
                Message(
                    sender="David Chen",
                    message_id="msg-david-1",
                    timestamp=datetime(2025, 10, 15, 14, 35, 0, tzinfo=UTC).timestamp(),
                    content="Sure, no problem! I work from home on Tuesdays and Wednesdays, so I'm usually here. Just let me know.",
                ),
                Message(
                    sender="User",
                    message_id="msg-user-2",
                    timestamp=datetime(2025, 10, 15, 14, 37, 0, tzinfo=UTC).timestamp(),
                    content="Perfect, thanks so much! I really appreciate it.",
                ),
                Message(
                    sender="David Chen",
                    message_id="msg-david-2",
                    timestamp=datetime(2025, 10, 15, 16, 45, 0, tzinfo=UTC).timestamp(),
                    content="Got your package! It's in front of your door. 📦",
                ),
            ],
        )

        self.messaging.conversations[neighbor_conversation_id] = neighbor_conversation

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.calendar, self.contacts, self.messaging]

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
            # Environment Event 1: Incoming delivery notification email from shipping carrier
            # This email contains critical information: signature required, Tuesday 1-5 PM delivery window,
            # and references the high-value estate documents from the parent
            delivery_email_event = email_app.send_email_to_user_with_id(
                email_id="email-delivery-notification",
                sender="notifications@rapidship.com",
                subject="Delivery Scheduled - Signature Required",
                content="Your package from Margaret Thompson is scheduled for delivery on Tuesday, November 25th between 1:00 PM - 5:00 PM. This package requires an adult signature for release. Tracking number: RS-2025-789456. The package contains important estate documents and cannot be left unattended. If you will not be available during the delivery window, you may authorize an alternate recipient by calling our customer service line or updating your delivery preferences online at rapidship.com/authorize.",
            ).delayed(30)

            # Oracle Event 2: Agent proactively detects the delivery conflict and offers multi-party coordination
            # Agent correlates: (1) delivery window conflicts with all-day meeting, (2) signature requirement,
            # (3) legal urgency from contact notes, (4) neighbor's Tuesday availability from messaging history,
            # (5) need to coordinate with carrier, neighbor, and parent
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed you have a delivery scheduled for Tuesday, November 25th between 1-5 PM that requires a signature. However, you have an all-day offsite meeting that day at the Downtown Conference Center. I see from your messaging history that your neighbor David Chen works from home on Tuesdays and has helped with packages before. I also noticed this package contains important estate documents from your mom with legal deadlines. Would you like me to: (1) message David to ask if he can accept the delivery, (2) email the shipping carrier to authorize David as an alternate recipient, (3) reply to your mom explaining the arrangement, and (4) add a calendar reminder for you to pick up the package from David Tuesday evening?"
                )
                .oracle()
                .depends_on(delivery_email_event, delay_seconds=3)
            )

            # Oracle Event 3: User accepts the comprehensive coordination plan
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, that would be perfect. Please coordinate all of that - I really appreciate you connecting all these pieces together."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent sends message to neighbor David requesting delivery assistance
            # The agent will naturally navigate to the messaging app and find the conversation
            send_neighbor_message_event = (
                messaging_app.send_message_to_group_conversation(
                    conversation_id="conv-neighbor-david",
                    content="Hi David! I have a bit of a favor to ask. I'm getting a delivery on Tuesday afternoon between 1-5 PM that requires a signature, but I'll be at an all-day meeting out of town. Would you be available to accept the package for me? It's important estate documents from my mom with a time-sensitive deadline. I'd really appreciate your help and can pick it up from you Tuesday evening. Let me know if that works!",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent replies to the shipping carrier with authorization for David
            # Using reply_to_email directly - agent will handle navigation to email detail view
            reply_carrier_event = (
                email_app.reply_to_email(
                    email_id="email-delivery-notification",
                    content="To Whom It May Concern,\n\nI am authorizing David Chen to accept delivery of package RS-2025-789456 scheduled for Tuesday, November 25th between 1-5 PM on my behalf. David Chen resides at the same building address and will provide signature confirmation. Please release the package to him.\n\nDavid Chen\nPhone: 555-345-6789\n\nThank you for your assistance.",
                )
                .oracle()
                .depends_on(send_neighbor_message_event, delay_seconds=3)
            )

            # Oracle Event 6: Agent sends new email to parent Margaret to reassure her
            # Using send_email directly - simpler than composing step-by-step
            send_parent_email_event = (
                email_app.send_email(
                    recipients=["margaret.thompson@email.com"],
                    subject="Re: Estate Document Delivery Arrangements",
                    content="Hi Mom,\n\nI wanted to let you know I've arranged for the estate documents to be received securely on Tuesday. I have an all-day work meeting that day, so I've coordinated with my neighbor David Chen to accept the signature-required delivery on my behalf. David is very trustworthy and has helped me with packages before. I've already notified the shipping carrier to authorize him.\n\nI'll pick up the documents from David Tuesday evening and will make sure everything is handled according to the legal deadlines. You don't need to worry - everything is taken care of.\n\nLove you!",
                )
                .oracle()
                .depends_on(reply_carrier_event, delay_seconds=3)
            )

            # Oracle Event 7: Agent adds calendar reminder to pick up package Tuesday evening
            add_reminder_event = (
                calendar_app.add_calendar_event(
                    title="Pick up estate documents package from David (Apt 4B)",
                    start_datetime="2025-11-25 18:30:00",
                    end_datetime="2025-11-25 19:00:00",
                    description="Retrieve important estate documents from neighbor David Chen who accepted the signature-required delivery. Package contains time-sensitive legal documents from Mom.",
                    location="David's apartment - 4B",
                )
                .oracle()
                .depends_on(send_parent_email_event, delay_seconds=2)
            )

            # Oracle Event 8: Agent confirms all coordination tasks completed
            completion_confirmation_event = (
                aui.send_message_to_user(
                    content="I've completed all the coordination for your Tuesday delivery:\n\n1. ✓ Sent message to David Chen asking if he can accept the delivery (mentioned the estate documents and time sensitivity)\n2. ✓ Emailed RapidShip carrier authorizing David as alternate recipient with his contact info\n3. ✓ Sent email to your mom explaining the secure arrangement so she won't worry\n4. ✓ Added calendar reminder for Tuesday 6:30 PM to pick up the package from David's apartment (4B)\n\nThe estate documents will be received safely despite your all-day meeting, and your mom will know the documents are being handled properly within the legal deadline."
                )
                .oracle()
                .depends_on(add_reminder_event, delay_seconds=2)
            )

        # TODO: Register ALL events here in self.events
        self.events: list[Event] = [
            delivery_email_event,
            proposal_event,
            acceptance_event,
            send_neighbor_message_event,
            reply_carrier_event,
            send_parent_email_event,
            add_reminder_event,
            completion_confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent sent comprehensive proposal mentioning the delivery conflict
            # Should reference David Chen (neighbor), Tuesday delivery window, and multi-party coordination
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "David" in e.action.args.get("content", "")
                and any(
                    keyword in e.action.args.get("content", "")
                    for keyword in ["Tuesday", "delivery", "signature", "November 25"]
                )
                for e in log_entries
            )

            # Check Step 2: Agent detected the calendar conflict by understanding the all-day meeting
            # This is implicit - validated by the comprehensive proposal mentioning the conflict
            # We check that the proposal mentions the offsite meeting or unavailability
            conflict_detection = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(
                    keyword in e.action.args.get("content", "")
                    for keyword in ["meeting", "offsite", "away", "not be available"]
                )
                for e in log_entries
            )

            # Check Step 3a: Agent sent message to neighbor David requesting delivery assistance
            neighbor_message_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message_to_group_conversation"
                and e.action.args.get("conversation_id") == "conv-neighbor-david"
                and any(
                    keyword in e.action.args.get("content", "")
                    for keyword in ["delivery", "package", "signature", "Tuesday"]
                )
                for e in log_entries
            )

            # Check Step 3b: Agent replied to shipping carrier authorizing David as alternate recipient
            carrier_authorization_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == "email-delivery-notification"
                and "David Chen" in e.action.args.get("content", "")
                and any(
                    keyword in e.action.args.get("content", "")
                    for keyword in ["authoriz", "accept delivery", "alternate recipient"]
                )
                for e in log_entries
            )

            # Check Step 3c: Agent sent email to parent Margaret explaining the secure arrangement
            parent_reassurance_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "send_email"
                and "margaret.thompson@email.com" in e.action.args.get("recipients", [])
                and any(
                    keyword in e.action.args.get("content", "")
                    for keyword in ["David", "neighbor", "arranged", "estate documents"]
                )
                for e in log_entries
            )

            # Check Step 3d: Agent added calendar reminder to pick up package Tuesday evening
            reminder_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "2025-11-25" in e.action.args.get("start_datetime", "")
                and any(
                    keyword in e.action.args.get("title", "").lower()
                    for keyword in ["pick up", "package", "david", "estate documents"]
                )
                for e in log_entries
            )

            # Strict checks: proposal, neighbor message, carrier authorization, and calendar reminder are critical
            # Flexible check: parent reassurance is important but not strictly required for functional success
            strict_success = (
                proposal_found
                and conflict_detection
                and neighbor_message_sent
                and carrier_authorization_sent
                and reminder_created
            )

            # Full success includes all coordinations including parent reassurance
            full_success = strict_success and parent_reassurance_sent

            # Return success if strict requirements are met (parent email is nice-to-have)
            success = strict_success
            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
