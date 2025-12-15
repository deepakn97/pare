"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
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


@register_scenario("lease_renewal_roommate_departure")
class LeaseRenewalRoommateDeparture(PASScenario):
    """The user receives an email from their apartment property management on October 15th stating that their annual lease expires November 30th and they must decide by October 31st whether to renew for another year or provide 60-day notice to vacate. The email mentions that rent will increase by 12% if they renew, and that the landlord needs to know the exact number of occupants for the new lease term. The user's calendar shows they've been living with a roommate whose contact details note they split rent 50/50. Three days after the landlord's email arrives, the user receives a message from their roommate apologizing for short notice and explaining they've accepted a job in another city starting December 15th, so they'll be moving out and cannot sign a lease renewal.

    The proactive agent detects the landlord's renewal deadline and correlates it with the roommate's departure announcement in the messaging thread. It recognizes a cascading financial decision: the user must choose within two weeks whether to find a replacement roommate to maintain affordability, negotiate with the landlord to move into a smaller unit at lower cost, or commit to paying the full increased rent alone. The agent identifies from the calendar and contacts that the roommate's mid-December departure creates a timing gap where the user would need to cover full rent for the last two weeks of their current lease if they choose to stay, and notes the 60-day notice requirement means delaying the decision eliminates the option to leave without penalty.

    The agent proactively offers to draft an email to the property management requesting an extension of the decision deadline given the unexpected roommate situation and asking whether a smaller unit is available at the current rental rate, compose a message to the roommate asking them to confirm their exact move-out date and whether they're willing to help find a replacement tenant, search the user's messaging history for friends who have previously mentioned looking for housing or might know prospective roommates, and create a calendar timeline showing the October 31st decision deadline, November 30th lease end, December 15th roommate departure, and key financial milestones. The user accepts this housing crisis coordination, recognizing the agent connected lease obligations, financial constraints, relationship dynamics, and time-sensitive institutional deadlines into a structured decision framework that preserves multiple options while respecting both landlord requirements and roommate circumstances..
    """

    start_time = datetime(2025, 10, 15, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with baseline data for lease renewal scenario."""
        # Initialize all apps
        self.email = StatefulEmailApp(name="Emails")
        self.messaging = StatefulMessagingApp(name="Messages")
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.contacts = StatefulContactsApp(name="Contacts")
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Populate contacts
        # Alex Martinez - roommate who will be moving out
        self.contacts.add_contact(
            Contact(
                first_name="Alex",
                last_name="Martinez",
                contact_id="contact-alex-martinez",
                email="alex.martinez@email.com",
                phone="555-123-4567",
                description="Current roommate, splits rent 50/50",
            )
        )

        # Sarah Park Properties - property management company contact
        self.contacts.add_contact(
            Contact(
                first_name="Sarah",
                last_name="Park",
                contact_id="contact-sarah-park",
                email="sarah.park@parkproperties.com",
                phone="555-987-6543",
                job="Property Manager",
                description="Property manager for apartment building",
            )
        )

        # Jamie Chen - friend who previously mentioned housing search
        self.contacts.add_contact(
            Contact(
                first_name="Jamie",
                last_name="Chen",
                contact_id="contact-jamie-chen",
                email="jamie.chen@email.com",
                phone="555-234-5678",
                description="Friend who was apartment hunting last year",
            )
        )

        # Populate calendar with existing rent payment reminders and lease end date
        self.calendar.add_calendar_event(
            title="Rent Payment Due",
            start_datetime="2025-11-01 09:00:00",
            end_datetime="2025-11-01 10:00:00",
            description="Monthly rent payment - current lease",
        )

        self.calendar.add_calendar_event(
            title="Current Lease Ends",
            start_datetime="2025-11-30 00:00:00",
            end_datetime="2025-11-30 23:59:00",
            description="Annual lease expiration date",
        )

        # Populate messaging with conversation history with roommate
        # Add Alex Martinez as a user in the messaging app
        self.messaging.add_users(["Alex Martinez"])
        alex_id = self.messaging.name_to_id["Alex Martinez"]

        # Create conversation history showing prior apartment-related discussions
        roommate_conv = ConversationV2(
            participant_ids=[alex_id, self.messaging.current_user_id],
            title="Alex Martinez",
        )

        # Past message about utilities split (September, 2 months ago)
        roommate_conv.messages.append(
            MessageV2(
                sender_id=alex_id,
                content="Hey, I just paid the electric bill. Your half is $45. Can you Venmo me?",
                timestamp=datetime(2025, 9, 15, 18, 30, 0, tzinfo=UTC).timestamp(),
            )
        )

        roommate_conv.messages.append(
            MessageV2(
                sender_id=self.messaging.current_user_id,
                content="Just sent it! Thanks for handling that.",
                timestamp=datetime(2025, 9, 15, 19, 0, 0, tzinfo=UTC).timestamp(),
            )
        )

        # Earlier message about apartment maintenance (August)
        roommate_conv.messages.append(
            MessageV2(
                sender_id=self.messaging.current_user_id,
                content="Did you report that leaky faucet to Sarah at the property office?",
                timestamp=datetime(2025, 8, 20, 10, 15, 0, tzinfo=UTC).timestamp(),
            )
        )

        roommate_conv.messages.append(
            MessageV2(
                sender_id=alex_id,
                content="Yeah, she said maintenance will come by Thursday.",
                timestamp=datetime(2025, 8, 20, 10, 45, 0, tzinfo=UTC).timestamp(),
            )
        )

        roommate_conv.last_updated = datetime(2025, 9, 15, 19, 0, 0, tzinfo=UTC).timestamp()
        self.messaging.add_conversation(roommate_conv)

        # Populate messaging with conversation history with Jamie Chen (friend who mentioned housing search)
        self.messaging.add_users(["Jamie Chen"])
        jamie_id = self.messaging.name_to_id["Jamie Chen"]

        jamie_conv = ConversationV2(
            participant_ids=[jamie_id, self.messaging.current_user_id],
            title="Jamie Chen",
        )

        # Message from last year where Jamie mentioned apartment hunting
        jamie_conv.messages.append(
            MessageV2(
                sender_id=jamie_id,
                content="Ugh, apartment hunting in this city is impossible! Everything's so expensive.",
                timestamp=datetime(2024, 11, 10, 14, 20, 0, tzinfo=UTC).timestamp(),
            )
        )

        jamie_conv.messages.append(
            MessageV2(
                sender_id=self.messaging.current_user_id,
                content="I know, right? We got lucky with our place. Good luck with the search!",
                timestamp=datetime(2024, 11, 10, 15, 0, 0, tzinfo=UTC).timestamp(),
            )
        )

        jamie_conv.last_updated = datetime(2024, 11, 10, 15, 0, 0, tzinfo=UTC).timestamp()
        self.messaging.add_conversation(jamie_conv)

        # Populate email with past lease-related correspondence (original lease signing confirmation)
        self.email.create_and_add_email_with_time(
            sender="sarah.park@parkproperties.com",
            recipients=[self.email.user_email],
            subject="Lease Agreement Confirmation - Unit 4B",
            content="Dear Tenant,\n\nThank you for signing your lease agreement for Unit 4B at Riverside Apartments. Your lease term is from December 1, 2024 to November 30, 2025. Monthly rent is $2,000.\n\nPlease don't hesitate to reach out if you have any questions.\n\nBest regards,\nSarah Park\nPark Properties Management",
            email_time="2024-11-25 10:00:00",
            folder_name="INBOX",
        )

        # Register all apps
        self.apps = [
            self.email,
            self.messaging,
            self.calendar,
            self.contacts,
            self.agent_ui,
            self.system_app,
        ]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Lease renewal email arrives from property management
            lease_email_event = email_app.send_email_to_user_with_id(
                email_id="email-lease-renewal",
                sender="sarah.park@parkproperties.com",
                subject="Lease Renewal Notice - Unit 4B - Action Required by October 31",
                content="Dear Tenant,\n\nYour current lease for Unit 4B at Riverside Apartments expires on November 30, 2025. Please notify us by October 31, 2025 whether you intend to renew or vacate.\n\nRenewal terms: 12-month lease, rent increases to $2,240/month (12% increase). We need confirmation of all occupants who will sign the new lease.\n\nIf vacating, 60-day notice is required per your lease agreement.\n\nPlease respond by October 31st.\n\nBest regards,\nSarah Park\nPark Properties Management",
            ).delayed(20)

            # Environment Event 2: Roommate announces departure (3 days later)
            alex_id = messaging_app.name_to_id["Alex Martinez"]
            roommate_conv_id = None
            for conv_id, conv in messaging_app.conversations.items():
                if alex_id in conv.participant_ids:
                    roommate_conv_id = conv_id
                    break

            roommate_message_event = messaging_app.create_and_add_message(
                conversation_id=roommate_conv_id,
                sender_id=alex_id,
                content="Hey, I need to tell you something important. I just accepted a job offer in Seattle and I'll be moving there by mid-December (around the 15th). I'm really sorry for the short notice, but I won't be able to renew the lease with you. I know the deadline is coming up soon. Let me know if there's anything I can do to help you figure things out.",
            ).delayed(3 * 24 * 3600)

            # Oracle Event 1: Agent sends proposal to user
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed you received a lease renewal notice requiring a decision by October 31st, and Alex just told you they're moving out in mid-December. This creates a time-sensitive housing decision with financial implications.\n\nWould you like me to help coordinate your response? I can draft an email to the property manager requesting a deadline extension and asking about smaller units, message Alex to confirm their move-out date, and search your messages for friends who might know prospective roommates."
                )
                .oracle()
                .depends_on(roommate_message_event, delay_seconds=10)
            )

            # Oracle Event 2: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please help me with this. I need to figure out my options quickly.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event 3: Agent drafts and sends email to property manager
            email_to_landlord_event = (
                email_app.reply_to_email(
                    email_id="email-lease-renewal",
                    folder_name="INBOX",
                    content="Dear Sarah,\n\nI received your lease renewal notice. My current roommate has just informed me they're relocating for work and will be moving out by December 15th.\n\nGiven this unexpected change, I'd like to request a brief extension on the October 31st decision deadline to explore my options. I'm also interested in knowing if any smaller (1-bedroom or studio) units are available at Riverside Apartments at or near my current rental rate of $2,000/month.\n\nI'd appreciate any flexibility you can offer as I navigate this situation.\n\nThank you,\n[User]",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent searches messaging history for housing leads
            search_messages_event = (
                messaging_app.search(
                    query="apartment housing roommate rent looking",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 5: Agent adds calendar event for decision deadline
            deadline_calendar_event = (
                calendar_app.add_calendar_event(
                    title="URGENT: Lease Decision Deadline",
                    start_datetime="2025-10-31 09:00:00",
                    end_datetime="2025-10-31 10:00:00",
                    description="Final day to notify property management about lease renewal or move-out. Alex moving out Dec 15. Options: find roommate, downsize, or pay full $2,240/mo alone.",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent sends confirmation summary to user
            summary_event = (
                aui.send_message_to_user(
                    content="I've taken the following actions:\n\n1. Emailed Sarah Park requesting a deadline extension and asking about smaller units\n2. Searched your messages for housing-related conversations (found past discussion with Jamie Chen about apartment hunting)\n3. Added October 31st lease decision deadline to your calendar\n\nNext steps to consider: confirm Alex's exact move-out date, reach out to Jamie or other contacts about roommate leads, and wait for Sarah's response about the extension."
                )
                .oracle()
                .depends_on(email_to_landlord_event, delay_seconds=3)
            )

        # Register ALL events
        self.events: list[Event] = [
            lease_email_event,
            roommate_message_event,
            proposal_event,
            acceptance_event,
            email_to_landlord_event,
            search_messages_event,
            deadline_calendar_event,
            summary_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent sent proposal mentioning the lease deadline and roommate situation
            # This is the core reasoning check - agent must recognize the conflict between lease deadline and roommate departure
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["lease", "renewal", "october 31", "deadline"]
                )
                and any(
                    keyword in e.action.args.get("content", "").lower() for keyword in ["alex", "roommate", "moving"]
                )
                for e in log_entries
            )

            # STRICT Check 2: Agent replied to the property management email requesting extension or asking about options
            # This is critical coordination - agent must contact the landlord
            email_to_landlord_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == "email-lease-renewal"
                for e in log_entries
            )

            # FLEXIBLE Check 3: Agent searched messages for housing-related conversations
            # The specific query terms are flexible, but the search action must occur
            message_search_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "search"
                and any(
                    keyword in str(e.action.args.get("query", "")).lower()
                    for keyword in ["apartment", "housing", "roommate", "rent", "looking"]
                )
                for e in log_entries
            )

            # STRICT Check 4: Agent created calendar reminder for the October 31st deadline
            # The deadline reminder is critical - but exact title/description wording is flexible
            calendar_reminder_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "2025-10-31" in e.action.args.get("start_datetime", "")
                and any(
                    keyword in e.action.args.get("title", "").lower()
                    for keyword in ["lease", "deadline", "decision", "renewal"]
                )
                for e in log_entries
            )

            # FLEXIBLE Check 5: Agent sent confirmation/summary message after taking actions
            # The presence of a follow-up message is good practice but exact content is flexible
            summary_message_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["email", "sarah", "calendar", "search"]
                )
                for e in log_entries
            )

            # Determine overall success: strict checks must pass, flexible checks are nice-to-have
            strict_checks = proposal_found and email_to_landlord_found and calendar_reminder_found
            flexible_checks = message_search_found and summary_message_found

            success = strict_checks

            # Build rationale if validation fails
            if not success:
                missing = []
                if not proposal_found:
                    missing.append("agent did not send proposal mentioning lease deadline and roommate situation")
                if not email_to_landlord_found:
                    missing.append("agent did not reply to property management email about lease renewal")
                if not calendar_reminder_found:
                    missing.append("agent did not create calendar reminder for October 31st deadline")
                rationale = "; ".join(missing) if missing else "validation failed"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
