from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulMessagingApp,
)
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("discount_expiry_gift_suggestion")
class DiscountExpiryGiftSuggestion(PASScenario):
    """Agent coordinates a gift purchase for a friend by leveraging an expiring discount code on items already in the shopping cart.

    The user has items in their shopping cart including a "Wireless Headphones" product. The user receives a shopping-alert message that discount code "SAVE20" (20% off headphones) expires today. The user then receives a message from their friend Sarah asking for headphone recommendations and explicitly asking if the user can buy a pair for her using a discount (she'll reimburse). The agent must:
    1. Detect the incoming product recommendation request from Sarah via messaging
    2. Check the shopping cart and identify the "Wireless Headphones" item
    3. Detect the shopping-alert message and recognize that "SAVE20" applies to headphones and expires today
    4. Propose purchasing the headphones as a gift for Sarah using the expiring discount (only after user approval)
    5. After user acceptance, complete checkout with the discount code applied
    6. Send a message to Sarah confirming the gift order (do not invent delivery estimates unless surfaced by an observable notification/email)

    This scenario exercises temporal discount awareness, cross-app correlation between messaging requests and shopping cart state, discount code validation, time-sensitive purchase decision-making, and post-purchase gift notification.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Shopping App
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Add "Wireless Headphones" product with a variant
        headphones_product_id = self.shopping.add_product("Wireless Headphones")
        headphones_item_id = self.shopping.add_item_to_product(
            product_id=headphones_product_id,
            price=149.99,
            options={"color": "black", "type": "over-ear"},
            available=True,
        )

        # Add discount code "SAVE20" (20% off) for the headphones item
        self.shopping.add_discount_code(item_id=headphones_item_id, discount_code={"SAVE20": 20.0})

        # Pre-populate cart with the headphones item
        self.shopping.add_to_cart(item_id=headphones_item_id, quantity=1)

        # Initialize Messaging App
        self.messaging = StatefulMessagingApp(name="Messages")

        # Add Sarah and a shopping-alert sender to messaging app.
        self.messaging.add_users(["Sarah Miller", "Acme Shop", "Shop Bot"])
        sarah_user_id = self.messaging.name_to_id["Sarah Miller"]
        shop_id = self.messaging.name_to_id["Acme Shop"]
        bot_id = self.messaging.name_to_id["Shop Bot"]

        # Seed an earlier conversation so the new message arriving in Step 3 feels organic
        conversation = ConversationV2(
            participant_ids=[self.messaging.current_user_id, sarah_user_id],
            title="Sarah Miller",
            messages=[
                MessageV2(
                    sender_id=self.messaging.current_user_id,
                    content="Hey Sarah! How's work going?",
                    timestamp=self.start_time - 86400,  # 1 day before scenario starts
                ),
                MessageV2(
                    sender_id=sarah_user_id,
                    content="Pretty busy! Hope you're doing well.",
                    timestamp=self.start_time - 86000,
                ),
            ],
        )
        self.messaging.add_conversation(conversation)
        self.sarah_conversation_id = conversation.conversation_id
        self.sarah_user_id = sarah_user_id

        # Seed a group conversation for shopping alerts (Meta-ARE requires >= 2 other participants).
        self.shop_alerts_conversation_id = self.messaging.create_group_conversation(
            user_ids=[shop_id, bot_id],
            title="Shopping Alerts",
        )
        self.shop_sender_id = shop_id

        self.headphones_item_id = headphones_item_id

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.shopping, self.messaging]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")

        with EventRegisterer.capture_mode():
            # Environment Event 0: Shopping alert mentions the discount code expiry (observable evidence).
            discount_alert_event = messaging_app.create_and_add_message(
                conversation_id=self.shop_alerts_conversation_id,
                sender_id=self.shop_sender_id,
                content="Reminder: discount code SAVE20 (20% off Wireless Headphones) expires today. Redeem before it ends.",
            ).delayed(5)

            # Environment Event 1: Sarah sends message asking for headphone recommendation
            sarah_message_event = messaging_app.create_and_add_message(
                conversation_id=self.sarah_conversation_id,
                sender_id=self.sarah_user_id,
                content="Do you have any good headphone recommendations? I need new ones for work. If you have a discount code, could you grab a pair for me? I'll reimburse you.",
            ).depends_on(discount_alert_event, delay_seconds=5)

            # Oracle Event 1: Agent reads the conversation to detect Sarah's request
            # Motivated by: incoming message notification from Sarah
            agent_read_conversation_event = (
                messaging_app.read_conversation(conversation_id=self.sarah_conversation_id, offset=0, limit=10)
                .oracle()
                .depends_on(sarah_message_event, delay_seconds=2)
            )

            # Oracle Event 1b: Agent reads the shopping-alert thread to confirm SAVE20 expiry context.
            # Motivated by: shopping alert message about SAVE20 expiring today.
            agent_read_alerts_event = (
                messaging_app.read_conversation(
                    conversation_id=self.shop_alerts_conversation_id,
                    offset=0,
                    limit=10,
                )
                .oracle()
                .depends_on(sarah_message_event, delay_seconds=1)
            )

            # Oracle Event 2: Agent checks shopping cart to see what's available
            # Motivated by: Sarah's product recommendation request detected in conversation
            agent_check_cart_event = (
                shopping_app.list_cart().oracle().depends_on(agent_read_conversation_event, delay_seconds=1)
            )

            # Oracle Event 3: Agent retrieves discount codes to check expiry and applicability
            # Motivated by: headphones found in cart matching Sarah's request
            agent_check_discount_event = (
                shopping_app.get_discount_code_info(discount_code="SAVE20")
                .oracle()
                .depends_on([agent_check_cart_event, agent_read_alerts_event], delay_seconds=1)
            )

            # Oracle Event 4: Agent proposes purchasing headphones as gift using discount
            # Motivated by: cart contains headphones matching Sarah's request + discount "SAVE20" applies to that item
            proposal_event = (
                aui.send_message_to_user(
                    content="Sarah asked for headphone recommendations and asked if you can buy a pair for her (she'll reimburse). You already have Wireless Headphones in your cart, and SAVE20 applies (20% off). The shopping alerts thread says SAVE20 expires today. Would you like me to check out with SAVE20 and treat it as a gift for Sarah?"
                )
                .oracle()
                .depends_on(agent_check_discount_event, delay_seconds=2)
            )

            # Oracle Event 5: User accepts the proposal
            # Motivated by: user approves agent's gift purchase suggestion
            acceptance_event = (
                aui.accept_proposal(content="Yes, go ahead and purchase them for Sarah!")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event 6: Agent completes checkout with discount code
            # Motivated by: user accepted the proposal to purchase as gift
            checkout_event = (
                shopping_app.checkout(discount_code="SAVE20").oracle().depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 7: Agent retrieves order details to get confirmation info
            # Motivated by: checkout completed, need order details to share with Sarah
            get_order_event = shopping_app.list_orders().oracle().depends_on(checkout_event, delay_seconds=1)

            # Oracle Event 8: Agent sends gift notification to Sarah
            # Motivated by: order confirmed, informing Sarah about the gift
            send_gift_message_event = (
                messaging_app.send_message(
                    user_id=self.sarah_user_id,
                    content="I just ordered Wireless Headphones for you using the SAVE20 discount — happy to send the order confirmation details once they're available. You can reimburse me when convenient.",
                )
                .oracle()
                .depends_on(get_order_event, delay_seconds=2)
            )

        # Register ALL events
        self.events = [
            discount_alert_event,
            sarah_message_event,
            agent_read_conversation_event,
            agent_read_alerts_event,
            agent_check_cart_event,
            agent_check_discount_event,
            proposal_event,
            acceptance_event,
            checkout_event,
            get_order_event,
            send_gift_message_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1 (STRICT): Agent read the messaging conversation to detect Sarah's request
            # Expected: StatefulMessagingApp.read_conversation with correct conversation_id
            agent_read_conversation = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "read_conversation"
                and e.action.args.get("conversation_id") == self.sarah_conversation_id
                for e in log_entries
            )

            # Check 2 (STRICT): Agent checked the shopping cart for relevant items
            # Expected: StatefulShoppingApp.list_cart
            agent_check_cart = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "list_cart"
                for e in log_entries
            )

            # Check 3 (STRICT): Agent checked discount code information
            # Expected: StatefulShoppingApp.get_discount_code_info with "SAVE20"
            agent_check_discount = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_discount_code_info"
                and e.action.args.get("discount_code") == "SAVE20"
                for e in log_entries
            )

            # Check 4 (STRICT): Agent sent proposal to user mentioning key elements
            # Expected: PASAgentUserInterface.send_message_to_user mentioning Sarah and headphones
            # FLEXIBLE: We don't check exact wording, only presence of key entities
            agent_sent_proposal = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "Sarah" in e.action.args.get("content", "")
                and any(keyword in e.action.args.get("content", "").lower() for keyword in ["headphone", "headphones"])
                for e in log_entries
            )

            # Check 5 (STRICT): Agent completed checkout with the correct discount code
            # Expected: StatefulShoppingApp.checkout with discount_code="SAVE20"
            agent_checkout = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                and e.action.args.get("discount_code") == "SAVE20"
                for e in log_entries
            )

            # Check 6 (STRICT): Agent retrieved order details after checkout
            # Expected: StatefulShoppingApp.list_orders
            agent_list_orders = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "list_orders"
                for e in log_entries
            )

            # Check 7 (STRICT): Agent sent message to Sarah notifying about the gift
            # Expected: StatefulMessagingApp.send_message to Sarah's user_id
            # FLEXIBLE: We don't check exact message content, just that a message was sent to Sarah
            agent_sent_message_to_sarah = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == self.sarah_user_id
                for e in log_entries
            )

            # All strict checks must pass for success
            success = (
                agent_read_conversation
                and agent_check_cart
                and agent_check_discount
                and agent_sent_proposal
                and agent_checkout
                and agent_list_orders
                and agent_sent_message_to_sarah
            )

            # Build rationale if validation fails
            if not success:
                missing_checks = []
                if not agent_read_conversation:
                    missing_checks.append("agent did not read conversation with Sarah")
                if not agent_check_cart:
                    missing_checks.append("agent did not check shopping cart")
                if not agent_check_discount:
                    missing_checks.append("agent did not check discount code SAVE20")
                if not agent_sent_proposal:
                    missing_checks.append("agent did not send proposal mentioning Sarah and headphones")
                if not agent_checkout:
                    missing_checks.append("agent did not complete checkout with SAVE20")
                if not agent_list_orders:
                    missing_checks.append("agent did not retrieve order details")
                if not agent_sent_message_to_sarah:
                    missing_checks.append("agent did not send gift notification to Sarah")

                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
