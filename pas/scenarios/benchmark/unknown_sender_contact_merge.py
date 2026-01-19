from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.contacts import Contact
from are.simulation.apps.messaging_v2 import ConversationV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulContactsApp,
    StatefulMessagingApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("unknown_sender_contact_merge")
class UnknownSenderContactMerge(PASScenario):
    """Agent identifies and updates contact information when receiving messages from an unknown phone number.

    The user receives a message from an unknown number "+1-555-0198" saying "Hey, this is Jessica Chen—I got a new phone. Please update my contact to use this number (my old one won't work)." The user has an existing contact "Jessica Chen" in their contacts app with an old phone number "+1-555-0142" and email "jessica.chen@email.com". The agent must:
    1. Identify that the message is from an unknown number not in the user's contacts
    2. Parse the message content to extract the sender's self-identified name ("Jessica Chen")
    3. Search the contacts app to find existing contacts matching that name
    4. After user approval, update Jessica Chen's contact record with the new phone number

    This scenario exercises unknown sender identification, natural language parsing for identity extraction, contact record matching, and contact record updating.

    ---

    **Why this is unique:**
    - **Trigger:** Incoming message from UNKNOWN number (not a shopping notification, not a known contact)
    - **Problem domain:** Contact data hygiene and identity reconciliation (not purchase decisions or discounts)
    - **Apps:** Only uses Messaging + Contacts (drops Shopping entirely)
    - **Core reasoning:** Identity inference from message content + contact record merging (completely different from shopping/discount workflows).
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with baseline data.

        Baseline state (pre-existing before scenario execution):
        - Contacts App: Contains Jessica Chen with OLD phone number (+1-555-0142) and email
        - Messaging App: No pre-existing conversation (the new number +1-555-0198 is truly unknown)

        The triggering message will arrive as an early environment event in Step 3.
        """
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Contacts App
        self.contacts = StatefulContactsApp(name="Contacts")

        # Populate contacts: Jessica Chen with OLD phone number
        self.jessica_contact_id = self.contacts.add_contact(
            Contact(
                first_name="Jessica",
                last_name="Chen",
                contact_id="contact-jessica-chen",
                email="jessica.chen@email.com",
                phone="+1-555-0142",  # OLD phone number
                description="",
            )
        )

        # Initialize Messaging App in PHONE_NUMBER mode (to allow unknown numbers)
        from are.simulation.apps.messaging_v2 import MessagingAppMode

        self.messaging = StatefulMessagingApp(name="Messages")
        self.messaging.mode = MessagingAppMode.PHONE_NUMBER

        # No baseline messaging history - the unknown number message arrives in Step 3

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.messaging]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")

        # Create unknown number conversation for baseline
        unknown_number = "+1-555-0198"
        user_id = messaging_app.current_user_id
        unknown_conversation = ConversationV2(participant_ids=[user_id, unknown_number])
        messaging_app.add_conversation(unknown_conversation)

        with EventRegisterer.capture_mode():
            # Environment Event 1: Message from unknown number with identity claim and new-number update request
            # This is the triggering event that starts the scenario
            env_message = messaging_app.create_and_add_message(
                conversation_id=unknown_conversation.conversation_id,
                sender_id=unknown_number,
                content=(
                    "Hey, this is Jessica Chen—I got a new phone. Please update my contact to use this number "
                    "(my old one won't work)."
                ),
            ).delayed(20)

            # Oracle Event 1: Agent searches contacts to find matching name
            # Evidence: The environment message explicitly states "this is Jessica Chen", giving the agent a name to search for
            search_event = (
                contacts_app.search_contacts(query="Jessica Chen").oracle().depends_on(env_message, delay_seconds=2)
            )

            # Oracle Event 3: Agent proposes to update contact with new phone number
            # Evidence: Message says "I got a new phone" and asks to "update my contact to use this number";
            # agent also observed a mismatch between sender number (+1-555-0198) and stored contact number (+1-555-0142).
            proposal_event = (
                aui.send_message_to_user(
                    content="I received a message from +1-555-0198 claiming to be Jessica Chen. Your existing contact for Jessica Chen has a different number (+1-555-0142). Would you like me to update Jessica's contact with this new phone number?"
                )
                .oracle()
                .depends_on(search_event, delay_seconds=2)
            )

            # Oracle Event 4: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please proceed.").oracle().depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent updates contact with new phone number
            # Evidence: User just accepted the proposal to update the contact
            update_event = (
                contacts_app.edit_contact(
                    contact_id=self.jessica_contact_id,
                    updates={"phone": unknown_number},
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

        # Register ALL events
        self.events = [
            env_message,
            search_event,
            proposal_event,
            acceptance_event,
            update_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent proposed contact update with new phone number (STRICT)
            # Evidence: Agent must inform user about the mismatch and seek approval
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check Step 2: Agent updated contact with new phone number (STRICT)
            # Evidence: User accepted the proposal, agent must execute the update
            update_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "edit_contact"
                and e.action.args.get("contact_id") == "contact-jessica-chen"
                and e.action.args.get("updates", {}).get("phone") == "+1-555-0198"
                for e in log_entries
            )

            # Build success result and rationale
            success = proposal_found and update_found

            if not success:
                missing = []
                if not proposal_found:
                    missing.append("proposal to user about contact update")
                if not update_found:
                    missing.append("edit_contact with new phone number +1-555-0198")

                rationale = f"Missing required agent actions: {', '.join(missing)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
