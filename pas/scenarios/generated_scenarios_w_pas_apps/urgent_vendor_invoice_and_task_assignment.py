from __future__ import annotations

from typing import Any

from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps.calendar.app import StatefulCalendarApp
from pas.apps.email.app import StatefulEmailApp
from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.proactive_aui import PASAgentUserInterface
from pas.apps.system import HomeScreenSystemApp


@register_scenario("urgent_vendor_invoice_and_task_assignment")
class UrgentVendorInvoiceAndTaskAssignment(Scenario):
    """Scenario where the agent identifies an urgent vendor payment email, offers.

    To notify finance team and automatically set up a review call on the user's calendar.
    """

    start_time: float | None = 0
    duration: float | None = 3500

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps and pre-populate with team and calendar context."""
        self.calendar_app = StatefulCalendarApp(name="StatefulCalendarApp")
        self.email_app = StatefulEmailApp(name="StatefulEmailApp")
        self.messaging_app = StatefulMessagingApp(name="StatefulMessagingApp")
        self.agent_ui = PASAgentUserInterface(name="PASAgentUserInterface")
        self.system_app = HomeScreenSystemApp(name="HomeScreenSystemApp")

        # Define messaging participants
        self.messaging_app.current_user_id = "usr-fin-001"
        self.messaging_app.current_user_name = "Jordan Evans"
        self.messaging_app.add_users([
            {"user_id": "acct-team", "user_name": "Accounts Team"},
            {"user_id": "fin-lead", "user_name": "Priya Kumar"},
            {"user_id": "vendor-rep", "user_name": "Vendor Support"},
        ])

        # Create a Finance group conversation
        self.finance_conv_id = self.messaging_app.create_group_conversation(
            user_ids=["acct-team", "fin-lead"], title="Finance - Vendor Requests"
        )

        # Add a placeholder calendar event for weekly ops sync
        self.ops_event_id = self.calendar_app.add_calendar_event(
            title="Weekly Operations Sync",
            start_datetime="2024-06-21 10:30:00",
            end_datetime="2024-06-21 11:00:00",
            location="Conference Room 3B",
            description="Status updates across departments",
            tag="ops",
            attendees=["Jordan Evans", "Operations Team"],
        )

        self.apps = [
            self.calendar_app,
            self.email_app,
            self.messaging_app,
            self.agent_ui,
            self.system_app,
        ]

    def build_events_flow(self) -> None:
        """Construct the email-based workflow where the agent assists with a vendor payment follow-up."""
        cal = self.get_typed_app(StatefulCalendarApp)
        emails = self.get_typed_app(StatefulEmailApp)
        msgs = self.get_typed_app(StatefulMessagingApp)
        aui = self.get_typed_app(PASAgentUserInterface)
        sys_app = self.get_typed_app(HomeScreenSystemApp)

        with EventRegisterer.capture_mode():
            # 1. Vendor sends an urgent invoice follow-up email
            vendor_email_evt = emails.send_email_to_user_with_id(
                email_id="email-inv-2049",
                sender="billing@datascan-analytics.com",
                subject="Urgent: Overdue Invoice #2049 requiring approval",
                content=(
                    "Dear Jordan, invoice #2049 for dataset subscription renewal "
                    "remains pending approval. The service will pause if unpaid by end of today."
                ),
            )

            # 2. The agent detects the urgency and proactively offers to coordinate a fix
            agent_offer_evt = (
                aui.send_message_to_user(
                    content=(
                        "I've noticed an urgent invoice from DataScan requiring approval. "
                        "Would you like me to notify the finance team and book a short review call now?"
                    )
                )
                .oracle()
                .depends_on(vendor_email_evt, delay_seconds=3)
            )

            # 3. User agrees to the suggestion
            user_accept_evt = (
                aui.accept_proposal(content="Yes, please notify the finance team and schedule a call.")
                .oracle()
                .depends_on(agent_offer_evt, delay_seconds=2)
            )

            # 4. Agent alerts finance team with contextual info
            finance_alert_evt = (
                msgs.send_message_to_group_conversation(
                    conversation_id=self.finance_conv_id,
                    content="Heads-up: Vendor DataScan sent a final reminder for invoice #2049. Approval needed ASAP.",
                )
                .oracle()
                .depends_on(user_accept_evt, delay_seconds=2)
            )

            # 5. Agent creates a quick review meeting on the calendar
            review_meeting_evt = (
                cal.add_calendar_event(
                    title="Vendor Invoice Review - DataScan",
                    start_datetime="2024-06-21 15:00:00",
                    end_datetime="2024-06-21 15:15:00",
                    location="Teams Call",
                    description="Discuss urgent invoice #2049 with finance.",
                    tag="finance",
                    attendees=["Jordan Evans", "Accounts Team", "Priya Kumar"],
                )
                .oracle()
                .depends_on(finance_alert_evt, delay_seconds=2)
            )

            # 6. Agent sends confirmation reply to vendor
            reply_evt = (
                emails.reply_to_email(
                    email_id="email-inv-2049",
                    folder_name="INBOX",
                    content="Thank you for notifying us. We've scheduled a review today with our finance team to finalize payment.",
                )
                .oracle()
                .depends_on(review_meeting_evt, delay_seconds=2)
            )

            # 7. System returns home
            home_evt = sys_app.go_home().oracle().depends_on(reply_evt, delay_seconds=1)

        self.events = [
            vendor_email_evt,
            agent_offer_evt,
            user_accept_evt,
            finance_alert_evt,
            review_meeting_evt,
            reply_evt,
            home_evt,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Ensure that the agent offered assistance, notified the finance team, created a meeting, and replied."""
        try:
            events = env.event_log.list_view()

            # Detect agent proactive proposal
            agent_prompt_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and "urgent invoice" in e.action.args.get("content", "").lower()
                for e in events
            )

            # Verify that message was posted in finance group chat
            finance_msg_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message_to_group_conversation"
                and "invoice #2049" in e.action.args.get("content", "")
                for e in events
            )

            # Confirm a calendar meeting was created
            meeting_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "Vendor Invoice Review" in e.action.args.get("title", "")
                for e in events
            )

            # Ensure a reply email was sent to the vendor
            reply_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and "scheduled a review" in e.action.args.get("content", "").lower()
                for e in events
            )

            success = all([agent_prompt_found, finance_msg_found, meeting_created, reply_sent])
            return ScenarioValidationResult(success=success)
        except Exception as ex:
            return ScenarioValidationResult(success=False, exception=ex)
