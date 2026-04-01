"""Agent detects duplicate headphone order after spouse reveals gift purchase."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import (
    AbstractEnvironment,
    Action,
    ConditionCheckEvent,
    EventRegisterer,
    EventType,
)

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulMessagingApp,
)
from pare.apps.shopping import StatefulShoppingApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("duplicate_order_cancellation_check")
class DuplicateOrderCancellationCheck(PAREScenario):
    """Agent detects and cancels duplicate headphone order after spouse reveals gift.

    The user has a pending order for "Wireless Headphones - Black" that is currently
    being shipped. The user's spouse Alex ordered the same headphones as a surprise
    gift (from their own account, not tracked in user's shopping app) and the package
    has arrived.

    The agent must:
    1. Observe the messaging conversation between user and spouse
    2. Detect when user mentions they also ordered headphones after spouse reveals the gift
    3. Check the shopping app and find the user's pending headphone order
    4. Propose canceling the user's order since they received headphones as a gift
    5. If user accepts, cancel the order

    This scenario exercises conversation monitoring, cross-app correlation (messaging
    to shopping), duplicate detection, and proactive order cancellation.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    additional_system_prompt = """You ordered wireless headphones online a few days ago and they're currently
being shipped. Your spouse Alex messages you about a package they sent you.

CONVERSATION INSTRUCTIONS:
- When Alex first messages about the package, reply asking what they ordered
- When Alex reveals they ordered wireless headphones, express surprise and mention
  that you also ordered the same headphones yourself (say something like "No way! I also ordered headphones haha")

AGENT INTERACTION RULES:
- Do NOT tell the agent what is happening in your conversation with Alex
- Do NOT accept any proactive assistance from the agent UNLESS it specifically offers
  to cancel your headphone order because you received headphones as a gift
- If the agent proposes to cancel the order BEFORE Alex has revealed they ordered
  headphones for you, REJECT the proposal without explaining why
- Only accept if the agent correctly identifies the duplicate headphone situation
  after Alex has revealed the gift"""

    @staticmethod
    def _user_asked_about_order(env: AbstractEnvironment) -> bool:
        """Check if user asked Alex what they ordered."""
        # In oracle mode, skip user action checks (oracle events handle the flow)
        if getattr(env, "oracle_mode", False):
            return True
        for entry in env.event_log.list_view():
            if (
                entry.event_type == EventType.USER
                and isinstance(entry.action, Action)
                and entry.action.class_name == "StatefulMessagingApp"
                and entry.action.function_name == "send_message"
            ):
                content = entry.action.args.get("content", "").lower()
                if "what" in content and ("order" in content or "get" in content or "send" in content):
                    return True
        return False

    @staticmethod
    def _user_mentioned_own_order(env: AbstractEnvironment) -> bool:
        """Check if user mentioned they also ordered headphones."""
        # In oracle mode, skip user action checks (oracle events handle the flow)
        if getattr(env, "oracle_mode", False):
            return True
        for entry in env.event_log.list_view():
            if (
                entry.event_type == EventType.USER
                and isinstance(entry.action, Action)
                and entry.action.class_name == "StatefulMessagingApp"
                and entry.action.function_name == "send_message"
            ):
                content = entry.action.args.get("content", "").lower()
                if ("also" in content or "too" in content) and ("order" in content or "headphone" in content):
                    return True
        return False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Shopping app with user's pending headphone order
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Create the product and item
        product_id = self.shopping.add_product(name="Wireless Headphones - Black")
        self.headphones_item_id = self.shopping.add_item_to_product(
            product_id=product_id, price=79.99, options={"color": "black"}, available=True
        )

        # Add user's order (placed 3 days ago, currently shipped/in transit)
        order_timestamp = self.start_time - (3 * 24 * 60 * 60)
        self.order_id = self.shopping.add_order(
            order_id="4521",
            order_status="shipped",
            order_date=order_timestamp,
            order_total=79.99,
            item_id=self.headphones_item_id,
            quantity=1,
        )

        # Initialize Messaging app
        self.messaging = StatefulMessagingApp(name="Messages")

        # Add spouse Alex as a user
        self.messaging.add_users(["Alex"])
        self.alex_id = self.messaging.name_to_id["Alex"]

        # Create conversation with Alex using send_message
        self.alex_convo_id = self.messaging.send_message(
            user_id=self.alex_id,
            content="Hey!",
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.shopping, self.messaging]

    def build_events_flow(self) -> None:
        """Build event flow with user-agent conversation and condition checks."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")

        with EventRegisterer.capture_mode():
            # ENV Event 1: Alex's first message about the package
            alex_msg1 = messaging_app.create_and_add_message(
                conversation_id=self.alex_convo_id,
                sender_id=self.alex_id,
                content="Hey, did you get the package? I ordered something for you :)",
            ).delayed(10)

            # ORACLE (user): User asks what Alex ordered
            user_asks_event = (
                messaging_app.send_message(
                    user_id=self.alex_id,
                    content="Package? What did you order?",
                )
                .oracle()
                .depends_on(alex_msg1, delay_seconds=2)
            )

            # Condition: Wait for user to ask what Alex ordered
            user_asked_condition = ConditionCheckEvent.from_condition(self._user_asked_about_order).delayed(10)

            # ENV Event 2: Alex reveals headphones (depends on user asking)
            alex_msg2 = messaging_app.create_and_add_message(
                conversation_id=self.alex_convo_id,
                sender_id=self.alex_id,
                content="I ordered the wireless headphones that you wanted!",
            ).depends_on(user_asked_condition)

            # ORACLE (user): User mentions they also ordered headphones
            user_duplicate_event = (
                messaging_app.send_message(
                    user_id=self.alex_id,
                    content="No way! I also ordered the headphones haha",
                )
                .oracle()
                .depends_on(alex_msg2, delay_seconds=2)
            )

            # Condition: Wait for user to mention they also ordered headphones
            user_duplicate_condition = ConditionCheckEvent.from_condition(self._user_mentioned_own_order).delayed(10)

            # ORACLE: Agent checks shopping orders
            check_orders_event = (
                shopping_app.list_orders().oracle().depends_on(user_duplicate_condition, delay_seconds=2)
            )

            # ORACLE: Agent proposes canceling the order
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed you mentioned you also ordered headphones, but Alex just gifted you the same ones. You have order #4521 for Wireless Headphones - Black ($79.99) that's currently being shipped. Would you like me to cancel it to avoid having duplicates?"
                )
                .oracle()
                .depends_on(check_orders_event, delay_seconds=2)
            )

            # ORACLE: User accepts
            acceptance_event = (
                aui.accept_proposal(content="Yes, please cancel my order.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # ORACLE: Agent cancels the order
            cancel_order_event = (
                shopping_app.cancel_order(order_id="4521").oracle().depends_on(acceptance_event, delay_seconds=1)
            )

            # ORACLE: Agent confirms cancellation
            confirmation_event = (
                aui.send_message_to_user(
                    content="Done! I've canceled order #4521 for the Wireless Headphones. You won't be charged."
                )
                .oracle()
                .depends_on(cancel_order_event, delay_seconds=1)
            )

        self.events = [
            alex_msg1,
            user_asks_event,
            user_asked_condition,
            alex_msg2,
            user_duplicate_event,
            user_duplicate_condition,
            check_orders_event,
            proposal_event,
            acceptance_event,
            cancel_order_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate essential outcomes: proposal sent and order canceled."""
        try:
            log_entries = env.event_log.list_view()
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # Essential outcome 1: Agent proposed canceling the order
            proposal_sent = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PAREAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # Essential outcome 2: Agent canceled the order
            order_canceled = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "cancel_order"
                and e.action.args.get("order_id") == "4521"
                for e in agent_events
            )

            success = proposal_sent and order_canceled

            if not success:
                missing = []
                if not proposal_sent:
                    missing.append("proposal to cancel order not sent")
                if not order_canceled:
                    missing.append("order #4521 not canceled")

                rationale = f"Validation failed: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
