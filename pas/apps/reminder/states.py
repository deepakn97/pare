from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from are.simulation.types import OperationType

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

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def list_reminders(self) -> list[object]:
        """Return all reminders.

        Returns:
            Any: A list of reminders as returned by the backend.
        """
        app = cast("StatefulReminderApp", self.app)
        return app.get_all_reminders()

    @user_tool()
    @pas_event_registered()
    def open_reminder(self, reminder_id: str) -> dict[str, str]:
        """Request to view details of a specific reminder.

        Args:
            reminder_id (str): ID of the reminder to view.

        Returns:
            dict[str, str]: Payload containing the reminder ID.
        """
        return {"reminder_id": reminder_id}

    @user_tool()
    @pas_event_registered()
    def create_new(self) -> dict[str, bool]:
        """Request to start creating a new reminder.

        Returns:
            dict[str, bool]: Marker used by navigation to open AddReminder state.
        """
        return {"create": True}


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
    @pas_event_registered(operation_type=OperationType.READ)
    def get_reminder(self) -> object | None:
        """Fetch reminder details from the backend.

        Returns:
            Any: Reminder object or None.
        """
        app = cast("StatefulReminderApp", self.app)
        return app.reminders.get(self.reminder_id)

    @user_tool()
    @pas_event_registered()
    def edit(self) -> dict[str, str]:
        """Request to edit this reminder.

        Returns:
            dict[str, str]: Contains the reminder ID for editing.
        """
        return {"edit_reminder_id": self.reminder_id}

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def delete(self) -> str:
        """Delete this reminder.

        Returns:
            str: ID of deleted reminder.
        """
        app = cast("StatefulReminderApp", self.app)
        return app.delete_reminder(self.reminder_id)

    @user_tool()
    @pas_event_registered()
    def go_back(self) -> str:
        """Signal navigation to go back.

        Returns:
            str: The navigation directive ``"back"``.
        """
        return "back"


# AddReminder Wizard
class AddReminder(AppState):
    """State providing a multi-step form to create a new reminder."""

    def __init__(self) -> None:
        """Initialize the creation wizard and draft container."""
        super().__init__()
        self.draft = ReminderDraft()

    def on_enter(self) -> None:
        """Lifecycle hook called when entering AddReminder."""
        pass

    def on_exit(self) -> None:
        """Lifecycle hook called when leaving AddReminder."""
        pass

    @user_tool()
    @pas_event_registered()
    def set_title(self, title: str) -> dict[str, str]:
        """Set the title for the draft.

        Args:
            title (str): The reminder title.

        Returns:
            dict[str, str]: The updated title.
        """
        self.draft.title = title
        return {"title": title}

    @user_tool()
    @pas_event_registered()
    def set_description(self, description: str) -> dict[str, str]:
        """Set the description for the draft.

        Args:
            description (str): Reminder description.

        Returns:
            dict[str, str]: Updated description.
        """
        self.draft.description = description
        return {"description": description}

    @user_tool()
    @pas_event_registered()
    def set_due_datetime(self, due_datetime: str) -> dict[str, str]:
        """Set due datetime for the draft.

        Args:
            due_datetime (str): Datetime string.

        Returns:
            dict[str, str]: Updated due datetime.
        """
        self.draft.due_datetime = due_datetime
        return {"due_datetime": due_datetime}

    @user_tool()
    @pas_event_registered()
    def set_repetition(self, unit: str | None, value: int | None = None) -> dict[str, Any]:
        """Set repetition parameters.

        Args:
            unit (str | None): Unit of repetition.
            value (int | None): Repetition interval.

        Returns:
            dict[str, Any]: Updated repetition info.
        """
        self.draft.repetition_unit = unit
        self.draft.repetition_value = value
        return {"unit": unit, "value": value}

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def save(self) -> str:
        """Finalize creation of the reminder.

        Returns:
            str: Created reminder ID.
        """
        app = cast("StatefulReminderApp", self.app)
        return app.add_reminder(
            title=self.draft.title,
            description=self.draft.description,
            due_datetime=self.draft.due_datetime,
            repetition_unit=self.draft.repetition_unit,
            repetition_value=self.draft.repetition_value,
        )

    @user_tool()
    @pas_event_registered()
    def cancel(self) -> str:
        """Abort reminder creation.

        Returns:
            str: Signal to go back.
        """
        return "cancel"


# EditReminder Wizard
class EditReminder(AppState):
    """State enabling editing of an existing reminder."""

    def __init__(self, reminder_id: str) -> None:
        """Initialize the edit wizard.

        Args:
            reminder_id (str): ID of the reminder to edit.
        """
        super().__init__()
        self.reminder_id = reminder_id
        self.draft = ReminderDraft()

    def on_enter(self) -> None:
        """Load existing reminder fields into draft."""
        app = cast("StatefulReminderApp", self.app)
        r = app.reminders.get(self.reminder_id)
        if r:
            self.draft.title = r.title
            self.draft.description = r.description
            self.draft.due_datetime = r.due_datetime.strftime("%Y-%m-%d %H:%M:%S")
            self.draft.repetition_unit = r.repetition_unit
            self.draft.repetition_value = r.repetition_value

    def on_exit(self) -> None:
        """Lifecycle hook called when exiting EditReminder."""
        pass

    @user_tool()
    @pas_event_registered()
    def set_title(self, title: str) -> dict[str, str]:
        """Update title in the draft.

        Args:
            title (str): New title.

        Returns:
            dict[str, str]: Updated title.
        """
        self.draft.title = title
        return {"title": title}

    @user_tool()
    @pas_event_registered()
    def set_description(self, description: str) -> dict[str, str]:
        """Update description in draft.

        Args:
            description (str): New description.

        Returns:
            dict[str, str]: Updated description.
        """
        self.draft.description = description
        return {"description": description}

    @user_tool()
    @pas_event_registered()
    def set_due_datetime(self, due_datetime: str) -> dict[str, str]:
        """Update due datetime.

        Args:
            due_datetime (str): New datetime.

        Returns:
            dict[str, str]: Updated value.
        """
        self.draft.due_datetime = due_datetime
        return {"due_datetime": due_datetime}

    @user_tool()
    @pas_event_registered()
    def set_repetition(self, unit: str | None, value: int | None = None) -> dict[str, Any]:
        """Update repetition settings.

        Args:
            unit (str | None): Repetition unit.
            value (int | None): Repetition count.

        Returns:
            dict[str, Any]: Updated unit and value.
        """
        self.draft.repetition_unit = unit
        self.draft.repetition_value = value
        return {"unit": unit, "value": value}

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def save(self) -> str:
        """Persist updated reminder to backend.

        Returns:
            str: Reminder ID after update.
        """
        app = cast("StatefulReminderApp", self.app)
        return app.update_reminder(
            reminder_id=self.reminder_id,
            title=self.draft.title,
            description=self.draft.description,
            due_datetime=self.draft.due_datetime,
            repetition_unit=self.draft.repetition_unit,
            repetition_value=self.draft.repetition_value,
        )

    @user_tool()
    @pas_event_registered()
    def cancel(self) -> str:
        """Abort editing and go back.

        Returns:
            str: Navigation directive.
        """
        return "cancel"
