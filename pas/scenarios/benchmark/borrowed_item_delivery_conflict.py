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
    StatefulShoppingApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("borrowed_item_delivery_conflict")
class BorrowedItemDeliveryConflict(PASScenario):
    """Agent manages friend's borrowing request against delayed delivery timeline.

    The user's friend messages asking "Hey, can I borrow your portable projector for Friday's presentation?" The user knows they ordered a portable projector online. A shopping alert arrives indicating the projector order is delayed and provides the updated expected delivery date (next Monday), which is after the friend's Friday deadline. The friend's message implies urgency ("Friday's presentation"), so the agent must:
    1. Detect the incoming message with the borrowing request
    2. Search the user's shopping orders for "portable projector"
    3. Read the shopping alert to learn the updated expected delivery date (Monday) and recognize it conflicts with the friend's need (Friday)
    4. Infer that the user cannot fulfill the commitment with their delayed order
    5. Propose messaging the friend to explain the delay and apologize
    6. Optionally suggest searching for in-stock alternatives at nearby stores with same-day pickup to help the friend another way

    This scenario exercises cross-app reasoning between messaging and shopping to detect commitment conflicts, delivery timeline awareness to identify broken promises, inferring urgency from conversational context, and proactive conflict resolution through communication and alternative solution discovery. Unlike prior scenarios, the trigger is a social request rather than a sale/discount/ride notification, and the goal is managing interpersonal commitments rather than optimizing transactions or logistics..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize messaging app
        self.messaging = StatefulMessagingApp(name="Messages")
        # current_user_id is automatically set by StatefulMessagingApp

        # Add friend contact - this will automatically set up id_to_name and name_to_id
        self.messaging.add_users(["Alex"])
        friend_name = "Alex"
        friend_id = self.messaging.name_to_id[friend_name]
        self.friend_id = friend_id  # Store for use in events

        # Create existing conversation with friend (earlier casual chat)
        conversation_id = "conv_001"
        past_conversation = ConversationV2(
            conversation_id=conversation_id,
            participant_ids=[self.messaging.current_user_id, friend_id],
            title="Alex",
            last_updated=datetime(2025, 11, 15, 14, 30, 0, tzinfo=UTC).timestamp(),
        )
        # Add a couple of older messages for context
        past_conversation.messages.append(
            MessageV2(
                sender_id=friend_id,
                content="Hey! How have you been?",
                timestamp=datetime(2025, 11, 15, 14, 30, 0, tzinfo=UTC).timestamp(),
            )
        )
        past_conversation.messages.append(
            MessageV2(
                sender_id=self.messaging.current_user_id,
                content="Good! Been busy with work. How about you?",
                timestamp=datetime(2025, 11, 15, 14, 35, 0, tzinfo=UTC).timestamp(),
            )
        )
        self.messaging.add_conversation(past_conversation)
        self.friend_conversation_id = conversation_id

        # Seed a "Shopping Alerts" conversation so delivery timing is surfaced via an env message.
        # (Meta-ARE requires >=2 other participants for create_group_conversation.)
        self.messaging.add_users(["Acme Shop", "Shop Bot"])
        shop_id = self.messaging.name_to_id["Acme Shop"]
        bot_id = self.messaging.name_to_id["Shop Bot"]
        self.shopping_alerts_conversation_id = self.messaging.create_group_conversation(
            user_ids=[shop_id, bot_id],
            title="Shopping Alerts",
        )
        self.shop_sender_id = shop_id

        # Initialize shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Add portable projector product
        # Add projector product
        projector_product_id = self.shopping.add_product("Portable Mini Projector")
        projector_item_id = self.shopping.add_item_to_product(
            product_id=projector_product_id,
            price=199.99,
            options={"color": "black", "resolution": "1080p"},
            available=True,
        )

        # Add existing order for the projector (placed a few days ago, now delayed)
        # Note: Using add_order() but order_id needs to be preserved for later references
        order_id = "order_12345"
        order_date = datetime(2025, 11, 15, 10, 0, 0, tzinfo=UTC)
        self.shopping.add_order(
            order_id=order_id,
            order_status="shipped",
            order_date=order_date.timestamp(),
            order_total=199.99,
            item_id=projector_item_id,
            quantity=1,
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.shopping]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Environment event 1: Friend sends borrowing request message
            friend_request_event = messaging_app.create_and_add_message(
                conversation_id=self.friend_conversation_id,
                sender_id=self.friend_id,
                content="Hey, can I borrow your portable projector for Friday's presentation?",
            ).delayed(10)

            # Environment event 2: Shopping alert arrives with the updated expected delivery date.
            order_delay_alert_event = messaging_app.create_and_add_message(
                conversation_id=self.shopping_alerts_conversation_id,
                sender_id=self.shop_sender_id,
                content=(
                    "Shipping update: your Portable Mini Projector order (order_12345) is delayed. "
                    "Updated expected delivery: Monday, Nov 24."
                ),
            ).depends_on([friend_request_event], delay_seconds=2)

            # Oracle event 1: Agent reads the conversation to see the borrowing request
            # Motivated by: friend_request_event - the agent receives a notification about the new message
            read_conversation_event = (
                messaging_app.read_conversation(
                    conversation_id=self.friend_conversation_id,
                    offset=0,
                    limit=10,
                )
                .oracle()
                .depends_on(friend_request_event, delay_seconds=3)
            )

            # Oracle event 1b: Agent reads the shopping alert to learn the delivery date update.
            # Motivated by: order_delay_alert_event - the agent sees a shopping alert about an order delay.
            read_alert_event = (
                messaging_app.read_conversation(
                    conversation_id=self.shopping_alerts_conversation_id,
                    offset=0,
                    limit=10,
                )
                .oracle()
                .depends_on([order_delay_alert_event], delay_seconds=2)
            )

            # Oracle event 2: Agent searches orders for "projector" to check availability
            # Motivated by: read_conversation_event - the agent saw the request for "portable projector"
            search_orders_event = (
                shopping_app.list_orders().oracle().depends_on(read_conversation_event, delay_seconds=2)
            )

            # Oracle event 3: Agent retrieves order details to confirm the order exists / status (NOT delivery date).
            # Motivated by: search_orders_event - the agent found the order and confirms current state.
            get_order_details_event = (
                shopping_app.get_order_details(
                    order_id="order_12345",
                )
                .oracle()
                .depends_on(search_orders_event, delay_seconds=2)
            )

            # Oracle event 4: Agent proposes messaging the friend about the conflict
            # Motivated by: read_alert_event - the shopping alert provided the updated expected delivery date (Monday).
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed Alex asked to borrow your portable projector for Friday's presentation. A shopping alert says your projector order (order_12345) is delayed with updated expected delivery on Monday (Nov 24), which is after Friday. Would you like me to let Alex know about the delay?",
                )
                .oracle()
                .depends_on([get_order_details_event, read_alert_event], delay_seconds=3)
            )

            # Oracle event 5: User accepts the proposal
            # Motivated by: proposal_event - user agrees to the agent's suggestion
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please let Alex know I can't lend it.",
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=5)
            )

            # Oracle event 6: Agent sends message to friend explaining the situation
            # Motivated by: acceptance_event - user approved sending the message
            send_message_event = (
                messaging_app.send_message(
                    user_id=self.friend_id,
                    content="Hi Alex! Unfortunately, I won't be able to lend you the projector for Friday. My order is delayed and won't arrive until Monday. Sorry about that!",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

        # Register ALL events here in self.events
        self.events = [
            friend_request_event,
            order_delay_alert_event,
            read_conversation_event,
            read_alert_event,
            search_orders_event,
            get_order_details_event,
            proposal_event,
            acceptance_event,
            send_message_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Agent sent proposal to user about the borrowing conflict
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Agent sent message to friend about the conflict
            message_sent_to_friend = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name in ["send_message", "send_message_to_group_conversation"]
                for e in log_entries
            )

            # All strict checks must pass for success
            success = proposal_found and message_sent_to_friend

            if not success:
                # Build rationale for failure
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal about borrowing conflict")
                if not message_sent_to_friend:
                    missing_checks.append("sending message to friend Alex about the conflict")

                rationale = f"Missing critical checks: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
