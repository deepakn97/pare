"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.contacts import Contact
from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulContactsApp,
    StatefulMessagingApp,
)
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("contact_relocation_update")
class ContactRelocationUpdate(PASScenario):
    """Agent updates contact location information and verifies shopping order addresses when notified of a contact's relocation.

    The user receives a message from an existing contact, Michael Torres, saying: "Hey! I just moved to Seattle for a new job. Can you update my contact info? New address is 456 Pine Street, Seattle, WA 98101." The agent must:
    1. Parse the incoming message to extract relocation details (new city: Seattle, new address: 456 Pine Street, Seattle, WA 98101)
    2. Search contacts to find Michael Torres's contact record by name
    3. Update Michael's contact record with the new city_living and address fields
    4. Check the shopping app's order history to see if any recent orders (within last 30 days) were sent to Michael's old address or if he appears in any order-related context
    5. If address mismatches are found in pending/recent orders, alert the user to potential delivery issues
    6. Send a confirmation message back to Michael confirming the contact update and noting any order address concerns if applicable

    This scenario exercises natural language parsing for personal data updates, contact record modification, cross-app validation (contact address changes vs shopping order destinations), and proactive issue detection when personal information changes affect pending transactions.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Contacts app
        self.contacts = StatefulContactsApp(name="Contacts")

        # Create Michael Torres contact with old address (San Francisco)
        michael = Contact(
            first_name="Michael",
            last_name="Torres",
            phone="+1-555-0147",
            email="michael.torres@example.com",
            city_living="San Francisco",
            address="123 Market Street, San Francisco, CA 94103",
            job="Software Engineer",
        )
        self.contacts.add_contact(michael)

        # Create current user contact
        user = Contact(
            first_name="Alex",
            last_name="Chen",
            phone="+1-555-0100",
            email="alex.chen@example.com",
            is_user=True,
        )
        self.contacts.add_contact(user)

        # Initialize Messaging app
        self.messaging = StatefulMessagingApp(name="Messages")
        self.messaging.current_user_id = user.phone
        self.messaging.current_user_name = f"{user.first_name} {user.last_name}"

        # Register Michael Torres in messaging app
        self.messaging.add_contacts([("Michael Torres", michael.phone)])

        # Create a prior conversation with Michael (old message history)
        prior_conversation = ConversationV2(
            participant_ids=[user.phone, michael.phone],
            title="Michael Torres",
            messages=[
                MessageV2(
                    sender_id=michael.phone,
                    content="Thanks for the recommendation on that new restaurant!",
                    timestamp=self.start_time - 86400 * 7,  # 7 days ago
                ),
                MessageV2(
                    sender_id=user.phone,
                    content="Anytime! Let me know how it goes.",
                    timestamp=self.start_time - 86400 * 7 + 300,
                ),
            ],
        )
        self.messaging.add_conversation(prior_conversation)
        self.michael_conversation_id = prior_conversation.conversation_id

        # Initialize Shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Note: The scenario narrative mentions checking for orders to Michael's old address,
        # but in typical shopping apps, orders are associated with the user's account,
        # not with contacts' addresses. To make this scenario work, we'll assume the user
        # has placed orders in the past and the agent should verify no pending orders exist
        # that might be affected. For simplicity, we'll leave the shopping app with no orders
        # initially, as the main trigger will be the message itself.

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.messaging, self.shopping]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Michael sends message about relocation
            relocation_message_event = messaging_app.create_and_add_message(
                conversation_id=self.michael_conversation_id,
                sender_id="+1-555-0147",
                content="Hey! I just moved to Seattle for a new job. Can you update my contact info? New address is 456 Pine Street, Seattle, WA 98101.",
            ).delayed(1)

            # Oracle Event 1: Agent reads the conversation to see the relocation message
            # Motivated by: the incoming message notification will trigger the agent to check the conversation
            read_conversation_event = (
                messaging_app.read_conversation(
                    conversation_id=self.michael_conversation_id,
                    offset=0,
                    limit=10,
                )
                .oracle()
                .depends_on(relocation_message_event, delay_seconds=2)
            )

            # Oracle Event 2: Agent searches for Michael Torres in contacts to get contact_id
            # Motivated by: the message content mentions updating contact info, so agent needs to find the existing contact
            search_contacts_event = (
                contacts_app.search_contacts(query="Michael Torres")
                .oracle()
                .depends_on(read_conversation_event, delay_seconds=1)
            )

            # Oracle Event 3: Agent proposes to update Michael's contact and check shopping orders
            # Motivated by: agent has read the relocation request and found the matching contact
            proposal_event = (
                aui.send_message_to_user(
                    content="Michael Torres has moved to Seattle and requested a contact update. Would you like me to update his contact with the new address (456 Pine Street, Seattle, WA 98101) and verify if any pending orders might be affected?"
                )
                .oracle()
                .depends_on(search_contacts_event, delay_seconds=2)
            )

            # Oracle Event 4: User accepts the proposal
            # Motivated by: user agrees to the proposed contact update and order verification
            acceptance_event = (
                aui.accept_proposal(content="Yes, please update Michael's contact and check for any order issues.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=3)
            )

            # Oracle Event 5: Agent updates Michael's contact with new city and address
            # Motivated by: user has accepted the proposal, now agent executes the contact update with details from the message
            update_contact_event = (
                contacts_app.edit_contact(
                    contact_id=next(
                        iter(contacts_app.contacts.values())
                    ).contact_id,  # Michael's contact_id from search
                    updates={
                        "city_living": "Seattle",
                        "address": "456 Pine Street, Seattle, WA 98101",
                    },
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 6: Agent checks shopping orders to verify no address conflicts
            # Motivated by: part of the acceptance was to check for order issues related to the address change
            list_orders_event = shopping_app.list_orders().oracle().depends_on(update_contact_event, delay_seconds=1)

            # Oracle Event 7: Agent sends confirmation message back to Michael
            # Motivated by: agent has completed the contact update and verified no order issues (empty order list), so confirms back to Michael
            confirmation_event = (
                messaging_app.send_message(
                    user_id="+1-555-0147",
                    content="Done! I've updated your contact with the new Seattle address. No pending orders were affected.",
                )
                .oracle()
                .depends_on(list_orders_event, delay_seconds=2)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            relocation_message_event,
            read_conversation_event,
            search_contacts_event,
            proposal_event,
            acceptance_event,
            update_contact_event,
            list_orders_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1 (STRICT): Agent read the conversation to parse the relocation message
            # The agent must have read the conversation containing Michael's relocation request
            read_conversation_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "read_conversation"
                for e in log_entries
            )

            # Check Step 2 (STRICT): Agent searched for Michael Torres in contacts
            # The agent must have searched contacts to locate Michael's contact record
            search_contacts_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "search_contacts"
                for e in log_entries
            )

            # Check Step 3 (STRICT): Agent proposed the contact update and order verification
            # The agent must have sent a proposal to the user via PASAgentUserInterface
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check Step 4 (STRICT): Agent updated Michael's contact with new city and address
            # The agent must have called edit_contact to update the contact record
            update_contact_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "edit_contact"
                for e in log_entries
            )

            # Check Step 5 (STRICT): Agent checked shopping orders for address conflicts
            # The agent must have called list_orders to verify order addresses
            list_orders_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "list_orders"
                for e in log_entries
            )

            # All checks must pass for success
            success = (
                read_conversation_found
                and search_contacts_found
                and proposal_found
                and update_contact_found
                and list_orders_found
            )

            if not success:
                # Build rationale for failure
                missing_checks = []
                if not read_conversation_found:
                    missing_checks.append("read_conversation to parse relocation message")
                if not search_contacts_found:
                    missing_checks.append("search_contacts for Michael Torres")
                if not proposal_found:
                    missing_checks.append("proposal to update contact and verify orders")
                if not update_contact_found:
                    missing_checks.append("edit_contact with new city_living and address")
                if not list_orders_found:
                    missing_checks.append("list_orders to check for address conflicts")

                rationale = f"Missing required agent actions: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
