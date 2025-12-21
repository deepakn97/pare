# Stateful Reminder App

`pas.apps.reminder.app.StatefulReminderApp` extends the Meta-ARE `ReminderApp`
with PAS navigation support.
It launches in `ReminderList` and transitions between list, detail,
add, and edit flows based on completed reminder backend operations.

---

## Navigation States

---

### ReminderList

State showing the full list of reminders.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_reminders()` | `ReminderApp.get_all_reminders()` | `list[object]` reminders | Remains in `ReminderList` |
| `open_reminder(reminder_id)` | — | Payload containing reminder ID | → `ReminderDetail(reminder_id)` |
| `create_new()` | — | Navigation marker | → `AddReminder` |

---

### ReminderDetail

State displaying full details of a single reminder.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `get_reminder()` | Reads from `ReminderApp.reminders` | Reminder object | Remains in `ReminderDetail` |
| `edit()` | — | Payload with reminder ID | → `EditReminder(reminder_id)` |
| `delete()` | `ReminderApp.delete_reminder(reminder_id)` | Deleted reminder ID | → previous state |
| `go_back()` | — | Navigation directive `"back"` | → previous state |

---

### AddReminder

Wizard state for creating a new reminder using a draft container.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `set_title(title)` | — | Updated title | Remains in `AddReminder` |
| `set_description(description)` | — | Updated description | Remains in `AddReminder` |
| `set_due_datetime(due_datetime)` | — | Updated datetime | Remains in `AddReminder` |
| `set_repetition(unit, value=None)` | — | Updated repetition info | Remains in `AddReminder` |
| `save()` | `ReminderApp.add_reminder(...)` | Created reminder ID | → previous state |
| `cancel()` | — | Navigation directive `"cancel"` | → previous state |

---

### EditReminder

Wizard state for editing an existing reminder.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `set_title(title)` | — | Updated title | Remains in `EditReminder` |
| `set_description(description)` | — | Updated description | Remains in `EditReminder` |
| `set_due_datetime(due_datetime)` | — | Updated datetime | Remains in `EditReminder` |
| `set_repetition(unit, value=None)` | — | Updated repetition info | Remains in `EditReminder` |
| `save()` | `ReminderApp.update_reminder(...)` | Reminder ID | → previous state |
| `cancel()` | — | Navigation directive `"cancel"` | → previous state |

---

## Navigation Helpers

- Navigation transitions are handled in
  `StatefulReminderApp.handle_state_transition`
  based on the completed backend tool name.
- `open_reminder` always transitions into `ReminderDetail`
  using the provided `reminder_id`.
- `create_new` transitions into the `AddReminder` wizard.
- `edit` transitions into the `EditReminder` wizard.
- `save`, `delete`, `cancel`, and `"back"` signals always trigger `go_back()`
  to return to the previous navigation state.
- `go_back()` appears automatically when navigation history exists and pops
  to the prior screen.
