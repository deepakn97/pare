"""Tests for the stateful reminder app navigation flow."""

from __future__ import annotations

from typing import Any

import pytest
from are.simulation.types import (
    Action,
    CompletedEvent,
    EventMetadata,
    EventType,
)

from pas.apps.proactive_aui import PASAgentUserInterface
from pas.apps.reminder.app import StatefulReminderApp
from pas.apps.reminder.states import (
    EditReminder,
    ReminderDetail,
    ReminderList,
)
from pas.apps.system import HomeScreenSystemApp
from pas.environment import StateAwareEnvironmentWrapper

# =============================================================================
# Helper Functions
# =============================================================================


def _list_state(app: StatefulReminderApp) -> ReminderList:
    """Assert and return app is in ReminderList state."""
    state = app.current_state
    assert isinstance(state, ReminderList)
    return state


def _detail_state(app: StatefulReminderApp) -> ReminderDetail:
    """Assert and return app is in ReminderDetail state."""
    state = app.current_state
    assert isinstance(state, ReminderDetail)
    return state


def _edit_state(app: StatefulReminderApp) -> EditReminder:
    """Assert and return app is in EditReminder state."""
    state = app.current_state
    assert isinstance(state, EditReminder)
    return state


def _make_event(
    app: StatefulReminderApp,
    func: callable,
    result: Any | None = None,
    **kwargs: Any,
) -> CompletedEvent:
    """Utility to build a minimal CompletedEvent for state transition tests.

    Args:
        app: The StatefulReminderApp instance
        func: The function/method being called
        result: Optional return value for metadata
        **kwargs: Arguments to pass in the action
    """
    action = Action(function=func, args={"self": app, **kwargs}, app=app)

    metadata = EventMetadata()
    metadata.return_value = result

    return CompletedEvent(
        event_type=EventType.USER,
        action=action,
        metadata=metadata,
        event_time=0,
        event_id="reminder-test-event",
    )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def reminder_app() -> StatefulReminderApp:
    """Create a fresh reminder app."""
    return StatefulReminderApp(name="reminder")


@pytest.fixture
def env_with_reminder() -> StateAwareEnvironmentWrapper:
    """Create environment with reminder app registered and opened."""
    env = StateAwareEnvironmentWrapper()
    system_app = HomeScreenSystemApp(name="HomeScreen")
    aui_app = PASAgentUserInterface()
    reminder_app = StatefulReminderApp(name="reminder")
    env.register_apps([system_app, aui_app, reminder_app])
    env._open_app("reminder")
    return env


# =============================================================================
# Basic Startup Tests
# =============================================================================


def test_starts_in_list(reminder_app: StatefulReminderApp) -> None:
    """App should start in ReminderList with empty navigation stack."""
    assert isinstance(reminder_app.current_state, ReminderList)
    assert reminder_app.navigation_stack == []


# =============================================================================
# Unit Tests: State Transitions from ReminderList
# =============================================================================


def test_open_reminder_transition(reminder_app: StatefulReminderApp) -> None:
    """Handler: open_reminder event transitions to ReminderDetail."""
    rid = reminder_app.add_reminder(
        title="Test Reminder",
        description="Description",
        due_datetime="2025-01-01 10:00:00",
        repetition_unit=None,
        repetition_value=None,
    )

    event = _make_event(
        reminder_app,
        reminder_app.current_state.open_reminder,
        reminder_id=rid,
    )
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, ReminderDetail)
    assert reminder_app.current_state.reminder_id == rid


def test_create_new_transition(reminder_app: StatefulReminderApp) -> None:
    """Handler: create_new event transitions to EditReminder with reminder_id=None."""
    event = _make_event(reminder_app, reminder_app.current_state.create_new)
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, EditReminder)
    assert reminder_app.current_state.reminder_id is None


def test_list_all_reminders_no_transition(reminder_app: StatefulReminderApp) -> None:
    """Handler: list_all_reminders should not change state."""
    assert isinstance(reminder_app.current_state, ReminderList)

    event = _make_event(reminder_app, reminder_app.current_state.list_all_reminders)
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, ReminderList)


def test_list_upcoming_reminders_no_transition(reminder_app: StatefulReminderApp) -> None:
    """Handler: list_upcoming_reminders should not change state."""
    assert isinstance(reminder_app.current_state, ReminderList)

    event = _make_event(reminder_app, reminder_app.current_state.list_upcoming_reminders)
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, ReminderList)


def test_list_due_reminders_no_transition(reminder_app: StatefulReminderApp) -> None:
    """Handler: list_due_reminders should not change state."""
    assert isinstance(reminder_app.current_state, ReminderList)

    event = _make_event(reminder_app, reminder_app.current_state.list_due_reminders)
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, ReminderList)


# =============================================================================
# Unit Tests: State Transitions from ReminderDetail
# =============================================================================


def test_edit_transition(reminder_app: StatefulReminderApp) -> None:
    """Handler: edit event transitions to EditReminder with reminder_id."""
    rid = reminder_app.add_reminder(
        title="Test",
        description="Desc",
        due_datetime="2025-01-01 10:00:00",
        repetition_unit=None,
        repetition_value=None,
    )

    detail_state = ReminderDetail(rid)
    reminder_app.set_current_state(detail_state)

    event = _make_event(reminder_app, detail_state.edit, result=rid)
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, EditReminder)
    assert reminder_app.current_state.reminder_id == rid


def test_delete_transition(reminder_app: StatefulReminderApp) -> None:
    """Handler: delete event transitions to ReminderList (root, clears stack)."""
    rid = reminder_app.add_reminder(
        title="Test",
        description="Desc",
        due_datetime="2025-01-01 10:00:00",
        repetition_unit=None,
        repetition_value=None,
    )

    # Navigate to detail (builds stack)
    detail_state = ReminderDetail(rid)
    reminder_app.set_current_state(detail_state)

    event = _make_event(reminder_app, detail_state.delete, result=rid)
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, ReminderList)
    assert reminder_app.navigation_stack == []


# =============================================================================
# Unit Tests: State Transitions from EditReminder
# =============================================================================


def test_save_new_reminder_transition(reminder_app: StatefulReminderApp) -> None:
    """Handler: save event from EditReminder(None) transitions to ReminderDetail with new ID."""
    edit_state = EditReminder(reminder_id=None)
    reminder_app.set_current_state(edit_state)

    # Simulate saving - return value is the new reminder ID
    new_rid = "reminder_001"
    event = _make_event(reminder_app, edit_state.save, result=new_rid)
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, ReminderDetail)
    assert reminder_app.current_state.reminder_id == new_rid


def test_save_edit_reminder_transition(reminder_app: StatefulReminderApp) -> None:
    """Handler: save event from EditReminder(id) transitions to ReminderDetail with same ID."""
    rid = reminder_app.add_reminder(
        title="Old Title",
        description="Desc",
        due_datetime="2025-01-01 10:00:00",
        repetition_unit=None,
        repetition_value=None,
    )

    edit_state = EditReminder(reminder_id=rid)
    reminder_app.set_current_state(edit_state)

    event = _make_event(reminder_app, edit_state.save, result=rid)
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, ReminderDetail)
    assert reminder_app.current_state.reminder_id == rid


def test_cancel_new_reminder_transition(reminder_app: StatefulReminderApp) -> None:
    """Handler: cancel event from EditReminder(None) transitions to ReminderList."""
    edit_state = EditReminder(reminder_id=None)
    reminder_app.set_current_state(edit_state)

    event = _make_event(reminder_app, edit_state.cancel, result="Reminder editing cancelled.")
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, ReminderList)


def test_cancel_edit_reminder_transition(reminder_app: StatefulReminderApp) -> None:
    """Handler: cancel event from EditReminder(id) transitions to ReminderDetail with original ID."""
    rid = reminder_app.add_reminder(
        title="Test",
        description="Desc",
        due_datetime="2025-01-01 10:00:00",
        repetition_unit=None,
        repetition_value=None,
    )

    edit_state = EditReminder(reminder_id=rid)
    reminder_app.set_current_state(edit_state)

    event = _make_event(reminder_app, edit_state.cancel, result="Reminder editing cancelled.")
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, ReminderDetail)
    assert reminder_app.current_state.reminder_id == rid


# =============================================================================
# Unit Tests: Self-loop Transitions (EditReminder)
# =============================================================================


def test_set_title_no_transition(reminder_app: StatefulReminderApp) -> None:
    """Handler: set_title should not change state."""
    edit_state = EditReminder(reminder_id=None)
    reminder_app.set_current_state(edit_state)

    event = _make_event(reminder_app, edit_state.set_title, title="New Title")
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, EditReminder)


def test_set_description_no_transition(reminder_app: StatefulReminderApp) -> None:
    """Handler: set_description should not change state."""
    edit_state = EditReminder(reminder_id=None)
    reminder_app.set_current_state(edit_state)

    event = _make_event(reminder_app, edit_state.set_description, description="New Description")
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, EditReminder)


def test_set_due_datetime_no_transition(reminder_app: StatefulReminderApp) -> None:
    """Handler: set_due_datetime should not change state."""
    edit_state = EditReminder(reminder_id=None)
    reminder_app.set_current_state(edit_state)

    event = _make_event(reminder_app, edit_state.set_due_datetime, due_datetime="2025-06-01 10:00:00")
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, EditReminder)


def test_set_repetition_no_transition(reminder_app: StatefulReminderApp) -> None:
    """Handler: set_repetition should not change state."""
    edit_state = EditReminder(reminder_id=None)
    reminder_app.set_current_state(edit_state)

    event = _make_event(reminder_app, edit_state.set_repetition, unit="day", value=1)
    reminder_app.handle_state_transition(event)

    assert isinstance(reminder_app.current_state, EditReminder)


# =============================================================================
# Integration Tests (multi-step trajectories via environment)
# =============================================================================


class TestReminderEnvironmentIntegration:
    """Integration tests that exercise the full environment flow.

    These tests use the environment pattern where:
    1. Tool calls automatically log events via @pas_event_registered
    2. Events automatically trigger state transitions via StateAwareEnvironmentWrapper.add_to_log
    3. No manual event handling is needed - just call tools and verify state
    """

    def test_create_reminder_flow(self, env_with_reminder: StateAwareEnvironmentWrapper) -> None:
        """Integration: List -> create_new -> EditReminder -> set fields -> save -> Detail."""
        env = env_with_reminder
        app = env.get_app_with_class(StatefulReminderApp)

        # Start at ReminderList
        assert isinstance(app.current_state, ReminderList)
        assert len(app.navigation_stack) == 0

        # Step 1: create_new -> EditReminder(None)
        _list_state(app).create_new()
        assert isinstance(app.current_state, EditReminder)
        assert app.current_state.reminder_id is None
        assert len(app.navigation_stack) == 1

        # Step 2: Set fields (should stay in EditReminder)
        _edit_state(app).set_title("New Reminder")
        assert isinstance(app.current_state, EditReminder)

        _edit_state(app).set_description("Test description")
        assert isinstance(app.current_state, EditReminder)

        _edit_state(app).set_due_datetime("2025-06-01 10:00:00")
        assert isinstance(app.current_state, EditReminder)

        # Step 3: save -> ReminderDetail
        _edit_state(app).save()
        assert isinstance(app.current_state, ReminderDetail)
        assert app.current_state.reminder_id is not None

        # Verify reminder was created
        rid = app.current_state.reminder_id
        assert rid in app.reminders
        assert app.reminders[rid].title == "New Reminder"

    def test_edit_reminder_flow(self, env_with_reminder: StateAwareEnvironmentWrapper) -> None:
        """Integration: List -> open_reminder -> Detail -> edit -> EditReminder -> save -> Detail."""
        env = env_with_reminder
        app = env.get_app_with_class(StatefulReminderApp)

        # Create a reminder via backend
        rid = app.add_reminder(
            title="Original Title",
            description="Original description",
            due_datetime="2025-01-01 10:00:00",
            repetition_unit=None,
            repetition_value=None,
        )

        # Start at ReminderList
        assert isinstance(app.current_state, ReminderList)

        # Step 1: open_reminder -> ReminderDetail
        _list_state(app).open_reminder(rid)
        assert isinstance(app.current_state, ReminderDetail)
        assert app.current_state.reminder_id == rid
        assert len(app.navigation_stack) == 1

        # Step 2: edit -> EditReminder
        _detail_state(app).edit()
        assert isinstance(app.current_state, EditReminder)
        assert app.current_state.reminder_id == rid
        assert len(app.navigation_stack) == 2

        # Verify draft was populated by on_enter
        assert app.current_state.draft.title == "Original Title"

        # Step 3: Modify and save
        _edit_state(app).set_title("Updated Title")
        _edit_state(app).save()

        # Should be back at ReminderDetail
        assert isinstance(app.current_state, ReminderDetail)
        assert app.current_state.reminder_id == rid

        # Verify reminder was updated
        assert app.reminders[rid].title == "Updated Title"

    def test_view_and_delete_flow(self, env_with_reminder: StateAwareEnvironmentWrapper) -> None:
        """Integration: List -> open_reminder -> Detail -> delete -> List (stack cleared)."""
        env = env_with_reminder
        app = env.get_app_with_class(StatefulReminderApp)

        # Create a reminder
        rid = app.add_reminder(
            title="To Delete",
            description="Will be deleted",
            due_datetime="2025-01-01 10:00:00",
            repetition_unit=None,
            repetition_value=None,
        )
        assert rid in app.reminders

        # Navigate to detail
        _list_state(app).open_reminder(rid)
        assert isinstance(app.current_state, ReminderDetail)
        assert len(app.navigation_stack) == 1

        # Delete
        _detail_state(app).delete()

        # Should be at ReminderList with stack cleared
        assert isinstance(app.current_state, ReminderList)
        assert len(app.navigation_stack) == 0

        # Reminder should be deleted
        assert rid not in app.reminders

    def test_create_and_cancel_flow(self, env_with_reminder: StateAwareEnvironmentWrapper) -> None:
        """Integration: List -> create_new -> EditReminder -> cancel -> List."""
        env = env_with_reminder
        app = env.get_app_with_class(StatefulReminderApp)

        initial_reminder_count = len(app.reminders)

        # Navigate to create
        _list_state(app).create_new()
        assert isinstance(app.current_state, EditReminder)
        assert app.current_state.reminder_id is None

        # Set some fields
        _edit_state(app).set_title("Will Cancel")

        # Cancel
        _edit_state(app).cancel()

        # Should be back at ReminderList
        assert isinstance(app.current_state, ReminderList)
        assert len(app.navigation_stack) == 0

        # No new reminder should have been created
        assert len(app.reminders) == initial_reminder_count

    def test_edit_and_cancel_flow(self, env_with_reminder: StateAwareEnvironmentWrapper) -> None:
        """Integration: List -> open_reminder -> Detail -> edit -> EditReminder -> cancel -> Detail."""
        env = env_with_reminder
        app = env.get_app_with_class(StatefulReminderApp)

        # Create a reminder
        rid = app.add_reminder(
            title="Original",
            description="Desc",
            due_datetime="2025-01-01 10:00:00",
            repetition_unit=None,
            repetition_value=None,
        )

        # Navigate: List -> Detail -> Edit
        _list_state(app).open_reminder(rid)
        _detail_state(app).edit()
        assert isinstance(app.current_state, EditReminder)
        assert app.current_state.reminder_id == rid

        # Modify but then cancel
        _edit_state(app).set_title("Modified But Cancelled")
        _edit_state(app).cancel()

        # Should be back at ReminderDetail (NOT ReminderList)
        assert isinstance(app.current_state, ReminderDetail)
        assert app.current_state.reminder_id == rid

        # Reminder should be unchanged
        assert app.reminders[rid].title == "Original"

    def test_go_back_from_detail(self, env_with_reminder: StateAwareEnvironmentWrapper) -> None:
        """Integration: List -> open_reminder -> Detail -> go_back -> List."""
        env = env_with_reminder
        app = env.get_app_with_class(StatefulReminderApp)

        # Create a reminder
        rid = app.add_reminder(
            title="Test",
            description="Desc",
            due_datetime="2025-01-01 10:00:00",
            repetition_unit=None,
            repetition_value=None,
        )

        # Navigate to detail
        _list_state(app).open_reminder(rid)
        assert isinstance(app.current_state, ReminderDetail)
        assert len(app.navigation_stack) == 1

        # go_back
        app.go_back()

        assert isinstance(app.current_state, ReminderList)
        assert len(app.navigation_stack) == 0

    def test_go_back_from_edit(self, env_with_reminder: StateAwareEnvironmentWrapper) -> None:
        """Integration: List -> Detail -> EditReminder -> go_back -> Detail."""
        env = env_with_reminder
        app = env.get_app_with_class(StatefulReminderApp)

        # Create a reminder
        rid = app.add_reminder(
            title="Test",
            description="Desc",
            due_datetime="2025-01-01 10:00:00",
            repetition_unit=None,
            repetition_value=None,
        )

        # Navigate: List -> Detail -> Edit
        _list_state(app).open_reminder(rid)
        _detail_state(app).edit()
        assert isinstance(app.current_state, EditReminder)
        assert len(app.navigation_stack) == 2

        # go_back -> should return to Detail (NOT List)
        app.go_back()

        assert isinstance(app.current_state, ReminderDetail)
        assert app.current_state.reminder_id == rid
        assert len(app.navigation_stack) == 1

    def test_deep_navigation_and_go_back(self, env_with_reminder: StateAwareEnvironmentWrapper) -> None:
        """Integration: Complex navigation with multiple go_backs to verify stack integrity."""
        env = env_with_reminder
        app = env.get_app_with_class(StatefulReminderApp)

        # Create two reminders
        rid1 = app.add_reminder(
            title="Reminder 1",
            description="First",
            due_datetime="2025-01-01 10:00:00",
            repetition_unit=None,
            repetition_value=None,
        )
        rid2 = app.add_reminder(
            title="Reminder 2",
            description="Second",
            due_datetime="2025-01-02 10:00:00",
            repetition_unit=None,
            repetition_value=None,
        )

        # Flow 1: View and edit reminder 1
        # List -> open_reminder -> Detail (stack: [List])
        _list_state(app).open_reminder(rid1)
        assert len(app.navigation_stack) == 1

        # Detail -> edit -> Edit (stack: [List, Detail])
        _detail_state(app).edit()
        assert len(app.navigation_stack) == 2

        # Edit -> save -> Detail (stack: [List, Detail, Edit])
        _edit_state(app).set_title("Updated R1")
        _edit_state(app).save()
        assert isinstance(app.current_state, ReminderDetail)
        assert len(app.navigation_stack) == 3

        # go_back multiple times to return to List
        app.go_back()  # -> Edit
        assert isinstance(app.current_state, EditReminder)

        app.go_back()  # -> Detail
        assert isinstance(app.current_state, ReminderDetail)

        app.go_back()  # -> List
        assert isinstance(app.current_state, ReminderList)
        assert len(app.navigation_stack) == 0

        # Flow 2: View reminder 2
        _list_state(app).open_reminder(rid2)
        assert isinstance(app.current_state, ReminderDetail)
        assert app.current_state.reminder_id == rid2

        # go_back to List
        app.go_back()
        assert isinstance(app.current_state, ReminderList)
        assert len(app.navigation_stack) == 0

        # Verify state is clean
        assert app.reminders[rid1].title == "Updated R1"
        assert app.reminders[rid2].title == "Reminder 2"


# =============================================================================
# State Initialization Tests
# =============================================================================


def test_reminder_detail_initialization() -> None:
    """ReminderDetail stores reminder_id correctly."""
    state = ReminderDetail("reminder_123")
    assert state.reminder_id == "reminder_123"


def test_edit_reminder_new_initialization() -> None:
    """EditReminder(None) initializes with empty draft."""
    state = EditReminder(reminder_id=None)
    assert state.reminder_id is None
    assert state.draft.title == ""
    assert state.draft.description == ""
    assert state.draft.due_datetime == ""
    assert state.draft.repetition_unit is None
    assert state.draft.repetition_value is None


def test_edit_reminder_existing_initialization(reminder_app: StatefulReminderApp) -> None:
    """EditReminder(id) stores reminder_id and populates draft on on_enter."""
    rid = reminder_app.add_reminder(
        title="Existing Title",
        description="Existing Description",
        due_datetime="2025-03-15 14:30:00",
        repetition_unit="day",
        repetition_value=7,
    )

    edit_state = EditReminder(reminder_id=rid)
    reminder_app.set_current_state(edit_state)

    # on_enter is called by set_current_state
    assert edit_state.reminder_id == rid
    assert edit_state.draft.title == "Existing Title"
    assert edit_state.draft.description == "Existing Description"
    assert edit_state.draft.due_datetime == "2025-03-15 14:30:00"
    assert edit_state.draft.repetition_unit == "day"
    assert edit_state.draft.repetition_value == 7


# =============================================================================
# Edge Case Tests
# =============================================================================


def test_on_enter_with_invalid_reminder_id(reminder_app: StatefulReminderApp) -> None:
    """EditReminder.on_enter handles missing reminder gracefully (keeps draft empty)."""
    edit_state = EditReminder(reminder_id="nonexistent_id")
    reminder_app.set_current_state(edit_state)

    # Should not crash, draft remains empty
    assert edit_state.draft.title == ""
    assert edit_state.draft.description == ""


def test_delete_clears_navigation_stack(env_with_reminder: StateAwareEnvironmentWrapper) -> None:
    """Delete uses load_root_state which clears the entire navigation stack."""
    env = env_with_reminder
    app = env.get_app_with_class(StatefulReminderApp)

    # Create a reminder
    rid = app.add_reminder(
        title="Test",
        description="Desc",
        due_datetime="2025-01-01 10:00:00",
        repetition_unit=None,
        repetition_value=None,
    )

    # Build up navigation stack: List -> Detail
    _list_state(app).open_reminder(rid)
    assert len(app.navigation_stack) == 1

    # Delete should clear stack
    _detail_state(app).delete()

    assert isinstance(app.current_state, ReminderList)
    assert len(app.navigation_stack) == 0


def test_save_returns_reminder_id(env_with_reminder: StateAwareEnvironmentWrapper) -> None:
    """Save returns the reminder ID which is used for state transition."""
    env = env_with_reminder
    app = env.get_app_with_class(StatefulReminderApp)

    # Create new reminder flow
    _list_state(app).create_new()
    _edit_state(app).set_title("Test Reminder")
    _edit_state(app).set_due_datetime("2025-06-01 10:00:00")

    # Save and capture the result
    edit_state = _edit_state(app)
    result = edit_state.save()

    # Result should be the new reminder ID
    assert result is not None
    assert result in app.reminders
    assert app.reminders[result].title == "Test Reminder"
