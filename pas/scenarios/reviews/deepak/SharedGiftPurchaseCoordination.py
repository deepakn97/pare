"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulMessagingApp,
)
from pas.apps.reminder import StatefulReminderApp
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("shared_gift_purchase_coordination")
class SharedGiftPurchaseCoordination(PASScenario):
    """Agent coordinates a shared gift purchase by aggregating friend contributions and completing the purchase before a reminder deadline.

    The user has a reminder titled "Buy wedding gift for Lisa - ceremony is Saturday" due tomorrow. Two friends send messages confirming their contributions: Alice writes "I'm in for $30 toward Lisa's wedding gift" and Bob messages "Count me in for $25 for Lisa's gift." The agent must:
    1. Detect the due reminder about the wedding gift purchase task
    2. Parse the incoming messages extracting the monetary contributions ($30 from Alice, $25 from Bob)
    3. Calculate the total pooled budget ($55 from both friends)
    4. Search the shopping catalog for appropriate wedding gift items under $55
    5. Propose a specific product to purchase as the group gift
    6. After user acceptance, add the item to cart, complete checkout, and obtain order confirmation
    7. Delete the fulfilled reminder
    8. Send confirmation messages to Alice and Bob with the purchased gift details

    This scenario exercises temporal deadline awareness, multi-participant contribution parsing, budget-constrained product search, reminder-triggered proactive shopping, and post-purchase coordination messaging across multiple contacts.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with baseline data for shared gift purchase coordination.

        Baseline state includes:
        - Reminder: "Buy wedding gift for Lisa - ceremony is Saturday" due tomorrow
        - Contacts: Alice and Bob (friends who will contribute to the gift)
        - Messaging: Empty baseline (messages will arrive as environment events)
        - Shopping: Available products in the catalog with items around $50-55 price range
        """
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Reminder app with the wedding gift reminder
        self.reminder = StatefulReminderApp(name="Reminders")

        # Create reminder due tomorrow (2025-11-19 09:00:00)
        self.wedding_reminder_id = self.reminder.add_reminder(
            title="Buy wedding gift for Lisa - ceremony is Saturday",
            due_datetime="2025-11-19 09:00:00",
            description="Coordinate with Alice and Bob and purchase a wedding gift for Lisa before tomorrow.",
            repetition_unit=None,
            repetition_value=1,
        )

        # Initialize Messaging app
        self.messaging = StatefulMessagingApp(name="Messages")

        # Add users Alice and Bob to messaging
        self.messaging.add_users(["Alice", "Bob"])
        self.alice_id = self.messaging.get_user_id("Alice")
        self.bob_id = self.messaging.get_user_id("Bob")
        if self.alice_id is None or self.bob_id is None:
            raise RuntimeError("Failed to seed messaging users for Alice/Bob")

        # Seed a stable group conversation id so environment messages can arrive in a known thread.
        # NOTE: Meta-ARE requires at least two *other* participants for create_group_conversation, so we use a 3-person thread:
        # the user + Alice + Bob.
        self.contributions_conv_id = self.messaging.create_group_conversation(
            user_ids=[self.alice_id, self.bob_id],
            title="Wedding Gift for Lisa",
        )

        # Initialize Shopping app with product catalog
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Seed a few gift options that are <= $55 so the agent can select within the pooled budget.
        self.gift_product_id = self.shopping.add_product(name="Gift - Ceramic Serving Bowl Set")
        self.gift_item_id = self.shopping.add_item_to_product(
            product_id=self.gift_product_id,
            price=54.99,
            options={"color": "ivory", "set_size": 3},
            available=True,
        )

        alt_product_id = self.shopping.add_product(name="Gift - Wine Glass Set (4-pack)")
        self.shopping.add_item_to_product(
            product_id=alt_product_id,
            price=49.99,
            options={"material": "glass", "count": 4},
            available=True,
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.reminder, self.messaging, self.shopping]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        alice_id = self.alice_id
        bob_id = self.bob_id
        conv_id = self.contributions_conv_id

        with EventRegisterer.capture_mode():
            # Environment Event 1: Alice sends message about her contribution
            alice_message_event = messaging_app.create_and_add_message(
                conversation_id=conv_id, sender_id=alice_id, content="I'm in for $30 toward Lisa's wedding gift"
            ).delayed(10)

            # Environment Event 2: Bob sends message about his contribution
            bob_message_event = messaging_app.create_and_add_message(
                conversation_id=conv_id, sender_id=bob_id, content="Count me in for $25 for Lisa's gift"
            ).delayed(15)

            # Oracle Event 1: Agent lists recent conversations to notice the new contribution messages.
            # Motivated by: environment messages from Alice/Bob arriving in messaging.
            list_conversations_event = (
                messaging_app.list_recent_conversations(
                    offset=0,
                    limit=10,
                    offset_recent_messages_per_conversation=0,
                    limit_recent_messages_per_conversation=10,
                )
                .oracle()
                .depends_on(bob_message_event, delay_seconds=1)
            )

            # Oracle Event 2: Agent reads the contributions thread to extract both amounts ($30 + $25).
            # Motivated by: the new messages from Alice and Bob.
            read_thread_event = (
                messaging_app.read_conversation(conversation_id=conv_id, offset=0, limit=20)
                .oracle()
                .depends_on(list_conversations_event, delay_seconds=1)
            )

            # Oracle Event 4: Agent checks due reminders to connect the contributions to the wedding-gift deadline.
            # Motivated by: messages mention "Lisa's wedding gift" + a known reminder task exists.
            reminder_check_event = (
                reminder_app.get_due_reminders().oracle().depends_on(read_thread_event, delay_seconds=1)
            )

            # Oracle Event 5: Agent searches shopping catalog for gift options under the pooled $55 budget.
            # Motivated by: contributions ($30+$25) + reminder due tomorrow.
            search_event = (
                shopping_app.search_product(product_name="Gift", offset=0, limit=10)
                .oracle()
                .depends_on(reminder_check_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent proposes purchasing a specific gift to the user (requires approval).
            # Motivated by: pooled budget + reminder deadline + available gift options found via search.
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed Alice and Bob have contributed toward Lisa's wedding gift ($30 + $25 = $55 total). Your reminder for the wedding gift is due tomorrow. I found a suitable gift within budget. Would you like me to purchase it and complete checkout?"
                )
                .oracle()
                .depends_on(search_event, delay_seconds=3)
            )

            # Oracle Event 4: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please go ahead and purchase the gift.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=5)
            )

            # Oracle Event 7: Agent lists products to extract the specific product/item ids for the chosen gift.
            # Motivated by: user accepted; agent needs concrete ids to add to cart.
            list_products_event = (
                shopping_app.list_all_products(offset=0, limit=10)
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 8: Agent adds the selected gift item to cart.
            # Motivated by: list_products_event reveals the ids; this scenario uses a seeded gift item id.
            add_to_cart_event = (
                shopping_app.add_to_cart(item_id=self.gift_item_id, quantity=1)
                .oracle()
                .depends_on(list_products_event, delay_seconds=2)
            )

            # Oracle Event 9: Agent completes checkout.
            # Motivated by: item is in cart and user approved purchase.
            checkout_event = (
                shopping_app.checkout(discount_code=None).oracle().depends_on(add_to_cart_event, delay_seconds=2)
            )

            # Oracle Event 10: Agent deletes the fulfilled reminder.
            # Motivated by: purchase completed, so the task is done.
            delete_reminder_event = (
                reminder_app.delete_reminder(reminder_id=self.wedding_reminder_id)
                .oracle()
                .depends_on(checkout_event, delay_seconds=1)
            )

            # Oracle Event 9: Agent sends confirmation to Alice
            # Motivated by: Need to inform Alice that her contribution was used and the gift was purchased
            alice_confirmation_event = (
                messaging_app.send_message(
                    user_id=alice_id,
                    content="Thanks for contributing $30! I've purchased Lisa's wedding gift using the pooled funds.",
                )
                .oracle()
                .depends_on(delete_reminder_event, delay_seconds=2)
            )

            # Oracle Event 10: Agent sends confirmation to Bob
            # Motivated by: Need to inform Bob that his contribution was used and the gift was purchased
            bob_confirmation_event = (
                messaging_app.send_message(
                    user_id=bob_id,
                    content="Thanks for contributing $25! I've purchased Lisa's wedding gift using the pooled funds.",
                )
                .oracle()
                .depends_on(delete_reminder_event, delay_seconds=2)
            )

            # Oracle Event 11: Agent confirms completion to the user.
            # Motivated by: checkout + reminder cleanup + notifying friends.
            final_user_event = (
                aui.send_message_to_user(
                    content="Done — I purchased a wedding gift for Lisa under the $55 budget, deleted the reminder, and sent confirmations to Alice and Bob."
                )
                .oracle()
                .depends_on([alice_confirmation_event, bob_confirmation_event], delay_seconds=1)
            )

        # Register ALL events
        self.events = [
            alice_message_event,
            bob_message_event,
            list_conversations_event,
            read_thread_event,
            reminder_check_event,
            search_event,
            proposal_event,
            acceptance_event,
            list_products_event,
            add_to_cart_event,
            checkout_event,
            delete_reminder_event,
            alice_confirmation_event,
            bob_confirmation_event,
            final_user_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to AGENT events only (oracle events executed by the agent)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT CHECK 1: Agent checked reminders
            # The agent must query due reminders to discover the wedding gift task.
            reminder_check_found = any(
                e.action.class_name == "StatefulReminderApp" and e.action.function_name == "get_due_reminders"
                for e in agent_events
            )

            # STRICT CHECK 2: Agent searched for products
            # The agent must search the shopping catalog for gift items
            product_search_found = any(
                e.action.class_name == "StatefulShoppingApp" and e.action.function_name == "search_product"
                for e in agent_events
            )

            # STRICT CHECK 3: Agent sent proposal to user
            # The agent must propose the purchase plan to the user
            proposal_found = any(
                e.action.class_name == "PASAgentUserInterface" and e.action.function_name == "send_message_to_user"
                for e in agent_events
            )

            # STRICT CHECK 4: Agent added item to cart
            # The agent must add a product to the shopping cart
            add_to_cart_found = any(
                e.action.class_name == "StatefulShoppingApp" and e.action.function_name == "add_to_cart"
                for e in agent_events
            )

            # STRICT CHECK 5: Agent completed checkout
            # The agent must complete the purchase
            checkout_found = any(
                e.action.class_name == "StatefulShoppingApp" and e.action.function_name == "checkout"
                for e in agent_events
            )

            # STRICT CHECK 6: Agent deleted the reminder
            # The agent must clean up the fulfilled reminder
            reminder_delete_found = any(
                e.action.class_name == "StatefulReminderApp" and e.action.function_name == "delete_reminder"
                for e in agent_events
            )

            # STRICT CHECK 7: Agent sent confirmation messages
            # The agent must notify both Alice and Bob about the purchase
            # We check for send_message calls to StatefulMessagingApp
            messaging_send_events = [
                e
                for e in agent_events
                if e.action.class_name == "StatefulMessagingApp" and e.action.function_name == "send_message"
            ]

            # We need at least 2 send_message calls (one for Alice, one for Bob)
            confirmations_sent = len(messaging_send_events) >= 2

            # Compile all strict checks
            all_strict_checks = [
                ("reminder_check", reminder_check_found),
                ("product_search", product_search_found),
                ("proposal_sent", proposal_found),
                ("add_to_cart", add_to_cart_found),
                ("checkout", checkout_found),
                ("reminder_deleted", reminder_delete_found),
                ("confirmations_sent", confirmations_sent),
            ]

            # Determine which checks failed
            failed_checks = [name for name, passed in all_strict_checks if not passed]

            if failed_checks:
                success = False
                rationale = f"Failed strict checks: {', '.join(failed_checks)}"
            else:
                success = True
                rationale = "All critical agent actions were executed correctly"

            return ScenarioValidationResult(success=success, rationale=rationale)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
