"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.calendar import CalendarEvent
from are.simulation.apps.contacts import Contact
from are.simulation.apps.email_client import Email
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


@register_scenario("warranty_recall_claim_coordination")
class WarrantyRecallClaimCoordination(PASScenario):
    """The user receives an email from a consumer electronics manufacturer announcing a voluntary recall for a laptop battery model due to fire risk, offering free replacement batteries to affected customers who purchased devices between specific dates. The user's email history contains the original purchase receipt from eighteen months ago showing they bought this exact model. Their calendar has an entry from three months ago titled "laptop battery draining fast - check warranty" that was never acted upon, with the manufacturer's customer service contact details attached. Meanwhile, a messaging thread with a tech-savvy friend discusses the recent battery performance issues and the friend mentions they successfully claimed warranty service for a different product by submitting photos and serial numbers through an online portal.

    The proactive agent correlates the recall announcement with the stored purchase receipt, confirming the user owns an affected unit within the specified manufacturing date range. It recognizes the calendar entry represents an unresolved complaint that now has an official remedy path through the recall program, and notes the user's original three-year warranty expires in six months, making this recall their last opportunity for free battery replacement. By analyzing the messaging thread, the agent learns the process requires documentation and that the friend's successful claim provides a template for navigating manufacturer support systems.

    The agent proactively offers to draft a recall claim email to the manufacturer including the purchase date and receipt details, create a checklist of required documentation based on the recall notice instructions, add a calendar reminder to follow up if replacement confirmation isn't received within two weeks, and send a message to the tech-savvy friend asking for tips on the submission portal they used successfully. The user accepts this consumer protection coordination, appreciating that the agent connected the safety recall with their documented battery complaints, purchase history, warranty timeline, and peer knowledge about claims processes into an actionable response plan..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with baseline data for warranty recall scenario."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Contacts app
        self.contacts = StatefulContactsApp(name="Contacts")
        manufacturer_contact = Contact(
            first_name="TechPro",
            last_name="Support",
            email="support@techpro.com",
            phone="+1-800-555-0199",
            job="Customer Service",
        )
        friend_contact = Contact(
            first_name="Alex",
            last_name="Chen",
            email="alex.chen@email.com",
            phone="+1-555-0142",
            job="Software Engineer",
        )
        self.contacts.add_contact(manufacturer_contact)
        self.contacts.add_contact(friend_contact)

        # Initialize Email app with purchase receipt (18 months ago)
        self.email = StatefulEmailApp(name="Emails", user_email="user@email.com")
        purchase_timestamp = datetime(2024, 5, 18, 14, 30, 0, tzinfo=UTC).timestamp()
        purchase_receipt = Email(
            sender="orders@techpro.com",
            recipients=["user@email.com"],
            subject="Order Confirmation #TP-2024-05-8472",
            content="""Thank you for your purchase from TechPro Electronics!

Order Number: TP-2024-05-8472
Order Date: May 18, 2024
Product: TechPro UltraBook Pro 15
Model: TB-Pro-15-2024
Serial Number: TB2024051800847
Battery Model: Li-Ion 6-Cell Battery Pack (Model: BP-6C-2024A)
Manufacturing Date: April 2024
Warranty: 3 years from purchase date (expires May 18, 2027)

Total: $1,299.99

Your warranty covers manufacturing defects and includes battery replacement if capacity drops below 80% within the warranty period.

For support, contact us at support@techpro.com or call +1-800-555-0199.

Thank you for choosing TechPro!""",
            timestamp=purchase_timestamp,
            is_read=True,
        )
        self.email.add_email(purchase_receipt)

        # Initialize Calendar app with unresolved battery complaint (3 months ago)
        self.calendar = StatefulCalendarApp(name="Calendar")
        reminder_timestamp = datetime(2025, 8, 18, 10, 0, 0, tzinfo=UTC).timestamp()
        battery_reminder = CalendarEvent(
            title="laptop battery draining fast - check warranty",
            start_datetime=reminder_timestamp,
            end_datetime=reminder_timestamp + 3600,
            description="""Battery performance has degraded significantly over the past few months. Need to:
- Check warranty status (purchased May 2024, should have 3-year warranty until May 2027)
- Contact TechPro support if still covered
- Contact: support@techpro.com or +1-800-555-0199
- Model: TB-Pro-15-2024
- Serial: TB2024051800847""",
            tag="personal",
            location="Home",
        )
        self.calendar.set_calendar_event(battery_reminder)

        # Initialize Messaging app with tech-savvy friend conversation
        self.messaging = StatefulMessagingApp(name="Messages")
        self.messaging.add_users(["Alex Chen"])
        alex_id = self.messaging.name_to_id["Alex Chen"]

        conversation = ConversationV2(
            participant_ids=["user_id", alex_id],
            title="Alex Chen",
        )

        # Messages discussing battery issues (recent, within last week)
        msg1_timestamp = datetime(2025, 11, 12, 15, 30, 0, tzinfo=UTC).timestamp()
        msg1 = MessageV2(
            sender_id="user_id",
            content="Hey Alex, my laptop battery has been terrible lately. It barely lasts 2 hours now when it used to last 8+",
            timestamp=msg1_timestamp,
        )

        msg2_timestamp = datetime(2025, 11, 12, 15, 35, 0, tzinfo=UTC).timestamp()
        msg2 = MessageV2(
            sender_id=alex_id,
            content="That's rough! How old is the laptop?",
            timestamp=msg2_timestamp,
        )

        msg3_timestamp = datetime(2025, 11, 12, 15, 40, 0, tzinfo=UTC).timestamp()
        msg3 = MessageV2(
            sender_id="user_id",
            content="Bought it in May 2024, so about 18 months. It's a TechPro UltraBook Pro",
            timestamp=msg3_timestamp,
        )

        msg4_timestamp = datetime(2025, 11, 12, 15, 45, 0, tzinfo=UTC).timestamp()
        msg4 = MessageV2(
            sender_id=alex_id,
            content="Should still be under warranty then! I had a similar issue with my camera last year. I submitted a warranty claim through their online portal - just needed photos of the serial number and a description of the problem. They approved it in like 3 days and sent a replacement.",
            timestamp=msg4_timestamp,
        )

        msg5_timestamp = datetime(2025, 11, 12, 15, 50, 0, tzinfo=UTC).timestamp()
        msg5 = MessageV2(
            sender_id="user_id",
            content="Good to know! I've been meaning to look into it but haven't gotten around to it yet",
            timestamp=msg5_timestamp,
        )

        conversation.messages = [msg1, msg2, msg3, msg4, msg5]
        conversation.last_updated = msg5_timestamp
        self.messaging.add_conversation(conversation)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.email, self.calendar, self.messaging]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")

        # Get Alex's user ID from messaging app
        alex_id = messaging_app.name_to_id["Alex Chen"]

        with EventRegisterer.capture_mode():
            # Event 1: Recall notification email arrives from manufacturer
            recall_email_id = "recall-email-bp6c2024a"
            recall_event = email_app.send_email_to_user_with_id(
                email_id=recall_email_id,
                sender="safety@techpro.com",
                subject="IMPORTANT: Voluntary Safety Recall - Battery Model BP-6C-2024A",
                content="""Dear TechPro Customer,

We are issuing a voluntary safety recall for Li-Ion 6-Cell Battery Pack (Model: BP-6C-2024A) manufactured between March 2024 and June 2024 due to a potential fire hazard. This battery was included in TechPro UltraBook Pro 15 (Model: TB-Pro-15-2024) devices.

AFFECTED UNITS: Devices purchased between April 2024 and July 2024.

IMMEDIATE ACTION REQUIRED: Stop using the affected battery and contact us for a free replacement.

TO FILE A CLAIM:
1. Verify your purchase date and battery model from your order confirmation
2. Email support@techpro.com with:
   - Order number and purchase date
   - Device serial number (found on bottom of laptop)
   - Battery model number (BP-6C-2024A)
   - Your shipping address
3. We will send a replacement battery within 5-7 business days
4. Return the defective battery using the prepaid shipping label we provide

For questions, contact support@techpro.com or call +1-800-555-0199.

We apologize for this inconvenience and thank you for your cooperation in this important safety matter.

TechPro Safety Team""",
            ).delayed(30)

            # Event 2: Agent proposes comprehensive recall response plan (oracle)
            proposal_event = (
                aui.send_message_to_user(
                    content="""I noticed a safety recall for your TechPro UltraBook Pro battery (BP-6C-2024A). Your May 2024 purchase falls within the affected date range, and this recall directly addresses the battery drainage issues you noted in your August calendar reminder.

Would you like me to:
1. Draft a claim email to support@techpro.com with your order details (TP-2024-05-8472, serial TB2024051800847)
2. Add a 2-week follow-up reminder to check on replacement confirmation
3. Message Alex Chen to ask about the warranty portal process they mentioned

This is time-sensitive given the fire risk, and your 3-year warranty expires in 6 months."""
                )
                .oracle()
                .depends_on(recall_event, delay_seconds=5)
            )

            # Event 3: User accepts the proposal (oracle)
            acceptance_event = (
                aui.accept_proposal(content="Yes please! Let's get this handled right away.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Event 4: Agent sends recall claim email (oracle)
            claim_email_event = (
                email_app.send_email(
                    recipients=["support@techpro.com"],
                    subject="Battery Recall Claim - Order #TP-2024-05-8472",
                    content="""Dear TechPro Support,

I am filing a claim for the voluntary safety recall of Battery Model BP-6C-2024A.

DEVICE INFORMATION:
- Order Number: TP-2024-05-8472
- Purchase Date: May 18, 2024
- Product: TechPro UltraBook Pro 15
- Model: TB-Pro-15-2024
- Serial Number: TB2024051800847
- Battery Model: BP-6C-2024A (manufactured April 2024)

SHIPPING ADDRESS:
[User address - to be confirmed]

I have been experiencing battery performance degradation since August 2025 and request an expedited replacement given the fire safety concern.

Please confirm receipt and provide an estimated timeline for the replacement battery.

Thank you,
[User name]""",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Event 5: Agent adds follow-up calendar reminder (oracle)
            followup_timestamp = datetime(2025, 12, 2, 9, 0, 0, tzinfo=UTC).timestamp()
            calendar_event = (
                calendar_app.set_calendar_event(
                    event=CalendarEvent(
                        title="Follow up on TechPro battery recall claim",
                        start_datetime=followup_timestamp,
                        end_datetime=followup_timestamp + 1800,
                        description="""Check if TechPro has confirmed the battery replacement claim filed on Nov 18, 2025.

Order #TP-2024-05-8472
Contact: support@techpro.com or +1-800-555-0199

If no response received, send follow-up email.""",
                        tag="personal",
                        location="Home",
                    )
                )
                .oracle()
                .depends_on(claim_email_event, delay_seconds=1)
            )

            # Event 6: Agent gets conversation ID for Alex Chen
            alex_conversation_id = next(iter(messaging_app.conversations.keys()))

            # Event 7: Agent sends message to Alex asking about portal process (oracle)
            message_event = (
                messaging_app.send_message(
                    user_id=alex_id,
                    content="Hey Alex! Quick question about that warranty claim portal you mentioned. I'm filing a recall claim with TechPro and want to make sure I have all the documentation they need. What info did you have to submit through the portal?",
                )
                .oracle()
                .depends_on(calendar_event, delay_seconds=2)
            )

            # Event 8: Agent confirms completion to user (oracle)
            summary_event = (
                aui.send_message_to_user(
                    content="""Done! I've completed all three actions:

✓ Sent recall claim email to support@techpro.com with your order and device details
✓ Added Dec 2 follow-up reminder to check on replacement confirmation
✓ Messaged Alex to ask about warranty portal documentation requirements

You should receive confirmation from TechPro within 1-2 business days. I'll remind you to follow up if needed."""
                )
                .oracle()
                .depends_on(message_event, delay_seconds=3)
            )

        # Register ALL events
        self.events: list[Event] = [
            recall_event,
            proposal_event,
            acceptance_event,
            claim_email_event,
            calendar_event,
            message_event,
            summary_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:  # noqa: C901
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent sent proposal to the user
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["recall", "battery", "bp-6c-2024a"]
                )
                for e in log_entries
            )

            # Check Step 2a: Agent detected purchase receipt correlation
            purchase_detection = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["tp-2024-05-8472", "may 2024", "order"]
                )
                for e in log_entries
            )

            # Check Step 2b: Agent detected calendar reminder about battery issues
            calendar_detection = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["warranty", "august", "reminder"]
                )
                for e in log_entries
            )

            # Check Step 3a: Agent sent recall claim email to TechPro support
            claim_email_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "send_email"
                and "support@techpro.com" in e.action.args.get("recipients", [])
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["tp-2024-05-8472", "bp-6c-2024a", "tb2024051800847"]
                )
                for e in log_entries
            )

            # Check Step 3b: Agent added follow-up calendar reminder
            followup_reminder_created = False
            for e in log_entries:
                if (
                    e.event_type == EventType.AGENT
                    and isinstance(e.action, Action)
                    and e.action.class_name == "StatefulCalendarApp"
                    and e.action.function_name == "set_calendar_event"
                ):
                    event_arg = e.action.args.get("event")
                    if event_arg:
                        # event_arg could be a CalendarEvent object or a dict
                        if isinstance(event_arg, CalendarEvent):
                            title = event_arg.title.lower()
                        elif isinstance(event_arg, dict):
                            title = event_arg.get("title", "").lower()
                        else:
                            title = ""

                        if any(keyword in title for keyword in ["follow up", "techpro", "battery", "recall"]):
                            followup_reminder_created = True
                            break

            # Check Step 3c: Agent sent message to Alex Chen asking about warranty portal
            alex_message_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["portal", "warranty", "documentation", "claim"]
                )
                for e in log_entries
            )

            # Strict checks: proposal with recall detection, claim email, and follow-up reminder are critical
            # Flexible checks: exact wording and specific detection mentions are less critical as long as the actions were taken
            strict_success = proposal_found and claim_email_sent and followup_reminder_created

            # Full success includes all detection signals and messaging coordination
            full_success = strict_success and purchase_detection and calendar_detection and alex_message_sent

            # Return success if strict requirements are met (detection mentions and Alex message are nice-to-have)
            success = strict_success

            # Generate rationale for failure
            if not success:
                missing = []
                if not proposal_found:
                    missing.append("agent proposal mentioning recall/battery")
                if not claim_email_sent:
                    missing.append("claim email to support@techpro.com with order details")
                if not followup_reminder_created:
                    missing.append("follow-up calendar reminder about TechPro battery claim")

                rationale = f"Missing critical checks: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
