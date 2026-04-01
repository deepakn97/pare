"""Stateful email application package."""

from __future__ import annotations

from pare.apps.email.app import StatefulEmailApp
from pare.apps.email.states import ComposeEmail, EmailDetail, MailboxView

__all__ = ["ComposeEmail", "EmailDetail", "MailboxView", "StatefulEmailApp"]
