from typing import Any

from are.simulation.apps.messaging_v2 import MessagingAppV2
from are.simulation.types import CompletedEvent

from pas.apps.core import StatefulApp
from pas.apps.messaging.states import ConversationList, ConversationOpened


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
        initial_state = ConversationList()
        self.set_current_state(initial_state)

    def handle_state_transition(self, event: CompletedEvent) -> None:
        """Handle state transitions based on tool events.

        // RL NOTE: This implements T(s,a) -> s' for the messaging MDP.

        Args:
            event: Completed event from tool execution
        """
        function_name = event.function_name()

        # Transition: ConversationList -> ConversationOpened
        if function_name == "open_conversation":
            conversation_id = event.action.args.get("conversation_id")
            if conversation_id:
                new_state = ConversationOpened(conversation_id)
                self.set_current_state(new_state)

        # go_back transitions are handled automatically by StatefulApp.go_back()
