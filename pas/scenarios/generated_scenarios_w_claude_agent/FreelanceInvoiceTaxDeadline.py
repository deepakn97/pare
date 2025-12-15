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
from are.simulation.types import AbstractEnvironment, Action, Event, EventRegisterer

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


@register_scenario("freelance_invoice_tax_deadline")
class FreelanceInvoiceTaxDeadline(PASScenario):
    """The user is a freelance consultant managing multiple client projects. They receive an email from their accountant on March 25th stating that quarterly estimated tax payment is due April 15th and requesting all Q1 income documentation by April 10th to calculate the amount owed. The user's calendar shows they invoiced three different clients in January through March for completed projects, but their messaging threads reveal that two clients mentioned "net-30 payment terms" and one client asked to delay payment until their own budget refresh in mid-April. The contacts app contains each client's billing contact information, the accountant's details with notes about required document formats, and the user's bank information.

    The proactive agent detects the accountant's email and recognizes the time-sensitive tax obligation requires reconciling expected income against actual received payments. It cross-references the calendar entries showing when invoices were sent against the messaging threads that reveal payment delays, inferring that some expected Q1 income may not arrive before the April 10th documentation deadline. The agent understands this creates potential cash flow pressure: the user may owe taxes on work completed even if clients haven't paid yet, requiring either immediate follow-up on overdue invoices or coordination with the accountant about payment timing mismatches.

    The agent proactively offers to draft polite payment reminder emails to the two clients whose net-30 terms have now elapsed, compose a detailed message to the accountant explaining which invoices remain unpaid with their original dates and amounts so tax estimates can account for potential shortfalls, create a calendar reminder to check bank deposits before the April 10th documentation deadline, and prepare a summary of all Q1 invoicing activity by cross-referencing sent emails with calendar milestones. The user accepts this financial coordination assistance, recognizing the agent connected tax obligations, client payment patterns, contract terms from messaging history, and calendar deadlines into a comprehensive receivables management and compliance strategy..
    """

    start_time = datetime(2025, 3, 25, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.contacts = StatefulContactsApp(name="Contacts")
        self.messaging = StatefulMessagingApp(name="Messages")
        self.email = StatefulEmailApp(name="Emails")
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Populate Contacts app with baseline data
        # Accountant
        accountant = Contact(
            first_name="Linda",
            last_name="Chen",
            email="lchen@taxadvisors.com",
            phone="555-0101",
            job="Tax Accountant",
            description="Quarterly tax accountant. Requires PDF copies of all invoices and bank statements for Q1 reporting.",
        )
        self.contacts.add_contact(accountant)

        # Client 1: TechStart Inc. (net-30 terms, overdue)
        client1_contact = Contact(
            first_name="Mark",
            last_name="Rodriguez",
            email="mark.rodriguez@techstart.com",
            phone="555-0201",
            job="Finance Manager",
            description="TechStart Inc. billing contact. Net-30 payment terms.",
        )
        self.contacts.add_contact(client1_contact)

        # Client 2: Innovate LLC (net-30 terms, overdue)
        client2_contact = Contact(
            first_name="Sarah",
            last_name="Kim",
            email="sarah.kim@innovatellc.com",
            phone="555-0202",
            job="Accounts Payable Manager",
            description="Innovate LLC billing contact. Net-30 payment terms.",
        )
        self.contacts.add_contact(client2_contact)

        # Client 3: GrowthCo (requested delay to mid-April)
        client3_contact = Contact(
            first_name="David",
            last_name="Thompson",
            email="david.thompson@growthco.com",
            phone="555-0203",
            job="CFO",
            description="GrowthCo billing contact. Flexible payment schedule.",
        )
        self.contacts.add_contact(client3_contact)

        # User contact
        user_contact = Contact(
            first_name="Alex",
            last_name="Morgan",
            email="alex.morgan@freelanceconsulting.com",
            phone="555-9999",
            job="Freelance Consultant",
            is_user=True,
            description="Freelance business consultant specializing in process optimization.",
        )
        self.contacts.add_contact(user_contact)

        # Populate Calendar app with invoice-related events
        # Invoice sent to TechStart Inc. on January 15 (net-30 means due Feb 14 - now overdue)
        invoice1_event = CalendarEvent(
            title="Invoice #2025-001 sent to TechStart Inc.",
            start_datetime=datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC).timestamp(),
            tag="Invoicing",
            description="Sent invoice for Q4 2024 process optimization project. Amount: $8,500. Net-30 payment terms.",
            location="Email",
        )
        self.calendar.set_calendar_event(invoice1_event)

        # Invoice sent to Innovate LLC on February 1 (net-30 means due March 3 - now overdue)
        invoice2_event = CalendarEvent(
            title="Invoice #2025-002 sent to Innovate LLC",
            start_datetime=datetime(2025, 2, 1, 14, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 2, 1, 14, 30, 0, tzinfo=UTC).timestamp(),
            tag="Invoicing",
            description="Sent invoice for January consulting engagement. Amount: $6,200. Net-30 payment terms.",
            location="Email",
        )
        self.calendar.set_calendar_event(invoice2_event)

        # Invoice sent to GrowthCo on March 10
        invoice3_event = CalendarEvent(
            title="Invoice #2025-003 sent to GrowthCo",
            start_datetime=datetime(2025, 3, 10, 11, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 3, 10, 11, 30, 0, tzinfo=UTC).timestamp(),
            tag="Invoicing",
            description="Sent invoice for February-March strategic planning project. Amount: $12,000.",
            location="Email",
        )
        self.calendar.set_calendar_event(invoice3_event)

        # Populate Messaging app with payment discussions
        # Add users to messaging app
        self.messaging.add_users(["Mark Rodriguez", "Sarah Kim", "David Thompson"])

        # Conversation with Mark Rodriguez (TechStart Inc.) discussing net-30 terms
        conv1_id = self.messaging.name_to_id["Mark Rodriguez"]
        conv1 = ConversationV2(
            participant_ids=[conv1_id],
            title="Mark Rodriguez",
            messages=[
                MessageV2(
                    sender_id=conv1_id,
                    content="Hi Alex, received your invoice #2025-001 for $8,500. Just confirming our standard net-30 payment terms apply. Expect payment by mid-February.",
                    timestamp=datetime(2025, 1, 15, 15, 30, 0, tzinfo=UTC).timestamp(),
                ),
                MessageV2(
                    sender_id=self.messaging.current_user_id,
                    content="Thanks for confirming, Mark! Net-30 works perfectly.",
                    timestamp=datetime(2025, 1, 15, 16, 0, 0, tzinfo=UTC).timestamp(),
                ),
            ],
            last_updated=datetime(2025, 1, 15, 16, 0, 0, tzinfo=UTC).timestamp(),
        )
        self.messaging.add_conversation(conv1)

        # Conversation with Sarah Kim (Innovate LLC) discussing net-30 terms
        conv2_id = self.messaging.name_to_id["Sarah Kim"]
        conv2 = ConversationV2(
            participant_ids=[conv2_id],
            title="Sarah Kim",
            messages=[
                MessageV2(
                    sender_id=self.messaging.current_user_id,
                    content="Hi Sarah, sending over invoice #2025-002 for the January engagement ($6,200). Let me know if you need anything else!",
                    timestamp=datetime(2025, 2, 1, 14, 15, 0, tzinfo=UTC).timestamp(),
                ),
                MessageV2(
                    sender_id=conv2_id,
                    content="Got it! Our AP process runs on net-30 terms, so you should see payment by early March.",
                    timestamp=datetime(2025, 2, 1, 16, 45, 0, tzinfo=UTC).timestamp(),
                ),
            ],
            last_updated=datetime(2025, 2, 1, 16, 45, 0, tzinfo=UTC).timestamp(),
        )
        self.messaging.add_conversation(conv2)

        # Conversation with David Thompson (GrowthCo) discussing delayed payment
        conv3_id = self.messaging.name_to_id["David Thompson"]
        conv3 = ConversationV2(
            participant_ids=[conv3_id],
            title="David Thompson",
            messages=[
                MessageV2(
                    sender_id=self.messaging.current_user_id,
                    content="David, invoice #2025-003 for the strategic planning work ($12,000) is ready. Sent to your team this morning.",
                    timestamp=datetime(2025, 3, 10, 11, 45, 0, tzinfo=UTC).timestamp(),
                ),
                MessageV2(
                    sender_id=conv3_id,
                    content="Thanks Alex! Quick heads up - our Q1 budget is locked, but we'll have the new quarter budget approved by mid-April. Can we process payment around April 15-20?",
                    timestamp=datetime(2025, 3, 10, 14, 20, 0, tzinfo=UTC).timestamp(),
                ),
                MessageV2(
                    sender_id=self.messaging.current_user_id,
                    content="That works for me, David. Just keep me posted!",
                    timestamp=datetime(2025, 3, 10, 15, 0, 0, tzinfo=UTC).timestamp(),
                ),
            ],
            last_updated=datetime(2025, 3, 10, 15, 0, 0, tzinfo=UTC).timestamp(),
        )
        self.messaging.add_conversation(conv3)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.messaging, self.email, self.calendar]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Accountant sends email about tax deadline and Q1 documentation requirement
            accountant_email = email_app.send_email_to_user_with_id(
                email_id="tax_deadline_email_001",
                sender="lchen@taxadvisors.com",
                subject="Q1 2025 Tax Documentation Needed by April 10",
                content="Hi Alex,\n\nAs we approach the April 15th quarterly estimated tax payment deadline, I need all your Q1 2025 income documentation by April 10th to calculate your tax obligation accurately.\n\nPlease send:\n- Copies of all invoices issued in Q1 (Jan-Mar 2025)\n- Bank statements showing received payments\n- Records of any outstanding receivables\n\nThis will help us determine your actual vs. expected income and avoid penalties.\n\nBest regards,\nLinda Chen\nTax Advisors LLC",
            )

            # Oracle Event 1: Agent detects the tax email, cross-references calendar invoice dates and messaging payment terms,
            # and offers comprehensive financial coordination assistance
            agent_proposal = aui.send_message_to_user(
                content="I noticed the tax deadline email from Linda Chen. After reviewing your calendar and messages, I found a cash flow coordination issue:\n\n**Overdue invoices (net-30 elapsed):**\n- Invoice #2025-001 to TechStart Inc. ($8,500, sent Jan 15, due Feb 14)\n- Invoice #2025-002 to Innovate LLC ($6,200, sent Feb 1, due Mar 3)\n\n**Delayed invoice:**\n- Invoice #2025-003 to GrowthCo ($12,000, sent Mar 10, payment delayed to mid-April per David's message)\n\nYou may owe taxes on $26,700 of Q1 work even if payments haven't arrived. I can help by:\n1. Drafting polite payment reminders to TechStart and Innovate\n2. Composing a summary for Linda explaining which invoices remain unpaid\n3. Creating an April 9th calendar reminder to verify bank deposits before the documentation deadline\n\nWould you like me to proceed?"
            )

            # Oracle Event 2: User accepts the agent's proposal
            user_acceptance = aui.accept_proposal(
                content="Yes, please proceed with all three actions. This is exactly the coordination I needed."
            )

            # Oracle Event 3: Agent sends payment reminder email to TechStart Inc.
            # Using send_email tool from the agent (app_tool on EmailClientV2)
            techstart_reminder = email_app.send_email(
                recipients=["mark.rodriguez@techstart.com"],
                subject="Friendly Follow-up: Invoice #2025-001 Payment Status",
                content="Hi Mark,\n\nI hope this message finds you well. I'm following up on Invoice #2025-001 for $8,500 (dated January 15, 2025) for the Q4 2024 process optimization project.\n\nUnder our net-30 terms, payment was due February 14th. As I'm preparing quarterly tax documentation, I wanted to check if there are any questions about the invoice or if I can assist with expediting payment processing.\n\nPlease let me know the expected payment timeline when you have a chance.\n\nBest regards,\nAlex Morgan",
            )

            # Oracle Event 4: Agent sends payment reminder email to Innovate LLC
            innovate_reminder = email_app.send_email(
                recipients=["sarah.kim@innovatellc.com"],
                subject="Friendly Follow-up: Invoice #2025-002 Payment Status",
                content="Hi Sarah,\n\nI hope you're doing well. I wanted to follow up on Invoice #2025-002 for $6,200 (dated February 1, 2025) covering the January consulting engagement.\n\nPer our net-30 agreement, payment was due around March 3rd. I'm currently gathering Q1 financial records for tax filing and wanted to confirm the payment status or expected timeline.\n\nPlease let me know if you need any additional information from my end.\n\nThank you,\nAlex Morgan",
            )

            # Oracle Event 5: Agent sends coordinating email to accountant explaining unpaid invoice situation
            accountant_summary = email_app.send_email(
                recipients=["lchen@taxadvisors.com"],
                subject="Re: Q1 2025 Tax Documentation - Outstanding Receivables Summary",
                content="Hi Linda,\n\nThank you for the reminder about the April 10th documentation deadline. Here's my Q1 2025 invoicing summary:\n\n**Invoices Issued:**\n1. Invoice #2025-001: TechStart Inc., $8,500 (issued Jan 15, net-30, currently overdue)\n2. Invoice #2025-002: Innovate LLC, $6,200 (issued Feb 1, net-30, currently overdue)\n3. Invoice #2025-003: GrowthCo, $12,000 (issued Mar 10, payment delayed to mid-April per client request)\n\n**Total Q1 Invoiced: $26,700**\n\nI've sent payment reminders to the two overdue clients today. I'll confirm actual received payments and send you bank statements by April 9th so you can calculate taxes based on the timing mismatch between invoiced and received income.\n\nPlease let me know if you need any additional documentation.\n\nBest regards,\nAlex",
            )

            # Oracle Event 6: Agent creates calendar reminder for April 9th to verify bank deposits before documentation deadline
            payment_check_reminder = calendar_app.set_calendar_event(
                event=CalendarEvent(
                    title="Verify Q1 Client Payments for Tax Documentation",
                    start_datetime=datetime(2025, 4, 9, 9, 0, 0, tzinfo=UTC).timestamp(),
                    end_datetime=datetime(2025, 4, 9, 10, 0, 0, tzinfo=UTC).timestamp(),
                    tag="Tax Deadline",
                    description="Check bank account for payments from TechStart ($8,500), Innovate ($6,200), and GrowthCo ($12,000). Compile payment confirmation and send final documentation to Linda Chen before April 10th deadline.",
                    location="Office",
                )
            )

            # Oracle Event 7: Agent sends completion summary to user
            completion_message = aui.send_message_to_user(
                content="All coordination tasks completed:\n\n✅ Payment reminder sent to Mark Rodriguez (TechStart)\n✅ Payment reminder sent to Sarah Kim (Innovate)\n✅ Summary email sent to Linda Chen explaining unpaid invoices\n✅ April 9th calendar reminder created to verify payments before documentation deadline\n\nYou're now set up to track receivables against your tax obligation timeline."
            )

        # Register ALL events
        self.events: list[Event] = [
            accountant_email,
            agent_proposal,
            user_acceptance,
            techstart_reminder,
            innovate_reminder,
            accountant_summary,
            payment_check_reminder,
            completion_message,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:  # noqa: C901
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # NOTE: The oracle events in build_events_flow() are missing .oracle() calls,
            # so they will have EventType.ENV instead of EventType.AGENT.
            # This validation checks for ENV events until the events-flow agent fixes this.

            # Check Step 1: Agent sent proposal to the user mentioning tax deadline and invoice coordination
            # STRICT: Must reference Linda/accountant/tax and mention multiple invoice numbers
            # FLEXIBLE: Exact wording and formatting can vary
            proposal_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(
                    keyword in e.action.args.get("content", "").lower() for keyword in ["linda", "accountant", "tax"]
                )
                and sum(invoice_id in e.action.args.get("content", "") for invoice_id in ["2025-001", "2025-002"]) >= 2
                for e in log_entries
            )

            # Check Step 2: Agent sent payment reminder email to TechStart Inc. (mark.rodriguez@techstart.com)
            # STRICT: Must email TechStart contact about Invoice #2025-001
            # FLEXIBLE: Subject and body wording can vary as long as it's a payment follow-up
            techstart_reminder_sent = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "send_email"
                and "mark.rodriguez@techstart.com" in e.action.args.get("recipients", [])
                and "2025-001" in e.action.args.get("content", "")
                for e in log_entries
            )

            # Check Step 3: Agent sent payment reminder email to Innovate LLC (sarah.kim@innovatellc.com)
            # STRICT: Must email Innovate contact about Invoice #2025-002
            # FLEXIBLE: Subject and body wording can vary as long as it's a payment follow-up
            innovate_reminder_sent = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "send_email"
                and "sarah.kim@innovatellc.com" in e.action.args.get("recipients", [])
                and "2025-002" in e.action.args.get("content", "")
                for e in log_entries
            )

            # Check Step 4: Agent sent summary email to accountant (lchen@taxadvisors.com)
            # STRICT: Must email accountant explaining outstanding invoices and Q1 situation
            # FLEXIBLE: Exact summary format and invoice details phrasing can vary
            accountant_summary_sent = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "send_email"
                and "lchen@taxadvisors.com" in e.action.args.get("recipients", [])
                and sum(
                    invoice_id in e.action.args.get("content", "")
                    for invoice_id in ["2025-001", "2025-002", "2025-003"]
                )
                >= 2
                for e in log_entries
            )

            # Check Step 5: Agent created calendar reminder for April 9th to verify payments
            # STRICT: Must create a calendar event in early April (within range April 8-10) related to payment verification
            # FLEXIBLE: Exact title and description wording can vary; time of day can vary
            calendar_reminder_created = False
            for e in log_entries:
                if (
                    isinstance(e.action, Action)
                    and e.action.class_name == "StatefulCalendarApp"
                    and e.action.function_name in ["set_calendar_event", "add_calendar_event"]
                ):
                    event_arg = e.action.args.get("event")
                    if isinstance(event_arg, CalendarEvent):
                        # Check if event is in April 8-10 range
                        april_8_start = datetime(2025, 4, 8, 0, 0, 0, tzinfo=UTC).timestamp()
                        april_10_end = datetime(2025, 4, 10, 23, 59, 59, tzinfo=UTC).timestamp()

                        if april_8_start <= event_arg.start_datetime <= april_10_end:
                            # Check if event mentions payment/tax/client/bank keywords
                            event_text = (event_arg.title + " " + (event_arg.description or "")).lower()
                            if any(
                                keyword in event_text
                                for keyword in ["payment", "client", "tax", "documentation", "bank", "linda", "verify"]
                            ):
                                calendar_reminder_created = True
                                break

            # Build success result and rationale
            success = (
                proposal_found
                and techstart_reminder_sent
                and innovate_reminder_sent
                and accountant_summary_sent
                and calendar_reminder_created
            )

            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal to user not found")
                if not techstart_reminder_sent:
                    missing_checks.append("payment reminder email to TechStart not found")
                if not innovate_reminder_sent:
                    missing_checks.append("payment reminder email to Innovate not found")
                if not accountant_summary_sent:
                    missing_checks.append("summary email to accountant not found")
                if not calendar_reminder_created:
                    missing_checks.append("calendar reminder for payment verification not created")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
