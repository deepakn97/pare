# Stateful Email App

`pare.apps.email.app.StatefulEmailApp` pairs PARE navigation with the Meta-ARE `EmailClientV2`. It starts in `MailboxView("INBOX")` and pushes additional states for email detail and compose flows.

## Navigation States

### MailboxView

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_emails(offset: int = 0, limit: int = 10)` | `EmailClientV2.list_emails(folder_name=current_folder, offset=offset, limit=limit)` | `ReturnedEmails` dict with items and counts | Remains in `MailboxView` |
| `search_emails(query: str, min_date: Optional[str] = None, max_date: Optional[str] = None, limit: Optional[int] = 10)` | `EmailClientV2.search_emails(query=query, folder_name=current_folder)` followed by local UTC filtering | `list[Email]` obeying provided bounds | Remains in `MailboxView` |
| `open_email_by_id(email_id: str)` | `EmailClientV2.get_email_by_id(email_id=email_id, folder_name=current_folder)` | `Email` object | Completed event transitions to `EmailDetail(email_id, current_folder)` |
| `open_email_by_index(index: int)` | `EmailClientV2.get_email_by_index(idx=index, folder_name=current_folder)` | `Email` object | Completed event transitions to `EmailDetail` for the resolved id |
| `switch_folder(folder_name: str)` | Normalises folder, then `EmailClientV2.list_emails(folder_name=resolved)` | `ReturnedEmails` for target folder | Replaces current state with `MailboxView(folder_name)` |
| `start_compose()` | Emits sentinel string (metadata may include an optional `draft`) | Literal string `"compose_started"` | Completed event pushes `ComposeEmail` (blank draft when metadata absent) |

### EmailDetail

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `refresh()` | `EmailClientV2.get_email_by_id(email_id=current, folder_name=current_folder)` | Updated `Email` object | Remains in `EmailDetail` |
| `reply(content: str = "", attachment_paths: Optional[list[str]] = None)` | `EmailClientV2.reply_to_email(...)` | New email id created by the reply | Remains in `EmailDetail` |
| `forward(recipients: list[str])` | `EmailClientV2.forward_email(email_id=current, recipients=recipients, folder_name=current_folder)` | New forwarded email id | Remains in `EmailDetail` |
| `move(destination_folder: str)` | `EmailClientV2.move_email(email_id=current, source_folder_name=current_folder, dest_folder_name=resolved)` | Backend status string | On success pops back to previous state |
| `delete()` | `EmailClientV2.delete_email(email_id=current, folder_name=current_folder)` | Backend status string | On success pops back to previous state |
| `download_attachments(path_to_save: str)` | `EmailClientV2.download_attachments(email_id=current, folder_name=current_folder, path_to_save=path_to_save)` | `list[str]` of saved file paths | Remains in `EmailDetail` |
| `start_compose_reply()` | Uses cached email to build metadata | Dict with `draft` describing reply context | Completed event transitions to `ComposeEmail` |

### ComposeEmail

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `set_recipients(recipients: list[str])` | Draft mutation only | Dict `{"recipients": updated_list}` | Remains in `ComposeEmail` |
| `add_recipient(recipient: str)` | Draft mutation only (append) | Dict `{"recipients": updated_list}` | Remains in `ComposeEmail` |
| `set_cc(cc: list[str])` | Draft mutation only | Dict `{"cc": updated_list}` | Remains in `ComposeEmail` |
| `set_subject(subject: str)` | Draft mutation only | Dict `{"subject": subject}` | Remains in `ComposeEmail` |
| `set_body(body: str)` | Draft mutation only | Dict `{"body": body}` | Remains in `ComposeEmail` |
| `attach_file(attachment_path: str)` | Draft mutation only (append path) | Dict `{"attachments": updated_list}` | Remains in `ComposeEmail` |
| `send_composed_email()` | Reply drafts call `StatefulEmailApp.send_reply_from_draft`; new drafts call `EmailClientV2.send_email(...)` | Sent email id | Pops compose state and returns to previous view |
| `save_draft()` | `EmailClientV2.create_and_add_email(..., folder_name="DRAFT")` | Draft email id | Pops back to previous state |
| `discard_draft()` | Resets in-memory draft | String `"draft_discarded"` | Pops back to previous state |

## Navigation Helpers
- `go_back()` pops to the previous view when the navigation stack has history (e.g., from detail back to mailbox).
- Compose completion (`send_composed_email`, `save_draft`, `discard_draft`) and destructive detail operations (`delete`, `move`) automatically invoke the back stack so the caller lands on the prior screen.
