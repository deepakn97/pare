from __future__ import annotations

NOTIFICATION_TEMPLATES = {
    "user": {
        "StatefulEmailApp": {
            "send_email_to_user_only": "New email from {{sender}}: {{subject}}\n{{content[:20]}}...",
            "reply_to_email_from_user": "Reply from {{sender}}: {{content[:20]}}...",
            "create_and_add_email": "New email from {{sender}}: {{subject}}\n{{content[:20]}}...",
        },
        "StatefulMessagingApp": {
            "create_and_add_message": "New message from {{sender_id}} in {{conversation_id}}: {{content[:20]}}...",
        },
        "StatefulCalendarApp": {
            "add_calendar_event_by_attendee": "New calendar event by {{who_add}}: {{title}} at {{start_datetime}}",
            "delete_calendar_event_by_attendee": "Calendar event {{event_id}} deleted by {{who_delete}}",
        },
    },
    "agent": {
        "StatefulEmailApp": {
            "send_email_to_user_only": "New email from {{sender}}: {{subject}}\n\n{{content}}",
            "reply_to_email_from_user": "Reply from {{sender}} to email {{email_id}}:\n\n{{content}}",
            "create_and_add_email": "New email from {{sender}} to {{recipients|join(', ')}}: {{subject}}\n\n{{content}}",
        },
        "StatefulMessagingApp": {
            "create_and_add_message": "New message from {{sender_id}} in conversation {{conversation_id}}:\n{{content}}",
        },
        "StatefulCalendarApp": {
            "add_calendar_event_by_attendee": "New calendar event added by {{who_add}}:\nTitle: {{title}}\nStart: {{start_datetime}}\nEnd: {{end_datetime}}{% if description %}\nDescription: {{description}}{% endif %}{% if location %}\nLocation: {{location}}{% endif %}{% if attendees %}\nAttendees: {{attendees|join(', ')}}{% endif %}",
            "delete_calendar_event_by_attendee": "Calendar event {{event_id}} deleted by {{who_delete}}",
        },
    },
}
