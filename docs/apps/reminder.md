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
| `get_all_reminders()` | `ReminderApp.get_all_reminders()` | List of reminders | Remains in `ReminderList` |
| `create_new()` | None | Indicator | Completed event transitions to `AddReminder()` |
| `view_detail(reminder_id)` | `ReminderApp.get_reminder_details(...)` | Reminder object | Completed event transitions to `ReminderDetail(reminder_id)` |
| `delete_reminder(reminder_id)` | `ReminderApp.delete_reminder(...)` | Status string | Completed event transitions to `ReminderList()` or via `go_back()` |

---

## AddReminder

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `add_reminder(...)` | `ReminderApp.add_reminder(...)` | Reminder ID | Completed event transitions to `ReminderList()` |
| `cancel()` | None | Indicator | No navigation change (returns to previous state) |

---

## ReminderDetail

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `get_reminder_details(reminder_id)` | `ReminderApp.get_reminder_details(...)` | Reminder object | Remains in `ReminderDetail` |
| `edit(reminder_id)` | None | Indicator | Completed event transitions to `EditReminder(reminder_id)` |
| `delete_reminder(reminder_id)` | `ReminderApp.delete_reminder(...)` | Status string | Completed event transitions to `ReminderList()` or via navigation stack |
| `cancel()` | None | Indicator | No navigation change (returns to previous state) |

---

## EditReminder

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `update_reminder(...)` | `ReminderApp.update_reminder(...)` | Reminder ID | Completed event transitions to `ReminderDetail(reminder_id)` |
| `cancel()` | None | Indicator | No navigation change (returns to previous state) |

---

## Navigation Summary

- `ReminderList → AddReminder` via `create_new`
- `ReminderList → ReminderDetail` via `view_detail`
- `AddReminder → ReminderList` via `add_reminder`
- `ReminderDetail → EditReminder` via `edit`
- `EditReminder → ReminderDetail` via `update_reminder`
- `EditReminder → previous` via `cancel`
- `ReminderDetail → previous` via `cancel`
- `delete_reminder` returns to list or pops navigation stack
- `get_all_reminders` keeps user in `ReminderList`

---

## Navigation Helpers

- `load_root_state()` resets app to `ReminderList`
- `set_current_state(...)` pushes a new state instance
- `go_back()` returns to previous state when available
