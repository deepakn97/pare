# Stateful Reminder App

`pas.apps.reminder.app.StatefulReminderApp` layers PAS navigation on top of the
Meta-ARE `ReminderApp`. It begins in the `ReminderList` state and transitions
into add, edit, or detail screens depending on which user tool completes.

---

## Navigation States

---

## ReminderList

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_reminders()` | `ReminderApp.get_all_reminders()` | List of reminders | Remains in `ReminderList` |
| `create_new()` | None | Indicator | → `AddReminder()` |
| `open_reminder(reminder_id)` | None | Indicator | → `ReminderDetail(reminder_id)` |

---

## AddReminder

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `save()` | `ReminderApp.add_reminder(...)` | Reminder ID | → `ReminderList()` |
| `cancel()` | None | `"cancel"` | Pops navigation stack via `go_back()` |

---

## ReminderDetail

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `get_reminder()` | None | Reminder object | Remains in `ReminderDetail` |
| `edit()` | None | Indicator | → `EditReminder(reminder_id)` |
| `delete()` | `ReminderApp.delete_reminder(...)` | Status | → `ReminderList()` or `go_back()` |
| `cancel()` | None | `"cancel"` | Pops navigation stack via `go_back()` |

---

## EditReminder

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `save()` | `update_reminder(...)` | Reminder ID | → `ReminderDetail(reminder_id)` |
| `cancel()` | None | `"cancel"` | Pops navigation stack via `go_back()` |

---

## Navigation Summary

- `ReminderList → AddReminder` via `create_new`
- `ReminderList → ReminderDetail` via `open_reminder`
- `AddReminder → ReminderList` via `save`
- `ReminderDetail → EditReminder` via `edit`
- `EditReminder → ReminderDetail` via `save`
- `cancel()` always pops navigation stack when available
- `delete()` returns to list or pops navigation stack
- `list_reminders()` keeps user in `ReminderList`

---

## Navigation Helpers

- `load_root_state()` resets app to `ReminderList`
- `set_current_state(...)` pushes a new state instance
- `go_back()` pops the navigation stack when available
