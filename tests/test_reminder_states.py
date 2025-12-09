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


# Utility to create a CompletedEvent for state transitions
def _make_event(app: StatefulReminderApp, func: callable, **kwargs: Any) -> CompletedEvent:
    """Utility to build a minimal CompletedEvent for testing."""
    action = Action(function=func, args={"self": app, **kwargs}, app=app)
    return CompletedEvent(
        event_type=EventType.USER,
        action=action,
        metadata=EventMetadata(),
        event_time=0,
        event_id="reminder-test-event",
    )


# Fixtures
@pytest.fixture
def reminder_app() -> StatefulReminderApp:
    """Create a fresh reminder app."""
    app = StatefulReminderApp(name="reminder")
    return app


# Tests
def test_starts_in_list(reminder_app: StatefulReminderApp):
    """App should start in ReminderList."""
    assert isinstance(reminder_app.current_state, ReminderList)
    assert reminder_app.navigation_stack == []


def test_create_new_opens_add_reminder(reminder_app: StatefulReminderApp):
    """create_new should push AddReminder state."""
    # Trigger view action
    result = reminder_app.current_state.create_new()
    event = _make_event(reminder_app, reminder_app.current_state.create_new, **result)
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, AddReminder)


def test_add_reminder_save_transitions_back_to_list(reminder_app: StatefulReminderApp):
    """Saving from AddReminder should return to ReminderList."""
    # Move to AddReminder
    reminder_app.set_current_state(AddReminder())

    # Fill draft
    cs = reminder_app.current_state
    cs.set_title("test title")
    cs.set_description("desc")
    cs.set_due_datetime("2025-01-01 12:00:00")
    cs.set_repetition("day", 1)

    # Save (calls add_reminder)
    rid = cs.save()
    event = _make_event(reminder_app, reminder_app.add_reminder, reminder_id=rid)
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, ReminderList)


def test_view_detail_opens_detail_state(reminder_app: StatefulReminderApp):
    """view_detail should open ReminderDetail state."""
    # First add a reminder
    reminder_app.add_reminder(
        title="Title",
        description="desc",
        due_datetime="2025-01-01 10:00:00",
        repetition_unit=None,
        repetition_value=None,
    )
    rid = next(iter(reminder_app.reminders.keys()))

    # Trigger view_detail
    result = reminder_app.current_state.view_detail(rid)
    event = _make_event(
        reminder_app,
        reminder_app.current_state.view_detail,
        **result
    )
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, ReminderDetail)
    assert reminder_app.current_state.reminder_id == rid


def test_edit_detail_opens_edit_state(reminder_app: StatefulReminderApp):
    """edit should open EditReminder state."""
    # Add reminder
    reminder_app.add_reminder(
        title="Title",
        description="desc",
        due_datetime="2025-01-01 10:00:00",
        repetition_unit=None,
        repetition_value=None,
    )
    rid = next(iter(reminder_app.reminders.keys()))

    # Move to detail
    reminder_app.set_current_state(ReminderDetail(rid))

    # Trigger edit
    result = reminder_app.current_state.edit()
    event = _make_event(
        reminder_app,
        reminder_app.current_state.edit,
        **result
    )
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, EditReminder)
    assert reminder_app.current_state.reminder_id == rid


def test_edit_save_transitions_back_to_detail(reminder_app: StatefulReminderApp):
    """Saving from EditReminder should return to ReminderDetail."""
    # Add initial reminder
    reminder_app.add_reminder(
        title="Old",
        description="desc",
        due_datetime="2025-01-01 09:00:00",
        repetition_unit=None,
        repetition_value=None,
    )
    rid = next(iter(reminder_app.reminders.keys()))

    # Enter Edit state
    edit_state = EditReminder(rid)
    reminder_app.set_current_state(edit_state)
    edit_state.on_enter()

    # Modify draft
    edit_state.set_title("New Title")
    edit_state.set_due_datetime("2025-02-01 10:00:00")

    # Save → update_reminder
    edit_state.save()
    event = _make_event(
        reminder_app,
        reminder_app.update_reminder,
        reminder_id=rid
    )
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, ReminderDetail)
    assert reminder_app.current_state.reminder_id == rid

    # Ensure value updated
    assert reminder_app.reminders[rid].title == "New Title"


def test_delete_reminder_transitions_back(reminder_app: StatefulReminderApp):
    """delete_reminder should go back to list."""
    # Add reminder
    reminder_app.add_reminder(
        title="T",
        description="d",
        due_datetime="2025-01-01 12:00:00",
        repetition_unit=None,
        repetition_value=None,
    )
    rid = next(iter(reminder_app.reminders.keys()))

    # Go to detail
    reminder_app.set_current_state(ReminderDetail(rid))

    # Call delete
    reminder_app.current_state.delete()
    event = _make_event(reminder_app, reminder_app.delete_reminder, reminder_id=rid)
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, ReminderList)


def test_cancel_goes_back(reminder_app: StatefulReminderApp):
    """cancel action should cause go_back state change."""
    # Move to AddReminder
    reminder_app.set_current_state(AddReminder())

    # cancel
    reminder_app.current_state.cancel()
    event = _make_event(reminder_app, reminder_app.current_state.cancel)
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, ReminderList)


def test_get_all_reminders_keeps_list(reminder_app: StatefulReminderApp):
    """get_all_reminders should keep or restore the list view."""
    reminder_app.set_current_state(AddReminder())

    # call get_all_reminders
    reminder_app.get_all_reminders()
    event = _make_event(
        reminder_app,
        reminder_app.get_all_reminders,
    )
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, ReminderList)
