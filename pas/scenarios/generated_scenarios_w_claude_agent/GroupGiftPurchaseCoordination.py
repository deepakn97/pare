"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
from are.simulation.apps.shopping import Item, Product
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
    """Agent coordinates group gift purchase by tracking contributions from messaging conversation and completing shared checkout.

    The user participates in a group message conversation titled "Sarah's Birthday Gift" with three friends (Jordan Lee, Casey Morgan, and Alex Rivera) planning to chip in for a shared birthday present. The conversation unfolds as follows: Jordan suggests "Let's get Sarah that yoga mat she mentioned - I can contribute $25," Casey responds "I'm in for $20," and Alex adds "Count me in for $20 too." The user hasn't responded yet but has the target yoga mat already saved in their shopping cart from earlier browsing. The agent must: 1. Parse the group conversation to identify the shared purchase goal (yoga mat for Sarah) and calculate total contributions ($65 from friends plus user's expected contribution). 2. Search the shopping cart to locate the yoga mat item. 3. Verify the item price fits within the collected budget. 4. Check for applicable discount codes that work with the yoga mat. 5. Propose completing the purchase using the group's pooled budget and applying any valid discount. 6. After user acceptance, apply the discount code and complete checkout. 7. Send a confirmation message to the group chat with order details and per-person cost breakdown.

    This scenario exercises group conversation financial coordination, implicit user participation inference (user is part of the gift group even without explicit statement), cross-app shopping cart validation against discussed budget constraints, opportunistic discount discovery for group purchases, and transparent group communication about shared expense allocation after transaction completion.

    Wait, this has a problem - the scenario assumes the user has the item "already saved in their shopping cart from earlier browsing," which means I'm setting up baseline state that references specific items. But the prompt warns: "DO NOT rely on internal IDs/handles (e.g., `email_id`, `product_id`, `order_id`, etc.) that the agent could not plausibly know."

    Let me revise: The agent should search the shopping catalog by product name (mentioned in messages) rather than assuming it's in the cart.

    Scenario ID: group_gift_purchase_coordination
    Class Name: GroupGiftPurchaseCoordination
    Description:
    Agent coordinates group gift purchase by synthesizing product choice and budget from group conversation and completing shared shopping task.

    The user participates in a group message conversation titled "Sarah's Birthday Gift" with three friends (Jordan Lee, Casey Morgan, and Alex Rivera) planning to buy a shared present. The conversation unfolds: Jordan suggests "Let's get Sarah that wireless headphones set - I saw some good ones for around $80," Casey responds "Perfect, I can chip in $25," Alex adds "I'm in for $25 too," and Jordan confirms "I'll put in $30." The user is expected to contribute the remaining amount to reach $80. The agent must: 1. Parse the group conversation to identify the product (wireless headphones), target price ($80), and contribution tracking (friends committed $80 total). 2. Search the shopping catalog for wireless headphones around the target price. 3. Select an appropriate product and add it to the cart. 4. Check for applicable discount codes and apply if available. 5. Propose completing the purchase on behalf of the group. 6. After user acceptance, complete checkout. 7. Send a confirmation message to the group with order details, total cost, and per-person breakdown ($20 each if four people split evenly).

    This scenario exercises multi-party financial coordination from group messaging, product search based on natural language descriptions and price constraints, proactive shopping task completion for collaborative purchases, group expense calculation and transparent communication, and social context understanding where the user's role in the group implies participation without explicit statement.

    Hmm, but there's still an issue: "friends committed $80 total" - but that includes the user's implied contribution. Let me be more careful with the math:

    Jordan: $30
    Casey: $25
    Alex: $25
    Total from friends: $80

    But they're buying a gift "for Sarah" who is presumably NOT one of the four participants. So the four friends (Jordan, Casey, Alex, and the user) are splitting the cost. If the target is $80 and three friends committed $80, that's already the full amount - the user doesn't need to contribute.

    Let me fix the math:
    Jordan: $25
    Casey: $20
    Alex: $20
    Total from three friends: $65
    User expected to contribute: ~$15-20 to reach $80

    Scenario ID: group_gift_purchase_coordination
    Class Name: GroupGiftPurchaseCoordination
    Description:
    Agent coordinates group gift purchase by synthesizing product selection and budget from messaging conversation and completing shared checkout.

    The user participates in a group message conversation titled "Sarah's Birthday" with three friends (Jordan Lee, Casey Morgan, and Alex Rivera) planning to buy a birthday present for their mutual friend Sarah Chen. The conversation unfolds: Jordan suggests "Let's get Sarah those wireless earbuds she mentioned - good ones are around $80," Casey responds "Great idea! I can put in $20," Alex adds "Same, I'm in for $20," and Jordan confirms "I'll contribute $25." The user hasn't responded yet. The agent must: 1. Parse the group conversation to extract the gift idea (wireless earbuds), target price (~$80), and track contributions (Jordan $25, Casey $20, Alex $20 = $65 collected, ~$15 expected from user). 2. Search the shopping catalog for wireless earbuds near the $80 price point. 3. Select an appropriate product, check its price against the pooled budget, and add it to cart. 4. Search for applicable discount codes. 5. Propose completing the purchase as the user's contribution to the group gift, with cost breakdown. 6. After user acceptance, checkout with discount if available. 7. Send confirmation to the group chat with order details and final per-person costs.

    This scenario exercises group messaging financial coordination, implicit participation inference (user is part of the buying group despite not explicitly committing), product search with price constraints from conversation context, collaborative shopping completion, budget reconciliation across multiple contributors, and transparent expense communication after checkout.

    This is better! Let me format it properly:

    Scenario ID: group_gift_purchase_coordination
    Class Name: GroupGiftPurchaseCoordination
    Description:
    Agent coordinates group gift purchase by synthesizing product selection and contributions from group conversation.

    The user participates in a group message conversation titled "Sarah's Birthday" with three friends (Jordan Lee, Casey Morgan, and Alex Rivera) planning to buy a birthday present for their mutual friend Sarah Chen. The conversation unfolds: Jordan suggests "Let's get Sarah those wireless earbuds she mentioned - good ones are around $80," Casey responds "Great idea! I can put in $20," Alex adds "Same, I'm in for $20," and Jordan confirms "I'll contribute $25." The user hasn't responded yet. The agent must: 1. Parse the group conversation to extract the gift idea (wireless earbuds), target price (~$80), and contributions (Jordan $25, Casey $20, Alex $20 = $65 total, ~$15 expected from user). 2. Search the shopping catalog for wireless earbuds near the $80 price point. 3. Select an appropriate product and add it to the cart. 4. Search for applicable discount codes that apply to the selected product. 5. Propose completing the purchase as the user's contribution to the group gift, showing cost breakdown. 6. After user acceptance, apply discount if available and complete checkout. 7. Send confirmation message to the group chat with order details and final per-person costs.

    This scenario exercises multi-party financial coordination from group messaging, implicit user role inference (part of gift group without explicit commitment), product search based on natural language descriptions and price constraints, collaborative purchase completion where the user acts as buyer for the group, budget reconciliation across multiple contributors, and transparent post-purchase expense communication.
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

        # Add participants to messaging app's name-to-id mapping
        self.messaging.add_users(["Jordan Lee", "Casey Morgan", "Alex Rivera", "Sarah Chen"])

        # Create group conversation about Sarah's birthday gift
        jordan_id = self.messaging.name_to_id["Jordan Lee"]
        casey_id = self.messaging.name_to_id["Casey Morgan"]
        alex_id = self.messaging.name_to_id["Alex Rivera"]

        # Create the group conversation with user and three friends
        birthday_convo = ConversationV2(
            title="Sarah's Birthday",
            participant_ids=[jordan_id, casey_id, alex_id],
            messages=[
                MessageV2(
                    sender_id=jordan_id,
                    content="Let's get Sarah those wireless earbuds she mentioned - good ones are around $80",
                    timestamp=self.start_time - 3600,  # 1 hour ago
                ),
                MessageV2(
                    sender_id=casey_id,
                    content="Great idea! I can put in $20",
                    timestamp=self.start_time - 3300,  # 55 minutes ago
                ),
                MessageV2(
                    sender_id=alex_id,
                    content="Same, I'm in for $20",
                    timestamp=self.start_time - 3000,  # 50 minutes ago
                ),
                MessageV2(
                    sender_id=jordan_id,
                    content="I'll contribute $25",
                    timestamp=self.start_time - 2700,  # 45 minutes ago
                ),
            ],
        )
        self.messaging.add_conversation(birthday_convo)

        # Initialize shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Add wireless earbuds products around $80
        product1 = Product(name="SoundWave Pro Wireless Earbuds", product_id="prod_earbuds_001")
        product1.variants["item_earbuds_001"] = Item(
            item_id="item_earbuds_001", price=79.99, available=True, options={"color": "black", "battery": "24hrs"}
        )
        self.shopping.products["prod_earbuds_001"] = product1

        product2 = Product(name="AudioMax Wireless Earbuds Premium", product_id="prod_earbuds_002")
        product2.variants["item_earbuds_002"] = Item(
            item_id="item_earbuds_002",
            price=84.99,
            available=True,
            options={"color": "white", "noise_cancelling": "yes"},
        )
        self.shopping.products["prod_earbuds_002"] = product2

        # Add discount codes for the first product
        self.shopping.discount_codes["item_earbuds_001"] = {
            "GIFT10": 10.0,  # 10% off
            "WELCOME15": 15.0,  # 15% off
        }

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.shopping]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        # Get the conversation ID from the seeded conversation
        birthday_convo_id = next(iter(messaging_app.conversations.keys()))

        with EventRegisterer.capture_mode():
            # Environment event 1: Agent reads the group conversation to understand the gift coordination
            read_convo_event = (
                messaging_app.read_conversation(conversation_id=birthday_convo_id, offset=0, limit=10)
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
                shopping_app.get_product_details(product_id="prod_earbuds_001")
                .oracle()
                .depends_on(search_event, delay_seconds=2)
            )

            # Oracle event 4: Agent checks for discount codes
            discount_check_event = (
                shopping_app.get_discount_code_info(discount_code="GIFT10")
                .oracle()
                .depends_on(product_details_event, delay_seconds=2)
            )

            # Oracle event 5: Agent adds the item to cart
            add_to_cart_event = (
                shopping_app.add_to_cart(item_id="item_earbuds_001", quantity=1)
                .oracle()
                .depends_on(discount_check_event, delay_seconds=1)
            )

            # Oracle event 6: Agent proposes completing the group gift purchase
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed your group conversation about buying wireless earbuds for Sarah's birthday. Your friends have committed $65 (Jordan $25, Casey $20, Alex $20). I found SoundWave Pro Wireless Earbuds for $79.99, and there's a GIFT10 discount code available (10% off, bringing it to $71.99). With your contribution of about $7, the total per person would be $18. Would you like me to complete this purchase for the group?"
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
                shopping_app.checkout(discount_code="GIFT10").oracle().depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle event 9: Agent sends confirmation to the group chat
            confirmation_event = (
                messaging_app.send_message_to_group_conversation(
                    conversation_id=birthday_convo_id,
                    content="Great news! I've ordered the SoundWave Pro Wireless Earbuds for Sarah's birthday. Total with 10% discount: $71.99. Cost per person: $18. Order confirmed!",
                )
                .oracle()
                .depends_on(checkout_event, delay_seconds=2)
            )

        # Register ALL events
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

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:  # noqa: C901
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only AGENT events
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # Check 1: Agent read the group conversation to understand gift coordination
            conversation_read = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "read_conversation"
                for e in agent_events
            )

            # Check 2: Agent searched shopping catalog for wireless earbuds
            product_search = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "search_product"
                and "wireless earbuds" in e.action.args.get("product_name", "").lower()
                for e in agent_events
            )

            # Check 3: Agent retrieved product details
            product_details_checked = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_product_details"
                and e.action.args.get("product_id")
                for e in agent_events
            )

            # Check 4: Agent checked for discount codes
            discount_checked = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "get_discount_code_info"
                and e.action.args.get("discount_code")
                for e in agent_events
            )

            # Check 5: Agent added item to cart
            item_added = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
                and e.action.args.get("item_id")
                for e in agent_events
            )

            # Check 6: Agent sent proposal to user (flexible on exact wording)
            proposal_sent = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and e.action.args.get("content")
                for e in agent_events
            )

            # Check 7: User accepted proposal
            proposal_accepted = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "accept_proposal"
                for e in agent_events
            )

            # Check 8: Agent completed checkout (strict check: must apply discount)
            checkout_completed = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                and e.action.args.get("discount_code")
                for e in agent_events
            )

            # Check 9: Agent sent confirmation to group chat (flexible on exact message content)
            group_confirmation = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message_to_group_conversation"
                and e.action.args.get("conversation_id")
                and e.action.args.get("content")
                for e in agent_events
            )

            # Combine all checks - strict on logic, flexible on content
            success = (
                conversation_read
                and product_search
                and product_details_checked
                and discount_checked
                and item_added
                and proposal_sent
                and proposal_accepted
                and checkout_completed
                and group_confirmation
            )

            if not success:
                # Build rationale for failure
                missing = []
                if not conversation_read:
                    missing.append("conversation not read")
                if not product_search:
                    missing.append("product search not performed")
                if not product_details_checked:
                    missing.append("product details not checked")
                if not discount_checked:
                    missing.append("discount code not checked")
                if not item_added:
                    missing.append("item not added to cart")
                if not proposal_sent:
                    missing.append("proposal not sent to user")
                if not proposal_accepted:
                    missing.append("proposal not accepted")
                if not checkout_completed:
                    missing.append("checkout not completed with discount")
                if not group_confirmation:
                    missing.append("group confirmation message not sent")

                rationale = f"Validation failed: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
