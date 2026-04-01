from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.email_client import EmailClientApp
from are.simulation.apps.reminder import ReminderApp
from are.simulation.apps.sandbox_file_system import Files
from are.simulation.apps.shopping import Shopping
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("shopping_delivery_tracking")
class ShoppingDeliveryTracking(Scenario):
    """A proactive scenario where the agent organizes a user's online purchase.

    The agent:
    - checks current date
    - searches for a product and adds it to cart
    - saves the purchase receipt file
    - proposes to email receipt to friend
    - sets a reminder for delivery tracking.

    Demonstrates: Shopping, Files, Email, System, Reminder, and AgentUserInterface in one flow.
    """

    start_time: float | None = 0
    duration: float | None = 25

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps for shopping, email, reminders, files, and system context."""
        self.apps = [
            AgentUserInterface(),
            Shopping(),
            EmailClientApp(),
            ReminderApp(),
            Files(name="files", sandbox_dir=kwargs.get("sandbox_dir")),
            SystemApp(name="system"),
        ]

    def build_events_flow(self) -> None:
        """Builds event flow where agent coordinates online purchase and user confirmation."""
        aui = self.get_typed_app(AgentUserInterface)
        shopper = self.get_typed_app(Shopping)
        system = self.get_typed_app(SystemApp)
        email_client = self.get_typed_app(EmailClientApp)
        reminder = self.get_typed_app(ReminderApp)
        files = self.get_typed_app(Files)

        with EventRegisterer.capture_mode():
            # User message: start of session (request help buying item)
            user_start = aui.send_message_to_agent(
                content="I want to buy a new wireless keyboard and keep track of its delivery."
            ).depends_on(None, delay_seconds=1)

            # Agent action: gets current system time for timestamp
            time_event = system.get_current_time().oracle().depends_on(user_start, delay_seconds=1)

            # Agent searches product in shopping
            search_product = (
                shopper.search_product(product_name="wireless keyboard", limit=1)
                .oracle()
                .depends_on(time_event, delay_seconds=1)
            )

            # Agent adds the item to cart
            add_to_cart_event = (
                shopper.add_to_cart(item_id="keyboard123", quantity=1)
                .oracle()
                .depends_on(search_product, delay_seconds=1)
            )

            # Agent checks out purchase
            checkout_event = (
                shopper.checkout(discount_code=None).oracle().depends_on(add_to_cart_event, delay_seconds=1)
            )

            # Agent writes receipt file in local Documents folder
            mkdir_event = (
                files.makedirs(path="Documents/Receipts", exist_ok=True)
                .oracle()
                .depends_on(checkout_event, delay_seconds=1)
            )

            # Agent opens and writes a receipt file
            open_receipt_file = (
                files.open(path="Documents/Receipts/keyboard_order.txt", mode="w")
                .oracle()
                .depends_on(mkdir_event, delay_seconds=1)
            )

            # Agent records structured info about confirmation
            info_log = (
                files.info(path="Documents/Receipts/keyboard_order.txt")
                .oracle()
                .depends_on(open_receipt_file, delay_seconds=1)
            )

            # Agent proactively proposes emailing the receipt to a friend
            propose_email_user = aui.send_message_to_user(
                content=(
                    "Your purchase receipt for the wireless keyboard is ready. "
                    "Would you like me to email the receipt file to your friend Jordan?"
                )
            ).depends_on(info_log, delay_seconds=1)

            # User gives contextual approval
            user_approval = aui.send_message_to_agent(
                content="Yes, please email the receipt file to Jordan."
            ).depends_on(propose_email_user, delay_seconds=1)

            # Agent emails the receipt to Jordan after approval
            email_receipt = (
                email_client.send_email(
                    recipients=["jordan@example.com"],
                    subject="Wireless Keyboard Purchase Receipt",
                    content="Attaching purchase confirmation for wireless keyboard order.",
                    attachment_paths=["Documents/Receipts/keyboard_order.txt"],
                )
                .oracle()
                .depends_on(user_approval, delay_seconds=1)
            )

            # Agent sets reminder for expected delivery (three days later)
            add_rem_event = (
                reminder.add_reminder(
                    title="Check wireless keyboard delivery",
                    due_datetime="2024-06-05 09:00:00",
                    description="Confirm if wireless keyboard has arrived.",
                )
                .oracle()
                .depends_on(email_receipt, delay_seconds=1)
            )

            # Agent informs user the reminder is set
            completion_notice = (
                aui.send_message_to_user(
                    content="I've emailed the receipt to Jordan and set a reminder to check the keyboard delivery in three days."
                )
                .oracle()
                .depends_on(add_rem_event, delay_seconds=1)
            )

        self.events = [
            user_start,
            time_event,
            search_product,
            add_to_cart_event,
            checkout_event,
            mkdir_event,
            open_receipt_file,
            info_log,
            propose_email_user,
            user_approval,
            email_receipt,
            add_rem_event,
            completion_notice,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent used all apps and completed the proactive purchase workflow."""
        try:
            events = env.event_log.list_view()

            used_apps = set()
            user_proposal_detected = False
            user_confirmation_detected = False
            receipt_email_sent = False
            reminder_created = False

            for ev in events:
                if ev.event_type == EventType.AGENT and isinstance(ev.action, Action):
                    used_apps.add(ev.action.class_name)

                    # detect AUI messages
                    if (
                        ev.action.class_name == "AgentUserInterface"
                        and "Would you like me to email" in ev.action.args.get("content", "")
                    ):
                        user_proposal_detected = True
                    if (
                        ev.action.class_name == "AgentUserInterface"
                        and "reminder" in ev.action.args.get("content", "").lower()
                    ):
                        user_confirmation_detected = True
                    # detect email sending
                    if (
                        ev.action.class_name == "EmailClientApp"
                        and ev.action.function_name == "send_email"
                        and "jordan@example.com" in str(ev.action.args.get("recipients"))
                    ):
                        receipt_email_sent = True
                    # detect reminder creation
                    if ev.action.class_name == "ReminderApp" and ev.action.function_name == "add_reminder":
                        reminder_created = True

            all_apps_used = {
                "AgentUserInterface",
                "Shopping",
                "EmailClientApp",
                "ReminderApp",
                "Files",
                "SystemApp",
            }.issubset(used_apps)
            success = all([all_apps_used, receipt_email_sent, reminder_created, user_proposal_detected])
            return ScenarioValidationResult(success=success)
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
