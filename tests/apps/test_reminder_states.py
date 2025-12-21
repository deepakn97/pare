"""Tests for the stateful reminder app navigation flow."""

from typing import Any
import pytest

from are.simulation.types import (
    Action,
    CompletedEvent,
    EventMetadata,
    EventType,
)

from pas.apps.reminder.app import StatefulReminderApp
from pas.apps.reminder.states import (
    ReminderList,
    ReminderDetail,
    AddReminder,
    EditReminder,
)


def _make_event(
    app: StatefulReminderApp,
    function_name: str,
    return_value: Any | None = None,
    **kwargs: Any,
) -> CompletedEvent:
    """Utility to build a minimal CompletedEvent for testing.

    Args:
        app: The StatefulReminderApp instance
        function_name: Name of the user_tool method (e.g., "open_reminder", "save")
        return_value: Optional return value for metadata
        **kwargs: Arguments to pass in the action
    """
    # Create a dummy function with the right name
    def dummy_func():
        pass
    dummy_func.__name__ = function_name

    action = Action(function=dummy_func, args=kwargs, app=app)

    metadata = EventMetadata()
    if return_value is not None:
        metadata.return_value = return_value

    return CompletedEvent(
        event_type=EventType.USER,
        action=action,
        metadata=metadata,
        event_time=0,
        event_id="reminder-test-event",
    )


@pytest.fixture
def reminder_app() -> StatefulReminderApp:
    """Create a fresh reminder app."""
    return StatefulReminderApp(name="reminder")


def test_starts_in_list(reminder_app: StatefulReminderApp):
    """App should start in ReminderList."""
    assert isinstance(reminder_app.current_state, ReminderList)
    assert reminder_app.navigation_stack == []


def test_create_new_opens_add_reminder(reminder_app: StatefulReminderApp):
    """create_new should open AddReminder state."""
    event = _make_event(reminder_app, "create_new")
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, AddReminder)


def test_add_reminder_save_transitions_back_to_list(reminder_app: StatefulReminderApp):
    """Saving from AddReminder should return to ReminderList."""
    reminder_app.set_current_state(AddReminder())

    # Simulate the save operation
    event = _make_event(reminder_app, "save")
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, ReminderList)


def test_open_reminder_opens_detail_state(reminder_app: StatefulReminderApp):
    """open_reminder should open ReminderDetail state."""
    # Add a reminder directly via the backend
    rid = reminder_app.add_reminder(
        title="Title",
        description="desc",
        due_datetime="2025-01-01 10:00:00",
        repetition_unit=None,
        repetition_value=None,
    )

    # Simulate opening the reminder
    event = _make_event(reminder_app, "open_reminder", reminder_id=rid)
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, ReminderDetail)
    assert reminder_app.current_state.reminder_id == rid


def test_edit_detail_opens_edit_state(reminder_app: StatefulReminderApp):
    """edit from ReminderDetail should open EditReminder state."""
    rid = reminder_app.add_reminder(
        title="Title",
        description="desc",
        due_datetime="2025-01-01 10:00:00",
        repetition_unit=None,
        repetition_value=None,
    )

    reminder_app.set_current_state(ReminderDetail(rid))

    # Simulate edit action
    event = _make_event(reminder_app, "edit", edit_reminder_id=rid)
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, EditReminder)
    assert reminder_app.current_state.reminder_id == rid


def test_edit_save_transitions_back_to_detail(reminder_app: StatefulReminderApp):
    """Saving from EditReminder should return to previous state (ReminderDetail)."""
    rid = reminder_app.add_reminder(
        title="Old",
        description="desc",
        due_datetime="2025-01-01 09:00:00",
        repetition_unit=None,
        repetition_value=None,
    )

    # Navigate: List -> Detail -> Edit
    reminder_app.set_current_state(ReminderDetail(rid))
    edit_state = EditReminder(rid)
    reminder_app.set_current_state(edit_state)
    edit_state.on_enter()

    # Modify and save
    edit_state.set_title("New Title")
    edit_state.set_due_datetime("2025-02-01 10:00:00")
    edit_state.save()

    # Simulate save transition
    event = _make_event(reminder_app, "save")
    reminder_app.handle_state_transition(event)

    # Should go back to ReminderDetail
    assert isinstance(reminder_app.current_state, ReminderDetail)
    assert reminder_app.current_state.reminder_id == rid
    assert reminder_app.reminders[rid].title == "New Title"


def test_delete_reminder_transitions_back(reminder_app: StatefulReminderApp):
    """delete should transition back to previous state."""
    rid = reminder_app.add_reminder(
        title="T",
        description="d",
        due_datetime="2025-01-01 12:00:00",
        repetition_unit=None,
        repetition_value=None,
    )

    # Navigate List -> Detail
    reminder_app.set_current_state(ReminderDetail(rid))

    # Delete the reminder
    reminder_app.current_state.delete()

    # Simulate delete transition
    event = _make_event(reminder_app, "delete")
    reminder_app.handle_state_transition(event)

    # Should go back to ReminderList
    assert isinstance(reminder_app.current_state, ReminderList)


def test_cancel_from_add_goes_back_to_list(reminder_app: StatefulReminderApp):
    """cancel from AddReminder should go back to ReminderList."""
    # Navigate List -> Add
    reminder_app.set_current_state(AddReminder())

    # Cancel uses metadata return_value
    event = _make_event(reminder_app, "cancel", return_value="cancel")
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, ReminderList)


def test_go_back_from_detail(reminder_app: StatefulReminderApp):
    """go_back from ReminderDetail should return to ReminderList."""
    rid = reminder_app.add_reminder(
        title="T",
        description="d",
        due_datetime="2025-01-01 12:00:00",
        repetition_unit=None,
        repetition_value=None,
    )

    # Navigate List -> Detail
    reminder_app.set_current_state(ReminderDetail(rid))

    # Go back using metadata
    event = _make_event(reminder_app, "go_back", return_value="back")
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, ReminderList)


def test_list_reminders_stays_in_list(reminder_app: StatefulReminderApp):
    """list_reminders should not change state."""
    assert isinstance(reminder_app.current_state, ReminderList)

    # Simulate list_reminders call
    event = _make_event(reminder_app, "list_reminders")
    reminder_app.handle_state_transition(event)

    # Should still be in ReminderList
    assert isinstance(reminder_app.current_state, ReminderList)


def test_set_title_stays_in_add_state(reminder_app: StatefulReminderApp):
    """set_title should not change state."""
    reminder_app.set_current_state(AddReminder())

    # Simulate set_title call
    event = _make_event(reminder_app, "set_title", title="Test")
    reminder_app.handle_state_transition(event)

    # Should still be in AddReminder
    assert isinstance(reminder_app.current_state, AddReminder)
