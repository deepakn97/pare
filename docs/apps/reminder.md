# Stateful Reminder App

`pare.apps.reminder.app.StatefulReminderApp` extends the Meta-ARE `ReminderApp`
with PARE navigation support.
It launches in `ReminderList` and transitions between list, detail,
and edit flows based on completed reminder backend operations.

---

## State Transition Diagram

```text
                                ┌─────────────────────────────────────┐
                                │          ReminderList               │
                                │          (ROOT STATE)               │
                                │                                     │
                                │ ○ list_all_reminders                │
                                │ ○ list_upcoming_reminders           │
                                │ ○ list_due_reminders                │
                                └─────────────────────────────────────┘
                                      │                    │
                                      │ open_reminder      │ create_new
                                      ▼                    ▼
           ┌─────────────────────────────────────┐    ┌─────────────────────────────────────┐
           │          ReminderDetail             │    │          EditReminder               │
           │          (reminder_id)              │    │          (reminder_id=None)         │
           │                                     │    │                                     │
           │ + go_back (from StatefulApp)        │    │ ○ set_title                         │
           └─────────────────────────────────────┘    │ ○ set_description                   │
                  │        │                          │ ○ set_due_datetime                  │
                  │        │                          │ ○ set_repetition                    │
            edit  │        │ delete                   │ + go_back (from StatefulApp)        │
                  │        │                          └─────────────────────────────────────┘
                  ▼        ▼                                 │            │
           ┌─────────────────────────────────────┐      save │            │ cancel
           │          EditReminder               │           │            │
           │          (reminder_id)              │           ▼            ▼
           │                                     │    ┌─────────────────────────────────────┐
           │ ○ set_title                         │    │  ReminderDetail (new ID)            │
           │ ○ set_description                   │    │         OR                          │
           │ ○ set_due_datetime                  │    │  ReminderList (if cancel & new)     │
           │ ○ set_repetition                    │    └─────────────────────────────────────┘
           │ + go_back (from StatefulApp)        │
           └─────────────────────────────────────┘
                  │            │
             save │            │ cancel
                  ▼            ▼
           ┌─────────────────────────────────────┐
           │  ReminderDetail (same reminder_id)  │
           └─────────────────────────────────────┘
```

**Legend**: `○` = self-loop (no state change), `+` = inherited from StatefulApp

---

## Navigation States

---

### ReminderList

Root state showing the full list of reminders.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_all_reminders()` | `ReminderApp.get_all_reminders()` | `list[Reminder]` | Remains in `ReminderList` |
| `list_upcoming_reminders()` | `ReminderApp.get_all_reminders()` (filtered) | `list[Reminder]` upcoming | Remains in `ReminderList` |
| `list_due_reminders()` | `ReminderApp.get_due_reminders()` | `list[Reminder]` due | Remains in `ReminderList` |
| `open_reminder(reminder_id)` | `get_reminder_with_id(reminder_id)` | `Reminder` object | → `ReminderDetail(reminder_id)` |
| `create_new()` | — | `ReminderDraft` (empty) | → `EditReminder(reminder_id=None)` |

---

### ReminderDetail

State displaying full details of a single reminder.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `edit()` | — | `str` reminder ID | → `EditReminder(reminder_id)` |
| `delete()` | `ReminderApp.delete_reminder(reminder_id)` | `str` deleted ID | → `ReminderList` (stack cleared) |

**Note**: `go_back()` is available via `StatefulApp` when navigation history exists.

---

### EditReminder

Unified wizard state for both creating new reminders and editing existing ones.

- When `reminder_id=None`: Creating a new reminder (draft starts empty)
- When `reminder_id` is set: Editing existing reminder (draft populated via `on_enter`)

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `set_title(title)` | — | `ReminderDraft` | Remains in `EditReminder` |
| `set_description(description)` | — | `ReminderDraft` | Remains in `EditReminder` |
| `set_due_datetime(due_datetime)` | — | `ReminderDraft` | Remains in `EditReminder` |
| `set_repetition(unit, value=None)` | — | `ReminderDraft` | Remains in `EditReminder` |
| `save()` | `add_reminder(...)` or `update_reminder(...)` | `str` reminder ID | → `ReminderDetail(saved_id)` |
| `cancel()` | — | `str` message | → `ReminderDetail(original_id)` or `ReminderList` |

**Save behavior**:

- New reminder (`reminder_id=None`): Calls `ReminderApp.add_reminder()`, transitions to `ReminderDetail` with new ID
- Existing reminder: Calls `StatefulReminderApp.update_reminder()`, transitions to `ReminderDetail` with same ID

**Cancel behavior**:

- From edit mode (`reminder_id` set): Returns to `ReminderDetail(original_id)`
- From create mode (`reminder_id=None`): Returns to `ReminderList` (stack cleared)

**Note**: `go_back()` is available via `StatefulApp` when navigation history exists.

---

## Navigation Helpers

- Navigation transitions are handled in `StatefulReminderApp.handle_state_transition`
  based on the completed backend tool name.
- `open_reminder` always transitions to `ReminderDetail` with the provided `reminder_id`.
- `create_new` transitions to `EditReminder` with `reminder_id=None`.
- `edit` transitions to `EditReminder` with the current `reminder_id`.
- `delete` clears the navigation stack and returns to `ReminderList` (root state).
- `save` transitions to `ReminderDetail` with the saved reminder ID.
- `cancel` behavior depends on context:
  - From edit mode: Returns to `ReminderDetail` with original ID
  - From create mode: Clears stack and returns to `ReminderList`
- `go_back()` is inherited from `StatefulApp` and pops to the previous screen when navigation history exists.

---

## Summary Table

| State | Context | Transitions Out | Self-Loops |
|-------|---------|-----------------|------------|
| **ReminderList** | (none) | `open_reminder` → Detail, `create_new` → Edit(None) | `list_all_reminders`, `list_upcoming_reminders`, `list_due_reminders` |
| **ReminderDetail** | reminder_id | `edit` → Edit(id), `delete` → List (root) | (none) |
| **EditReminder** | reminder_id (optional), draft | `save` → Detail(id), `cancel` → Detail or List | `set_title`, `set_description`, `set_due_datetime`, `set_repetition` |
