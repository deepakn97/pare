"""Stateful email application package."""

from __future__ import annotations

from pas.apps.email.app import StatefulEmailApp
from pas.apps.email.states import ComposeEmail, EmailDetail, MailboxView

__all__ = ["ComposeEmail", "EmailDetail", "MailboxView", "StatefulEmailApp"]
