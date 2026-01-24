"""Scenario: Agent compares cab costs to restaurants and replies to friend's email."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

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
    """Agent compares cab costs to two restaurants and replies to friend with recommendation.

    The user receives an email from their friend Sarah asking for help comparing cab costs
    from the user's office to two restaurant options for their dinner meetup. The agent
    gathers quotations for both Default and Premium service types, proactively creates a
    comparison note for the user's reference, and replies to Sarah with a recommendation.

    This scenario tests:
    - Email-triggered proactive assistance
    - Cab quotation gathering across multiple destinations and service types
    - Proactive note creation for user reference (without explicit request)
    - Email reply with synthesized recommendation
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    additional_system_prompt = """Your friend Sarah is meeting you at your office for dinner tonight.
She's asking for help deciding between two restaurants based on cab costs.

BEFORE Sarah's email arrives:
- Check your email inbox

AFTER Sarah's email arrives:

ACCEPT proposals that:
- Offer to check cab costs for both restaurants
- Offer to compare Default and Premium service options
- Offer to reply to Sarah with the results

REJECT proposals that:
- Only check one restaurant
- Only check one service type (need both Default and Premium)"""

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with baseline data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails")

        # Initialize note app
        self.note = StatefulNotesApp(name="Notes")

        # Initialize cab app
        self.cab = StatefulCabApp(name="Cab")

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.note, self.cab]

    def build_events_flow(self) -> None:
        """Build event flow - email triggers cab cost comparison workflow."""
        aui = self.get_typed_app(PASAgentUserInterface)
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # ENV Event: Email from Sarah asking for cab cost comparison
            sarah_email_event = email_app.send_email_to_user_with_id(
                email_id="email-sarah-restaurant",
                sender="sarah.m@email.com",
                subject="Quick question about dinner tonight",
                content="""Hey! I'm meeting you at your office later and trying to decide between two restaurants for dinner. Can you check how much a cab would cost from your place (Downtown Office, 123 Main St) to:

1. Bella Trattoria (456 Elm St)
2. Sakura Sushi Bar (789 Oak Ave)

If you could check both regular and premium cab options that would be great - I want to compare. Let me know which one you'd recommend!

- Sarah""",
            ).delayed(5)

            # Oracle: Agent proposes to gather cab quotations
            proposal_event = (
                aui.send_message_to_user(
                    content="Sarah is asking for cab cost comparisons to two restaurants for your dinner tonight. I can check both Default and Premium pricing for each location and reply with a recommendation. Would you like me to do that?"
                )
                .oracle()
                .depends_on(sarah_email_event, delay_seconds=3)
            )

            # Oracle: User accepts
            acceptance_event = (
                aui.accept_proposal(content="Yes, please check the costs and let her know.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle: Get quotation for Bella Trattoria - Default
            quotation_bella_default = (
                cab_app.get_quotation(
                    start_location="Downtown Office, 123 Main St",
                    end_location="456 Elm St",
                    service_type="Default",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle: Get quotation for Bella Trattoria - Premium
            quotation_bella_premium = (
                cab_app.get_quotation(
                    start_location="Downtown Office, 123 Main St",
                    end_location="456 Elm St",
                    service_type="Premium",
                )
                .oracle()
                .depends_on(quotation_bella_default, delay_seconds=1)
            )

            # Oracle: Get quotation for Sakura Sushi Bar - Default
            quotation_sakura_default = (
                cab_app.get_quotation(
                    start_location="Downtown Office, 123 Main St",
                    end_location="789 Oak Ave",
                    service_type="Default",
                )
                .oracle()
                .depends_on(quotation_bella_premium, delay_seconds=1)
            )

            # Oracle: Get quotation for Sakura Sushi Bar - Premium
            quotation_sakura_premium = (
                cab_app.get_quotation(
                    start_location="Downtown Office, 123 Main St",
                    end_location="789 Oak Ave",
                    service_type="Premium",
                )
                .oracle()
                .depends_on(quotation_sakura_default, delay_seconds=1)
            )

            # Oracle: Agent proactively creates a comparison note for user reference
            create_note_event = (
                note_app.create_note(
                    folder="Personal",
                    title="Dinner Cab Cost Comparison",
                    content="""Cab Cost Comparison for Dinner with Sarah
From: Downtown Office, 123 Main St

Bella Trattoria (456 Elm St):
- Default: [quotation retrieved]
- Premium: [quotation retrieved]

Sakura Sushi Bar (789 Oak Ave):
- Default: [quotation retrieved]
- Premium: [quotation retrieved]""",
                )
                .oracle()
                .depends_on(quotation_sakura_premium, delay_seconds=2)
            )

            # Oracle: Agent replies to Sarah with recommendation
            reply_event = (
                email_app.reply_to_email(
                    email_id="email-sarah-restaurant",
                    folder_name="INBOX",
                    content="""Hey Sarah!

I checked the cab costs from my office to both restaurants:

Bella Trattoria (456 Elm St):
- Default: checked
- Premium: checked

Sakura Sushi Bar (789 Oak Ave):
- Default: checked
- Premium: checked

Based on the prices, I'd recommend going with whichever has the lower Default fare since we don't need Premium. See you tonight!""",
                )
                .oracle()
                .depends_on(create_note_event, delay_seconds=2)
            )

        self.events = [
            sarah_email_event,
            proposal_event,
            acceptance_event,
            quotation_bella_default,
            quotation_bella_premium,
            quotation_sakura_default,
            quotation_sakura_premium,
            create_note_event,
            reply_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent gathers quotations, creates note, and replies to Sarah."""
        try:
            log_entries = env.event_log.list_view()

            # Essential outcome 1: Agent sent proposal to user
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Essential outcome 2: Agent gathered cab quotations (4 total: 2 restaurants x 2 service types)
            quotation_count = sum(
                1
                for e in log_entries
                if e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "get_quotation"
            )
            quotations_found = quotation_count >= 4

            # Essential outcome 3: Agent created a comparison note
            note_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "create_note"
                for e in log_entries
            )

            # Essential outcome 4: Agent replied to Sarah's email
            reply_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == "email-sarah-restaurant"
                for e in log_entries
            )

            success = proposal_found and quotations_found and note_created and reply_sent

            if not success:
                missing = []
                if not proposal_found:
                    missing.append("proposal to user")
                if not quotations_found:
                    missing.append(f"cab quotations (found {quotation_count}, need at least 4)")
                if not note_created:
                    missing.append("comparison note")
                if not reply_sent:
                    missing.append("reply to Sarah's email")
                rationale = f"Missing: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
