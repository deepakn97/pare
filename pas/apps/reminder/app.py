from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from are.simulation.apps.reminder import ReminderApp

from pas.apps.core import StatefulApp
from pas.apps.reminder.states import (
    AddReminder,
    EditReminder,
    ReminderDetail,
    ReminderList,
)

if TYPE_CHECKING:
    from are.simulation.types import CompletedEvent


class StatefulReminderApp(StatefulApp, ReminderApp):
    """ReminderApp with PAS navigation."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialise reminder app with root state."""
        super().__init__(*args, **kwargs)
        self.load_root_state()

    def create_root_state(self) -> ReminderList:
        """Return the default root state."""
        return ReminderList()

    # Backend data update helper
    def update_reminder(
        self,
        reminder_id: str,
        title: str,
        description: str,
        due_datetime: str,
        repetition_unit: str | None,
        repetition_value: int | None,
    ) -> str:
        """Update fields of an existing reminder."""
        if reminder_id not in self.reminders:
            raise ValueError(f"Reminder {reminder_id} not found.")

        dt = datetime.strptime(due_datetime, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)

        r = self.reminders[reminder_id]
        r.title = title
        r.description = description
        r.due_datetime = dt
        r.repetition_unit = repetition_unit
        r.repetition_value = repetition_value

        for k in list(self.reminders.keys()):
            if k.startswith(reminder_id + "_rep_"):
                del self.reminders[k]

        next_id = reminder_id
        count = 0
        while repetition_unit and next_id and count < self.max_reminder_repetitions:
            next_id = self.add_reminder_repetition(next_id)
            if next_id:
                count += 1

        return reminder_id

    # Navigation handling
    def handle_state_transition(self, event: CompletedEvent) -> None:
        """Update navigation state based on reminder operations."""
        function_name = event.function_name()
        if function_name is None:
            return
        metadata = getattr(event, "metadata", None)
        if metadata and metadata.return_value in ("cancel", "back"):
            self.go_back()
            return
        action = getattr(event, "action", None)
        event_args: dict[str, Any] = {}
        if action is not None and hasattr(action, "args"):
            event_args = cast("dict[str, Any]", action.args)

        if self._handle_backend_transitions(function_name, event_args):
            return
        if self._handle_list_transitions(function_name, event_args):
            return
        if self._handle_detail_transitions(function_name, event_args):
            return

    # Backend operations
    def _handle_backend_transitions(self, fname: str, args: dict[str, Any]) -> bool:
        """Handle transitions caused by WRITE/READ backend calls."""
        match fname:
            case "add_reminder":
                self.set_current_state(ReminderList())
                return True

            case "update_reminder":
                rid = args.get("reminder_id")
                if rid:
                    self.set_current_state(ReminderDetail(rid))
                return True

            case "delete_reminder":
                if self.navigation_stack:
                    self.go_back()
                else:
                    self.set_current_state(ReminderList())
                return True

            case "get_all_reminders":
                if not isinstance(self.current_state, ReminderList):
                    self.set_current_state(ReminderList())
                return True

        return False

    # From list view
    def _handle_list_transitions(self, fname: str, args: dict[str, Any]) -> bool:
        """Handle transitions originating in ReminderList."""
        if not isinstance(self.current_state, ReminderList):
            return False

        if fname == "create_new":
            self.set_current_state(AddReminder())
            return True

        if fname == "open_reminder":
            rid = args.get("reminder_id")
            if rid:
                self.set_current_state(ReminderDetail(rid))
            return True

        return False

    # From detail/edit views
    def _handle_detail_transitions(self, fname: str, args: dict[str, Any]) -> bool:
        """Handle transitions from ReminderDetail or EditReminder."""
        if not isinstance(self.current_state, (ReminderDetail, EditReminder)):
            return False

        if fname == "edit":
            rid = args.get("edit_reminder_id")
            if rid:
                self.set_current_state(EditReminder(rid))
            return True

        if fname == "cancel":
            self.go_back()
            return True

        return False
