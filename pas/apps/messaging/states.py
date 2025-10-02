from are.simulation.apps.messaging_v2 import ConversationV2
from are.simulation.tool_utils import user_tool

from pas.apps.core import AppState


class ConversationOpened(AppState):
    """Navigation state representing an open conversation view.

    // RL NOTE: This is a conversation-specific state in the navigation MDP.
    // Context (conversation_id) is part of the state representation.
    """

    def __init__(self, conversation_id: str) -> None:
        """Initialize conversation state with the id of the conversation.

        Args:
            conversation_id: The conversation context
        """
        super().__init__()
        self.conversation_id = conversation_id

    def on_enter(self) -> None:
        """Called when entering the conversation state."""
        # TODO: Could log state entry here for any use case in future.
        pass

    def on_exit(self) -> None:
        """Called when exiting the conversation state."""
        # TODO: Could log state exit here for any use case in future.
        pass

    @user_tool()
    def send_message(self, content: str, attachment_path: str | None = None) -> str:
        """Send message in current conversation (context-aware).

        Args:
            content: The message content
            attachment_path: The path to the attachment file

        Returns:
            The id of the conversation the message was sent to
        """
        return self.app.send_message_to_group_conversation(
            conversation_id=self.conversation_id, content=content, attachment_path=attachment_path
        )

    @user_tool()
    def read_messages(
        self, offset: int = 0, limit: int = 10, min_date: str | None = None, max_date: str | None = None
    ) -> dict[str, object]:
        """Read the conversation with the given conversation_id.

        Shows the last 'limit' messages after offset. Which means messages between offset and offset + limit will be shown.
        Messages are sorted by timestamp, most recent first.

        Args:
            offset: Offset to shift the view window
            limit: Number of messages to show
            min_date: Minimum date of the messages to be shown (YYYY-MM-DD %H:%M:%S format). Default is None, which means no minimum date.
            max_date: Maximum date of the messages to be shown (YYYY-MM-DD %H:%M:%S format). Default is None, which means no maximum date.

        Returns:
            Dict with messages and additional info
        """
        return self.app.read_conversation(
            conversation_id=self.conversation_id, offset=offset, limit=limit, min_date=min_date, max_date=max_date
        )


class ConversationList(AppState):
    """Navigation state representing the conversations list view.

    // RL NOTE: This is typically an initial/hub state in the messaging app navigation graph.
    """

    def __init__(self) -> None:
        """Create conversation list state.

        Note: No app parameter - uses late binding pattern.
        """
        super().__init__()

    def on_enter(self) -> None:
        """Called when entering conversation list state."""
        pass

    def on_exit(self) -> None:
        """Called when exiting conversation list state."""
        pass

    @user_tool()
    def list_recent_conversations(
        self,
        offset: int = 0,
        limit: int = 5,
        offset_recent_messages_per_conversation: int = 0,
        limit_recent_messages_per_conversation: int = 10,
    ) -> list[ConversationV2]:
        """List recent conversations ordered by most recent modification.

        Args:
            offset: Starting index from which to list conversations
            limit: Number of conversations to list
            offset_recent_messages_per_conversation: Starting index for messages per conversation
            limit_recent_messages_per_conversation: Number of messages to list per conversation

        Returns:
            List of conversation details
        """
        return self.app.list_recent_conversations(
            offset=offset,
            limit=limit,
            offset_recent_messages_per_conversation=offset_recent_messages_per_conversation,
            limit_recent_messages_per_conversation=limit_recent_messages_per_conversation,
        )

    @user_tool()
    def search_conversations(
        self, query: str, min_date: str | None = None, max_date: str | None = None, limit: int = 10
    ) -> list[str]:
        """Search conversations by query string.

        Args:
            query: Search query
            min_date: Minimum date (YYYY-MM-DD %H:%M:%S format)
            max_date: Maximum date (YYYY-MM-DD %H:%M:%S format)
            limit: Maximum number of results

        Returns:
            List of matching conversations
        """
        return self.app.search(query=query, min_date=min_date, max_date=max_date, limit=limit)

    @user_tool()
    def open_conversation(self, conversation_id: str, offset: int = 0, limit: int = 20) -> dict[str, object]:
        """Open specific conversation (triggers state transition).

        Returns conversation data as the observation when opening.

        Args:
            conversation_id: The conversation to open
            offset: Message offset
            limit: Number of messages to load

        Returns:
            Conversation data with messages
        """
        return self.app.read_conversation(conversation_id=conversation_id, offset=offset, limit=limit)
