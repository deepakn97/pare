from __future__ import annotations

NOTIFICATION_TEMPLATES = {
    "user": {
        "StatefulEmailApp": {
            "send_email_to_user_only": "New email from {{sender}}: {{subject}}\n{{content[:20]}}...",
            "send_email_to_user_with_id": "New email from {{sender}}: {{subject}}\n{{content[:20]}}...",
            "reply_to_email_from_user": "Reply from {{sender}}: {{content[:20]}}...",
            "create_and_add_email": "New email from {{sender}}: {{subject}}\n{{content[:20]}}...",
        },
        "StatefulMessagingApp": {
            "create_and_add_message": "New message from {{sender_id}} in {{conversation_id}}: {{content[:20]}}...",
            "create_group_conversation": "New group chat created with {{user_ids|join(', ')}}{% if title %} ({{title}}){% endif %}",
            "add_participant_to_conversation": "Added {{user_id}} to conversation {{conversation_id}}",
            "remove_participant_from_conversation": "Removed {{user_id}} from conversation {{conversation_id}}",
            "change_conversation_title": "Conversation {{conversation_id}} renamed to: {{title}}",
        },
        "StatefulCalendarApp": {
            "add_calendar_event_by_attendee": "New calendar event by {{who_add}}: {{title}} at {{start_datetime}}",
            "delete_calendar_event_by_attendee": "Calendar event {{event_id}} deleted by {{who_delete}}",
        },
        "StatefulShoppingApp": {
            "add_product": "New product added: {{name}}",
            "add_item_to_product": "New item added to product {{product_id}} (price={{price}}, available={{available}})",
            "update_item": "Item {{item_id}} updated{% if new_price is not none %} (new price={{new_price}}){% endif %}{% if new_availability is not none %} (available={{new_availability}}){% endif %}",
            "add_discount_code": "New discount code added for item {{item_id}}",
            "update_order_status": "Order {{order_id}} status updated to {{status}}",
            "cancel_order": "Order {{order_id}} cancelled",
        },
        "StatefulCabApp": {
            "cancel_ride": "Ride cancelled{% if who_cancel %} by {{who_cancel}}{% endif %}{% if message %}: {{message}}{% endif %}",
            "update_ride_status": "Ride status updated to {{status}}{% if message %}: {{message}}{% endif %}",
            "end_ride": "Ride completed",
        },
        "StatefulApartmentApp": {
            "add_new_apartment": "New apartment listed: {{name}} ({{location}}) - ${{price}}",
            "update_apartment": "Apartment {{apartment_id}} price updated to ${{new_price}}",
            "delete_apartment": "Apartment {{apartment_id}} removed",
        },
    },
    "agent": {
        "StatefulEmailApp": {
            "send_email_to_user_only": "New email from {{sender}}: {{subject}}\n\n{{content}}",
            "send_email_to_user_with_id": "New email from {{sender}}: {{subject}}\n\n{{content}}",
            "reply_to_email_from_user": "Reply from {{sender}} to email {{email_id}}:\n\n{{content}}",
            "create_and_add_email": "New email from {{sender}} to {{recipients|join(', ')}}: {{subject}}\n\n{{content}}",
        },
        "StatefulMessagingApp": {
            "create_and_add_message": "New message from {{sender_id}} in conversation {{conversation_id}}:\n{{content}}",
            "create_group_conversation": "Messaging update: new group conversation created\nParticipants: {{user_ids|join(', ')}}{% if title %}\nTitle: {{title}}{% endif %}",
            "add_participant_to_conversation": "Messaging update: participant added\nConversation: {{conversation_id}}\nUser added: {{user_id}}",
            "remove_participant_from_conversation": "Messaging update: participant removed\nConversation: {{conversation_id}}\nUser removed: {{user_id}}",
            "change_conversation_title": "Messaging update: conversation title changed\nConversation: {{conversation_id}}\nNew title: {{title}}",
        },
        "StatefulCalendarApp": {
            "add_calendar_event_by_attendee": "New calendar event added by {{who_add}}:\nTitle: {{title}}\nStart: {{start_datetime}}\nEnd: {{end_datetime}}{% if description %}\nDescription: {{description}}{% endif %}{% if location %}\nLocation: {{location}}{% endif %}{% if attendees %}\nAttendees: {{attendees|join(', ')}}{% endif %}",
            "delete_calendar_event_by_attendee": "Calendar event {{event_id}} deleted by {{who_delete}}",
        },
        "StatefulShoppingApp": {
            "add_product": "Inventory update: new product added\nName: {{name}}",
            "add_item_to_product": "Inventory update: new item added to product {{product_id}}\nItem price: {{price}}\nAvailable: {{available}}{% if options %}\nOptions: {{options}}{% endif %}",
            "update_item": "Inventory update: item {{item_id}} updated{% if new_price is not none %}\nNew price: {{new_price}}{% endif %}{% if new_availability is not none %}\nNew availability: {{new_availability}}{% endif %}",
            "add_discount_code": "Inventory update: discount code(s) added for item {{item_id}}{% if discount_code %}\n{% for code, pct in discount_code.items() %}- {{code}}: {{pct}}%{% endfor %}{% endif %}",
            "update_order_status": "Order update: {{order_id}}\nNew status: {{status}}",
            "cancel_order": "Order update: {{order_id}} cancelled",
        },
        "StatefulCabApp": {
            "cancel_ride": "Cab update: ride cancelled{% if who_cancel %}\nCancelled by: {{who_cancel}}{% endif %}{% if message %}\nMessage: {{message}}{% endif %}",
            "update_ride_status": "Cab update: ride status change\nNew status: {{status}}{% if message %}\nMessage: {{message}}{% endif %}",
            "end_ride": "Cab update: ride completed",
        },
        "StatefulApartmentApp": {
            "add_new_apartment": "New apartment listing added\nName: {{name}}\nLocation: {{location}}\nZip: {{zip_code}}\nPrice: {{price}}\nBedrooms: {{number_of_bedrooms}}\nBathrooms: {{number_of_bathrooms}}\nSq ft: {{square_footage}}{% if property_type %}\nProperty type: {{property_type}}{% endif %}{% if furnished_status %}\nFurnished: {{furnished_status}}{% endif %}{% if floor_level %}\nFloor: {{floor_level}}{% endif %}{% if pet_policy %}\nPet policy: {{pet_policy}}{% endif %}{% if lease_term %}\nLease term: {{lease_term}}{% endif %}{% if amenities %}\nAmenities: {{amenities|join(', ')}}{% endif %}",
            "update_apartment": "Apartment update: {{apartment_id}}\nNew price: {{new_price}}",
            "delete_apartment": "Apartment removed: {{apartment_id}}",
        },
    },
}
