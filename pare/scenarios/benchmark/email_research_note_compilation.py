"""Scenario for compiling research findings from email attachments into organized notes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps import SandboxLocalFileSystem
from are.simulation.apps.email_client import Email, EmailFolderName
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulEmailApp,
)
from pare.apps.note import StatefulNotesApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("email_research_note_compilation")
class EmailResearchNoteCompilation(PAREScenario):
    """Agent compiles research findings from vendor email attachments into organized notes.

    Story:
    1. User previously sent emails to four vendors requesting proposals for two different projects:
       - Project Management Platform: TaskFlow Solutions and ProjectSync Technologies
       - CRM System: SalesForce Connect and ClientHub Pro
    2. All four vendors replied with their proposals as markdown file attachments
    3. User receives email from colleague Sarah specifically asking for a comparison
       of the "Project Management Platform" proposals
    4. Agent must identify the correct project and only compile those proposals
    5. Agent downloads the relevant proposal attachments and creates a comparison note

    This scenario exercises cross-app information synthesis, attachment handling,
    selective filtering based on project context, and structured note creation.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    additional_system_prompt = """You need a vendor comparison note for the Project Management Platform project.
After receiving Sarah's email, try to read the vendor emails to understand what proposals you have.

ACCEPT proposals that:
- Compile a comparison note for Project Management Platform vendors only
- Include TaskFlow Solutions and ProjectSync Technologies in the comparison

REJECT proposals that:
- Include CRM System vendors (SalesForce Connect, ClientHub Pro) in the comparison
- Reply to Sarah's email (you only need the note created, not an email reply)
- Mix proposals from different projects"""

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize filesystem for attachments
        self.files = SandboxLocalFileSystem(name="Files")

        # Initialize apps
        self.email = StatefulEmailApp(name="Emails")
        self.note = StatefulNotesApp(name="Notes")

        # Set internal filesystem for email app
        self.email.internal_fs = self.files

        # ============================================================
        # PROJECT MANAGEMENT PLATFORM PROPOSALS (the ones Sarah needs)
        # ============================================================

        with self.files.open("/taskflow_proposal.md", "w") as f:
            f.write("""# TaskFlow Solutions - Project Management Platform Proposal

## Pricing
- Enterprise Plan: $25,000/year
- Up to 100 users included
- Additional users: $20/user/month

## Timeline
- Implementation: 6-8 weeks
- Training: 2 weeks
- Go-live: Week 10

## Key Features
- Advanced task management with dependencies
- Real-time collaboration tools
- Customizable dashboards
- 50+ API integrations
- 24/7 priority support
- Mobile apps (iOS/Android)
""")

        with self.files.open("/projectsync_proposal.md", "w") as f:
            f.write("""# ProjectSync Technologies - Project Management Platform Proposal

## Pricing
- Professional Tier: $30,000/year
- Up to 150 users included
- Extra users: $15/user/month

## Timeline
- Setup and configuration: 4-6 weeks
- User training: 3 weeks
- Full deployment: Week 9

## Key Features
- Gantt charts and timeline views
- Resource allocation and planning
- Built-in time tracking
- Advanced reporting and analytics
- 100+ app integrations
- Dedicated account manager
- Cloud and on-premise options
""")

        # ============================================================
        # CRM SYSTEM PROPOSALS (should NOT be included in Sarah's request)
        # ============================================================

        with self.files.open("/salesforce_connect_proposal.md", "w") as f:
            f.write("""# SalesForce Connect - CRM System Proposal

## Pricing
- Business Plan: $45,000/year
- Up to 50 sales reps included
- Additional reps: $75/user/month

## Timeline
- Implementation: 8-10 weeks
- Data migration: 3 weeks
- Go-live: Week 14

## Key Features
- Lead and opportunity tracking
- Sales pipeline visualization
- Email integration
- Customer 360 view
- AI-powered insights
- Mobile CRM app
""")

        with self.files.open("/clienthub_proposal.md", "w") as f:
            f.write("""# ClientHub Pro - CRM System Proposal

## Pricing
- Standard Plan: $35,000/year
- Up to 75 users included
- Extra users: $50/user/month

## Timeline
- Setup: 5-6 weeks
- Training: 2 weeks
- Launch: Week 8

## Key Features
- Contact management
- Deal tracking
- Email campaigns
- Reporting dashboards
- Third-party integrations
- Custom workflows
""")

        # Create Downloads directory for attachments
        self.files.makedirs("/Downloads")

        # ============================================================
        # USER'S EMAILS TO VENDORS (sent 7 days ago)
        # The project name is specified in USER's email, not vendor's reply
        # ============================================================

        # Project Management Platform vendors
        self.user_to_taskflow_id = "user_request_taskflow"
        user_to_taskflow = Email(
            email_id=self.user_to_taskflow_id,
            sender=self.email.user_email,
            recipients=["m.rodriguez@taskflow.com"],
            subject="Request for Proposal - Project Management Platform",
            content=(
                "Dear TaskFlow Solutions,\n\n"
                "We are evaluating vendors for our Project Management Platform initiative. "
                "Please send your proposal with pricing, timeline, and features.\n\n"
                "Best regards"
            ),
            timestamp=self.start_time - (7 * 24 * 3600),
            is_read=True,
        )
        self.email.add_email(user_to_taskflow, EmailFolderName.SENT)

        self.user_to_projectsync_id = "user_request_projectsync"
        user_to_projectsync = Email(
            email_id=self.user_to_projectsync_id,
            sender=self.email.user_email,
            recipients=["j.thompson@projectsync.com"],
            subject="Request for Proposal - Project Management Platform",
            content=(
                "Dear ProjectSync Technologies,\n\n"
                "We are evaluating vendors for our Project Management Platform initiative. "
                "Please send your proposal with pricing, timeline, and features.\n\n"
                "Best regards"
            ),
            timestamp=self.start_time - (7 * 24 * 3600),
            is_read=True,
        )
        self.email.add_email(user_to_projectsync, EmailFolderName.SENT)

        # CRM System vendors
        self.user_to_salesforce_id = "user_request_salesforce"
        user_to_salesforce = Email(
            email_id=self.user_to_salesforce_id,
            sender=self.email.user_email,
            recipients=["sales@salesforceconnect.com"],
            subject="Request for Proposal - CRM System",
            content=(
                "Dear SalesForce Connect,\n\n"
                "We are evaluating vendors for our CRM System project. "
                "Please send your proposal with pricing, timeline, and features.\n\n"
                "Best regards"
            ),
            timestamp=self.start_time - (7 * 24 * 3600),
            is_read=True,
        )
        self.email.add_email(user_to_salesforce, EmailFolderName.SENT)

        self.user_to_clienthub_id = "user_request_clienthub"
        user_to_clienthub = Email(
            email_id=self.user_to_clienthub_id,
            sender=self.email.user_email,
            recipients=["proposals@clienthub.com"],
            subject="Request for Proposal - CRM System",
            content=(
                "Dear ClientHub Pro,\n\n"
                "We are evaluating vendors for our CRM System project. "
                "Please send your proposal with pricing, timeline, and features.\n\n"
                "Best regards"
            ),
            timestamp=self.start_time - (7 * 24 * 3600),
            is_read=True,
        )
        self.email.add_email(user_to_clienthub, EmailFolderName.SENT)

        # Register all apps including filesystem
        self.apps = [self.agent_ui, self.system_app, self.files, self.email, self.note]

    def build_events_flow(self) -> None:
        """Build event flow - colleague request triggers agent to compile comparison from attachments."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        files_app = self.get_typed_app(SandboxLocalFileSystem, "Files")

        # ============================================================
        # Vendor replies with attachments (BEFORE capture_mode per guideline #14)
        # Note: Vendor replies are generic - they don't mention the project name
        # ============================================================

        # Project Management Platform vendors
        self.taskflow_reply_id = email_app.reply_to_email_from_user(
            sender="m.rodriguez@taskflow.com",
            email_id=self.user_to_taskflow_id,
            content=(
                "Dear John,\n\n"
                "Thank you for your interest. Please find our proposal attached.\n\n"
                "Best regards,\nMichael Rodriguez\nTaskFlow Solutions Sales"
            ),
            attachment_paths=["/taskflow_proposal.md"],
        )

        self.projectsync_reply_id = email_app.reply_to_email_from_user(
            sender="j.thompson@projectsync.com",
            email_id=self.user_to_projectsync_id,
            content=(
                "Hi there,\n\n"
                "We're excited to present our solution. Details are in the attached proposal.\n\n"
                "Regards,\nJessica Thompson\nProjectSync Technologies"
            ),
            attachment_paths=["/projectsync_proposal.md"],
        )

        # CRM System vendors
        self.salesforce_reply_id = email_app.reply_to_email_from_user(
            sender="sales@salesforceconnect.com",
            email_id=self.user_to_salesforce_id,
            content=(
                "Hello,\n\n"
                "Thank you for considering SalesForce Connect. Our proposal is attached.\n\n"
                "Best,\nSalesForce Connect Team"
            ),
            attachment_paths=["/salesforce_connect_proposal.md"],
        )

        self.clienthub_reply_id = email_app.reply_to_email_from_user(
            sender="proposals@clienthub.com",
            email_id=self.user_to_clienthub_id,
            content=(
                "Hi,\n\n"
                "Please find our proposal attached. Let us know if you have questions.\n\n"
                "Thanks,\nClientHub Pro Sales"
            ),
            attachment_paths=["/clienthub_proposal.md"],
        )

        with EventRegisterer.capture_mode():
            # ENV Event: Colleague asks specifically for Project Management Platform comparison
            colleague_request = email_app.send_email_to_user_only(
                sender="sarah.chen@company.com",
                subject="Project Management Platform Comparison Needed",
                content=(
                    "Hi,\n\n"
                    "The project committee meeting is this afternoon. Could you compile a comparison "
                    "of the vendor proposals for the Project Management Platform project? "
                    "We need to compare pricing, timelines, and features.\n\n"
                    "Thanks,\nSarah"
                ),
            ).delayed(5)

            # Oracle: Agent proposes to compile comparison note
            proposal = (
                aui.send_message_to_user(
                    content=(
                        "I saw Sarah's email requesting a vendor comparison for the Project Management Platform. "
                        "I found two relevant proposals from TaskFlow Solutions and ProjectSync Technologies. "
                        "I can download and read their attached proposals, then compile a comparison note "
                        "in your Work folder. Would you like me to do that?"
                    )
                )
                .oracle()
                .depends_on(colleague_request, delay_seconds=3)
            )

            # Oracle: User accepts
            acceptance = (
                aui.accept_proposal(content="Yes, please compile the comparison note.")
                .oracle()
                .depends_on(proposal, delay_seconds=2)
            )

            # Oracle: Agent downloads TaskFlow Solutions attachments
            download_taskflow = (
                email_app.download_attachments(
                    email_id=self.taskflow_reply_id,
                    folder_name="INBOX",
                    path_to_save="/Downloads/",
                )
                .oracle()
                .depends_on(acceptance, delay_seconds=2)
            )

            # Oracle: Agent reads TaskFlow Solutions proposal
            read_taskflow = (
                files_app.read_document(file_path="/Downloads/taskflow_proposal.md")
                .oracle()
                .depends_on(download_taskflow, delay_seconds=1)
            )

            # Oracle: Agent downloads ProjectSync Technologies attachments
            download_projectsync = (
                email_app.download_attachments(
                    email_id=self.projectsync_reply_id,
                    folder_name="INBOX",
                    path_to_save="/Downloads/",
                )
                .oracle()
                .depends_on(read_taskflow, delay_seconds=2)
            )

            # Oracle: Agent reads ProjectSync Technologies proposal
            read_projectsync = (
                files_app.read_document(file_path="/Downloads/projectsync_proposal.md")
                .oracle()
                .depends_on(download_projectsync, delay_seconds=1)
            )

            # Oracle: Agent creates comparison note (only for Project Management Platform)
            create_note = (
                note_app.create_note(
                    folder="Work",
                    title="Vendor Comparison - Project Management Platform",
                    content="""# Vendor Comparison Summary - Project Management Platform

## Pricing
| Vendor | Annual Cost | Users Included | Additional Users |
|--------|-------------|----------------|------------------|
| TaskFlow Solutions | $25,000/year | 100 | $20/user/month |
| ProjectSync Technologies | $30,000/year | 150 | $15/user/month |

## Timeline
| Vendor | Setup | Training | Go-live |
|--------|-------|----------|---------|
| TaskFlow Solutions | 6-8 weeks | 2 weeks | Week 10 |
| ProjectSync Technologies | 4-6 weeks | 3 weeks | Week 9 |

## Key Features
**TaskFlow Solutions**: Task dependencies, real-time collaboration, customizable dashboards, 50+ integrations, 24/7 support, mobile apps

**ProjectSync Technologies**: Gantt charts, resource planning, time tracking, advanced analytics, 100+ integrations, dedicated account manager, cloud/on-premise

## Summary
- **Faster deployment**: ProjectSync Technologies (Week 9 vs Week 10)
- **Lower cost**: TaskFlow Solutions ($25k vs $30k)
- **More users included**: ProjectSync Technologies (150 vs 100)
- **More integrations**: ProjectSync Technologies (100+ vs 50+)
""",
                )
                .oracle()
                .depends_on(read_projectsync, delay_seconds=3)
            )

        self.events = [
            colleague_request,
            proposal,
            acceptance,
            download_taskflow,
            read_taskflow,
            download_projectsync,
            read_projectsync,
            create_note,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent compiled correct vendor comparison into a note.

        Essential outcomes checked:
        1. Agent sent proposal to user
        2. Agent created a note
        3. Note contains correct vendor details (TaskFlow: $25,000, ProjectSync: $30,000)
        4. Note does NOT contain CRM vendor details (SalesForce: $45,000, ClientHub: $35,000)
        """
        try:
            log_entries = env.event_log.list_view()

            # Check 1: Agent sent proposal to user
            proposal_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PAREAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 2: Agent created a note and extract its content
            note_created = False
            note_content = ""
            for e in log_entries:
                if (
                    e.event_type == EventType.AGENT
                    and isinstance(e.action, Action)
                    and e.action.class_name == "StatefulNotesApp"
                    and e.action.function_name == "create_note"
                ):
                    note_created = True
                    note_content = e.action.args.get("content", "")
                    break

            # Check 3: Note contains correct Project Management Platform vendor details
            # TaskFlow: $25,000, ProjectSync: $30,000
            has_taskflow = "TaskFlow" in note_content and "25,000" in note_content
            has_projectsync = "ProjectSync" in note_content and "30,000" in note_content
            correct_vendors_included = has_taskflow and has_projectsync

            # Check 4: Note does NOT contain CRM vendor details
            # SalesForce: $45,000, ClientHub: $35,000
            has_salesforce = "SalesForce" in note_content or "45,000" in note_content
            has_clienthub = "ClientHub" in note_content or "35,000" in note_content
            wrong_vendors_excluded = not has_salesforce and not has_clienthub

            success = proposal_sent and note_created and correct_vendors_included and wrong_vendors_excluded

            if not success:
                issues = self._build_validation_issues(
                    proposal_sent, note_created, has_taskflow, has_projectsync, has_salesforce, has_clienthub
                )
                return ScenarioValidationResult(
                    success=False,
                    rationale=f"Validation failed: {'; '.join(issues)}",
                )

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)

    def _build_validation_issues(
        self,
        proposal_sent: bool,
        note_created: bool,
        has_taskflow: bool,
        has_projectsync: bool,
        has_salesforce: bool,
        has_clienthub: bool,
    ) -> list[str]:
        """Build list of validation issues for failure reporting."""
        issues: list[str] = []
        if not proposal_sent:
            issues.append("proposal to user not sent")
        if not note_created:
            issues.append("note not created")
        if not (has_taskflow and has_projectsync):
            missing = []
            if not has_taskflow:
                missing.append("TaskFlow ($25,000)")
            if not has_projectsync:
                missing.append("ProjectSync ($30,000)")
            issues.append(f"missing correct vendors: {', '.join(missing)}")
        if has_salesforce or has_clienthub:
            included = []
            if has_salesforce:
                included.append("SalesForce")
            if has_clienthub:
                included.append("ClientHub")
            issues.append(f"incorrectly included CRM vendors: {', '.join(included)}")
        return issues
