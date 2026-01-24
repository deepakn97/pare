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


@register_scenario("group_gift_purchase_coordination")
class GroupGiftPurchaseCoordination(PASScenario):
    """Agent coordinates group gift purchase with equal cost sharing within stated budgets.

    The user participates in a group message conversation titled "Sarah's Birthday" with
    three friends (Jordan Lee, Casey Morgan, and Alex Rivera) planning to buy a birthday
    present for their mutual friend Sarah Chen. Each friend states their maximum contribution:
    Jordan offers up to $25, Casey up to $20, and Alex up to $20.

    The agent must:
    1. Parse the group conversation to extract the gift idea (wireless earbuds) and each
       person's stated budget ceiling
    2. Search the shopping catalog for wireless earbuds
    3. Find a product + discount combination where equal split (4 ways) is within everyone's
       stated budget (minimum is $20)
    4. Propose completing the purchase with equal cost sharing
    5. After user acceptance, complete checkout with discount
    6. Send confirmation to the group with equal per-person cost

    This scenario exercises budget-aware equal cost sharing where the agent finds a solution
    that works for all participants' stated limits, rather than having the user pay remainder.
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

        # Add participants to messaging app
        self.messaging.add_users(["Jordan Lee", "Casey Morgan", "Alex Rivera", "Sarah Chen"])

        # Get user IDs
        jordan_id = self.messaging.name_to_id["Jordan Lee"]
        casey_id = self.messaging.name_to_id["Casey Morgan"]
        alex_id = self.messaging.name_to_id["Alex Rivera"]
        user_id = self.messaging.current_user_id

        # Create group conversation with user and three friends (Sarah Chen is the gift recipient, not in chat)
        birthday_convo = ConversationV2(
            title="Sarah's Birthday",
            participant_ids=[user_id, jordan_id, casey_id, alex_id],
            messages=[
                MessageV2(
                    sender_id=jordan_id,
                    content="Let's get Sarah those wireless earbuds she mentioned - good ones are around $80",
                    timestamp=self.start_time - 3600,  # 1 hour ago
                ),
                MessageV2(
                    sender_id=casey_id,
                    content="Great idea! I can put in up to $20",
                    timestamp=self.start_time - 3300,  # 55 minutes ago
                ),
                MessageV2(
                    sender_id=alex_id,
                    content="Same here, I'm good for up to $20",
                    timestamp=self.start_time - 3000,  # 50 minutes ago
                ),
                MessageV2(
                    sender_id=jordan_id,
                    content="I can do up to $25",
                    timestamp=self.start_time - 2700,  # 45 minutes ago
                ),
            ],
        )
        self.messaging.add_conversation(birthday_convo)
        self.birthday_convo_id = birthday_convo.conversation_id

        # Initialize shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Add wireless earbuds products using proper API methods
        # Product 1: $79.99 -> with 10% discount = $71.99 -> $18/person (within everyone's budget)
        self.prod1_id = self.shopping.add_product(name="SoundWave Pro Wireless Earbuds")
        self.item1_id = self.shopping.add_item_to_product(
            product_id=self.prod1_id, price=79.99, options={"color": "black", "battery": "24hrs"}, available=True
        )

        # Product 2: $84.99 -> too expensive even with discount
        prod2_id = self.shopping.add_product(name="AudioMax Wireless Earbuds Premium")
        self.shopping.add_item_to_product(
            product_id=prod2_id, price=84.99, options={"color": "white", "noise_cancelling": "yes"}, available=True
        )

        # Add discount codes for the first product item
        self.shopping.add_discount_code(item_id=self.item1_id, discount_code={"GIFT10": 10.0, "WELCOME15": 15.0})

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.shopping]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Oracle event 1: Agent reads the group conversation to understand the gift coordination
            read_convo_event = (
                messaging_app.read_conversation(conversation_id=self.birthday_convo_id, offset=0, limit=10)
                .oracle()
                .delayed(15)
            )

            # Oracle event 2: Agent searches shopping catalog for wireless earbuds
            search_event = (
                shopping_app.search_product(product_name="wireless earbuds", offset=0, limit=10)
                .oracle()
                .depends_on(read_convo_event, delay_seconds=3)
            )

            # Oracle event 3: Agent gets details of the first product (SoundWave Pro)
            product_details_event = (
                shopping_app.get_product_details(product_id=self.prod1_id)
                .oracle()
                .depends_on(search_event, delay_seconds=2)
            )

            # Oracle event 4: Agent checks for discount codes (uses best available: WELCOME15 = 15% off)
            discount_check_event = (
                shopping_app.get_discount_code_info(discount_code="WELCOME15")
                .oracle()
                .depends_on(product_details_event, delay_seconds=2)
            )

            # Oracle event 5: Agent adds the item to cart
            add_to_cart_event = (
                shopping_app.add_to_cart(item_id=self.item1_id, quantity=1)
                .oracle()
                .depends_on(discount_check_event, delay_seconds=1)
            )

            # Oracle event 6: Agent proposes completing the group gift purchase with equal split
            # $79.99 with 15% discount = $67.99 / 4 people = ~$17 each (within everyone's budget)
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed your group conversation about buying wireless earbuds for Sarah's birthday. I found SoundWave Pro Wireless Earbuds for $79.99, and with the WELCOME15 discount (15% off), the total comes to $67.99. Split equally 4 ways, that's $17 per person - within everyone's stated budget (Jordan: $25, Casey: $20, Alex: $20). Would you like me to complete this purchase?"
                )
                .oracle()
                .depends_on(add_to_cart_event, delay_seconds=3)
            )

            # Oracle event 7: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please complete the purchase!")
                .oracle()
                .depends_on(proposal_event, delay_seconds=5)
            )

            # Oracle event 8: Agent completes checkout with discount code
            checkout_event = (
                shopping_app.checkout(discount_code="WELCOME15").oracle().depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle event 9: Agent sends confirmation to the group chat with equal split
            confirmation_event = (
                messaging_app.send_message_to_group_conversation(
                    conversation_id=self.birthday_convo_id,
                    content="I've ordered the SoundWave Pro Wireless Earbuds for Sarah's birthday! Total with 15% discount: $67.99. That's $17 each for the 4 of us. Order confirmed!",
                )
                .oracle()
                .depends_on(checkout_event, delay_seconds=2)
            )

        self.events = [
            read_convo_event,
            search_event,
            product_details_event,
            discount_check_event,
            add_to_cart_event,
            proposal_event,
            acceptance_event,
            checkout_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate essential outcomes: proposal sent, checkout with best discount, group notified with split."""
        try:
            log_entries = env.event_log.list_view()
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # Essential outcome 1: Agent sent proposal to user
            proposal_sent = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and e.action.args.get("content")
                for e in agent_events
            )

            # Essential outcome 2: Agent completed checkout with the best discount code (WELCOME15)
            checkout_with_best_discount = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                and e.action.args.get("discount_code") == "WELCOME15"
                for e in agent_events
            )

            # Essential outcome 3: Agent sent confirmation to group chat mentioning equal split/contribution
            group_confirmation_with_split = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message_to_group_conversation"
                and e.action.args.get("conversation_id")
                and e.action.args.get("content")
                and "$17" in e.action.args.get("content", "")
                for e in agent_events
            )

            success = proposal_sent and checkout_with_best_discount and group_confirmation_with_split

            if not success:
                missing = []
                if not proposal_sent:
                    missing.append("proposal not sent to user")
                if not checkout_with_best_discount:
                    missing.append("checkout not completed with best discount (WELCOME15)")
                if not group_confirmation_with_split:
                    missing.append("group confirmation missing equal split/contribution info")

                rationale = f"Validation failed: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
