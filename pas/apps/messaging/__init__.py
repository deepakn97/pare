"""Stateful messaging application package."""

from __future__ import annotations

from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.messaging.states import ConversationList, ConversationOpened

# Optional alias for convenience
# Allows: from pas.apps.messaging import MessagingApp
MessagingApp = StatefulMessagingApp

__all__ = [
    "ConversationList",
    "ConversationOpened",
    "StatefulMessagingApp",
    "MessagingApp",
]
