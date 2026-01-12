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
    StatefulMessagingApp,
    StatefulShoppingApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("abandoned_cart_checkout_nudge")
class AbandonedCartCheckoutNudge(PASScenario):
    """Agent monitors shopping cart status and proactively nudges user to complete checkout when discount code is about to expire.

    The user has items in their shopping cart but has not checked out. The user receives a message from a shopping notification service saying "Reminder: Your discount code SAVE15 expires in 2 hours!" The agent must:
    1. Detect the discount expiration notification in the incoming message
    2. Check the shopping cart to verify there are items waiting to be purchased
    3. Use get_discount_code_info to verify SAVE15 is valid for the cart items
    4. Calculate potential savings if the user checks out now
    5. Send a proactive message to the user via messaging summarizing cart contents, applicable discount, and expiration urgency

    This scenario exercises cross-app coordination (messaging → shopping), discount validation, time-sensitive decision making, and proactive user nudging based on external event triggers rather than passive information capture..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize messaging app
        self.messaging = StatefulMessagingApp(name="Messages")
        # Add the shopping notification service as a contact
        self.messaging.add_contacts([("ShopNotify", "+15551234567")])
        # Create a conversation with ShopNotify
        from are.simulation.apps.messaging_v2 import ConversationV2

        self.user_id = self.messaging.current_user_id
        self.shop_notify_conversation = ConversationV2(participant_ids=[self.user_id, "+15551234567"])
        self.messaging.add_conversation(self.shop_notify_conversation)

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

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.shopping]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Event 1: Environment event - discount expiration notification message arrives
            shop_notify_id = "+15551234567"
            discount_notification_event = messaging_app.create_and_add_message(
                conversation_id=self.shop_notify_conversation.conversation_id,
                sender_id=shop_notify_id,
                content="Reminder: Your discount code SAVE15 expires in 2 hours! Complete your purchase now to save 15% on eligible items.",
            ).delayed(5)

            # Event 2: Agent reads the conversation to see the discount expiration message
            # Motivated by: the incoming message notification about discount expiration
            read_conversation_event = (
                messaging_app.read_conversation(
                    conversation_id=self.shop_notify_conversation.conversation_id, offset=0, limit=10
                )
                .oracle()
                .depends_on(discount_notification_event, delay_seconds=2)
            )

            # Event 3: Agent checks the shopping cart to see what items are waiting
            # Motivated by: the discount notification mentions cart items, so agent needs to check what's in the cart
            check_cart_event = shopping_app.list_cart().oracle().depends_on(read_conversation_event, delay_seconds=1)

            # Event 4: Agent verifies the discount code SAVE15 applies to cart items
            # Motivated by: need to confirm SAVE15 works for the items in cart before proposing checkout
            check_discount_event = (
                shopping_app.get_discount_code_info(discount_code="SAVE15")
                .oracle()
                .depends_on(check_cart_event, delay_seconds=1)
            )

            # Event 5: Agent sends proactive proposal to user about completing checkout
            # Motivated by: verified cart has items, discount is valid, and expiration is urgent (2 hours)
            proposal_event = (
                aui.send_message_to_user(
                    content="Your SAVE15 discount code expires in 2 hours. You have items in your cart that qualify for 15% off. Would you like me to help complete your checkout with the discount applied?"
                )
                .oracle()
                .depends_on(check_discount_event, delay_seconds=2)
            )

            # Event 6: User accepts the proposal
            # Motivated by: user wants to save money and not miss the expiring discount
            acceptance_event = (
                aui.accept_proposal(content="Yes, please checkout with the SAVE15 code.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Event 7: Agent completes checkout with discount code
            # Motivated by: user explicitly accepted the proposal to checkout with SAVE15
            checkout_event = (
                shopping_app.checkout(discount_code="SAVE15").oracle().depends_on(acceptance_event, delay_seconds=1)
            )

        # Register ALL events here in self.events
        self.events = [
            discount_notification_event,
            read_conversation_event,
            check_cart_event,
            check_discount_event,
            proposal_event,
            acceptance_event,
            checkout_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1 (STRICT): Agent read the conversation to detect the discount expiration notification
            read_conversation_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "read_conversation"
                and e.action.args.get("conversation_id") == self.shop_notify_conversation.conversation_id
                for e in log_entries
            )

            # Check 2 (STRICT): Agent checked the shopping cart to verify items are present
            check_cart_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "list_cart"
                for e in log_entries
            )

            # Check 3 (STRICT): Agent verified the discount code SAVE15
            check_discount_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_discount_code_info"
                and e.action.args.get("discount_code") == "SAVE15"
                for e in log_entries
            )

            # Check 4 (STRICT - logic, FLEXIBLE - wording): Agent sent proactive proposal mentioning discount expiration and cart
            # Do NOT check exact message content, only check that the proposal was sent
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 5 (STRICT): Agent completed checkout with SAVE15 discount code after user acceptance
            checkout_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                and e.action.args.get("discount_code") == "SAVE15"
                for e in log_entries
            )

            # All strict checks must pass
            success = (
                read_conversation_found
                and check_cart_found
                and check_discount_found
                and proposal_found
                and checkout_found
            )

            # Build rationale for failure
            rationale = None
            if not success:
                missing_checks = []
                if not read_conversation_found:
                    missing_checks.append("agent did not read the conversation with ShopNotify")
                if not check_cart_found:
                    missing_checks.append("agent did not check the shopping cart")
                if not check_discount_found:
                    missing_checks.append("agent did not verify discount code SAVE15")
                if not proposal_found:
                    missing_checks.append("agent did not send proactive proposal to user")
                if not checkout_found:
                    missing_checks.append("agent did not complete checkout with SAVE15 discount")
                rationale = "Missing critical checks: " + "; ".join(missing_checks)

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
