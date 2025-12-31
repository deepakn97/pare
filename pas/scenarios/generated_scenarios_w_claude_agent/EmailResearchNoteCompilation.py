"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.contacts import Contact
from are.simulation.apps.email_client import Email, EmailFolderName
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulEmailApp,
)
from pas.apps.note import StatefulNotesApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("email_research_note_compilation")
class EmailResearchNoteCompilation(PASScenario):
    """Agent compiles research findings from multiple emails into organized notes.

    The user is researching vendors for an upcoming project and has received proposals from three different vendors via separate emails, each containing pricing, timeline, and feature information. The scattered information makes comparison difficult. An email from a colleague arrives asking for a vendor comparison summary by end of day. The agent must:
    1. Parse the colleague's request from the incoming email
    2. Search and read the vendor proposal emails (three separate threads)
    3. Extract key information: pricing, timelines, and features from each proposal
    4. Create a new note in the "Work" folder with structured comparison table
    5. Add relevant vendor emails as attachments to the note for reference
    6. Reply to the colleague's email with confirmation and note location

    This scenario exercises cross-app information synthesis (email -> notes), multi-source extraction, structured note creation with attachments, and contextual email response coordinated with note organization..
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
        self.note = StatefulNotesApp(name="Notes")

        # Populate baseline data - contacts
        colleague = Contact(
            first_name="Sarah",
            last_name="Chen",
            email="sarah.chen@company.com",
            phone="+1-555-0101",
        )
        vendor_a_rep = Contact(
            first_name="Michael",
            last_name="Rodriguez",
            email="m.rodriguez@vendora.com",
            phone="+1-555-0201",
        )
        vendor_b_rep = Contact(
            first_name="Jessica",
            last_name="Thompson",
            email="j.thompson@vendorb.com",
            phone="+1-555-0301",
        )
        vendor_c_rep = Contact(
            first_name="David",
            last_name="Kim",
            email="d.kim@vendorc.com",
            phone="+1-555-0401",
        )

        # Populate baseline email data - vendor proposals received 3-5 days ago
        # Vendor A proposal (received 5 days ago)
        vendor_a_email = Email(
            email_id="vendor_a_proposal",
            sender="m.rodriguez@vendora.com",
            recipients=[self.email.user_email],
            subject="Vendor A - Proposal for Project Management Platform",
            content="""Dear User,

Thank you for your interest in Vendor A's project management platform. Please find our proposal below:

**Pricing:**
- Enterprise Plan: $25,000/year
- Includes up to 100 users
- Additional users: $20/user/month

**Timeline:**
- Implementation: 6-8 weeks
- Training: 2 weeks
- Go-live: Week 10

**Key Features:**
- Advanced task management with dependencies
- Real-time collaboration tools
- Customizable dashboards
- API integrations with 50+ tools
- 24/7 priority support
- Mobile apps for iOS and Android

We look forward to working with you.

Best regards,
Michael Rodriguez
Vendor A Sales Team""",
            timestamp=self.start_time - (5 * 24 * 3600),  # 5 days before start
            is_read=True,
        )
        self.email.add_email(vendor_a_email, EmailFolderName.INBOX)

        # Vendor B proposal (received 4 days ago)
        vendor_b_email = Email(
            email_id="vendor_b_proposal",
            sender="j.thompson@vendorb.com",
            recipients=[self.email.user_email],
            subject="Vendor B - Comprehensive Solution for Your Needs",
            content="""Hi there,

We're excited to present Vendor B's solution for your project management needs.

**Pricing:**
- Professional Tier: $30,000/year
- Up to 150 users included
- Extra users: $15/user/month
- Volume discounts available

**Timeline:**
- Setup and configuration: 4-6 weeks
- User training program: 3 weeks
- Full deployment: Week 9

**Key Features:**
- Gantt charts and timeline views
- Resource allocation and planning
- Built-in time tracking
- Advanced reporting and analytics
- Integration marketplace (100+ apps)
- Dedicated account manager
- Cloud and on-premise options

Let us know if you have any questions!

Regards,
Jessica Thompson
Vendor B Solutions""",
            timestamp=self.start_time - (4 * 24 * 3600),  # 4 days before start
            is_read=True,
        )
        self.email.add_email(vendor_b_email, EmailFolderName.INBOX)

        # Vendor C proposal (received 3 days ago)
        vendor_c_email = Email(
            email_id="vendor_c_proposal",
            sender="d.kim@vendorc.com",
            recipients=[self.email.user_email],
            subject="Vendor C - Agile Project Management Proposal",
            content="""Hello,

Thank you for considering Vendor C. Here's our proposal:

**Pricing:**
- Standard Package: $20,000/year
- Covers 75 users
- Additional users: $25/user/month
- Free trial: 30 days

**Timeline:**
- Initial setup: 3-4 weeks
- Team onboarding: 1 week
- Launch date: Week 6

**Key Features:**
- Agile/Scrum board management
- Sprint planning and retrospectives
- Burndown charts and velocity tracking
- File sharing and document management
- Email and Slack integrations
- Standard support (9-5 EST)
- Web-based platform

Please reach out with any questions.

Best,
David Kim
Vendor C Team""",
            timestamp=self.start_time - (3 * 24 * 3600),  # 3 days before start
            is_read=True,
        )
        self.email.add_email(vendor_c_email, EmailFolderName.INBOX)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.note]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")

        with EventRegisterer.capture_mode():
            # Environment event: Colleague Sarah sends request email asking for vendor comparison
            colleague_request_event = email_app.send_email_to_user_with_id(
                email_id="colleague_request",
                sender="sarah.chen@company.com",
                subject="Vendor Comparison Needed ASAP",
                content="Hi,\n\nI hope you're doing well. The project committee meeting is this afternoon, and we need to make a decision on which vendor to go with for the new project management platform. Could you please compile a summary comparing the three vendors (A, B, and C) that sent proposals last week?\n\nWe specifically need to compare:\n- Pricing and user limits\n- Implementation timelines\n- Key features and capabilities\n\nCan you write down those in your notes to prepare for the meeting? Thanks!\n\nBest,\nSarah Chen\nProject Committee Lead",
            ).delayed(5)

            # Agent detects the colleague's request and offers to help compile the vendor comparison
            # Motivation: Sarah's email explicitly asks for a vendor comparison summary from three vendor proposals
            proposal_event = (
                aui.send_message_to_user(
                    content="I saw Sarah's email requesting a vendor comparison. I can compile the information from the three vendor proposal emails (Vendor A, B, and C) into a structured note and reply to Sarah about the notes confirmation. Would you like me to do that?"
                )
                .oracle()
                .depends_on(colleague_request_event, delay_seconds=3)
            )

            # User accepts the agent's proposal
            user_acceptance_event = (
                aui.accept_proposal(content="Yes, please compile the vendor comparison note and reply to Sarah.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Agent searches for vendor proposal emails to gather information
            # Motivation: Agent needs to locate the vendor emails mentioned in Sarah's request and in the proposal
            search_vendor_emails_event = (
                email_app.search_emails(query="vendor proposal", folder_name="INBOX")
                .oracle()
                .depends_on(user_acceptance_event, delay_seconds=2)
            )

            # Agent reads Vendor A proposal to extract details
            # Motivation: Search results revealed vendor_a_proposal email; agent needs to extract pricing/timeline/features
            read_vendor_a_event = (
                email_app.get_email_by_id(email_id="vendor_a_proposal", folder_name="INBOX")
                .oracle()
                .depends_on(search_vendor_emails_event, delay_seconds=2)
            )

            # Agent reads Vendor B proposal to extract details
            # Motivation: Search results revealed vendor_b_proposal email; agent needs to extract pricing/timeline/features
            read_vendor_b_event = (
                email_app.get_email_by_id(email_id="vendor_b_proposal", folder_name="INBOX")
                .oracle()
                .depends_on(read_vendor_a_event, delay_seconds=2)
            )

            # Agent reads Vendor C proposal to extract details
            # Motivation: Search results revealed vendor_c_proposal email; agent needs to extract pricing/timeline/features
            read_vendor_c_event = (
                email_app.get_email_by_id(email_id="vendor_c_proposal", folder_name="INBOX")
                .oracle()
                .depends_on(read_vendor_b_event, delay_seconds=2)
            )

            # Agent creates a structured comparison note in the Work folder
            # Motivation: After reading all three vendor emails, agent has extracted comparison data and can now synthesize it into a note
            create_note_event = (
                note_app.create_note(
                    folder="Work",
                    title="Vendor Comparison - Project Management Platform",
                    content="""# Vendor Comparison Summary

## Pricing Comparison
- **Vendor A**: $25,000/year (100 users included, $20/user/month additional)
- **Vendor B**: $30,000/year (150 users included, $15/user/month additional)
- **Vendor C**: $20,000/year (75 users included, $25/user/month additional)

## Implementation Timeline
- **Vendor A**: 10 weeks total (6-8 weeks implementation + 2 weeks training)
- **Vendor B**: 9 weeks total (4-6 weeks setup + 3 weeks training)
- **Vendor C**: 6 weeks total (3-4 weeks setup + 1 week onboarding)

## Key Features
**Vendor A:**
- Advanced task management with dependencies
- Real-time collaboration tools
- Customizable dashboards
- 50+ API integrations
- 24/7 priority support
- Mobile apps (iOS/Android)

**Vendor B:**
- Gantt charts and timeline views
- Resource allocation and planning
- Built-in time tracking
- Advanced reporting and analytics
- 100+ app integrations
- Dedicated account manager
- Cloud and on-premise options

**Vendor C:**
- Agile/Scrum board management
- Sprint planning and retrospectives
- Burndown charts and velocity tracking
- File sharing and document management
- Email and Slack integrations
- Standard support (9-5 EST)
- Web-based platform

## Summary
- **Best Value**: Vendor C (lowest cost, fastest deployment)
- **Most Features**: Vendor B (comprehensive features, dedicated support)
- **Balanced Option**: Vendor A (good features, reasonable timeline)
""",
                )
                .oracle()
                .depends_on(read_vendor_c_event, delay_seconds=3)
            )

            # Agent replies to Sarah's email with confirmation and note location
            # Motivation: User accepted the proposal to reply to Sarah; note has been created with the comparison
            reply_to_colleague_event = (
                email_app.reply_to_email(
                    email_id="colleague_request",
                    folder_name="INBOX",
                    content="Hi Sarah,\n\nI've compiled the vendor comparison you requested. I've created a detailed note for the meeting in the afternoon in the Work folder titled 'Vendor Comparison - Project Management Platform' that includes:\n\n- Pricing comparison across all three vendors\n- Implementation timeline comparison\n- Key features breakdown for each vendor\n- Summary with recommendations.\n\nLet me know if you need any additional details!\n\nBest regards",
                )
                .oracle()
                .depends_on(create_note_event, delay_seconds=2)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            colleague_request_event,
            proposal_event,
            user_acceptance_event,
            search_vendor_emails_event,
            read_vendor_a_event,
            read_vendor_b_event,
            read_vendor_c_event,
            create_note_event,
            reply_to_colleague_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only agent/oracle events (EventType.AGENT)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent sent proposal to the user
            # The agent must detect Sarah's request and offer to help
            proposal_found = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT Check 2: Agent searched or accessed vendor emails
            # Accept either search_emails OR direct access via get_email_by_id/list_emails
            email_search_found = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name in ["search_emails", "get_email_by_id", "list_emails"]
                for e in agent_events
            )

            # STRICT Check 3: Agent read all three vendor proposal emails
            # We need to ensure the agent accessed the vendor proposals
            # Look for get_email_by_id calls with vendor email IDs
            vendor_email_reads = [
                e
                for e in agent_events
                if e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "get_email_by_id"
                and "email_id" in e.action.args
            ]

            # Check if at least 3 email reads occurred (for the 3 vendor proposals)
            # We're flexible on exact IDs but strict on the count
            sufficient_email_reads = len(vendor_email_reads) >= 3

            # STRICT Check 4: Agent created a note
            # The note must be created with the comparison information
            note_creation_found = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "create_note"
                for e in agent_events
            )

            # STRICT Check 5: Agent replied to Sarah's email
            # Accept reply_to_email, send_email, or send_batch_reply
            reply_found = any(
                e.event_type == EventType.AGENT
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name in ["reply_to_email", "send_email", "send_batch_reply"]
                for e in agent_events
            )

            # Determine overall success
            success = (
                proposal_found and email_search_found and sufficient_email_reads and note_creation_found and reply_found
            )

            if not success:
                # Build a rationale explaining what's missing
                missing_items = []
                if not proposal_found:
                    missing_items.append("agent proposal to user not found")
                if not email_search_found:
                    missing_items.append("email search/access not found")
                if not sufficient_email_reads:
                    missing_items.append(f"insufficient vendor email reads (found {len(vendor_email_reads)}, need 3)")
                if not note_creation_found:
                    missing_items.append("note creation in folder not found")
                if not reply_found:
                    missing_items.append("reply to Sarah's email not found")

                rationale = "; ".join(missing_items)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
