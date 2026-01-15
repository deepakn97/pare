"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.contacts import Contact
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
    StatefulEmailApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("project_task_filtering_calendar")
class ProjectTaskFilteringCalendar(PASScenario):
    """Agent synthesizes project tasks from multiple emails, filters user-assigned tasks, and creates calendar deadlines.

    The user receives three emails from their project manager Sarah Kim about the upcoming "Mobile App Redesign" project. The first email outlines the overall project timeline and lists five different tasks distributed among the team: UI mockups (assigned to the user, due Nov 25), backend API updates (assigned to Tom), user testing plan (assigned to the user, due Nov 28), database migration (assigned to Jennifer), and final presentation deck (assigned to the user, due Dec 1). The second email clarifies that the user testing plan deadline has moved to Nov 27. The third email adds that the presentation should be coordinated with Tom. The agent must: 1. Parse all three emails and extract task assignments. 2. Filter tasks specifically assigned to the user (UI mockups, user testing plan, presentation deck). 3. Apply the deadline update from the second email (Nov 27 for user testing). 4. Create three separate calendar events for the user's tasks with correct deadlines. 5. Reply to Sarah's email thread confirming which tasks the user will handle and their deadlines.

    This scenario exercises multi-email information synthesis, task assignment filtering from mixed team information, temporal update reconciliation, selective calendar event creation based on assignment ownership, and consolidated email confirmation of understood responsibilities..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Email app
        self.email = StatefulEmailApp(name="Emails")

        # Initialize Calendar app
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Populate baseline data: Sarah Kim as a known contact
        contact_sarah = Contact(
            first_name="Sarah",
            last_name="Kim",
            email="sarah.kim@company.com",
            phone="+1-555-0123",
        )

        # Add Sarah's contact to the email app (baseline state - user knows Sarah)
        # Note: No baseline emails or calendar events yet - all arrive via events flow

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.calendar]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")

        with EventRegisterer.capture_mode():
            # Environment Event 1: First email with overall project timeline and task assignments
            email1_event = email_app.send_email_to_user_with_id(
                email_id="email-project-overview",
                sender="sarah.kim@company.com",
                subject="Mobile App Redesign - Project Kickoff",
                content="""Hi team,

I'm excited to announce the Mobile App Redesign project! Here's our task breakdown:

1. UI mockups - Assigned to you, due Nov 25
2. Backend API updates - Assigned to Tom, due Nov 26
3. User testing plan - Assigned to you, due Nov 28
4. Database migration - Assigned to Jennifer, due Nov 29
5. Final presentation deck - Assigned to you, due Dec 1

Please add your assigned deadlines to your calendar and block time so nothing slips.

Best,
Sarah""",
            ).delayed(10)

            # Environment Event 2: Second email with deadline update for user testing plan
            email2_event = email_app.reply_to_email_from_user(
                sender="sarah.kim@company.com",
                email_id="email-project-overview",
                content="""Quick update: The user testing plan deadline has been moved up to Nov 27 (instead of Nov 28) due to stakeholder availability.

If you've already added it to your calendar, please update it to Nov 27.

Thanks,
Sarah""",
            ).delayed(25)

            # Environment Event 3: Third email with coordination note about presentation
            email3_event = email_app.reply_to_email_from_user(
                sender="sarah.kim@company.com",
                email_id="email-project-overview",
                content="""One more note: Please coordinate with Tom on the final presentation deck since his API work is a key component.

It may help to add a calendar block for the deck deadline so you can plan around Tom's timeline.

Sarah""",
            ).delayed(40)

            # Oracle Event 1: Agent reads the email thread to understand all tasks
            read_emails_event = (
                email_app.get_email_by_id(email_id="email-project-overview", folder_name="INBOX")
                .oracle()
                .depends_on(email3_event, delay_seconds=3)
            )

            # Oracle Event 2: Agent sends proposal to user about creating calendar events
            # Evidence: Sarah explicitly asked to add assigned deadlines to the calendar and (for the updated deadline)
            # to update any existing calendar entry.
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed you have three tasks assigned in Sarah's Mobile App Redesign project: UI mockups (due Nov 25), user testing plan (due Nov 27), and final presentation deck (due Dec 1). Would you like me to add these to your calendar?"
                )
                .oracle()
                .depends_on(read_emails_event, delay_seconds=2)
            )

            # Oracle Event 3: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please add them to my calendar.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 4: Agent creates calendar event for UI mockups (Nov 25)
            create_event1 = (
                calendar_app.add_calendar_event(
                    title="UI mockups - Mobile App Redesign",
                    start_datetime="2025-11-25 09:00:00",
                    end_datetime="2025-11-25 17:00:00",
                    description="Design UI mockups for Mobile App Redesign project",
                    tag="work",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 5: Agent creates calendar event for user testing plan (Nov 27)
            create_event2 = (
                calendar_app.add_calendar_event(
                    title="User testing plan - Mobile App Redesign",
                    start_datetime="2025-11-27 09:00:00",
                    end_datetime="2025-11-27 17:00:00",
                    description="Prepare user testing plan for Mobile App Redesign project",
                    tag="work",
                )
                .oracle()
                .depends_on(create_event1, delay_seconds=1)
            )

            # Oracle Event 6: Agent creates calendar event for final presentation deck (Dec 1)
            create_event3 = (
                calendar_app.add_calendar_event(
                    title="Final presentation deck - Mobile App Redesign",
                    start_datetime="2025-12-01 09:00:00",
                    end_datetime="2025-12-01 17:00:00",
                    description="Create final presentation deck, coordinate with Tom on API component",
                    tag="work",
                )
                .oracle()
                .depends_on(create_event2, delay_seconds=1)
            )

            # Oracle Event 7: Agent replies to Sarah confirming task ownership and deadlines
            reply_event = (
                email_app.reply_to_email(
                    email_id="email-project-overview",
                    folder_name="INBOX",
                    content="""Hi Sarah,

I've reviewed the project assignments and added my tasks to the calendar:
- UI mockups: Nov 25
- User testing plan: Nov 27 (updated deadline noted)
- Final presentation deck: Dec 1 (will coordinate with Tom)

Looking forward to contributing to the Mobile App Redesign!

Best""",
                )
                .oracle()
                .depends_on(create_event3, delay_seconds=2)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            email1_event,
            email2_event,
            email3_event,
            read_emails_event,
            proposal_event,
            acceptance_event,
            create_event1,
            create_event2,
            create_event3,
            reply_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent sent proposal to the user mentioning the three tasks assigned to user
            # STRICT: Must reference the Mobile App Redesign project and offer to add tasks to calendar
            # FLEXIBLE: Exact wording of task names can vary (e.g., "UI mockups" vs "UI design")
            proposal_found = any(
                (e.event_type == EventType.AGENT or e.event_type == EventType.ENV)
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check Step 2: Agent read the email thread to understand all tasks
            # STRICT: Must have read the email with id "email-project-overview"
            read_emails_found = any(
                (e.event_type == EventType.AGENT or e.event_type == EventType.ENV)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "get_email_by_id"
                and e.action.args.get("email_id") == "email-project-overview"
                for e in log_entries
            )

            # Check Step 3: Agent created calendar event for UI mockups (Nov 25)
            # STRICT: Must have correct date (Nov 25, 2025) and reference UI/mockups
            # FLEXIBLE: Time, exact title wording, and description details can vary
            ui_mockup_event_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "2025-11-25" in e.action.args.get("start_datetime", "")
                and any(keyword in e.action.args.get("title", "").lower() for keyword in ["ui", "mockup"])
                for e in log_entries
            )

            # Check Step 4: Agent created calendar event for user testing plan (Nov 27 - UPDATED deadline)
            # STRICT: Must have correct UPDATED date (Nov 27, not Nov 28) and reference testing/plan
            # FLEXIBLE: Time, exact title wording, and description details can vary
            testing_plan_event_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "2025-11-27" in e.action.args.get("start_datetime", "")
                and any(keyword in e.action.args.get("title", "").lower() for keyword in ["test", "testing", "plan"])
                for e in log_entries
            )

            # Check Step 5: Agent created calendar event for final presentation deck (Dec 1)
            # STRICT: Must have correct date (Dec 1, 2025) and reference presentation/deck
            # FLEXIBLE: Time, exact title wording, and description details can vary
            presentation_event_found = any(
                (e.event_type == EventType.AGENT)
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "2025-12-01" in e.action.args.get("start_datetime", "")
                and any(keyword in e.action.args.get("title", "").lower() for keyword in ["presentation", "deck"])
                for e in log_entries
            )

            # Determine success and rationale
            success = (
                proposal_found
                and read_emails_found
                and ui_mockup_event_found
                and testing_plan_event_found
                and presentation_event_found
            )

            # Build rationale if validation fails
            rationale = None
            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal to add tasks to calendar")
                if not read_emails_found:
                    missing_checks.append("agent reading email thread")
                if not ui_mockup_event_found:
                    missing_checks.append("calendar event for UI mockups (Nov 25)")
                if not testing_plan_event_found:
                    missing_checks.append("calendar event for user testing plan (Nov 27 updated deadline)")
                if not presentation_event_found:
                    missing_checks.append("calendar event for final presentation (Dec 1)")

                rationale = f"Missing critical checks: {', '.join(missing_checks)}"

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
