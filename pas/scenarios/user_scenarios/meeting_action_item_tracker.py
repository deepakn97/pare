"""
Scenario: proactive_meeting_action_item_tracker
Agent reviews meeting notes, extracts action items, identifies responsible contacts,
and proactively schedules follow-up reminders with notifications.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps.calendar import StatefulCalendarApp
from pas.apps.contacts import StatefulContactsApp
from pas.apps.messaging import StatefulMessagingApp


# ---------- Parameters ----------
@dataclass
class ActionItemParams:
    meeting_title: str
    action_items: list[tuple[str, str]]
    followup_date: str


# ---------- Scenario ----------
@register_scenario("proactive_meeting_action_item_tracker")
class ScenarioMeetingActionItemTracker(Scenario):
    """Agent proactively summarizes meeting action items and sets follow-up reminders."""

    def __init__(self) -> None:
        super().__init__()
        self._params = self._get_default_params()

    def _get_default_params(self) -> ActionItemParams:
        return ActionItemParams(
            meeting_title="Product Sprint Sync",
            action_items=[
                ("Prepare new API documentation", "Alice"),
                ("Finalize UI mockups", "Bob"),
                ("Test login flow", "Carol"),
            ],
            followup_date="2025-11-05T17:00:00Z",
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps required for this scenario."""
        agui = AgentUserInterface()
        system = SystemApp()
        calendar = StatefulCalendarApp()
        contacts = StatefulContactsApp()
        messaging = StatefulMessagingApp()
        self.apps = [agui, system, calendar, contacts, messaging]

    def build_events_flow(self) -> None:
        """Build proactive event flow."""
        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(StatefulCalendarApp)
        contacts = self.get_typed_app(StatefulContactsApp)
        messaging = self.get_typed_app(StatefulMessagingApp)
        p = self._params

        action_summary = "\n  - " + "\n  - ".join([f"{t} → {a}" for t, a in p.action_items])

        with EventRegisterer.capture_mode():
            # Agent proactively summarizes meeting notes
            proactive_start = aui.send_message_to_user(
                content=(
                    f"I reviewed the notes from '{p.meeting_title}' and extracted these action items:"
                    f"{action_summary}"
                )
            ).depends_on(None, delay_seconds=1)

            # Agent offers to schedule reminders
            offer_followup = aui.send_message_to_user(
                content=f"Would you like me to set reminders for these tasks on {p.followup_date.split('T')[0]}?"
            ).depends_on(proactive_start, delay_seconds=1)

            # User confirms scheduling
            user_confirm = aui.send_message_to_agent(
                content="Yes, please schedule follow-up reminders for everyone."
            ).depends_on(offer_followup, delay_seconds=1)

            # Oracle retrieves contacts (realistic action)
            fetch_contacts = (
                contacts.search_contacts(query="; ".join([a for _, a in p.action_items]))
                .oracle()
                .depends_on(user_confirm, delay_seconds=1)
            )

            # Oracle creates follow-up calendar event
            create_event = (
                calendar.add_calendar_event(
                    title=f"Follow-up: {p.meeting_title}",
                    start_datetime=p.followup_date,
                    end_datetime=p.followup_date,
                    description="Automated reminder for meeting action items.",
                    location="Office",
                    attendees=[a for _, a in p.action_items],
                    tag="followup",
                )
                .oracle()
                .depends_on(fetch_contacts, delay_seconds=1)
            )

            # Oracle sends team notification
            notify_team = (
                messaging.send_message(
                    user_id="team_channel",
                    content=(
                        f"Follow-up scheduled for '{p.meeting_title}'. "
                        f"Action items:{action_summary}"
                    ),
                )
                .oracle()
                .depends_on(create_event, delay_seconds=1)
            )

            # Agent confirms completion
            confirm_msg = aui.send_message_to_user(
                content=f"Reminders and notifications have been set for '{p.meeting_title}'."
            ).depends_on(notify_team, delay_seconds=1)

        self.events = [
            proactive_start,
            offer_followup,
            user_confirm,
            fetch_contacts,
            create_event,
            notify_team,
            confirm_msg,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate proactive initiation, calendar creation, and messaging notification."""
        print("[DEBUG] proactive_meeting_action_item_tracker: validate() called")

        try:
            events = env.event_log.list_view()
            p = self._params

            # Agent proactive initiation
            proactive_detected = any(
                isinstance(e.action, Action)
                and e.action.class_name == "AgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "i reviewed the notes" in e.action.args.get("content", "").lower()
                for e in events
            )

            # Calendar event creation
            followup_created = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and p.meeting_title.lower() in e.action.args.get("title", "").lower()
                for e in events
            )

            # Messaging notification
            team_notified = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                for e in events
            )

            success = proactive_detected and followup_created and team_notified

            print("\n[VALIDATION SUMMARY]")
            print(f"  - Proactive start detected:  {'PASS' if proactive_detected else 'FAIL'}")
            print(f"  - Calendar event created:    {'PASS' if followup_created else 'FAIL'}")
            print(f"  - Team notified via message: {'PASS' if team_notified else 'FAIL'}")
            print(f"  => Scenario result: {'PASS' if success else 'FAIL'}\n")

            return ScenarioValidationResult(success=success)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return ScenarioValidationResult(success=False, exception=e)
