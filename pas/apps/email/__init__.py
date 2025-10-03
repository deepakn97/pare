"""Stateful email application package."""

from pas.apps.email.app import StatefulEmailApp
from pas.apps.email.states import ComposeEmail, EmailDetail, MailboxView

__all__ = [
    "StatefulEmailApp",
    "ComposeEmail",
    "EmailDetail",
    "MailboxView",
]
