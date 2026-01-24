"""Scenario for coordinating a group purchase with bulk discount."""

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

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulEmailApp,
    StatefulMessagingApp,
)
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("group_purchase_coordinator")
class GroupPurchaseCoordinator(PASScenario):
    """Agent coordinates a group purchase after user receives bulk discount email.

    Story:
    1. User is part of a "Group Buys" chat with Lisa, Mark, and Jennifer who
       regularly coordinate bulk purchases together
    2. User receives email from "Office Deals" about BULK3FOR20 discount
       (20% off ErgoMax Office Chairs when buying 3+)
    3. Agent proposes messaging the group to see who's interested
    4. User accepts, agent sends message to group
    5. Lisa and Mark confirm interest, Jennifer declines
    6. Agent proposes placing order for 3 chairs (User + Lisa + Mark)
    7. User accepts, agent places order with discount

    This scenario exercises email-triggered opportunity detection, group messaging
    coordination, conditional participant responses, and discount-applied checkout.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    additional_system_prompt = """You are part of a group chat called 'Group Buys' with Lisa, Mark, and Jennifer
where you coordinate bulk purchases together.

ACCEPT proposals that:
- Offer to coordinate with the group about bulk discount opportunities
- Show you the discount details and participant confirmations before placing an order

REJECT proposals that:
- Place orders without first confirming everyone's interest
- Don't show you who confirmed and the pricing breakdown"""

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Messaging app
        self.messaging = StatefulMessagingApp(name="Messages")

        # Add contacts using proper API
        self.messaging.add_contacts([
            ("Lisa Park", "+1-555-0201"),
            ("Mark Stevens", "+1-555-0202"),
            ("Jennifer Wu", "+1-555-0203"),
        ])
        self.lisa_id = self.messaging.name_to_id["Lisa Park"]
        self.mark_id = self.messaging.name_to_id["Mark Stevens"]
        self.jennifer_id = self.messaging.name_to_id["Jennifer Wu"]

        # Create group conversation for bulk purchases
        self.group_conv_id = self.messaging.create_group_conversation(
            user_ids=[self.lisa_id, self.mark_id, self.jennifer_id],
            title="Group Buys",
        )

        # Add historical messages showing previous group purchase coordination
        self.messaging.add_message(
            conversation_id=self.group_conv_id,
            sender_id=self.lisa_id,
            content="Thanks everyone for joining the coffee machine group buy last month! We saved 25%!",
            timestamp=self.start_time - 86400 * 7,  # 7 days ago
        )
        self.messaging.add_message(
            conversation_id=self.group_conv_id,
            sender_id=self.mark_id,
            content="Great deal! Let me know if there are any other bulk discounts coming up.",
            timestamp=self.start_time - 86400 * 7 + 3600,
        )
        self.messaging.add_message(
            conversation_id=self.group_conv_id,
            sender_id=self.jennifer_id,
            content="Same here, always happy to join group buys!",
            timestamp=self.start_time - 86400 * 7 + 7200,
        )

        # Initialize Shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Add ErgoMax Office Chair product using proper API
        product_id = self.shopping.add_product(name="ErgoMax Office Chair")
        self.item_id = self.shopping.add_item_to_product(
            product_id=product_id,
            price=299.99,
            options={},
            available=True,
        )

        # Add bulk discount code
        self.shopping.add_discount_code(
            item_id=self.item_id,
            discount_code={"BULK3FOR20": 0.20},
        )

        # Initialize Email app
        self.email = StatefulEmailApp(name="Emails")

        self.apps = [self.agent_ui, self.system_app, self.messaging, self.shopping, self.email]

    def build_events_flow(self) -> None:
        """Build event flow for group purchase coordination."""
        aui = self.get_typed_app(PASAgentUserInterface)
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")

        # Condition function: check if agent sent message to group
        def agent_messaged_group(env: AbstractEnvironment) -> bool:
            for event in env.event_log.list_view():
                if (
                    event.event_type == EventType.AGENT
                    and isinstance(event.action, Action)
                    and event.action.class_name == "StatefulMessagingApp"
                    and event.action.function_name == "send_message_to_group_conversation"
                    and event.action.args.get("conversation_id") == self.group_conv_id
                ):
                    return True
            return False

        with EventRegisterer.capture_mode():
            # ENV: Email arrives about bulk discount opportunity
            discount_email_event = email_app.send_email_to_user_with_id(
                email_id="email-bulk-discount-001",
                sender="deals@officedeals.com",
                subject="Exclusive Bulk Discount: ErgoMax Office Chairs - 20% Off!",
                content=(
                    "Limited time offer!\n\n"
                    "Purchase 3 or more ErgoMax Office Chairs and get 20% off "
                    "with discount code BULK3FOR20.\n\n"
                    "Regular price: $299.99 each\n"
                    "With discount (3+): $239.99 each\n\n"
                    "Don't miss out on this deal!"
                ),
            ).delayed(10)

            # Oracle: Agent proposes messaging the group
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "You received an email about a 20% bulk discount on ErgoMax Office Chairs "
                        "(code BULK3FOR20, requires 3+ items). Would you like me to message your "
                        "'Group Buys' chat with Lisa, Mark, and Jennifer to see if they're interested "
                        "in joining a group purchase?"
                    )
                )
                .oracle()
                .depends_on(discount_email_event, delay_seconds=3)
            )

            # Oracle: User accepts
            acceptance_event = (
                aui.accept_proposal(content="Yes, ask them if they want to join!")
                .oracle()
                .depends_on(proposal_event, delay_seconds=5)
            )

            # Oracle: Agent sends message to group
            group_message_event = (
                messaging_app.send_message_to_group_conversation(
                    conversation_id=self.group_conv_id,
                    content=(
                        "Hey everyone! I found a bulk discount for ErgoMax Office Chairs - "
                        "20% off if we buy 3+. Regular $299.99, with discount $239.99 each. "
                        "Anyone interested in joining?"
                    ),
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Condition: Wait for agent to actually message the group
            agent_messaged_condition = ConditionCheckEvent.from_condition(agent_messaged_group).depends_on(
                discount_email_event, delay_seconds=15
            )

            # ENV: Lisa responds - YES
            lisa_response = messaging_app.create_and_add_message(
                conversation_id=self.group_conv_id,
                sender_id=self.lisa_id,
                content="I'm in! I've been needing a new chair anyway.",
            ).depends_on(agent_messaged_condition, delay_seconds=30)

            # ENV: Mark responds - YES
            mark_response = messaging_app.create_and_add_message(
                conversation_id=self.group_conv_id,
                sender_id=self.mark_id,
                content="Count me in too!",
            ).depends_on(agent_messaged_condition, delay_seconds=45)

            # ENV: Jennifer responds - NO
            jennifer_response = messaging_app.create_and_add_message(
                conversation_id=self.group_conv_id,
                sender_id=self.jennifer_id,
                content="Sorry, just bought a new chair last month. Maybe next time!",
            ).depends_on(agent_messaged_condition, delay_seconds=60)

            # Oracle: Agent reads responses
            read_responses_event = (
                messaging_app.read_conversation(
                    conversation_id=self.group_conv_id,
                    offset=0,
                    limit=20,
                )
                .oracle()
                .depends_on([lisa_response, mark_response, jennifer_response], delay_seconds=5)
            )

            # Oracle: Agent proposes placing order for 3 chairs (User + Lisa + Mark)
            order_proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "Lisa and Mark confirmed they want to join! Jennifer declined. "
                        "That's 3 chairs total (you, Lisa, and Mark) - enough to qualify for the "
                        "BULK3FOR20 discount (20% off). Should I place the order? "
                        "Total: $719.97 (saves $180)."
                    )
                )
                .oracle()
                .depends_on(read_responses_event, delay_seconds=3)
            )

            # Oracle: User accepts order
            order_acceptance = (
                aui.accept_proposal(content="Yes, place the order!")
                .oracle()
                .depends_on(order_proposal_event, delay_seconds=5)
            )

            # Oracle: Agent adds to cart
            add_to_cart_event = (
                shopping_app.add_to_cart(item_id=self.item_id, quantity=3)
                .oracle()
                .depends_on(order_acceptance, delay_seconds=2)
            )

            # Oracle: Agent checkouts with discount
            checkout_event = (
                shopping_app.checkout(discount_code="BULK3FOR20")
                .oracle()
                .depends_on(add_to_cart_event, delay_seconds=2)
            )

        self.events = [
            discount_email_event,
            proposal_event,
            acceptance_event,
            group_message_event,
            agent_messaged_condition,
            lisa_response,
            mark_response,
            jennifer_response,
            read_responses_event,
            order_proposal_event,
            order_acceptance,
            add_to_cart_event,
            checkout_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate essential outcomes.

        Checks:
        1. Agent sent proposal to user
        2. Agent sent message to group chat
        3. Agent added 3 items to cart
        4. Agent checked out with BULK3FOR20 discount code
        """
        try:
            log_entries = env.event_log.list_view()
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # Check 1: Proposal sent to user
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # Check 2: Message sent to group
            group_message_found = any(
                e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message_to_group_conversation"
                and e.action.args.get("conversation_id") == self.group_conv_id
                for e in agent_events
            )

            # Check 3: Cart had quantity 3
            cart_correct = any(
                e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
                and e.action.args.get("quantity") == 3
                for e in agent_events
            )

            # Check 4: Checkout with discount
            checkout_found = any(
                e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                and e.action.args.get("discount_code") == "BULK3FOR20"
                for e in agent_events
            )

            success = proposal_found and group_message_found and cart_correct and checkout_found

            if not success:
                missing = []
                if not proposal_found:
                    missing.append("proposal to user")
                if not group_message_found:
                    missing.append("message to group chat")
                if not cart_correct:
                    missing.append("add 3 items to cart")
                if not checkout_found:
                    missing.append("checkout with BULK3FOR20")
                return ScenarioValidationResult(
                    success=False,
                    rationale=f"Missing: {', '.join(missing)}",
                )

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
