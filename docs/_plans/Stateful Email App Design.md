# Stateful Email App Design

## Motivation
- Extend Meta-ARE `EmailClientV2` with navigation state semantics so user agents experience a realistic mobile email workflow.
- Reuse existing PAS abstractions (`AppState`, `StatefulApp`, `StateAwareEnvironmentWrapper`) to manage view-specific tool exposure and navigation history.
- Support upcoming proactive agent research scenarios focused on email triage, drafting, and follow-up.

## Architecture Summary
- `StatefulEmailApp(StatefulApp, EmailClientV2)` mixes the Meta-ARE email backend with PAS navigation infrastructure.
- Navigation states live in `pas.apps.email.states` and model distinct screens:
  - `MailboxView`: folder listing view (INBOX/SENT/DRAFT/TRASH).
  - `EmailDetail`: email detail view for a specific message.
- `ComposeEmail`: compose/reply/forward flow; maintains transient draft data.
  - Future: `FolderOverview` if multi-account or label browsing is required.
- `StateAwareEnvironmentWrapper` already dispatches completed events to `handle_state_transition`; email app hooks into this to realize `T(s,a) -> s'` transitions.
- `tests/test_email_states.py` will contain behavioural tests covering state initialization, transitions, navigation stack semantics, and state-specific tool exposure.

## State Definitions & User Tools
### MailboxView
Represents paginated email listing for a folder.

Context: `folder` (default INBOX), optional pagination/search params stored on the state for future enhancements.

User tools (delegating to `EmailClientV2`):
- `list_emails(folder_name: str = self.folder, offset: int = 0, limit: int = 10)`
- `search_emails(query: str, folder_name: str | None = None)` (auto uses current folder when omitted)
  - Optional date/limit filters are handled client-side since the backend API only accepts `query` and `folder_name`.
- `open_email_by_id(email_id: str)`
- `open_email_by_index(index: int)`
- `switch_folder(folder_name: str)` (triggers new `MailboxView` state)
- `start_compose()` (transitions to `ComposeEmail` with empty draft)

### EmailDetail
Represents viewing a single email in a folder.

Context: `folder_name`, `email_id` cached for subsequent actions.

User tools:
- `refresh()` (re-fetch email data via `get_email_by_id`)
- `reply(content: str = "", attachment_paths: list[str] | None = None)`
- `forward(recipients: list[str])`
- `move(dest_folder: str)`
- `delete()`
- `download_attachments(path_to_save: str)`
- Navigation helpers: `open_adjacent_email(index_delta: int)` (optional stretch), `start_compose_reply()` bridging to compose state pre-filled

### ComposeEmail
Represents the compose/reply editor.

Context: `ComposeDraft` dataclass (recipients, cc, subject, body, attachments, reply_metadata).

User tools:
- `set_recipients`, `add_recipient`, `set_cc`
- `set_subject`, `set_body`
- `attach_file(path: str)` using `EmailClientV2.add_attachment`
- `send()` delegates to `send_email` or constructs a threaded reply preserving edited recipients/cc/subject (our user tools expose editing, but the native `reply_to_email` ignores those fields), then clears draft and pops state
- `save_to_drafts()` delegates to `create_and_add_email` with folder `DRAFT`
- `discard()` simply pops state and drops draft

## Transition Logic (`handle_state_transition`)
- `open_email_by_id`/`open_email_by_index` ⇒ instantiate `EmailDetail` using resolved email ID.
  - `switch_folder` ⇒ new `MailboxView` with selected folder.
  - `start_compose` ⇒ `ComposeEmail` with empty draft context.
  - `start_compose_reply` / `start_compose_forward` from detail state ⇒ `ComposeEmail` seeded with metadata for reply/forward flows; quick `reply`/`forward` methods stay within detail.
  - `send` / `save_draft` / `discard_draft` inside compose ⇒ operation succeeds then `go_back()` restores prior state.
  - `delete` / `move` within detail ⇒ after mutation the app returns to the previous state (typically the mailbox view).

## Testing Strategy
- `tests/test_email_states.py` mirrors the messaging suite.
- Coverage targets:
  1. **Initialization**: app starts in INBOX `MailboxView`, navigation stack empty.
  2. **Folder transitions**: `switch_folder` pushes old state to stack, updates current state.
  3. **Email open**: invoking `open_email_by_id` transitions to `EmailDetail`, stack preserves previous `MailboxView`.
  4. **Go back**: `go_back` returns to last state, removing stack frames as expected.
  5. **Compose flow**: `start_compose` → `ComposeEmail`; send/save/discard returns to previous state.
  6. **Tool filtering**: ensure each state exposes only relevant user tools (mailbox lacks send, compose lacks list, etc.).
  7. **Late binding**: states initially unbound; after `set_current_state` they share app context.
  8. **State-conditional transitions**: verify `handle_state_transition` respects both state and action.

## Implementation Notes
- Introduce package `pas.apps.email` with `__init__.py`, `app.py`, `states.py`.
- Shared enums/utility: use `EmailFolderName` from Meta-ARE; avoid duplicating dataclasses.
- Compose draft attachments: prefer delegating to `EmailClientV2.add_attachment` when sandbox FS is available, fallback to base64 file read.
- Ensure state classes only touch `self.app` after binding; rely on `bind_to_app` in `StatefulApp.set_current_state`.
- Keep return payloads JSON-friendly for event logging.
- Document state graph in docstring for easier visualisation once implemented.

## Open Questions
- Should reply/forward actions transition to compose state or remain synchronous? For MVP, `EmailDetail.reply` will call underlying API directly (quick reply). We can revisit for interactive editing.
- Attachment handling in compose state may require FS protocols; tests will mock or stub as needed.
- Future enhancements: multi-account, labels, background sync events from environment.

## Timeline
1. Draft design + expectations (done).
2. Implement states, transition handler, and user tools (done).
3. Maintain docs/tests as new features are added.
