from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from are.simulation.apps.reminder import Reminder  # noqa: TC002 - runtime import required for get_type_hints()
from are.simulation.types import OperationType, disable_events

from pas.apps.core import AppState
from pas.apps.tool_decorators import pas_event_registered, user_tool

if TYPE_CHECKING:
    from pas.apps.reminder.app import StatefulReminderApp


# Draft object
@dataclass
class ReminderDraft:
    """Container representing mutable reminder fields during editing or creation."""

    title: str = ""
    description: str = ""
    due_datetime: str = ""
    repetition_unit: str | None = None
    repetition_value: int | None = None


# Reminder List
class ReminderList(AppState):
    """State showing the full list of reminders."""

    def on_enter(self) -> None:
        """Lifecycle hook called when entering ReminderList."""
        pass

    def on_exit(self) -> None:
        """Lifecycle hook called when leaving ReminderList."""
        pass

    @user_tool(llm_formatter=lambda x: "\n\n".join([str(reminder) for reminder in x]))
    @pas_event_registered(operation_type=OperationType.READ)
    def list_all_reminders(self) -> list[Reminder]:
        """Get all the reminders from the reminder system.

        Returns:
            list[Reminder]: A list of reminders as returned by the backend.
        """
        app = cast("StatefulReminderApp", self.app)
        with disable_events():
            return app.get_all_reminders()

    @user_tool(llm_formatter=lambda x: "\n\n".join([str(reminder) for reminder in x]))
    @pas_event_registered(operation_type=OperationType.READ)
    def list_upcoming_reminders(self) -> list[Reminder]:
        """Get upcoming reminders from the reminder system. Upcoming reminders are those that are due in the near future.

        Returns:
            list[Reminder]: A list of upcoming reminders as returned by the backend.
        """
        app = cast("StatefulReminderApp", self.app)
        upcoming_reminders = []
        current_time = app.time_manager.time()
        with disable_events():
            reminders = app.get_all_reminders()
        for _, reminder in reminders.items():
            if reminder.due_datetime.timestamp() > current_time:
                upcoming_reminders.append(reminder)
        return upcoming_reminders

    @user_tool(llm_formatter=lambda x: "\n\n".join([str(reminder) for reminder in x]))
    @pas_event_registered(operation_type=OperationType.READ)
    def list_due_reminders(self) -> list[Reminder]:
        """Get due reminders from the reminder system. Due reminders are those that are past their due datetime.

        Returns:
            list[Reminder]: A list of due reminders as returned by the backend.
        """
        app = cast("StatefulReminderApp", self.app)
        with disable_events():
            return app.get_due_reminders()

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def open_reminder(self, reminder_id: str) -> Reminder:
        """Request to view details of a specific reminder.

        Args:
            reminder_id (str): ID of the reminder to view.

        Returns:
            Reminder: The Reminder object corresponding to the given ID.
        """
        app = cast("StatefulReminderApp", self.app)
        return app.get_reminder_with_id(reminder_id=reminder_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def create_new(self) -> ReminderDraft:
        """Request to start creating a new reminder. Initially the reminder is empty.

        Returns:
            ReminderDraft: Draft Reminder object to be filled out.
        """
        return ReminderDraft()


# Reminder Detail
class ReminderDetail(AppState):
    """State displaying the full details of a single reminder."""

    def __init__(self, reminder_id: str) -> None:
        """Initialize the detail view.

        Args:
            reminder_id (str): The ID of the reminder being displayed.
        """
        super().__init__()
        self.reminder_id = reminder_id

    def on_enter(self) -> None:
        """Lifecycle hook called when entering ReminderDetail."""
        pass

    def on_exit(self) -> None:
        """Lifecycle hook called when leaving ReminderDetail."""
        pass

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def edit(self) -> str:
        """Request to edit this reminder.

        Returns:
            str: ID of reminder to edit.
        """
        return self.reminder_id

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def delete(self) -> str:
        """Delete this reminder.

        Returns:
            str: ID of deleted reminder.
        """
        app = cast("StatefulReminderApp", self.app)
        with disable_events():
            return app.delete_reminder(self.reminder_id)


# EditReminder Wizard
class EditReminder(AppState):
    """State enabling editing of an existing reminder."""

    def __init__(self, reminder_id: str | None = None) -> None:
        """Initialize the edit wizard.

        Args:
            reminder_id (str | None): ID of the reminder to edit.
        """
        super().__init__()
        self.reminder_id = reminder_id
        self.draft = ReminderDraft()

    def on_enter(self) -> None:
        """Load existing reminder fields into draft."""
        if self.reminder_id is None:
            return
        app = cast("StatefulReminderApp", self.app)
        try:
            r = app.get_reminder_with_id(self.reminder_id)
            self.draft.title = r.title
            self.draft.description = r.description
            self.draft.due_datetime = r.due_datetime.strftime("%Y-%m-%d %H:%M:%S")
            self.draft.repetition_unit = r.repetition_unit
            self.draft.repetition_value = r.repetition_value
        except KeyError:
            # If the reminder does not exist, keep the draft empty
            pass

    def on_exit(self) -> None:
        """Lifecycle hook called when exiting EditReminder."""
        pass

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def set_title(self, title: str) -> ReminderDraft:
        """Update title in the draft.

        Args:
            title (str): New title.

        Returns:
            ReminderDraft: Updated draft with new title.
        """
        self.draft.title = title
        return self.draft

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def set_description(self, description: str) -> ReminderDraft:
        """Update description in draft.

        Args:
            description (str): New description.

        Returns:
            ReminderDraft: Updated draft with new description.
        """
        self.draft.description = description
        return self.draft

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def set_due_datetime(self, due_datetime: str) -> ReminderDraft:
        """Update due datetime.

        Args:
            due_datetime (str): New datetime.

        Returns:
            ReminderDraft: Updated draft with new due datetime.
        """
        self.draft.due_datetime = due_datetime
        return self.draft

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def set_repetition(self, unit: str | None, value: int | None = None) -> ReminderDraft:
        """Update repetition settings.

        Args:
            unit (str | None): Repetition unit.
            value (int | None): Repetition count.

        Returns:
            ReminderDraft: Updated draft with new repetition settings.
        """
        self.draft.repetition_unit = unit
        self.draft.repetition_value = value
        return self.draft

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def save(self) -> str:
        """Save the changes to the reminder.

        Returns:
            str: Reminder ID after update.
        """
        app = cast("StatefulReminderApp", self.app)
        if self.reminder_id is None:
            # Creating a new reminder
            return app.add_reminder(
                title=self.draft.title,
                description=self.draft.description,
                due_datetime=self.draft.due_datetime,
                repetition_unit=self.draft.repetition_unit,
                repetition_value=self.draft.repetition_value,
            )
        else:
            return app.update_reminder(
                reminder_id=self.reminder_id,
                title=self.draft.title,
                description=self.draft.description,
                due_datetime=self.draft.due_datetime,
                repetition_unit=self.draft.repetition_unit,
                repetition_value=self.draft.repetition_value,
            )

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def cancel(self) -> str:
        """Abort editing and go back.

        Returns:
            str: Confirmation of cancellation.
        """
        return "Reminder editing cancelled."
