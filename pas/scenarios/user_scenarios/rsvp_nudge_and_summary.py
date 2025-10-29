"""
Scenario: rsvp_nudge_and_summary
Agent invites a contact list through messaging + email, nudges non-responders,
creates a calendar event upon confirmations, and returns an RSVP summary.

Only uses existing apps in your tree: agent_ui, calendar, contacts, email, messaging.

Design differences vs your existing scenarios
--------------------------------------------
- Focuses on RSVP orchestration (invite → track → nudge → calendar → summary)
- Uses multi-channel outreach (messaging + email) rather than just scheduling
- Includes a compact roster summary and a follow-up nudge step
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Any, TYPE_CHECKING

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps.calendar import StatefulCalendarApp
from pas.apps.contacts import StatefulContactsApp as ContactsApp
from pas.apps.email import StatefulEmailApp as EmailApp
from pas.apps.messaging import StatefulMessagingApp as MessagingApp


@dataclass
class RSVPParams:
    """Parameters for the RSVP + nudge + summary flow."""
    title: str
    start_time: str
    end_time: str
    invitees: List[str]   # use emails/usernames; ContactsApp can map if needed
    message_template: str
    email_subject: str
    email_body_template: str


@register_scenario("rsvp_nudge_and_summary")
class ScenarioRSVPNudgeAndSummary(Scenario):
    """Invite via messaging+email, track responses, nudge, create event, summarize."""

    def __init__(self) -> None:
        super().__init__()
        self._params = self._get_default_params()

    def _get_default_params(self) -> RSVPParams:
        return RSVPParams(
            title="Sprint Retro",
            start_time="2025-10-30T17:00:00Z",
            end_time="2025-10-30T17:30:00Z",
            invitees=["alice@example.com", "bob@example.com", "carol@example.com"],
            message_template=(
                "Hi {name}! Can you join '{title}'? Reply yes/no. Time: {start}"
            ),
            email_subject="RSVP: {title}",
            email_body_template=(
                "Hello {name},\n\nWe're planning '{title}'. Time: {start}.\nPlease reply yes/no.\n"
            ),
        )

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        print("[DEBUG] rsvp_nudge_and_summary: init_and_populate_apps")
        agui = AgentUserInterface()
        system = SystemApp()
        calendar = StatefulCalendarApp()
        contacts = ContactsApp()
        email = EmailApp()
        messaging = MessagingApp()
        self.apps = [agui, system, calendar, contacts, email, messaging]

    def build_events_flow(self) -> None:
        print("[DEBUG] rsvp_nudge_and_summary: build_events_flow")
        aui = self.get_typed_app(AgentUserInterface)
        calendar = self.get_typed_app(StatefulCalendarApp)
        contacts = self.get_typed_app(ContactsApp)
        email = self.get_typed_app(EmailApp)
        messaging = self.get_typed_app(MessagingApp)
        p = self._params
        user_id = "demo_user"  # added placeholder user_id for MessagingAppV2 compatibility

        def resolve_name(addr: str) -> str:
            try:
                c = contacts.lookup(addr)  # if your ContactsApp exposes lookup
                return c.get("name", addr)
            except Exception:
                return addr

        with EventRegisterer.capture_mode():
            # 1) System detects need to coordinate
            detected = aui.send_message_to_agent(
                content=f"[System] Need to coordinate RSVPs for '{p.title}'."
            ).depends_on(None, delay_seconds=1)

            # 2) Agent drafts and sends invites over messaging & email
            invite_msgs = []
            invite_emails = []
            prev = detected
            for addr in p.invitees:
                name = resolve_name(addr)
