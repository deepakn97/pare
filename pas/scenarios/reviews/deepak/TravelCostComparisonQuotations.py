"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulEmailApp,
)
from pas.apps.cab import StatefulCabApp
from pas.apps.note import StatefulNotesApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("travel_cost_comparison_quotations")
class TravelCostComparisonQuotations(PASScenario):
    """Agent provides ride cost comparisons across multiple destinations based on an email request.

    The user receives an email from a friend, Sarah Martinez (sarah.m@email.com), asking for help comparing cab costs from the user's current location (Downtown Office, 123 Main St) to three different restaurant options for an upcoming dinner meetup: "Bella Trattoria" (456 Elm St), "Sakura Sushi Bar" (789 Oak Ave), and "The Green Bistro" (321 Pine Rd). The email explicitly requests: (1) cost estimates for each route using standard and premium cab services, (2) a summary note the user can reference later, and (3) a recommendation on which restaurant offers the best value considering ride costs. The agent must: 1. Parse the email to extract the start location and three destination addresses. 2. Propose gathering Standard and Premium cab quotations for each route. 3. After user acceptance, request cab quotations for each of the three routes using `get_quotation`. 4. Create a new note titled "Restaurant Ride Cost Comparison" in the "Personal" folder summarizing the destinations and confirming quotations were retrieved for both Standard and Premium service types. 5. Create/move the note to a new folder called "Travel Planning" for organization. 6. Reply to Sarah's email with a brief summary and recommendation, referencing the saved note.

    This scenario exercises cab fare quotation workflows (`get_quotation`, `list_service_types`), structured note creation with comparative data synthesis, note organization via folder management (`new_folder`, `move_note`), and email-driven proactive assistance with actionable recommendations.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with baseline data.

        Baseline data in this scenario:
        - No pre-existing emails (the trigger email arrives as an environment event in Step 3)
        - No pre-existing notes (notes will be created by the agent during the workflow)
        - No pre-existing cab rides or quotations (quotations will be fetched by the agent)

        The email from Sarah Martinez arrives as an environment event, not baseline data,
        so the agent observes it arriving and can react to it.
        """
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize email app (no baseline emails)
        self.email = StatefulEmailApp(name="Emails")

        # Initialize note app with default folders (Inbox, Personal, Work)
        self.note = StatefulNotesApp(name="Notes")

        # Initialize cab app (no baseline rides or quotations)
        self.cab = StatefulCabApp(name="Cab")

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.note, self.cab]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Incoming email from Sarah requesting cab cost comparison
            # This email contains all necessary details: start location, three destinations, and requirements
            sarah_email_event = email_app.send_email_to_user_with_id(
                email_id="email-sarah-restaurant-comparison",
                sender="sarah.m@email.com",
                subject="Help with Restaurant Choice for Dinner Meetup?",
                content="""Hi! I'm planning our dinner meetup and trying to decide between three restaurants. Could you help me compare the cab costs from your office (Downtown Office, 123 Main St) to each option? I'd really appreciate it if you could check both Standard and Premium cab pricing for:

1. Bella Trattoria (456 Elm St)
2. Sakura Sushi Bar (789 Oak Ave)
3. The Green Bistro (321 Pine Rd)

If you could put together a quick comparison note with the cost estimates and let me know which restaurant would be most economical ride-wise, that would be amazing! If you have a folder like "Travel Planning", please save the note there so we can reference it later. Thanks so much!

- Sarah""",
            ).delayed(5)

            # Oracle Event 2: Agent reads the incoming email to understand the request
            # Motivation: sarah_email_event contains explicit request "help me compare the cab costs" and "check both Standard and Premium cab pricing"
            read_email_event = (
                email_app.get_email_by_id(
                    email_id="email-sarah-restaurant-comparison",
                    folder_name="INBOX",
                )
                .oracle()
                .depends_on(sarah_email_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent sends proposal to user (before doing bulk quotation gathering)
            # Motivation: sarah_email_event explicitly requests "help me compare the cab costs" and "check both Standard and Premium cab pricing".
            proposal_event = (
                aui.send_message_to_user(
                    content="""I received Sarah's email requesting cab cost comparisons for three restaurant options. I can gather quotations for Standard and Premium rides to each location, create a comparison note with cost analysis, and reply to her with a recommendation. Would you like me to proceed?"""
                )
                .oracle()
                .depends_on(read_email_event, delay_seconds=2)
            )

            # Oracle Event 4: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please go ahead and help Sarah with the comparison.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent gets quotation for first destination (Bella Trattoria) - Standard service (user-gated)
            # Motivation: acceptance_event approved doing the comparison work; read_email_event provides destination address.
            quotation_bella_standard = (
                cab_app.get_quotation(
                    start_location="Downtown Office, 123 Main St",
                    end_location="456 Elm St",
                    service_type="Default",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent gets quotation for first destination (Bella Trattoria) - Premium service (user-gated)
            quotation_bella_premium = (
                cab_app.get_quotation(
                    start_location="Downtown Office, 123 Main St",
                    end_location="456 Elm St",
                    service_type="Premium",
                )
                .oracle()
                .depends_on(quotation_bella_standard, delay_seconds=1)
            )

            # Oracle Event 7: Agent gets quotation for second destination (Sakura Sushi Bar) - Standard service (user-gated)
            quotation_sakura_standard = (
                cab_app.get_quotation(
                    start_location="Downtown Office, 123 Main St",
                    end_location="789 Oak Ave",
                    service_type="Default",
                )
                .oracle()
                .depends_on(quotation_bella_premium, delay_seconds=1)
            )

            # Oracle Event 8: Agent gets quotation for second destination (Sakura Sushi Bar) - Premium service (user-gated)
            quotation_sakura_premium = (
                cab_app.get_quotation(
                    start_location="Downtown Office, 123 Main St",
                    end_location="789 Oak Ave",
                    service_type="Premium",
                )
                .oracle()
                .depends_on(quotation_sakura_standard, delay_seconds=1)
            )

            # Oracle Event 9: Agent gets quotation for third destination (The Green Bistro) - Standard service (user-gated)
            quotation_green_standard = (
                cab_app.get_quotation(
                    start_location="Downtown Office, 123 Main St",
                    end_location="321 Pine Rd",
                    service_type="Default",
                )
                .oracle()
                .depends_on(quotation_sakura_premium, delay_seconds=1)
            )

            # Oracle Event 10: Agent gets quotation for third destination (The Green Bistro) - Premium service (user-gated)
            quotation_green_premium = (
                cab_app.get_quotation(
                    start_location="Downtown Office, 123 Main St",
                    end_location="321 Pine Rd",
                    service_type="Premium",
                )
                .oracle()
                .depends_on(quotation_green_standard, delay_seconds=1)
            )

            # Oracle Event 11: Agent creates a new note with the comparison data (user-gated write)
            # Motivation: acceptance_event approved the work; read_email_event requested "put together a quick comparison note".
            create_note_event = (
                note_app.create_note(
                    folder="Personal",
                    title="Restaurant Ride Cost Comparison",
                    content="""Restaurant Cab Cost Comparison for Dinner Meetup
From: Downtown Office, 123 Main St

Destination 1: Bella Trattoria (456 Elm St)
- Standard Service: Quotation retrieved (see Cab quotation results)
- Premium Service: Quotation retrieved (see Cab quotation results)

Destination 2: Sakura Sushi Bar (789 Oak Ave)
- Standard Service: Quotation retrieved (see Cab quotation results)
- Premium Service: Quotation retrieved (see Cab quotation results)

Destination 3: The Green Bistro (321 Pine Rd)
- Standard Service: Quotation retrieved (see Cab quotation results)
- Premium Service: Quotation retrieved (see Cab quotation results)

Value Recommendation: Based on the quotations, choose the lowest-cost route/service combination.""",
                )
                .oracle()
                .depends_on(quotation_green_premium, delay_seconds=2)
            )

            # Oracle Event 12: Agent creates new folder "Travel Planning"
            # Motivation: read_email_event asks to save the comparison note in a folder like "Travel Planning" for later reference.
            # WRITE action gated by user acceptance (acceptance_event through create_note_event dependency)
            create_folder_event = (
                note_app.new_folder(folder_name="Travel Planning")
                .oracle()
                .depends_on(create_note_event, delay_seconds=1)
            )

            # Oracle Event 13: Agent moves note to the new folder
            # Motivation: read_email_event requests saving the note in "Travel Planning"; create_folder_event ensures the folder exists.
            # WRITE action gated by user acceptance (acceptance_event through dependency chain)
            move_note_event = (
                note_app.move_note(
                    note_id=create_note_event.metadata.return_value
                    if hasattr(create_note_event, "metadata") and create_note_event.metadata
                    else "",
                    source_folder_name="Personal",
                    dest_folder_name="Travel Planning",
                )
                .oracle()
                .depends_on(create_folder_event, delay_seconds=1)
            )

            # Oracle Event 14: Agent replies to Sarah's email with the comparison summary
            # Motivation: read_email_event requested "let me know which restaurant would be most economical ride-wise", and acceptance_event approved helping Sarah
            # WRITE action gated by user acceptance (acceptance_event through dependency chain)
            reply_email_event = (
                email_app.reply_to_email(
                    email_id="email-sarah-restaurant-comparison",
                    folder_name="INBOX",
                    content="""Hi Sarah!

I've gathered the cab cost estimates for all three restaurants from Downtown Office. Here's the comparison:

**Bella Trattoria (456 Elm St)**
- Standard: Quotation retrieved
- Premium: Quotation retrieved

**Sakura Sushi Bar (789 Oak Ave)**
- Standard: Quotation retrieved
- Premium: Quotation retrieved

**The Green Bistro (321 Pine Rd)**
- Standard: Quotation retrieved
- Premium: Quotation retrieved

**Recommendation:** Based on the quotations, the lowest-cost route/service combination is the best value for ride costs.

I've saved the detailed comparison in a note in my Travel Planning folder for future reference. Hope this helps with your decision!""",
                )
                .oracle()
                .depends_on(move_note_event, delay_seconds=2)
            )

        # Register ALL events here in self.events
        self.events = [
            sarah_email_event,
            read_email_event,
            proposal_event,
            acceptance_event,
            quotation_bella_standard,
            quotation_bella_premium,
            quotation_sakura_standard,
            quotation_sakura_premium,
            quotation_green_standard,
            quotation_green_premium,
            create_note_event,
            create_folder_event,
            move_note_event,
            reply_email_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only agent/oracle events
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent sent proposal to the user mentioning Sarah and cost comparison
            proposal_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["sarah", "restaurant", "cab", "cost", "comparison", "quotation"]
                )
                for e in agent_events
            )

            # STRICT Check 2: Agent read the incoming email to parse the request
            # Accept either get_email_by_id or list_emails as equivalent methods for detecting the email
            email_read_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name in ["get_email_by_id", "list_emails"]
                for e in agent_events
            )

            # STRICT Check 3: Agent requested cab quotations (should be at least 3-6 quotations for the destinations)
            # Flexible on exact count, but needs multiple quotations
            quotation_events = [
                e
                for e in agent_events
                if isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "get_quotation"
            ]
            quotations_found = len(quotation_events) >= 3  # At least 3 destinations checked

            # STRICT Check 4: Agent created a comparison note
            # Flexible on exact title wording, but must create a note
            note_created = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "create_note"
                for e in agent_events
            )

            # STRICT Check 5: Agent created a new folder for organization
            # Flexible on exact folder name, but must create a folder
            folder_created = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "new_folder"
                for e in agent_events
            )

            # STRICT Check 6: Agent moved the note to organize it
            note_moved = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "move_note"
                for e in agent_events
            )

            # STRICT Check 7: Agent replied to Sarah's email with the comparison results
            # Flexible on exact content, just check that reply_to_email was called
            email_reply_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                for e in agent_events
            )

            # Determine overall success
            success = (
                proposal_found
                and email_read_found
                and quotations_found
                and note_created
                and folder_created
                and note_moved
                and email_reply_found
            )

            # Build failure rationale if not successful
            if not success:
                failed_checks = []
                if not proposal_found:
                    failed_checks.append("no proposal message to user found")
                if not email_read_found:
                    failed_checks.append("agent did not read Sarah's email")
                if not quotations_found:
                    failed_checks.append(
                        f"insufficient cab quotations (found {len(quotation_events)}, expected at least 3)"
                    )
                if not note_created:
                    failed_checks.append("no comparison note created")
                if not folder_created:
                    failed_checks.append("no folder created for organization")
                if not note_moved:
                    failed_checks.append("note was not moved to folder")
                if not email_reply_found:
                    failed_checks.append("no reply email sent to Sarah")

                rationale = "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
