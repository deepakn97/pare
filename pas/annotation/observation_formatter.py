"""Observation formatter for converting raw tool observations to human-readable text.

.. deprecated::
    This module is part of the old binary annotation pipeline and will be removed
    after the UI update. The ternary pipeline uses raw ``llm_input`` messages instead
    of formatted observations.

This module provides formatters for all return types used in PAS apps.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

# Import meta-ARE types for proper parsing
from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2

logger = logging.getLogger(__name__)

# Namespace for safe eval of meta-ARE dataclass repr strings
_SAFE_EVAL_NAMESPACE: dict[str, Any] = {
    "ConversationV2": ConversationV2,
    "MessageV2": MessageV2,
}


class ObservationFormatter:
    """Formats raw observations into human-readable displays."""

    @staticmethod
    def format(tool_name: str, raw_observation: Any, tool_args: dict[str, Any] | None = None) -> str:  # noqa: ANN401, C901
        """Format an observation based on the tool that produced it.

        Args:
            tool_name: The name of the tool (e.g., "Emails__list_emails").
            raw_observation: The raw observation data (usually a string repr of dataclass).
            tool_args: Optional dictionary of tool arguments for context.

        Returns:
            A human-readable formatted string.
        """
        obs_str = str(raw_observation)
        tool_args = tool_args or {}

        # Handle special simple cases
        if isinstance(raw_observation, str):
            if "Opened" in raw_observation and "App" in raw_observation:
                return raw_observation
            if "Switched to home screen" in raw_observation:
                return raw_observation
            if _is_uuid(raw_observation):
                return "Action completed."

        # Route based on tool name
        app_name = tool_name.split("__")[0] if "__" in tool_name else ""
        action_name = tool_name.split("__")[1] if "__" in tool_name else tool_name

        # Email app
        if app_name == "Emails":
            return _format_email_observation(action_name, obs_str, tool_args)

        # Contacts app
        if app_name == "Contacts":
            return _format_contacts_observation(action_name, obs_str, tool_args)

        # Calendar app
        if app_name == "Calendar":
            return _format_calendar_observation(action_name, obs_str, tool_args)

        # Messages app
        if app_name == "Messages":
            return _format_messages_observation(action_name, obs_str, tool_args)

        # Notes app
        if app_name == "Notes":
            return _format_notes_observation(action_name, obs_str, tool_args)

        # Reminder app
        if app_name == "Reminders":
            return _format_reminder_observation(action_name, obs_str, tool_args)

        # Cab app
        if app_name == "Cab":
            return _format_cab_observation(action_name, obs_str, tool_args)

        # Apartment app
        if app_name == "Apartment":
            return _format_apartment_observation(action_name, obs_str, tool_args)

        # Shopping app
        if app_name == "Shopping":
            return _format_shopping_observation(action_name, obs_str, tool_args)

        # System app
        if app_name == "System":
            return obs_str

        # PASAgentUserInterface
        if app_name == "PASAgentUserInterface":
            if _is_uuid(obs_str.strip()):
                return "Response recorded."
            return obs_str

        # Default: truncate if too long
        if len(obs_str) > 500:
            return obs_str[:500] + "..."
        return obs_str


# ============================================================================
# Helper Functions
# ============================================================================


def _is_uuid(s: str) -> bool:
    """Check if a string looks like a UUID."""
    uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    return bool(re.match(uuid_pattern, s.strip(), re.IGNORECASE))


def _extract_field(obs_str: str, field_name: str) -> str | None:
    """Extract a single-quoted field value from a dataclass string representation."""
    pattern = rf"{field_name}='([^']*?)'"
    match = re.search(pattern, obs_str)
    return match.group(1) if match else None


def _extract_field_any(obs_str: str, field_name: str) -> str | None:
    """Extract a field value (any type) from a dataclass string representation."""
    # Try quoted string first
    pattern = rf"{field_name}='([^']*?)'"
    match = re.search(pattern, obs_str)
    if match:
        return match.group(1)

    # Try unquoted value (number, bool, None, etc.)
    pattern = rf"{field_name}=([^,\)]+)"
    match = re.search(pattern, obs_str)
    return match.group(1).strip() if match else None


def _format_timestamp(ts_str: str | None) -> str:
    """Format a Unix timestamp string to readable date/time."""
    if not ts_str:
        return "Unknown"
    try:
        ts = float(ts_str)
        dt = datetime.fromtimestamp(ts, tz=UTC)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return ts_str


def _truncate(s: str, length: int = 60) -> str:
    """Truncate a string and add ellipsis if needed."""
    s = s.replace("\\n", " ").replace("\n", " ").strip()
    if len(s) > length:
        return s[:length] + "..."
    return s


def _is_hex_id(s: str) -> bool:
    """Check if a string looks like a hex ID (UUID without dashes or similar)."""
    return bool(re.match(r"^[0-9a-f]{20,}$", s.strip(), re.IGNORECASE))


def format_notification(raw_notification: str, id_to_name_map: dict[str, str] | None = None) -> str:
    """Format a notification to be human-readable.

    Converts raw notifications like:
    '[2025-11-18 09:00:05] New message from 22c41f3ff12fe5f2a0a02c1da9d15b57 in conversation xyz: Hello!'

    To:
    '[2025-11-18 09:00:05] New message: Hello!'

    Args:
        raw_notification: The raw notification string.
        id_to_name_map: Optional mapping from IDs to human-readable names.

    Returns:
        A cleaned notification string.
    """
    id_to_name_map = id_to_name_map or {}
    lines = []

    for line in raw_notification.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        # Handle message notifications - match any ID format (hex, conv_xxx, etc.)
        # Pattern: [timestamp] New message from <any_id> in [conversation] <any_id>: <content>
        msg_match = re.match(
            r"(\[[\d\-: ]+\])\s*New message from (\S+) in (?:conversation )?(\S+):\s*(.+)",
            line,
            re.IGNORECASE | re.DOTALL,
        )
        if msg_match:
            timestamp, sender_id, _conv_id, content = msg_match.groups()
            # Strip trailing colon from conv_id if present
            _conv_id = _conv_id.rstrip(":")
            sender_name = id_to_name_map.get(sender_id, None)
            if sender_name:
                lines.append(f"{timestamp} New message from {sender_name}: {content}")
            else:
                # Just show the content without the confusing IDs
                lines.append(f"{timestamp} New message: {content}")
            continue

        # Handle email notifications: "New email from <email>: <subject>"
        email_match = re.match(
            r"(\[[\d\-: ]+\])\s*New email from ([^:]+):\s*(.+)",
            line,
            re.IGNORECASE,
        )
        if email_match:
            timestamp, sender, subject = email_match.groups()
            lines.append(f"{timestamp} New email from {sender}: {subject}")
            continue

        # Handle calendar notifications
        cal_match = re.match(
            r"(\[[\d\-: ]+\])\s*(Upcoming event|Event reminder|Calendar):\s*(.+)",
            line,
            re.IGNORECASE,
        )
        if cal_match:
            timestamp, notif_type, content = cal_match.groups()
            lines.append(f"{timestamp} {notif_type}: {content}")
            continue

        # Handle calendar event with ID: "Calendar event <id> deleted/updated/created by <name>"
        # ID can be hex (a-f0-9) or readable format (word_word_123)
        cal_event_match = re.match(
            r"(\[[\d\-: ]+\])\s*Calendar event \S+ (deleted|updated|created|cancelled)(.*)$",
            line,
            re.IGNORECASE,
        )
        if cal_event_match:
            timestamp, action, rest = cal_event_match.groups()
            lines.append(f"{timestamp} Calendar event {action}{rest}")
            continue

        # Handle reminder notifications
        reminder_match = re.match(
            r"(\[[\d\-: ]+\])\s*(Reminder):\s*(.+)",
            line,
            re.IGNORECASE,
        )
        if reminder_match:
            timestamp, notif_type, content = reminder_match.groups()
            lines.append(f"{timestamp} {notif_type}: {content}")
            continue

        # Handle other notifications - just pass through
        lines.append(line)

    return "\n".join(lines)


# ============================================================================
# Email Formatters
# ============================================================================


def _format_email_observation(action: str, obs_str: str, args: dict[str, Any]) -> str:
    """Format email app observations."""
    if action in ("list_emails", "search_emails"):
        return _format_email_list(obs_str)

    if action == "switch_folder":
        folder = args.get("folder_name", "folder")
        return _format_email_list(obs_str, folder_name=folder)

    if action in ("open_email_by_id", "open_email", "open_email_by_index", "refresh"):
        return _format_email_detail(obs_str)

    if action in ("reply", "forward", "send_composed_email"):
        if _is_uuid(obs_str.strip()) or len(obs_str.strip()) == 32:
            return "Email sent successfully."
        return f"Email sent. (ID: {obs_str[:8]}...)"

    if action in ("move", "delete"):
        return "Email moved." if action == "move" else "Email deleted."

    if action == "start_compose":
        return "Compose email started."

    if action in ("set_recipients", "add_recipient", "set_cc", "set_subject", "set_body", "attach_file"):
        return _format_compose_draft(obs_str)

    if action in ("save_draft", "discard_draft"):
        return "Draft saved." if action == "save_draft" else "Draft discarded."

    return _truncate(obs_str, 300)


def _format_email_list(obs_str: str, folder_name: str | None = None) -> str:
    """Format ReturnedEmails or list[Email]."""
    if "emails=[]" in obs_str or obs_str.strip() == "[]":
        if folder_name:
            return f"[{folder_name.title()}] No emails."
        return "No emails."

    # Extract individual emails
    emails = _parse_emails(obs_str)

    if not emails:
        return "Emails loaded."

    # Build formatted output
    lines = [f"[{folder_name.title()}] {len(emails)} email(s):"] if folder_name else [f"{len(emails)} email(s):"]

    lines.append("-" * 40)

    for i, email in enumerate(emails[:5], 1):
        lines.append(f"{i}. From: {email.get('sender', 'Unknown')}")
        lines.append(f"   Subject: {email.get('subject', '(no subject)')}")
        preview = _truncate(email.get("content") or "", 50)
        if preview:
            lines.append(f"   Preview: {preview}")
        is_read = email.get("is_read", "")
        if is_read == "False":
            lines.append("   [UNREAD]")
        lines.append("")

    if len(emails) > 5:
        lines.append(f"... and {len(emails) - 5} more emails")

    return "\n".join(lines)


def _format_email_detail(obs_str: str) -> str:
    """Format a single Email with proper newlines."""
    # Check if already formatted with proper structure - just truncate content, preserve newlines
    if "From:" in obs_str and "Subject:" in obs_str and "Content:" in obs_str and not obs_str.startswith("Email("):
        # Already formatted with newlines, just truncate the total length
        if len(obs_str) > 500:
            return obs_str[:500] + "..."
        return obs_str

    sender = _extract_field(obs_str, "sender") or "Unknown"
    recipients = _extract_field(obs_str, "recipients") or ""
    subject = _extract_field(obs_str, "subject") or "(no subject)"
    content = _extract_field(obs_str, "content") or ""
    cc = _extract_field(obs_str, "cc") or ""
    timestamp = _extract_field_any(obs_str, "timestamp")

    lines = [
        f"From: {sender}",
        f"To: {recipients}",
    ]
    if cc and cc != "[]":
        lines.append(f"CC: {cc}")
    lines.append(f"Subject: {subject}")
    if timestamp:
        lines.append(f"Date: {_format_timestamp(timestamp)}")
    lines.append("")
    lines.append(_truncate(content, 300))

    return "\n".join(lines)


def _format_compose_draft(obs_str: str) -> str:
    """Format compose email draft state."""
    recipients = _extract_field(obs_str, "recipients") or ""
    subject = _extract_field(obs_str, "subject") or ""
    body = _extract_field(obs_str, "body") or ""

    lines = ["Draft updated:"]
    if recipients:
        lines.append(f"  To: {recipients}")
    if subject:
        lines.append(f"  Subject: {subject}")
    if body:
        lines.append(f"  Body: {_truncate(body, 50)}")

    return "\n".join(lines) if len(lines) > 1 else "Draft updated."


def _parse_emails(obs_str: str) -> list[dict[str, str | None]]:
    """Parse Email objects from string representation."""
    emails = []
    # Match Email( ... ) blocks
    email_blocks = re.findall(r"Email\([^)]+(?:\([^)]*\)[^)]*)*\)", obs_str, re.DOTALL)

    for block in email_blocks:
        email = {
            "sender": _extract_field(block, "sender"),
            "subject": _extract_field(block, "subject"),
            "content": _extract_field(block, "content"),
            "is_read": _extract_field_any(block, "is_read"),
        }
        emails.append(email)

    return emails


# ============================================================================
# Contacts Formatters
# ============================================================================


def _format_contacts_observation(action: str, obs_str: str, args: dict[str, Any]) -> str:
    """Format contacts app observations."""
    if action in ("list_contacts", "search_contacts"):
        return _format_contacts_list(obs_str)

    if action in ("open_contact", "view_contact", "view_current_user"):
        return _format_contact_detail(obs_str)

    if action == "create_contact":
        if _is_uuid(obs_str.strip()) or len(obs_str.strip()) == 32:
            return "Contact created."
        return f"Contact created. (ID: {obs_str[:8]}...)"

    if action == "delete_contact":
        return "Contact deleted."

    if action == "start_edit_contact":
        return _format_contact_detail(obs_str)

    if action == "update_contact":
        return "Contact updated."

    return _truncate(obs_str, 300)


def _format_contacts_list(obs_str: str) -> str:
    """Format list of contacts."""
    if "[]" in obs_str or "'contacts': []" in obs_str:
        return "No contacts found."

    contacts = _parse_contacts(obs_str)

    if not contacts:
        return "Contacts loaded."

    lines = [f"{len(contacts)} contact(s):"]
    lines.append("-" * 40)

    for i, contact in enumerate(contacts[:10], 1):
        name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
        if not name:
            name = "Unknown"
        lines.append(f"{i}. {name}")
        if contact.get("phone"):
            lines.append(f"   Phone: {contact['phone']}")
        if contact.get("email"):
            lines.append(f"   Email: {contact['email']}")
        lines.append("")

    if len(contacts) > 10:
        lines.append(f"... and {len(contacts) - 10} more contacts")

    return "\n".join(lines)


def _format_contact_detail(obs_str: str) -> str:
    """Format a single Contact."""
    first = _extract_field(obs_str, "first_name") or ""
    last = _extract_field(obs_str, "last_name") or ""
    name = f"{first} {last}".strip() or "Unknown"

    phone = _extract_field(obs_str, "phone")
    email = _extract_field(obs_str, "email")
    job = _extract_field(obs_str, "job")
    city = _extract_field(obs_str, "city_living")
    address = _extract_field(obs_str, "address")

    lines = [f"Contact: {name}"]
    lines.append("-" * 30)
    if phone and phone != "None":
        lines.append(f"Phone: {phone}")
    if email and email != "None":
        lines.append(f"Email: {email}")
    if job and job != "None":
        lines.append(f"Job: {job}")
    if city and city != "None":
        lines.append(f"City: {city}")
    if address and address != "None":
        lines.append(f"Address: {address}")

    return "\n".join(lines)


def _parse_contacts(obs_str: str) -> list[dict[str, str | None]]:
    """Parse Contact objects from string representation."""
    contacts = []
    contact_blocks = re.findall(r"Contact\([^)]+(?:\([^)]*\)[^)]*)*\)", obs_str, re.DOTALL)

    for block in contact_blocks:
        contact = {
            "first_name": _extract_field(block, "first_name"),
            "last_name": _extract_field(block, "last_name"),
            "phone": _extract_field(block, "phone"),
            "email": _extract_field(block, "email"),
        }
        contacts.append(contact)

    return contacts


# ============================================================================
# Calendar Formatters
# ============================================================================


def _format_calendar_observation(action: str, obs_str: str, args: dict[str, Any]) -> str:  # noqa: C901
    """Format calendar app observations."""
    if action in (
        "list_events",
        "search_events",
        "filter_by_tag",
        "filter_by_attendee",
        "get_calendar_events_by_tag",
        "read_today_calendar_events",
    ):
        return _format_calendar_events(obs_str)

    if action in ("open_event_by_id", "open_event_by_index", "refresh"):
        return _format_calendar_event_detail(obs_str)

    if action == "set_day":
        date = args.get("date", "")
        return f"Calendar switched to: {date}"

    if action == "start_create_event":
        return "Creating new event..."

    if action in ("save", "delete", "delete_by_attendee"):
        if action == "delete" or action == "delete_by_attendee":
            return "Event deleted."
        return "Event saved."

    if action.startswith("set_") or action.startswith("add_") or action.startswith("remove_"):
        return _format_event_draft(obs_str)

    if action == "get_all_tags":
        return _format_tag_list(obs_str)

    if action == "list_attendees":
        return _format_attendee_list(obs_str)

    if action == "edit_event":
        return "Editing event..."

    if action == "get_calendar_events_from_to":
        return _format_calendar_events(obs_str)

    return _truncate(obs_str, 300)


def _format_calendar_events(obs_str: str) -> str:
    """Format list of CalendarEvents."""
    if "[]" in obs_str or "'events': []" in obs_str:
        return "No events found."

    events = _parse_calendar_events(obs_str)

    if not events:
        return "Calendar events loaded."

    lines = [f"{len(events)} event(s):"]
    lines.append("-" * 40)

    for i, event in enumerate(events[:5], 1):
        title = event.get("title", "Untitled")
        start = event.get("start_strftime") or _format_timestamp(event.get("start_datetime"))
        end = event.get("end_strftime") or _format_timestamp(event.get("end_datetime"))
        location = event.get("location")

        lines.append(f"{i}. {title}")
        lines.append(f"   Time: {start} - {end}")
        if location and location != "None":
            lines.append(f"   Location: {location}")
        lines.append("")

    if len(events) > 5:
        lines.append(f"... and {len(events) - 5} more events")

    return "\n".join(lines)


def _format_calendar_event_detail(obs_str: str) -> str:
    """Format a single CalendarEvent."""
    title = _extract_field(obs_str, "title") or "Untitled"
    start = _extract_field(obs_str, "start_strftime") or _format_timestamp(
        _extract_field_any(obs_str, "start_datetime")
    )
    end = _extract_field(obs_str, "end_strftime") or _format_timestamp(_extract_field_any(obs_str, "end_datetime"))
    location = _extract_field(obs_str, "location")
    description = _extract_field(obs_str, "description")
    attendees = _extract_field(obs_str, "attendees")
    tag = _extract_field(obs_str, "tag")

    lines = [f"Event: {title}"]
    lines.append("-" * 30)
    lines.append(f"Start: {start}")
    lines.append(f"End: {end}")
    if location and location != "None":
        lines.append(f"Location: {location}")
    if tag and tag != "None":
        lines.append(f"Tag: {tag}")
    if attendees and attendees != "[]":
        lines.append(f"Attendees: {attendees}")
    if description and description != "None":
        lines.append(f"Description: {_truncate(description, 100)}")

    return "\n".join(lines)


def _format_event_draft(obs_str: str) -> str:
    """Format event draft update response."""
    return "Event draft updated."


def _format_tag_list(obs_str: str) -> str:
    """Format list of tags."""
    if "[]" in obs_str:
        return "No tags found."
    return f"Tags: {obs_str}"


def _format_attendee_list(obs_str: str) -> str:
    """Format list of attendees."""
    if "[]" in obs_str:
        return "No attendees."
    return f"Attendees: {obs_str}"


def _parse_calendar_events(obs_str: str) -> list[dict[str, str | None]]:
    """Parse CalendarEvent objects from string representation."""
    events = []
    event_blocks = re.findall(r"CalendarEvent\([^)]+(?:\([^)]*\)[^)]*)*\)", obs_str, re.DOTALL)

    for block in event_blocks:
        event = {
            "title": _extract_field(block, "title"),
            "start_datetime": _extract_field_any(block, "start_datetime"),
            "end_datetime": _extract_field_any(block, "end_datetime"),
            "start_strftime": _extract_field(block, "start_strftime"),
            "end_strftime": _extract_field(block, "end_strftime"),
            "location": _extract_field(block, "location"),
        }
        events.append(event)

    return events


# ============================================================================
# Messages Formatters
# ============================================================================


def _format_messages_observation(action: str, obs_str: str, args: dict[str, Any]) -> str:
    """Format messaging app observations."""
    if action == "list_recent_conversations":
        return _format_conversations_list(obs_str)

    if action in ("open_conversation", "read_messages"):
        return _format_messages_list(obs_str)

    if action == "send_message":
        if _is_uuid(obs_str.strip()):
            return "Message sent."
        return "Message sent."

    if action == "search_conversations":
        return _format_conversation_ids(obs_str)

    return _truncate(obs_str, 300)


def _format_conversations_list(obs_str: str) -> str:
    """Format list of Conversations in a chat-like format.

    Shows: [Name]: last message
    If name is not available, just shows the message.
    """
    if "[]" in obs_str:
        return "No conversations."

    convos = _parse_conversations(obs_str)

    if not convos:
        return "Conversations loaded."

    lines = []
    for convo in convos[:10]:
        title = convo.get("title")
        last_msg = convo.get("last_message") or ""

        if title and last_msg:
            lines.append(f"[{title}]: {_truncate(last_msg, 60)}")
        elif title:
            lines.append(f"[{title}]: (no messages)")
        elif last_msg:
            # No title available, just show the message
            lines.append(_truncate(last_msg, 70))
        else:
            lines.append("(empty conversation)")

    if len(convos) > 10:
        lines.append(f"... and {len(convos) - 10} more conversations")

    return "\n".join(lines)


def _format_messages_list(obs_str: str) -> str:
    """Format messages in a conversation."""
    if "'messages': []" in obs_str or "messages=[]" in obs_str:
        return "No messages in conversation."

    messages = _parse_messages(obs_str)

    if not messages:
        return "Messages loaded."

    lines = ["Messages:"]

    for msg in messages[-10:]:  # Show last 10 messages
        sender = (msg.get("sender") or "Unknown")[:20]
        content = _truncate(msg.get("content") or "", 60)
        lines.append(f"  [{sender}]: {content}")

    return "\n".join(lines)


def _format_conversation_ids(obs_str: str) -> str:
    """Format conversation search results (list of IDs)."""
    if "[]" in obs_str:
        return "No conversations found."
    return f"Found conversations: {obs_str}"


def _parse_conversations(obs_str: str) -> list[dict[str, str | None]]:  # noqa: C901
    """Parse Conversation objects using Python eval with safe namespace."""
    convos: list[dict[str, str | None]] = []

    # Try to parse as Python list using safe eval
    try:
        # Check if it looks like a list of ConversationV2 objects
        if "ConversationV2(" in obs_str:
            # Find the list bounds
            start = obs_str.find("[")
            if start == -1:
                start = 0

            parsed = eval(obs_str[start:], {"__builtins__": {}}, _SAFE_EVAL_NAMESPACE)  # noqa: S307

            if isinstance(parsed, list):
                for conv in parsed:
                    if isinstance(conv, ConversationV2):
                        last_msg = conv.messages[-1].content if conv.messages else None
                        convos.append({
                            "title": conv.title,
                            "last_message": last_msg,
                        })
            elif isinstance(parsed, ConversationV2):
                last_msg = parsed.messages[-1].content if parsed.messages else None
                convos.append({
                    "title": parsed.title,
                    "last_message": last_msg,
                })

            return convos
    except Exception as e:
        logger.debug(f"Failed to parse conversations with eval: {e}")

    # Fallback to regex parsing if eval fails
    i = 0
    while i < len(obs_str):
        conv_start = obs_str.find("ConversationV2(", i)
        if conv_start == -1:
            conv_start = obs_str.find("Conversation(", i)
        if conv_start == -1:
            break

        depth = 0
        end = conv_start
        for j in range(conv_start, len(obs_str)):
            if obs_str[j] == "(":
                depth += 1
            elif obs_str[j] == ")":
                depth -= 1
                if depth == 0:
                    end = j + 1
                    break

        block = obs_str[conv_start:end]
        title = _extract_field(block, "title")
        content_match = re.search(r"content='([^']*?)'", block)
        last_message = content_match.group(1) if content_match else None

        convos.append({
            "title": title,
            "last_message": last_message,
        })
        i = end

    return convos


def _parse_messages(obs_str: str) -> list[dict[str, str | None]]:
    """Parse Message objects."""
    messages = []
    # Match both Message and MessageV2
    msg_pattern = r"Message(?:V2)?\([^)]+\)"
    blocks = re.findall(msg_pattern, obs_str, re.DOTALL)

    for block in blocks:
        msg = {
            "sender": _extract_field(block, "sender") or _extract_field(block, "sender_id"),
            "content": _extract_field(block, "content"),
        }
        messages.append(msg)

    return messages


# ============================================================================
# Notes Formatters
# ============================================================================


def _format_notes_observation(action: str, obs_str: str, args: dict[str, Any]) -> str:  # noqa: C901
    """Format notes app observations."""
    if action in ("list_notes", "search"):
        return _format_notes_list(obs_str)

    if action in ("open", "refresh"):
        return _format_note_detail(obs_str)

    if action == "new_note":
        return "New note created."

    if action == "list_folders":
        return _format_folder_list(obs_str)

    if action == "delete":
        return "Note deleted."

    if action == "edit":
        return "Editing note..."

    if action == "update":
        return "Note updated."

    if action == "duplicate":
        return "Note duplicated."

    if action == "move":
        dest = args.get("dest_folder_name", "")
        return f"Note moved to {dest}." if dest else "Note moved."

    if action in ("list_attachments", "add_attachment", "remove_attachment"):
        return obs_str

    return _truncate(obs_str, 300)


def _format_notes_list(obs_str: str) -> str:
    """Format list of Notes or ReturnedNotes."""
    if "notes=[]" in obs_str or "[]" in obs_str:
        return "No notes found."

    notes = _parse_notes(obs_str)

    if not notes:
        return "Notes loaded."

    lines = [f"{len(notes)} note(s):"]
    lines.append("-" * 40)

    for i, note in enumerate(notes[:5], 1):
        title = note.get("title") or "Untitled"
        content = _truncate(note.get("content") or "", 50)
        pinned = " [PINNED]" if note.get("pinned") == "True" else ""

        lines.append(f"{i}. {title}{pinned}")
        if content:
            lines.append(f"   {content}")
        lines.append("")

    if len(notes) > 5:
        lines.append(f"... and {len(notes) - 5} more notes")

    return "\n".join(lines)


def _format_note_detail(obs_str: str) -> str:
    """Format a single Note."""
    # Check if it's already formatted
    if "Title:" in obs_str and "Content:" in obs_str and not obs_str.startswith("Note("):
        return _truncate(obs_str, 500)

    title = _extract_field(obs_str, "title") or "Untitled"
    content = _extract_field(obs_str, "content") or ""
    pinned = _extract_field_any(obs_str, "pinned")
    created = _format_timestamp(_extract_field_any(obs_str, "created_at"))
    updated = _format_timestamp(_extract_field_any(obs_str, "updated_at"))

    lines = [f"Note: {title}"]
    if pinned == "True":
        lines.append("[PINNED]")
    lines.append("-" * 30)
    lines.append(_truncate(content, 300))
    lines.append("")
    lines.append(f"Created: {created}")
    lines.append(f"Updated: {updated}")

    return "\n".join(lines)


def _format_folder_list(obs_str: str) -> str:
    """Format list of folder names."""
    if "[]" in obs_str:
        return "No folders."
    return f"Folders: {obs_str}"


def _parse_notes(obs_str: str) -> list[dict[str, str | None]]:
    """Parse Note objects."""
    notes = []
    note_blocks = re.findall(r"Note\([^)]+(?:\([^)]*\)[^)]*)*\)", obs_str, re.DOTALL)

    for block in note_blocks:
        note = {
            "title": _extract_field(block, "title"),
            "content": _extract_field(block, "content"),
            "pinned": _extract_field_any(block, "pinned"),
        }
        notes.append(note)

    return notes


# ============================================================================
# Reminder Formatters
# ============================================================================


def _format_reminder_observation(action: str, obs_str: str, args: dict[str, Any]) -> str:
    """Format reminder app observations."""
    if action in ("list_all_reminders", "list_upcoming_reminders", "list_due_reminders"):
        return _format_reminders_list(obs_str)

    if action == "open_reminder":
        return _format_reminder_detail(obs_str)

    if action == "create_new":
        return "Creating new reminder..."

    if action == "delete":
        return "Reminder deleted."

    if action == "edit":
        return "Editing reminder..."

    if action.startswith("set_"):
        return _format_reminder_draft(obs_str)

    if action == "save":
        return "Reminder saved."

    if action == "cancel":
        return "Edit cancelled."

    return _truncate(obs_str, 300)


def _format_reminders_list(obs_str: str) -> str:
    """Format list of Reminders."""
    if "[]" in obs_str:
        return "No reminders."

    reminders = _parse_reminders(obs_str)

    if not reminders:
        return "Reminders loaded."

    lines = [f"{len(reminders)} reminder(s):"]
    lines.append("-" * 40)

    for i, rem in enumerate(reminders[:5], 1):
        title = rem.get("title", "Untitled")
        due = rem.get("due_datetime", "")

        lines.append(f"{i}. {title}")
        if due:
            lines.append(f"   Due: {due}")
        lines.append("")

    if len(reminders) > 5:
        lines.append(f"... and {len(reminders) - 5} more reminders")

    return "\n".join(lines)


def _format_reminder_detail(obs_str: str) -> str:
    """Format a single Reminder."""
    title = _extract_field(obs_str, "title") or "Untitled"
    due = _extract_field(obs_str, "due_datetime") or ""
    description = _extract_field(obs_str, "description") or ""
    rep_unit = _extract_field(obs_str, "repetition_unit")
    rep_value = _extract_field_any(obs_str, "repetition_value")

    lines = [f"Reminder: {title}"]
    lines.append("-" * 30)
    if due:
        lines.append(f"Due: {due}")
    if description:
        lines.append(f"Description: {_truncate(description, 100)}")
    if rep_unit and rep_unit != "None":
        lines.append(f"Repeats: Every {rep_value} {rep_unit}")

    return "\n".join(lines)


def _format_reminder_draft(obs_str: str) -> str:
    """Format ReminderDraft."""
    return "Reminder draft updated."


def _parse_reminders(obs_str: str) -> list[dict[str, str | None]]:
    """Parse Reminder objects."""
    reminders = []
    blocks = re.findall(r"Reminder\([^)]+\)", obs_str, re.DOTALL)

    for block in blocks:
        rem = {
            "title": _extract_field(block, "title"),
            "due_datetime": _extract_field(block, "due_datetime"),
        }
        reminders.append(rem)

    return reminders


# ============================================================================
# Cab Formatters
# ============================================================================


def _format_cab_observation(action: str, obs_str: str, args: dict[str, Any]) -> str:
    """Format cab app observations."""
    if action == "list_rides":
        return _format_rides_list(obs_str)

    if action == "get_ride_history":
        return _format_ride_history(obs_str)

    if action in ("open_current_ride", "get_quotation", "show_quotation", "order_ride"):
        return _format_ride_detail(obs_str)

    if action == "cancel_ride":
        return "Ride cancelled."

    if action == "list_service_types":
        return f"Service types: {obs_str}"

    return _truncate(obs_str, 300)


def _format_rides_list(obs_str: str) -> str:
    """Format list of Rides."""
    if "[]" in obs_str:
        return "No rides available."

    rides = _parse_rides(obs_str)

    if not rides:
        return "Rides loaded."

    lines = [f"{len(rides)} ride option(s):"]
    lines.append("-" * 40)

    for i, ride in enumerate(rides[:5], 1):
        service = ride.get("service_type", "Standard")
        price = ride.get("price", "")
        duration = ride.get("duration", "")

        lines.append(f"{i}. {service}")
        if price:
            lines.append(f"   Price: ${price}")
        if duration:
            lines.append(f"   Duration: {duration} min")
        lines.append("")

    return "\n".join(lines)


def _format_ride_history(obs_str: str) -> str:
    """Format ride history."""
    if "[]" in obs_str or "'rides': []" in obs_str:
        return "No ride history."

    rides = _parse_rides(obs_str)

    if not rides:
        return "Ride history loaded."

    lines = [f"Ride history ({len(rides)} trips):"]
    lines.append("-" * 40)

    for i, ride in enumerate(rides[:5], 1):
        start = ride.get("start_location", "")
        end = ride.get("end_location", "")
        price = ride.get("price", "")

        lines.append(f"{i}. {start} -> {end}")
        if price:
            lines.append(f"   Fare: ${price}")
        lines.append("")

    if len(rides) > 5:
        lines.append(f"... and {len(rides) - 5} more trips")

    return "\n".join(lines)


def _format_ride_detail(obs_str: str) -> str:
    """Format a single Ride."""
    service = _extract_field(obs_str, "service_type") or "Standard"
    start = _extract_field(obs_str, "start_location") or ""
    end = _extract_field(obs_str, "end_location") or ""
    price = _extract_field_any(obs_str, "price")
    duration = _extract_field_any(obs_str, "duration")
    status = _extract_field(obs_str, "status")
    distance = _extract_field_any(obs_str, "distance_km")

    lines = [f"Ride: {service}"]
    lines.append("-" * 30)
    if start and end:
        lines.append(f"Route: {start} -> {end}")
    if price and price != "None":
        lines.append(f"Price: ${price}")
    if duration and duration != "None":
        lines.append(f"Duration: {duration} min")
    if distance and distance != "None":
        lines.append(f"Distance: {distance} km")
    if status and status != "None":
        lines.append(f"Status: {status}")

    return "\n".join(lines)


def _parse_rides(obs_str: str) -> list[dict[str, str | None]]:
    """Parse Ride objects."""
    rides = []
    blocks = re.findall(r"Ride\([^)]+\)", obs_str, re.DOTALL)

    for block in blocks:
        ride = {
            "service_type": _extract_field(block, "service_type"),
            "price": _extract_field_any(block, "price"),
            "duration": _extract_field_any(block, "duration"),
            "start_location": _extract_field(block, "start_location"),
            "end_location": _extract_field(block, "end_location"),
        }
        rides.append(ride)

    return rides


# ============================================================================
# Apartment Formatters
# ============================================================================


def _format_apartment_observation(action: str, obs_str: str, args: dict[str, Any]) -> str:
    """Format apartment app observations."""
    if action in ("list_apartments", "search"):
        return _format_apartments_list(obs_str)

    if action in ("view_apartment", "open_favorites"):
        if "Apartment(" in obs_str:
            return _format_apartment_detail(obs_str)
        return _format_apartments_list(obs_str)

    if action == "open_search":
        return "Search page opened."

    if action == "save":
        return "Apartment saved to favorites."

    if action == "unsave":
        return "Apartment removed from favorites."

    return _truncate(obs_str, 300)


def _format_apartments_list(obs_str: str) -> str:
    """Format list of Apartments."""
    if "[]" in obs_str or "{}" in obs_str:
        return "No apartments found."

    apartments = _parse_apartments(obs_str)

    if not apartments:
        return "Apartments loaded."

    lines = [f"{len(apartments)} apartment(s):"]
    lines.append("-" * 40)

    for i, apt in enumerate(apartments[:5], 1):
        name = apt.get("name", "Unnamed")
        location = apt.get("location", "")
        price = apt.get("price", "")
        beds = apt.get("bedrooms", "")
        saved = " [SAVED]" if apt.get("saved") == "True" else ""

        lines.append(f"{i}. {name}{saved}")
        if location:
            lines.append(f"   Location: {location}")
        if price:
            lines.append(f"   Price: ${price}/month")
        if beds:
            lines.append(f"   Bedrooms: {beds}")
        lines.append("")

    if len(apartments) > 5:
        lines.append(f"... and {len(apartments) - 5} more listings")

    return "\n".join(lines)


def _format_apartment_detail(obs_str: str) -> str:  # noqa: C901
    """Format a single Apartment."""
    name = _extract_field(obs_str, "name") or "Unnamed"
    location = _extract_field(obs_str, "location") or ""
    price = _extract_field_any(obs_str, "price")
    beds = _extract_field_any(obs_str, "bedrooms")
    baths = _extract_field_any(obs_str, "bathrooms")
    sqft = _extract_field_any(obs_str, "square_footage")
    prop_type = _extract_field(obs_str, "property_type")
    furnished = _extract_field(obs_str, "furnished_status")
    pets = _extract_field(obs_str, "pet_policy")
    amenities = _extract_field(obs_str, "amenities")
    saved = _extract_field_any(obs_str, "saved")

    lines = [f"Apartment: {name}"]
    if saved == "True":
        lines.append("[SAVED]")
    lines.append("-" * 30)
    if location:
        lines.append(f"Location: {location}")
    if price:
        lines.append(f"Price: ${price}/month")
    if beds:
        lines.append(f"Bedrooms: {beds}")
    if baths:
        lines.append(f"Bathrooms: {baths}")
    if sqft:
        lines.append(f"Size: {sqft} sq ft")
    if prop_type and prop_type != "None":
        lines.append(f"Type: {prop_type}")
    if furnished and furnished != "None":
        lines.append(f"Furnished: {furnished}")
    if pets and pets != "None":
        lines.append(f"Pets: {pets}")
    if amenities and amenities != "None" and amenities != "[]":
        lines.append(f"Amenities: {_truncate(amenities, 60)}")

    return "\n".join(lines)


def _parse_apartments(obs_str: str) -> list[dict[str, str | None]]:
    """Parse Apartment objects."""
    apartments = []
    blocks = re.findall(r"Apartment\([^)]+(?:\([^)]*\)[^)]*)*\)", obs_str, re.DOTALL)

    for block in blocks:
        apt = {
            "name": _extract_field(block, "name"),
            "location": _extract_field(block, "location"),
            "price": _extract_field_any(block, "price"),
            "bedrooms": _extract_field_any(block, "bedrooms"),
            "saved": _extract_field_any(block, "saved"),
        }
        apartments.append(apt)

    return apartments


# ============================================================================
# Shopping Formatters
# ============================================================================


def _format_shopping_observation(action: str, obs_str: str, args: dict[str, Any]) -> str:
    """Format shopping app observations."""
    if action == "list_products":
        return _format_products_list(obs_str)

    if action in ("view_product", "view_variant"):
        return _format_product_detail(obs_str)

    if action == "view_cart":
        return _format_cart(obs_str)

    if action == "list_orders":
        return _format_orders_list(obs_str)

    if action in ("view_order",):
        return _format_order_detail(obs_str)

    if action == "add_to_cart":
        return "Added to cart."

    if action == "remove_item":
        return "Item removed from cart."

    if action == "checkout":
        return "Order placed successfully."

    return _truncate(obs_str, 300)


def _format_products_list(obs_str: str) -> str:
    """Format list of products."""
    if "'products': []" in obs_str or "[]" in obs_str:
        return "No products found."
    # Extract product count if available
    total_match = re.search(r"'total':\s*(\d+)", obs_str)
    total = total_match.group(1) if total_match else "several"
    return f"Showing {total} products."


def _format_product_detail(obs_str: str) -> str:
    """Format product detail."""
    name = _extract_field(obs_str, "name") or _extract_field(obs_str, "product_name") or "Product"
    price = _extract_field_any(obs_str, "price")

    lines = [f"Product: {name}"]
    if price:
        lines.append(f"Price: ${price}")
    return "\n".join(lines)


def _format_cart(obs_str: str) -> str:
    """Format shopping cart."""
    if "'items': []" in obs_str or "'items': {}" in obs_str:
        return "Cart is empty."
    total = _extract_field_any(obs_str, "total")
    if total:
        return f"Cart total: ${total}"
    return "Cart loaded."


def _format_orders_list(obs_str: str) -> str:
    """Format list of orders."""
    if "[]" in obs_str:
        return "No orders."
    return "Orders loaded."


def _format_order_detail(obs_str: str) -> str:
    """Format order detail."""
    order_id = _extract_field(obs_str, "order_id") or ""
    status = _extract_field(obs_str, "status") or ""
    total = _extract_field_any(obs_str, "total")

    lines = [f"Order: {order_id[:8]}..." if len(order_id) > 8 else f"Order: {order_id}"]
    if status:
        lines.append(f"Status: {status}")
    if total:
        lines.append(f"Total: ${total}")
    return "\n".join(lines)
