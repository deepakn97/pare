from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
)
from pas.apps.reminder import StatefulReminderApp
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("discount_code_expiry_cart_reminder")
class DiscountCodeExpiryCartReminder(PASScenario):
    """Agent proactively reminds user to complete checkout before discount code expires based on shopping cart contents and timing.

    The user has previously added a "Wireless Keyboard" and "USB-C Hub" to their shopping cart but has not yet checked out. A user-created reminder notification fires that "HOLIDAY30" (30% off) expires in 24 hours, prompting immediate action. The agent must:
    1. Detect the reminder notification (time-driven; emitted automatically when the reminder is due)
    2. Check the current shopping cart contents
    3. Verify that the discount code applies to items in the cart (using `get_discount_code_info()`)
    4. Calculate time remaining until expiry
    5. Proactively remind the user about the pending cart and expiring discount
    6. Offer to complete the checkout with the discount code

    This scenario exercises discount code verification, cart state monitoring, time-sensitive coordination (shopping notification → cart analysis), expiry calculation, and proactive purchase completion assistance..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize reminder app (time-driven notifications)
        self.reminder = StatefulReminderApp(name="Reminders")

        # Initialize shopping app with baseline products and cart
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Seed catalog + cart via public APIs (avoid mutating internal dicts directly).
        keyboard_product_id = self.shopping.add_product("Wireless Keyboard - Mechanical RGB")
        self.keyboard_item_id = self.shopping.add_item_to_product(
            product_id=keyboard_product_id,
            price=89.99,
            options={"color": "black", "switch_type": "blue"},
            available=True,
        )

        hub_product_id = self.shopping.add_product("USB-C Hub 7-in-1")
        self.hub_item_id = self.shopping.add_item_to_product(
            product_id=hub_product_id,
            price=45.99,
            options={"ports": "7", "power_delivery": "100W"},
            available=True,
        )

        # Add both items to cart (user has already added these)
        self.shopping.add_to_cart(self.keyboard_item_id, quantity=1)
        self.shopping.add_to_cart(self.hub_item_id, quantity=1)

        # Register discount code "HOLIDAY30" (30% off) for both electronics items.
        # This discount exists already; a reminder will prompt the user to act on it.
        self.shopping.add_discount_code(self.keyboard_item_id, {"HOLIDAY30": 30.0})
        self.shopping.add_discount_code(self.hub_item_id, {"HOLIDAY30": 30.0})

        # Seed a time-driven reminder that will automatically notify the user+agent when due.
        # Following benchmark convention, set it shortly after start_time so it fires once the runner advances time.
        self.reminder.add_reminder(
            title="Use HOLIDAY30 before it expires",
            due_datetime="2025-11-18 09:01:00",
            description=(
                "HOLIDAY30 (30% off) expires in 24 hours. Check your Shopping cart and use the code to checkout before it runs out."
            ),
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.reminder, self.shopping]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # NOTE: Reminder notifications are time-driven in the Reminders app.
            # The reminder seeded in init (`due_datetime="2025-11-18 09:01:00"`) will automatically notify user+agent.
            # The agent does NOT need to poll reminders; we model reaction time by delaying the first oracle action.

            # Event 1: Agent checks discount code info to see which items it applies to (oracle)
            check_discount_event = shopping_app.get_discount_code_info(discount_code="HOLIDAY30").oracle().delayed(70)

            # Event 2: Agent checks cart contents to verify discount applicability (oracle)
            check_cart_event = shopping_app.list_cart().oracle().depends_on(check_discount_event, delay_seconds=1)

            # Event 3: Agent sends proposal to user about discount and cart (oracle)
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed you have items in your cart (Wireless Keyboard and USB-C Hub) and a 30% discount code 'HOLIDAY30' is available for them. Would you like me to complete the checkout with this discount code?"
                )
                .oracle()
                .depends_on(check_cart_event, delay_seconds=2)
            )

            # Event 4: User accepts the proposal (oracle)
            acceptance_event = (
                aui.accept_proposal(content="Yes, please proceed.").oracle().depends_on(proposal_event, delay_seconds=3)
            )

            # Event 5: Agent completes checkout with discount code (oracle)
            checkout_event = (
                shopping_app.checkout(discount_code="HOLIDAY30").oracle().depends_on(acceptance_event, delay_seconds=1)
            )

        self.events = [
            check_discount_event,
            check_cart_event,
            proposal_event,
            acceptance_event,
            checkout_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1: Agent sent proposal message to user (STRICT - must exist, content flexible)
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 2: Agent completed checkout with discount code (STRICT)
            checkout_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                and e.action.args.get("discount_code") == "HOLIDAY30"
                for e in log_entries
            )

            success = proposal_found and checkout_found

            if not success:
                rationale_parts = []
                if not proposal_found:
                    rationale_parts.append("agent did not send proposal message")
                if not checkout_found:
                    rationale_parts.append("agent did not complete checkout with HOLIDAY30 discount")
                rationale = "; ".join(rationale_parts)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
