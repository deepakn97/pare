from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulShoppingApp,
)
from pas.apps.reminder import StatefulReminderApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("abandoned_cart_checkout_nudge")
class AbandonedCartCheckoutNudge(PASScenario):
    """Agent monitors shopping cart status and proactively nudges user to complete checkout when discount code is about to expire.

    The user has items in their shopping cart but has not checked out. A user-created reminder notification fires saying "Your discount code SAVE15 expires in 2 hours!" The agent must:
    1. Detect the discount expiration reminder notification (time-driven; emitted automatically when the reminder is due)
    2. Check the shopping cart to verify there are items waiting to be purchased
    3. Use get_discount_code_info to verify SAVE15 is valid for the cart items
    4. Calculate potential savings if the user checks out now
    5. Send a proactive message to the user summarizing cart contents, applicable discount, and expiration urgency

    This scenario exercises cross-app coordination (reminder trigger → shopping), discount validation, time-sensitive decision making, and proactive user nudging based on external event triggers rather than passive information capture..
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

        # Initialize shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Seed products in the shopping catalog
        # Product 1: Wireless Headphones with multiple variants
        product1_id = self.shopping.add_product("Wireless Headphones")
        item1_id = self.shopping.add_item_to_product(
            product_id=product1_id, price=79.99, options={"color": "black", "size": "standard"}, available=True
        )

        # Product 2: USB-C Cable with multiple variants
        product2_id = self.shopping.add_product("USB-C Cable")
        item2_id = self.shopping.add_item_to_product(
            product_id=product2_id, price=15.99, options={"length": "6ft", "color": "white"}, available=True
        )

        # Add discount code SAVE15 (15% off) for both items
        self.shopping.add_discount_code(item1_id, {"SAVE15": 15.0})
        self.shopping.add_discount_code(item2_id, {"SAVE15": 15.0})

        # Add items to the user's cart (pre-existing state before scenario starts)
        self.shopping.add_to_cart(item1_id, quantity=1)
        self.shopping.add_to_cart(item2_id, quantity=2)

        # Seed a time-driven reminder that will automatically notify the user+agent when due.
        # Following benchmark convention, set it shortly after start_time so it fires once the runner advances time.
        self.reminder.add_reminder(
            title="Use SAVE15 before it expires",
            due_datetime="2025-11-18 09:02:00",
            description=(
                "SAVE15 expires in 2 hours. Remember to check the Shopping cart and checkout to save 15% on all the eligible items."
            ),
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.reminder, self.shopping]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # NOTE: Reminder notifications are time-driven in the Reminders app.
            # The reminder seeded in init (`due_datetime="2025-11-18 09:01:00"`) will automatically notify user+agent.
            # The agent does NOT need to poll reminders; we model reaction time by delaying the first oracle action.

            # Event 1: Agent checks the shopping cart to see what items are waiting
            # Motivated by: the expiring-discount reminder references checkout urgency, so agent checks cart contents.
            check_cart_event = shopping_app.list_cart().oracle().delayed(70)

            # Event 2: Agent verifies the discount code SAVE15 applies to cart items
            # Motivated by: need to confirm SAVE15 works for the items in cart before proposing checkout
            check_discount_event = (
                shopping_app.get_discount_code_info(discount_code="SAVE15")
                .oracle()
                .depends_on(check_cart_event, delay_seconds=1)
            )

            # Event 3: Agent sends proactive proposal to user about completing checkout
            # Motivated by: verified cart has items, discount is valid, and expiration is urgent (2 hours)
            proposal_event = (
                aui.send_message_to_user(
                    content="Your SAVE15 discount code expires in 2 hours. You have items in your cart that qualify for 15% off. Would you like me to help complete your checkout with the discount applied?"
                )
                .oracle()
                .depends_on(check_discount_event, delay_seconds=2)
            )

            # Event 4: User accepts the proposal
            # Motivated by: user wants to save money and not miss the expiring discount
            acceptance_event = (
                aui.accept_proposal(content="Yes, please proceed.").oracle().depends_on(proposal_event, delay_seconds=3)
            )

            # Event 5: Agent completes checkout with discount code
            # Motivated by: user explicitly accepted the proposal to checkout with SAVE15
            checkout_event = (
                shopping_app.checkout(discount_code="SAVE15").oracle().depends_on(acceptance_event, delay_seconds=1)
            )

        # Register ALL events here in self.events
        self.events = [
            check_cart_event,
            check_discount_event,
            proposal_event,
            acceptance_event,
            checkout_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1 (STRICT - logic, FLEXIBLE - wording): Agent sent proactive proposal mentioning discount expiration and cart
            # Do NOT check exact message content, only check that the proposal was sent
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # STRICT Check 2 (STRICT): Agent completed checkout with SAVE15 discount code after user acceptance
            checkout_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                and e.action.args.get("discount_code") == "SAVE15"
                for e in log_entries
            )

            # All strict checks must pass
            success = proposal_found and checkout_found

            # Build rationale for failure
            rationale = None
            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent did not send proactive proposal to user")
                if not checkout_found:
                    missing_checks.append("agent did not complete checkout with SAVE15 discount")
                rationale = "Missing critical checks: " + "; ".join(missing_checks)

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
