"""Stateful reminder app combining ARE ReminderApp with PARE navigation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from are.simulation.apps.reminder import Reminder, ReminderApp
from are.simulation.tool_utils import OperationType, app_tool

from pare.apps.core import StatefulApp
from pare.apps.reminder.states import (
    EditReminder,
    ReminderDetail,
    ReminderList,
)
from pare.apps.tool_decorators import pare_event_registered

if TYPE_CHECKING:
    from are.simulation.types import CompletedEvent


class StatefulReminderApp(StatefulApp, ReminderApp):
    """Reminder application with PARE navigation support."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the reminder app and load the root navigation state.

        Args:
            *args: Positional arguments passed to ReminderApp.
            **kwargs: Keyword arguments passed to ReminderApp.
        """
        super().__init__(*args, **kwargs)
        self.load_root_state()

    def create_root_state(self) -> ReminderList:
        """Create and return the root navigation state.

        Returns:
            The initial ReminderList state.
        """
        return ReminderList()

    def get_reminder_with_id(self, reminder_id: str) -> Reminder:
        """Retrieve a reminder by its ID.

        Args:
            reminder_id: The ID of the reminder to retrieve.

        Returns:
            The Reminder object corresponding to the given ID.

        Raises:
            KeyError: If the reminder ID does not exist.
        """
        if reminder_id not in self.reminders:
            raise KeyError(f"Reminder {reminder_id} not found.")
        return self.reminders[reminder_id]

    @app_tool()
    @pare_event_registered(operation_type=OperationType.WRITE)
    def update_reminder(
        self,
        reminder_id: str,
        title: str,
        description: str,
        due_datetime: str,
        repetition_unit: str | None,
        repetition_value: int | None,
    ) -> str:
        """Update an existing reminder and regenerate its repetitions.

        Args:
            reminder_id: ID of the reminder to update.
            title: Updated title.
            description: Updated description.
            due_datetime: Updated due datetime in "YYYY-MM-DD HH:MM:SS" format.
            repetition_unit: Repetition unit (e.g., "day", "week"), or None.
            repetition_value: Repetition interval value, or None.

        Returns:
            str: The reminder ID after update.

        Raises:
            ValueError: If the reminder ID does not exist.
        """
        if reminder_id not in self.reminders:
            raise ValueError(f"Reminder {reminder_id} not found.")

        dt = datetime.strptime(due_datetime, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)

        reminder = self.reminders[reminder_id]
        reminder.title = title
        reminder.description = description
        reminder.due_datetime = dt
        reminder.repetition_unit = repetition_unit
        reminder.repetition_value = repetition_value

        base_id = reminder_id.split("_rep_")[0]
        to_delete = [k for k in self.reminders if k.startswith(f"{base_id}_rep_")]
        for k in to_delete:
            del self.reminders[k]

        next_id = reminder_id
        count = 0
        while repetition_unit and next_id and count < self.max_reminder_repetitions:
            next_id = self.add_reminder_repetition(next_id)
            if next_id:
                count += 1

        return reminder_id

    def handle_state_transition(self, event: CompletedEvent) -> None:
        """Update navigation state after a reminder operation completes.

        Args:
            event: Completed event containing tool invocation information.
        """
        current_state = self.current_state
        fname = event.function_name()

        if current_state is None or fname is None:
            return

        action = event.action
        args: dict[str, Any] = action.args if action and hasattr(action, "args") else {}

        metadata = event.metadata

        if isinstance(current_state, ReminderList):
            self._handle_list_transition(fname, args)
        elif isinstance(current_state, ReminderDetail):
            reminder_id = current_state.reminder_id
            self._handle_detail_transition(fname, reminder_id)
        elif isinstance(current_state, EditReminder):
            # EditReminder state can be reached from both creating a new reminder and editing an existing reminder.
            # If we are editing an existing reminder, we use the current reminder ID to navigate back to the ReminderDetail state.
            # Whereas, if we are creating a new reminder, there is no current reminder ID and we get the ID from the metadata after saving.
            saved_reminder_id = getattr(metadata, "return_value", None) if metadata else None
            original_reminder_id = current_state.reminder_id
            self._handle_edit_transition(
                fname, saved_reminder_id=saved_reminder_id, original_reminder_id=original_reminder_id
            )

    def _handle_list_transition(self, fname: str, args: dict[str, Any]) -> None:
        """Handle transitions from the reminder list state.

        Args:
            fname: Name of the invoked tool.
            args: Tool arguments.
        """
        if fname == "open_reminder":
            reminder_id = args.get("reminder_id")
            if reminder_id:
                self.set_current_state(ReminderDetail(reminder_id))
        elif fname == "create_new":
            self.set_current_state(EditReminder())

    def _handle_detail_transition(self, fname: str, reminder_id: str) -> None:
        """Handle transitions from the reminder detail state.

        Args:
            fname: Name of the invoked tool.
            reminder_id: ID of the current reminder being viewed.
        """
        if fname == "edit":
            self.set_current_state(EditReminder(reminder_id=reminder_id))
        elif fname == "delete":
            self.load_root_state()

    def _handle_edit_transition(
        self, fname: str, saved_reminder_id: str | None, original_reminder_id: str | None
    ) -> None:
        """Handle transitions from the edit reminder state.

        Args:
            fname: Name of the invoked tool.
            saved_reminder_id: ID of the reminder after save, if any.
            original_reminder_id: ID of the reminder being edited, if any.
        """
        if fname == "save":
            if saved_reminder_id is not None:
                self.set_current_state(ReminderDetail(reminder_id=saved_reminder_id))
        elif fname == "cancel":
            if original_reminder_id is not None:
                self.set_current_state(ReminderDetail(reminder_id=original_reminder_id))
            else:
                self.load_root_state()
