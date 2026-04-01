"""Navigation state implementations for the stateful email app."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from are.simulation.apps.email_client import Email, EmailFolderName, ReturnedEmails
from are.simulation.types import OperationType, disable_events

from pare.apps.core import AppState
from pare.apps.tool_decorators import pare_event_registered, user_tool

logger = logging.getLogger(__name__)


def _normalise_folder(folder: str | None) -> str:
    """Convert caller provided folder strings into canonical enum values."""
    if not folder:
        return EmailFolderName.INBOX.value
    try:
        return EmailFolderName[folder.upper()].value
    except KeyError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Unknown email folder {folder}") from exc


@dataclass
class ComposeDraft:
    """In-memory representation of an email draft during composition."""

    recipients: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)
    subject: str = ""
    body: str = ""
    attachments: list[str] = field(default_factory=list)
    reply_to: str | None = None
    reply_to_folder: str | None = None
    default_recipients: list[str] = field(default_factory=list)
    default_subject: str | None = None


class MailboxView(AppState):
    """Mailbox listing state exposing folder-scoped navigation actions."""

    def __init__(self, folder: str = EmailFolderName.INBOX.value) -> None:
        """Initialise the mailbox view with the provided folder."""
        super().__init__()
        self.folder = _normalise_folder(folder)

    def on_enter(self) -> None:
        """No-op hook; future implementations may pre-fetch folder metadata."""

    def on_exit(self) -> None:
        """No-op hook for symmetry with on_enter."""

    @user_tool()
    @pare_event_registered()
    def list_emails(self, offset: int = 0, limit: int = 10) -> ReturnedEmails:
        """List emails in the current folder with pagination support."""
        with disable_events():
            emails = self.app.list_emails(folder_name=self.folder, offset=offset, limit=limit)

        logger.debug(f"Listed emails: {emails.emails}")

        return emails

    @user_tool()
    @pare_event_registered()
    def search_emails(
        self, query: str, min_date: str | None = None, max_date: str | None = None, limit: int | None = 10
    ) -> list[Email]:
        """Search for emails within the current folder.

        min/max filters are applied client-side because the backend API does not
        expose them. Invalid date strings are ignored.
        """
        results = self.app.search_emails(query=query, folder_name=self.folder)

        def to_timestamp(date_str: str | None) -> float | None:
            if not date_str:
                return None
            try:
                return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).timestamp()
            except ValueError:
                return None

        min_ts = to_timestamp(min_date)
        max_ts = to_timestamp(max_date)

        filtered: list[Email] = []
        for email in results:
            if min_ts is not None and email.timestamp < min_ts:
                continue
            if max_ts is not None and email.timestamp > max_ts:
                continue
            filtered.append(email)

        if limit is not None and limit >= 0:
            return filtered[:limit]

        return filtered

    @user_tool()
    @pare_event_registered()
    def open_email_by_id(self, email_id: str) -> Email:
        """Open a specific email by id within the current folder."""
        with disable_events():
            return self.app.get_email_by_id(email_id=email_id, folder_name=self.folder)

    @user_tool()
    @pare_event_registered()
    def open_email_by_index(self, index: int) -> Email:
        """Open a specific email by index within the current folder."""
        with disable_events():
            return self.app.get_email_by_index(idx=index, folder_name=self.folder)

    @user_tool()
    @pare_event_registered()
    def switch_folder(self, folder_name: str) -> ReturnedEmails:
        """Switch to a different folder and return its contents."""
        target_folder = _normalise_folder(folder_name)
        with disable_events():
            return self.app.list_emails(folder_name=target_folder)

    @user_tool()
    @pare_event_registered()
    def start_compose(self) -> str:
        """Begin a new compose flow originating from the mailbox view."""
        return "compose_started"


class EmailDetail(AppState):
    """Email detail state allowing follow-up actions on a single email."""

    def __init__(self, email_id: str, folder_name: str = EmailFolderName.INBOX.value) -> None:
        """Bind the detail view to a specific email and folder."""
        super().__init__()
        self.email_id = email_id
        self.folder_name = _normalise_folder(folder_name)
        self._email: Email | None = None

    def on_enter(self) -> None:
        """Attempt to refresh cached email details on entry."""
        self._email = self.app.get_email_by_id(email_id=self.email_id, folder_name=self.folder_name)

    def on_exit(self) -> None:
        """Clear cached email data when leaving the detail view."""
        # Keep cached email so that go_back restores the state without requiring
        # a fresh fetch. The cache is refreshed on demand via refresh().

    @property
    def email(self) -> Email | None:
        """Return the cached email if available."""
        return self._email

    @user_tool()
    @pare_event_registered()
    def refresh(self) -> Email:
        """Fetch the latest version of the current email."""
        self._email = self.app.get_email_by_id(email_id=self.email_id, folder_name=self.folder_name)
        return self._email

    @user_tool()
    @pare_event_registered(operation_type=OperationType.WRITE)
    def reply(self, content: str = "", attachment_paths: list[str] | None = None) -> str:
        """Send a reply to the current email."""
        with disable_events():
            return self.app.reply_to_email(
                email_id=self.email_id, folder_name=self.folder_name, content=content, attachment_paths=attachment_paths
            )

    @user_tool()
    @pare_event_registered(operation_type=OperationType.WRITE)
    def forward(self, recipients: list[str]) -> str:
        """Forward the current email to new recipients."""
        with disable_events():
            return self.app.forward_email(email_id=self.email_id, recipients=recipients, folder_name=self.folder_name)

    @user_tool()
    @pare_event_registered(operation_type=OperationType.WRITE)
    def move(self, destination_folder: str) -> str:
        """Move the current email to a different folder."""
        with disable_events():
            return self.app.move_email(
                email_id=self.email_id,
                source_folder_name=self.folder_name,
                dest_folder_name=_normalise_folder(destination_folder),
            )

    @user_tool()
    @pare_event_registered(operation_type=OperationType.WRITE)
    def delete(self) -> str:
        """Delete the current email (moves it to trash)."""
        with disable_events():
            return self.app.delete_email(email_id=self.email_id, folder_name=self.folder_name)

    @user_tool()
    @pare_event_registered()
    def download_attachments(self, path_to_save: str) -> list[str]:
        """Download attachments from the current email to a path."""
        with disable_events():
            return self.app.download_attachments(
                email_id=self.email_id, folder_name=self.folder_name, path_to_save=path_to_save
            )

    @user_tool()
    @pare_event_registered()
    def start_compose_reply(self) -> dict[str, object]:
        """Return metadata required to seed a reply draft in compose view."""
        email = self.email
        if email is None:
            return {"draft": None}

        return {
            "draft": {
                "recipients": [email.sender],
                "subject": f"Re: {email.subject}",
                "body": "",
                "reply_to": email.email_id,
                "folder_name": self.folder_name,
            }
        }


class ComposeEmail(AppState):
    """Compose state exposing draft editing and submission tools."""

    def __init__(self, draft: ComposeDraft | None = None) -> None:
        """Initialise the compose state with an optional existing draft."""
        super().__init__()
        self.draft = draft or ComposeDraft()
        if not self.draft.default_recipients:
            self.draft.default_recipients = list(self.draft.recipients)
        if self.draft.default_subject is None:
            self.draft.default_subject = self.draft.subject

    def on_enter(self) -> None:
        """Reset cached tools to ensure latest draft mutations are reflected."""
        self._cached_tools = None

    def on_exit(self) -> None:
        """Clear cached tools and reset draft state."""
        self._cached_tools = None

    def _mark_dirty(self) -> None:
        """Utility to invalidate cached tools after draft mutation."""
        self._cached_tools = None

    @user_tool()
    @pare_event_registered()
    def set_recipients(self, recipients: list[str]) -> dict[str, object]:
        """Replace the draft recipients list."""
        self.draft.recipients = recipients
        self._mark_dirty()
        return {"recipients": self.draft.recipients}

    @user_tool()
    @pare_event_registered()
    def add_recipient(self, recipient: str) -> dict[str, object]:
        """Append a single recipient to the draft."""
        self.draft.recipients.append(recipient)
        self._mark_dirty()
        return {"recipients": self.draft.recipients}

    @user_tool()
    @pare_event_registered()
    def set_cc(self, cc: list[str]) -> dict[str, object]:
        """Replace the CC list for the draft."""
        self.draft.cc = cc
        self._mark_dirty()
        return {"cc": self.draft.cc}

    @user_tool()
    @pare_event_registered()
    def set_subject(self, subject: str) -> dict[str, object]:
        """Update the subject line for the draft."""
        self.draft.subject = subject
        return {"subject": self.draft.subject}

    @user_tool()
    @pare_event_registered()
    def set_body(self, body: str) -> dict[str, object]:
        """Update the body content for the draft."""
        self.draft.body = body
        return {"body": self.draft.body}

    @user_tool()
    @pare_event_registered()
    def attach_file(self, attachment_path: str) -> dict[str, object]:
        """Attach a file path to the draft."""
        self.draft.attachments.append(attachment_path)
        return {"attachments": list(self.draft.attachments)}

    @user_tool()
    @pare_event_registered(operation_type=OperationType.WRITE)
    def send_composed_email(self) -> str:
        """Send the draft using the underlying email client."""
        attachments = self.draft.attachments or None

        if self.draft.reply_to:
            return self.app.send_reply_from_draft(self.draft)

        return self.app.send_email(
            recipients=self.draft.recipients,
            subject=self.draft.subject,
            content=self.draft.body,
            cc=self.draft.cc,
            attachment_paths=attachments,
        )

    @user_tool()
    @pare_event_registered(operation_type=OperationType.WRITE)
    def save_draft(self) -> str:
        """Persist the draft into the DRAFT folder."""
        return self.app.create_and_add_email(
            sender=self.app.user_email,
            recipients=self.draft.recipients,
            subject=self.draft.subject,
            content=self.draft.body,
            folder_name=EmailFolderName.DRAFT.value,
        )

    @user_tool()
    @pare_event_registered(operation_type=OperationType.WRITE)
    def discard_draft(self) -> str:
        """Discard the current draft without sending."""
        self.draft = ComposeDraft()
        return "draft_discarded"
