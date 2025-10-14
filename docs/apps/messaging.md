# Stateful Messaging App

`pas.apps.messaging.app.StatefulMessagingApp` mixes PAS navigation with the Meta-ARE `MessagingAppV2`. It begins in `ConversationList` and switches states when conversations are opened or the user goes back.

## Navigation States

### ConversationList

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_recent_conversations(offset: int = 0, limit: int = 5, offset_recent_messages_per_conversation: int = 0, limit_recent_messages_per_conversation: int = 10)` | `MessagingAppV2.list_recent_conversations(...)` with the provided pagination arguments | `list[ConversationV2]` including recent snippets and metadata | Remains in `ConversationList` |
| `search_conversations(query: str, min_date: Optional[str] = None, max_date: Optional[str] = None, limit: int = 10)` | `MessagingAppV2.search(query=query, min_date=min_date, max_date=max_date, limit=limit)` | `list[str]` of conversation ids that match | Remains in `ConversationList` |
| `open_conversation(conversation_id: str, offset: int = 0, limit: int = 20)` | `MessagingAppV2.read_conversation(conversation_id=conversation_id, offset=offset, limit=limit)` | Dict containing messages, participants, and paging info | Completed event transitions to `ConversationOpened(conversation_id)` |

### ConversationOpened

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `send_message(content: str, attachment_path: Optional[str] = None)` | `MessagingAppV2.send_message_to_group_conversation(conversation_id=current, content=content, attachment_path=attachment_path)` | Conversation id confirming delivery | Remains in `ConversationOpened` |
| `read_messages(offset: int = 0, limit: int = 10, min_date: Optional[str] = None, max_date: Optional[str] = None)` | `MessagingAppV2.read_conversation(conversation_id=current, offset=offset, limit=limit, min_date=min_date, max_date=max_date)` | Dict window of messages plus paging details | Remains in `ConversationOpened` |

## Navigation Helpers
- `go_back()` pops to `ConversationList` when history exists, mirroring mobile back navigation.
- All forward transitions are triggered by completed Meta-ARE events; there are no implicit state changes without a backend call.
