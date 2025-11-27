"""
Stateful Reminder App
=====================

`pas.apps.reminder.app.StatefulReminderApp` layers PAS navigation on top of the
Meta-ARE `ReminderApp`. It starts in the `ReminderList` state and transitions into
detail, add, or edit screens depending on which user tool or backend action completes.

---------------------------------------------------------------------
Navigation States
---------------------------------------------------------------------

ReminderList
------------

| Tool | Backend Call                      | Backend call(s)                            | Returns                | Navigation effect                                       |
| ---------------------------------------- | ------------------------------------------- | ---------------------- | -------------------------------------------------------- |
| `get_all_reminders()`                    | `ReminderApp.get_all_reminders()`           | List of reminders     | Remains in `ReminderList`                               |
| `create_new()`                           | None                                        | Indicator             | → `AddReminder()`                                       |
| `view_detail(reminder_id)`               | `ReminderApp.get_reminder_details(...)`     | Reminder object       | → `ReminderDetail(reminder_id)`                         |
| `delete_reminder(reminder_id)`           | `ReminderApp.delete_reminder(...)`          | Status                | → `ReminderList()` or return via `go_back()`            |

AddReminder
-----------

| Tool | Backend Call                      | Backend call(s)                            | Returns           | Navigation effect                                       |
| ---------------------------------------- | ------------------------------------------- | ----------------- | -------------------------------------------------------- |
| `add_reminder(...)`                      | `ReminderApp.add_reminder(...)`             | Reminder ID       | → `ReminderList()`                                      |
| `cancel()`                               | None                                        | Indicator         | → previous state                                         |

ReminderDetail
--------------

| Tool | Backend Call                      | Backend call(s)                            | Returns           | Navigation effect                                       |
| ---------------------------------------- | ------------------------------------------- | ----------------- | -------------------------------------------------------- |
| `get_reminder_details(reminder_id)`      | `ReminderApp.get_reminder_details(...)`     | Reminder object   | Remains in `ReminderDetail`                             |
| `edit(edit_reminder_id)`                 | None                                        | Indicator         | → `EditReminder(reminder_id)`                           |
| `delete_reminder(reminder_id)`           | `ReminderApp.delete_reminder(...)`          | Status            | → `ReminderList()` or return via navigation stack       |
| `cancel()`                               | None                                        | Indicator         | → previous state                                         |

EditReminder
------------

| Tool | Backend Call                      | Backend call(s)                            | Returns           | Navigation effect                                       |
| ---------------------------------------- | ------------------------------------------- | ----------------- | -------------------------------------------------------- |
| `update_reminder(...)`                   | `ReminderApp.update_reminder(...)`          | Reminder ID       | → `ReminderDetail(reminder_id)`                         |
| `cancel()`                               | None                                        | Indicator         | → previous state                                         |

---------------------------------------------------------------------
Navigation Summary
---------------------------------------------------------------------

- `ReminderList → AddReminder` via `create_new`
- `ReminderList → ReminderDetail` via `view_detail`
- `AddReminder → ReminderList` via `add_reminder`
- `ReminderDetail → EditReminder` via `edit`
- `EditReminder → ReminderDetail` via `update_reminder`
- `EditReminder → previous` via `cancel`
- `ReminderDetail → previous` via `cancel`
- `delete_reminder` returns to list or pops navigation stack
- `get_all_reminders` keeps user in `ReminderList`

---------------------------------------------------------------------
Backend Operations
---------------------------------------------------------------------

The app also handles backend-triggered transitions:

- `add_reminder` resets navigation to `ReminderList`
- `update_reminder` sends user to `ReminderDetail(reminder_id)`
- `delete_reminder` returns user to previous state or `ReminderList`
- `get_all_reminders` enforces the `ReminderList` state

---------------------------------------------------------------------
Navigation Helpers
---------------------------------------------------------------------

- `load_root_state()` resets to `ReminderList`
- `set_current_state(...)` pushes new state
- `go_back()` pops navigation stack when possible
- `_handle_backend_ops(...)`, `_handle_list_ops(...)`, `_handle_detail_ops(...)`
  implement the routing logic for reminder events
"""
