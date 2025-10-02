"""Expected behaviour for the forthcoming StatefulEmailApp implementation."""

from __future__ import annotations

from collections.abc import Generator
import types

import pytest

from are.simulation.apps.email_client import Email, EmailFolderName
from are.simulation.types import Action, CompletedEvent, EventMetadata, EventType

from pas.apps.email.app import StatefulEmailApp
from pas.apps.email.states import ComposeEmail, EmailDetail, MailboxView


def make_completed_event(
    app: StatefulEmailApp,
    owner: object,
    function_name: str,
    args: dict | None = None,
    *,
    return_value: object | None = None,
) -> CompletedEvent:
    """Fabricate a CompletedEvent mirroring the output of user tool execution."""

    args = args or {}
    function = getattr(owner, function_name)
    action = Action(function=function, args=args, resolved_args=args, app=app)
    metadata = EventMetadata(return_value=return_value, completed=True)
    return CompletedEvent(event_type=EventType.USER, action=action, metadata=metadata)


@pytest.fixture
def email_app() -> Generator[StatefulEmailApp, None, None]:
    """Create a stateful email app primed with a sample message."""

    app = StatefulEmailApp(name="mail")
    sample_inbox_email = Email(
        sender="alice@example.com",
        recipients=[app.user_email],
        subject="Hello",
        content="Hi there",
        email_id="sample-email-id",
    )
    app.add_email(sample_inbox_email, EmailFolderName.INBOX)

    sample_sent_email = Email(
        sender="bob@example.com",
        recipients=[app.user_email],
        subject="Sent Mail",
        content="Follow up",
        email_id="sample-sent-email-id",
    )
    app.add_email(sample_sent_email, EmailFolderName.SENT)

    setattr(app, "_sample_email_inbox", sample_inbox_email)
    setattr(app, "_sample_email_sent", sample_sent_email)
    yield app


class TestInitialState:
    """Expected initialisation semantics."""

    def test_app_initialises_with_mailbox_view(self, email_app: StatefulEmailApp) -> None:
        """App should boot into an INBOX MailboxView with empty navigation stack."""
        assert isinstance(email_app.current_state, MailboxView)
        assert email_app.current_state.app is email_app
        assert email_app.current_state.folder == EmailFolderName.INBOX.value
        assert not email_app.navigation_stack


class TestStateTransitions:
    """State transition expectations once implementation lands."""

    def test_open_email_transitions_to_detail(self, email_app: StatefulEmailApp) -> None:
        sample_email: Email = getattr(email_app, "_sample_email_inbox")
        mailbox_state = email_app.current_state
        event = make_completed_event(
            email_app,
            mailbox_state,
            "open_email_by_id",
            {"email_id": sample_email.email_id},
            return_value=sample_email,
        )
        email_app.handle_state_transition(event)

        assert isinstance(email_app.current_state, EmailDetail)
        assert email_app.current_state.email_id == sample_email.email_id
        assert isinstance(email_app.navigation_stack[-1], MailboxView)

    def test_switch_folder_pushes_previous_state(self, email_app: StatefulEmailApp) -> None:
        mailbox_state = email_app.current_state
        event = make_completed_event(
            email_app,
            mailbox_state,
            "switch_folder",
            {"folder_name": "SENT"},
        )
        email_app.handle_state_transition(event)

        assert isinstance(email_app.current_state, MailboxView)
        assert email_app.current_state.folder == EmailFolderName.SENT.value
        assert isinstance(email_app.navigation_stack[-1], MailboxView)
        # Previous state should remain INBOX so go_back returns correctly
        assert email_app.navigation_stack[-1].folder == EmailFolderName.INBOX.value

    def test_go_back_returns_to_previous_folder(self, email_app: StatefulEmailApp) -> None:
        mailbox_state = email_app.current_state
        email_app.handle_state_transition(
            make_completed_event(
                email_app,
                mailbox_state,
                "switch_folder",
                {"folder_name": "SENT"},
            )
        )

        assert email_app.current_state.folder == EmailFolderName.SENT.value
        result = email_app.go_back()

        assert "MailboxView" in result
        assert isinstance(email_app.current_state, MailboxView)
        assert email_app.current_state.folder == EmailFolderName.INBOX.value

    def test_switch_folder_accepts_enum(self, email_app: StatefulEmailApp) -> None:
        mailbox_state = email_app.current_state
        email_app.handle_state_transition(
            make_completed_event(
                email_app,
                mailbox_state,
                "switch_folder",
                {"folder_name": EmailFolderName.SENT},
            )
        )

        assert isinstance(email_app.current_state, MailboxView)
        assert email_app.current_state.folder == EmailFolderName.SENT.value

    def test_search_emails_filters_and_respects_limit(
        self, email_app: StatefulEmailApp, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mailbox_state = email_app.current_state

        sample_old = Email(
            sender="old@example.com",
            recipients=[email_app.user_email],
            subject="Old",
            content="Old message",
        )
        sample_old.timestamp = 60.0

        sample_recent = Email(
            sender="recent@example.com",
            recipients=[email_app.user_email],
            subject="Recent",
            content="Recent message",
        )
        sample_recent.timestamp = 3600.0

        calls: dict[str, tuple[str, str]] = {}

        def fake_search(self, query: str, folder_name: str = "INBOX") -> list[Email]:
            calls["args"] = (query, folder_name)
            return [sample_old, sample_recent]

        monkeypatch.setattr(
            email_app,
            "search_emails",
            types.MethodType(fake_search, email_app),
        )

        results = mailbox_state.search_emails(
            query="message",
            min_date="1970-01-01 00:30:00",
            max_date="1970-01-01 02:00:00",
            limit=1,
        )

        assert calls["args"] == ("message", EmailFolderName.INBOX.value)
        assert results == [sample_recent]

    def test_open_email_respects_current_folder(self, email_app: StatefulEmailApp) -> None:
        mailbox_state = email_app.current_state
        email_app.handle_state_transition(
            make_completed_event(
                email_app,
                mailbox_state,
                "switch_folder",
                {"folder_name": "SENT"},
            )
        )

        sent_mailbox_state = email_app.current_state
        sample_email: Email = getattr(email_app, "_sample_email_sent")
        event = make_completed_event(
            email_app,
            sent_mailbox_state,
            "open_email_by_id",
            {"email_id": sample_email.email_id},
            return_value=sample_email,
        )
        email_app.handle_state_transition(event)

        detail_state = email_app.current_state
        assert isinstance(detail_state, EmailDetail)
        assert detail_state.folder_name == EmailFolderName.SENT.value
        assert isinstance(email_app.navigation_stack[-1], MailboxView)


class TestComposeFlow:
    """Compose state management expectations."""

    def test_start_compose_enters_compose_state(self, email_app: StatefulEmailApp) -> None:
        mailbox_state = email_app.current_state
        event = make_completed_event(email_app, mailbox_state, "start_compose")
        email_app.handle_state_transition(event)

        assert isinstance(email_app.current_state, ComposeEmail)
        assert email_app.current_state.draft.recipients == []

    def test_send_compose_returns_to_previous_state(self, email_app: StatefulEmailApp) -> None:
        mailbox_state = email_app.current_state
        email_app.handle_state_transition(
            make_completed_event(email_app, mailbox_state, "start_compose")
        )
        compose_state = email_app.current_state
        compose_state.draft.recipients.append("a@example.com")
        sent_folder = email_app.folders[EmailFolderName.SENT]
        before = len(sent_folder.emails)

        result = compose_state.send_composed_email()
        email_app.handle_state_transition(
            make_completed_event(
                email_app,
                compose_state,
                "send_composed_email",
                return_value=result,
            )
        )

        assert not isinstance(email_app.current_state, ComposeEmail)
        assert not email_app.navigation_stack or not isinstance(email_app.navigation_stack[-1], ComposeEmail)
        assert len(sent_folder.emails) == before + 1


class TestToolFiltering:
    """Confirm state-specific user tools after implementation."""

    def test_mailbox_view_user_tools(self, email_app: StatefulEmailApp) -> None:
        tools = email_app.get_user_tools()
        names = {tool.name for tool in tools}
        assert any("list_emails" in name for name in names)
        assert any("open_email_by_id" in name for name in names)
        assert any("start_compose" in name for name in names)
        assert not any("send_composed_email" in name for name in names)

    def test_compose_user_tools(self, email_app: StatefulEmailApp) -> None:
        mailbox_state = email_app.current_state
        email_app.handle_state_transition(
            make_completed_event(email_app, mailbox_state, "start_compose")
        )
        tools = email_app.get_user_tools()
        names = {tool.name for tool in tools}
        assert any("send_composed_email" in name for name in names)
        assert not any("list_emails" in name for name in names)
        assert any("go_back" in name for name in names)

    def test_reply_flow_preserves_custom_fields(self, email_app: StatefulEmailApp) -> None:
        mailbox_state = email_app.current_state
        sample_email: Email = getattr(email_app, "_sample_email_inbox")
        email_app.handle_state_transition(
            make_completed_event(
                email_app,
                mailbox_state,
                "open_email_by_id",
                {"email_id": sample_email.email_id},
                return_value=sample_email,
            )
        )

        detail_state = email_app.current_state
        email_app.handle_state_transition(
            make_completed_event(
                email_app,
                detail_state,
                "start_compose_reply",
                return_value={
                    "draft": {
                        "recipients": [sample_email.sender],
                        "subject": f"Re: {sample_email.subject}",
                        "body": "",
                        "reply_to": sample_email.email_id,
                        "folder_name": EmailFolderName.INBOX.value,
                    }
                },
            )
        )

        compose_state = email_app.current_state
        assert isinstance(compose_state, ComposeEmail)

        compose_state.set_recipients(["charlie@example.com", "dana@example.com"])
        compose_state.set_cc(["eve@example.com"])
        compose_state.set_subject("Custom Subject")
        compose_state.set_body("Thanks for the update!")

        sent_folder = email_app.folders[EmailFolderName.SENT]
        before = len(sent_folder.emails)

        result = compose_state.send_composed_email()
        email_app.handle_state_transition(
            make_completed_event(
                email_app,
                compose_state,
                "send_composed_email",
                return_value=result,
            )
        )

        assert len(sent_folder.emails) == before + 1
        sent_email = sent_folder.emails[0]
        assert sent_email.recipients == ["charlie@example.com", "dana@example.com"]
        assert sent_email.cc == ["eve@example.com"]
        assert sent_email.subject == "Custom Subject"
        assert sent_email.content == "Thanks for the update!"
        assert sent_email.parent_id == sample_email.email_id

    def test_reply_flow_repeat_after_back(self, email_app: StatefulEmailApp) -> None:
        mailbox_state = email_app.current_state
        sample_email: Email = getattr(email_app, "_sample_email_inbox")
        email_app.handle_state_transition(
            make_completed_event(
                email_app,
                mailbox_state,
                "open_email_by_id",
                {"email_id": sample_email.email_id},
                return_value=sample_email,
            )
        )

        detail_state = email_app.current_state
        email_app.handle_state_transition(
            make_completed_event(
                email_app,
                detail_state,
                "start_compose_reply",
                return_value={
                    "draft": {
                        "recipients": [sample_email.sender],
                        "subject": f"Re: {sample_email.subject}",
                        "body": "",
                        "reply_to": sample_email.email_id,
                        "folder_name": EmailFolderName.INBOX.value,
                    }
                },
            )
        )

        compose_state = email_app.current_state
        assert isinstance(compose_state, ComposeEmail)
        result = compose_state.send_composed_email()
        email_app.handle_state_transition(
            make_completed_event(
                email_app,
                compose_state,
                "send_composed_email",
                return_value=result,
            )
        )

        # back to detail state (go_back triggered)
        detail_state = email_app.current_state
        assert isinstance(detail_state, EmailDetail)
        email_app.handle_state_transition(
            make_completed_event(
                email_app,
                detail_state,
                "start_compose_reply",
                return_value={
                    "draft": {
                        "recipients": [sample_email.sender],
                        "subject": f"Re: {sample_email.subject}",
                        "body": "",
                        "reply_to": sample_email.email_id,
                        "folder_name": EmailFolderName.INBOX.value,
                    }
                },
            )
        )

        second_compose_state = email_app.current_state
        assert isinstance(second_compose_state, ComposeEmail)
        assert second_compose_state.draft.reply_to == sample_email.email_id

    def test_forward_uses_supported_kwargs(
        self, email_app: StatefulEmailApp, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mailbox_state = email_app.current_state
        sample_email: Email = getattr(email_app, "_sample_email_inbox")
        email_app.handle_state_transition(
            make_completed_event(
                email_app,
                mailbox_state,
                "open_email_by_id",
                {"email_id": sample_email.email_id},
                return_value=sample_email,
            )
        )

        detail_state = email_app.current_state
        assert isinstance(detail_state, EmailDetail)

        called: dict[str, tuple] = {}

        def fake_forward(self, email_id: str, recipients: list[str] | None = None, folder_name: str = "INBOX") -> str:
            called["args"] = (email_id, tuple(recipients or []), folder_name)
            return "forwarded"

        monkeypatch.setattr(email_app, "forward_email", types.MethodType(fake_forward, email_app))

        result = detail_state.forward(["target@example.com"])

        assert result == "forwarded"
        assert called["args"] == (
            sample_email.email_id,
            ("target@example.com",),
            EmailFolderName.INBOX.value,
        )

    def test_reply_flow_attachments_use_helper(self, email_app: StatefulEmailApp, monkeypatch: pytest.MonkeyPatch) -> None:
        mailbox_state = email_app.current_state
        sample_email: Email = getattr(email_app, "_sample_email_inbox")
        email_app.handle_state_transition(
            make_completed_event(
                email_app,
                mailbox_state,
                "open_email_by_id",
                {"email_id": sample_email.email_id},
                return_value=sample_email,
            )
        )

        detail_state = email_app.current_state
        email_app.handle_state_transition(
            make_completed_event(
                email_app,
                detail_state,
                "start_compose_reply",
                return_value={
                    "draft": {
                        "recipients": [sample_email.sender],
                        "subject": f"Re: {sample_email.subject}",
                        "body": "",
                        "reply_to": sample_email.email_id,
                        "folder_name": EmailFolderName.INBOX.value,
                    }
                },
            )
        )

        compose_state = email_app.current_state
        assert isinstance(compose_state, ComposeEmail)

        compose_state.attach_file("Downloads/foo.txt")

        called: list[str] = []

        def fake_add_attachment(email, attachment_path):  # type: ignore[override]
            called.append(attachment_path)

        monkeypatch.setattr(email_app, "add_attachment", fake_add_attachment)

        result = compose_state.send_composed_email()
        email_app.handle_state_transition(
            make_completed_event(
                email_app,
                compose_state,
                "send_composed_email",
                return_value=result,
            )
        )

        assert "Downloads/foo.txt" in called
