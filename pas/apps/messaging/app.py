from __future__ import annotations

from typing import TYPE_CHECKING, Any

from are.simulation.apps.messaging_v2 import MessagingAppV2

from pas.apps.core import StatefulApp
from pas.apps.messaging.states import ConversationList, ConversationOpened
from pas.notifications import format_incoming_message, register_popup_for_event

if TYPE_CHECKING:
    from are.simulation.types import CompletedEvent


class StatefulMessagingApp(StatefulApp, MessagingAppV2):
    """Messaging app with navigation state management.

    // RL NOTE: This implements a simple 2-state MDP for messaging:
    // States: ConversationList, ConversationOpened
    // Transitions: open_conversation, go_back
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the stateful messaging app.

        Args:
            *args: Variable length argument list passed to parent classes.
            **kwargs: Arbitrary keyword arguments passed to parent classes.
        """
        super().__init__(*args, **kwargs)
        # Set initial state to conversation list
        self.load_root_state()

    def handle_state_transition(self, event: CompletedEvent) -> None:
        """Handle state transitions based on tool events.

        // RL NOTE: This implements T(s,a) -> s' for the messaging MDP.

        Args:
            event: Completed event from tool execution
        """
        current_state = self.current_state
        function_name = event.function_name()

        if current_state is None or function_name is None:
            return

        # Transition: ConversationList -> ConversationOpened
        if isinstance(current_state, ConversationList) and function_name in {"open_conversation", "read_conversation"}:
            args = event.action.resolved_args or event.action.args
            conversation_id = args.get("conversation_id")
            if conversation_id:
                self.set_current_state(ConversationOpened(conversation_id))

        # go_back transitions are handled automatically by StatefulApp.go_back()

    def create_root_state(self) -> ConversationList:
        """Return the conversation list root state."""
        return ConversationList()


register_popup_for_event("StatefulMessagingApp", "create_and_add_message", builder=format_incoming_message)
register_popup_for_event("MessagingApp", "add_message", builder=format_incoming_message)
