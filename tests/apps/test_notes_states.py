"""Tests for the stateful note app navigation flow."""

from __future__ import annotations

from typing import Any

import pytest
from are.simulation.types import (
    Action,
    CompletedEvent,
    EventMetadata,
    EventType,
)

from pas.apps.note.app import Note, ReturnedNotes, StatefulNotesApp
from pas.apps.note.states import (
    EditNote,
    FolderList,
    NoteDetail,
    NoteList,
)
from pas.apps.proactive_aui import PASAgentUserInterface
from pas.apps.system import HomeScreenSystemApp
from pas.environment import StateAwareEnvironmentWrapper

# =============================================================================
# State Helpers
# =============================================================================


def _note_list_state(app: StatefulNotesApp) -> NoteList:
    state = app.current_state
    assert isinstance(state, NoteList)
    return state


def _note_detail_state(app: StatefulNotesApp) -> NoteDetail:
    state = app.current_state
    assert isinstance(state, NoteDetail)
    return state


def _edit_note_state(app: StatefulNotesApp) -> EditNote:
    state = app.current_state
    assert isinstance(state, EditNote)
    return state


def _folder_list_state(app: StatefulNotesApp) -> FolderList:
    state = app.current_state
    assert isinstance(state, FolderList)
    return state


def _make_event(app: StatefulNotesApp, func: callable, return_value: Any = None, **kwargs: Any) -> CompletedEvent:
    """Create a mock event with proper function name."""
    action = Action(function=func, args={"self": app, **kwargs}, app=app)

    # Ensure the action has the function name properly set
    # The key is to make sure function_name() will work
    if hasattr(func, '__name__'):
        action._function_name = func.__name__

    metadata = EventMetadata()
    metadata.return_value = return_value

    event = CompletedEvent(
        event_type=EventType.USER,
        action=action,
        metadata=metadata,
        event_time=0,
        event_id="note-test-event",
    )

    return event


@pytest.fixture
def note_app() -> StatefulNotesApp:
    return StatefulNotesApp(name="note")


@pytest.fixture
def env_with_note() -> StateAwareEnvironmentWrapper:
    """Create environment with note app registered and opened."""
    env = StateAwareEnvironmentWrapper()
    system_app = HomeScreenSystemApp(name="HomeScreen")
    aui_app = PASAgentUserInterface()
    note_app = StatefulNotesApp(name="note")
    env.register_apps([system_app, aui_app, note_app])
    env._open_app("note")
    return env


# =============================================================================
# Existing Unit Tests
# =============================================================================


def test_starts_in_list(note_app: StatefulNotesApp):
    assert isinstance(note_app.current_state, NoteList)
    assert note_app.navigation_stack == []


def test_create_note_opens_edit(note_app: StatefulNotesApp):
    nid = note_app.current_state.new_note()

    # The function that gets called is the user tool, but the transition
    # checks for the backend method name
    event = _make_event(
        note_app,
        note_app.current_state.new_note,  # Use the state method
        return_value=nid,
    )

    # Manually set function name to match what transition handler expects
    event.action._function_name = "new_note"

    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, EditNote)
    assert note_app.current_state.note_id == nid


def test_edit_save_transitions_to_detail(note_app: StatefulNotesApp):
    nid = note_app.create_note("Inbox")
    note_app.set_current_state(NoteDetail(nid))
    note_app.set_current_state(EditNote(nid))

    note_app.current_state.update("My Title", "Hello world")

    event = _make_event(
        note_app,
        note_app.current_state.update,
        return_value=nid,
        title="My Title",
        content="Hello world",
    )
    event.action._function_name = "update"

    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, NoteDetail)
    assert note_app.current_state.note_id == nid


def test_open_note_shows_detail(note_app: StatefulNotesApp):
    nid = note_app.create_note("Inbox")

    note_app.current_state.open(nid)

    event = _make_event(
        note_app,
        note_app.current_state.open,
        note_id=nid,
    )
    event.action._function_name = "open"

    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, NoteDetail)
    assert note_app.current_state.note_id == nid


def test_delete_note_transitions_back_to_list(note_app: StatefulNotesApp):
    nid = note_app.create_note("Inbox")
    original_state = note_app.current_state
    note_app.set_current_state(NoteDetail(nid))

    note_app.current_state.delete()

    event = _make_event(
        note_app,
        note_app.current_state.delete,
        return_value=nid,
    )
    event.action._function_name = "delete"

    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, NoteList)
    assert note_app.current_state.folder == "Inbox"


def test_move_note_transitions_to_folder(note_app: StatefulNotesApp):
    nid = note_app.create_note("Inbox")
    note_app.set_current_state(NoteDetail(nid))

    note_app.current_state.move("Work")

    event = _make_event(
        note_app,
        note_app.current_state.move,
        return_value=nid,
        dest_folder_name="Work",
    )
    event.action._function_name = "move"

    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, NoteList)
    assert note_app.current_state.folder == "Work"


def test_duplicate_note_opens_detail(note_app: StatefulNotesApp):
    nid = note_app.create_note("Inbox")
    note_app.set_current_state(NoteDetail(nid))

    new_id = note_app.current_state.duplicate()

    event = _make_event(
        note_app,
        note_app.current_state.duplicate,
        return_value=new_id,
    )
    event.action._function_name = "duplicate"

    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, NoteDetail)
    assert note_app.current_state.note_id == new_id


def test_search_notes_stays_in_list(note_app: StatefulNotesApp):
    note_app.current_state.search("hello")

    event = _make_event(
        note_app,
        note_app.current_state.search,
        query="hello",
    )
    event.action._function_name = "search"

    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, NoteList)
    assert note_app.current_state.folder == "Inbox"


def test_list_folders_transitions_to_folder_list(note_app: StatefulNotesApp):
    note_app.current_state.list_folders()

    event = _make_event(
        note_app,
        note_app.current_state.list_folders,
    )
    event.action._function_name = "list_folders"

    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, FolderList)


def test_list_notes_pagination(note_app: StatefulNotesApp):
    for _ in range(12):
        note_app.create_note("Inbox")

    result = note_app.list_notes("Inbox", offset=0, limit=10)

    assert isinstance(result, ReturnedNotes)
    assert result.total_notes == 12
    assert len(result.notes) == 10
    assert result.notes_range == (0, 10)


def test_get_and_load_state_preserves_folders(note_app: StatefulNotesApp):
    note_app.create_note("Personal")
    note_app.create_note("Work")

    state = note_app.get_state()

    new_app = StatefulNotesApp(name="note")
    new_app.load_state(state)

    folders = new_app.list_folders()
    assert set(folders) == {"Inbox", "Personal", "Work"}


def test_go_back_from_folder_list(note_app: StatefulNotesApp):
    """Test going back from FolderList to NoteList."""
    assert isinstance(note_app.current_state, NoteList)

    note_app.set_current_state(FolderList())
    assert len(note_app.navigation_stack) == 1

    note_app.go_back()
    assert isinstance(note_app.current_state, NoteList)
    assert note_app.current_state.folder == "Inbox"
    assert len(note_app.navigation_stack) == 0


def test_create_and_delete_custom_folder(note_app: StatefulNotesApp):
    """Test creating and deleting custom folders."""
    folder_name = note_app.new_folder("Projects")
    assert folder_name == "Projects"
    assert "Projects" in note_app.list_folders()


    deleted = note_app.delete_folder("Projects")
    assert deleted == "Projects"
    assert "Projects" not in note_app.list_folders()


def test_cannot_delete_default_folders(note_app: StatefulNotesApp):
    """Test that default folders cannot be deleted."""
    with pytest.raises(KeyError, match="Cannot delete default folder"):
        note_app.delete_folder("Inbox")

    with pytest.raises(KeyError, match="Cannot delete default folder"):
        note_app.delete_folder("Personal")

    with pytest.raises(KeyError, match="Cannot delete default folder"):
        note_app.delete_folder("Work")


def test_rename_folder(note_app: StatefulNotesApp):
    """Test renaming a folder."""
    note_app.new_folder("OldName")


    new_name = note_app.rename_folder("OldName", "NewName")
    assert new_name == "NewName"

    folders = note_app.list_folders()
    assert "NewName" in folders
    assert "OldName" not in folders


def test_cannot_rename_default_folders(note_app: StatefulNotesApp):
    """Test that default folders cannot be renamed."""
    with pytest.raises(KeyError, match="Cannot rename default folder"):
        note_app.rename_folder("Inbox", "MyInbox")


# =============================================================================
# Missing Unit Tests (using _make_event pattern)
# =============================================================================


def test_edit_transition(note_app: StatefulNotesApp) -> None:
    """Handler: edit event transitions from NoteDetail to EditNote."""
    # Setup: create a note and navigate to NoteDetail
    nid = note_app.create_note("Inbox", title="Test Note", content="Test content")
    note_app.set_current_state(NoteDetail(nid))

    # Call the tool and verify functionality
    result = note_app.current_state.edit()
    assert isinstance(result, str)
    assert result == nid  # Should return the note_id

    # Create event and call handler
    event = _make_event(note_app, note_app.current_state.edit, return_value=nid)
    event.action._function_name = "edit"
    note_app.handle_state_transition(event)

    # Verify transition
    assert isinstance(note_app.current_state, EditNote)
    assert note_app.current_state.note_id == nid


def test_folder_open_transition(note_app: StatefulNotesApp) -> None:
    """Handler: open event transitions from FolderList to NoteList."""
    # Setup: create notes in Work folder and navigate to FolderList
    note_app.create_note("Work", title="Work Note", content="Work content")
    note_app.set_current_state(FolderList())

    # Call the tool and verify functionality
    result = note_app.current_state.open("Work")
    assert isinstance(result, list)
    assert len(result) == 1  # Should have one note in Work

    # Create event and call handler
    event = _make_event(note_app, note_app.current_state.open, folder="Work")
    event.action._function_name = "open"
    note_app.handle_state_transition(event)

    # Verify transition
    assert isinstance(note_app.current_state, NoteList)
    assert note_app.current_state.folder == "Work"


# =============================================================================
# Self-Loop Unit Tests (using _make_event pattern)
# =============================================================================


def test_list_notes_no_transition(note_app: StatefulNotesApp) -> None:
    """Handler: list_notes should not change state."""
    # Setup: create notes
    for i in range(5):
        note_app.create_note("Inbox", title=f"Note {i}", content=f"Content {i}")

    assert isinstance(note_app.current_state, NoteList)

    # Call tool and verify functionality
    result = note_app.current_state.list_notes(offset=0, limit=3)
    assert isinstance(result, ReturnedNotes)
    assert result.total_notes == 5
    assert len(result.notes) == 3

    # Create event and call handler
    event = _make_event(note_app, note_app.current_state.list_notes, return_value=result)
    event.action._function_name = "list_notes"
    note_app.handle_state_transition(event)

    # Verify no transition
    assert isinstance(note_app.current_state, NoteList)
    assert note_app.current_state.folder == "Inbox"


def test_refresh_no_transition(note_app: StatefulNotesApp) -> None:
    """Handler: refresh should not change state."""
    # Setup: create note and navigate to NoteDetail
    nid = note_app.create_note("Inbox", title="Test", content="Content")
    note_app.set_current_state(NoteDetail(nid))

    # Call tool and verify functionality
    result = note_app.current_state.refresh()
    assert isinstance(result, Note)
    assert result.note_id == nid
    assert result.title == "Test"

    # Create event and call handler
    event = _make_event(note_app, note_app.current_state.refresh, return_value=result)
    event.action._function_name = "refresh"
    note_app.handle_state_transition(event)

    # Verify no transition
    assert isinstance(note_app.current_state, NoteDetail)
    assert note_app.current_state.note_id == nid


def test_list_attachments_no_transition(note_app: StatefulNotesApp) -> None:
    """Handler: list_attachments should not change state."""
    # Setup: create note and navigate to NoteDetail
    nid = note_app.create_note("Inbox", title="Test", content="Content")
    note_app.set_current_state(NoteDetail(nid))

    # Call tool and verify functionality
    result = note_app.current_state.list_attachments()
    assert isinstance(result, list)
    assert len(result) == 0  # No attachments yet

    # Create event and call handler
    event = _make_event(note_app, note_app.current_state.list_attachments, return_value=result)
    event.action._function_name = "list_attachments"
    note_app.handle_state_transition(event)

    # Verify no transition
    assert isinstance(note_app.current_state, NoteDetail)
    assert note_app.current_state.note_id == nid


def test_folder_list_folders_no_transition(note_app: StatefulNotesApp) -> None:
    """Handler: list_folders in FolderList should not change state."""
    # Setup: navigate to FolderList
    note_app.set_current_state(FolderList())

    # Call tool and verify functionality
    result = note_app.current_state.list_folders()
    assert isinstance(result, list)
    assert "Inbox" in result
    assert "Personal" in result
    assert "Work" in result

    # Create event and call handler
    event = _make_event(note_app, note_app.current_state.list_folders, return_value=result)
    event.action._function_name = "list_folders"
    note_app.handle_state_transition(event)

    # Verify no transition
    assert isinstance(note_app.current_state, FolderList)


# =============================================================================
# Integration Tests (using StateAwareEnvironmentWrapper)
# =============================================================================


class TestNoteIntegration:
    """Integration tests that exercise the full environment flow."""

    def test_create_and_edit_note_flow(self, env_with_note: StateAwareEnvironmentWrapper) -> None:
        """Integration: NoteList -> new_note -> EditNote -> update -> NoteDetail."""
        app = env_with_note.get_app_with_class(StatefulNotesApp)

        # Start at NoteList
        assert isinstance(app.current_state, NoteList)
        assert len(app.navigation_stack) == 0

        # Step 1: new_note -> EditNote
        nid = _note_list_state(app).new_note()
        assert isinstance(app.current_state, EditNote)
        assert app.current_state.note_id == nid
        assert len(app.navigation_stack) == 1

        # Step 2: update -> NoteDetail
        _edit_note_state(app).update("My Title", "My Content")
        assert isinstance(app.current_state, NoteDetail)
        assert app.current_state.note_id == nid
        assert len(app.navigation_stack) == 2

        # Verify note content
        note = app.get_note_by_id(nid)
        assert note.title == "My Title"
        assert note.content == "My Content"

    def test_open_edit_save_flow(self, env_with_note: StateAwareEnvironmentWrapper) -> None:
        """Integration: NoteList -> open -> NoteDetail -> edit -> EditNote -> update -> NoteDetail."""
        app = env_with_note.get_app_with_class(StatefulNotesApp)

        # Setup: create a note
        nid = app.create_note("Inbox", title="Original Title", content="Original Content")

        # Start at NoteList
        assert isinstance(app.current_state, NoteList)

        # Step 1: open -> NoteDetail
        _note_list_state(app).open(nid)
        assert isinstance(app.current_state, NoteDetail)
        assert len(app.navigation_stack) == 1

        # Step 2: edit -> EditNote
        _note_detail_state(app).edit()
        assert isinstance(app.current_state, EditNote)
        assert len(app.navigation_stack) == 2

        # Step 3: update -> NoteDetail
        _edit_note_state(app).update("Updated Title", "Updated Content")
        assert isinstance(app.current_state, NoteDetail)
        assert len(app.navigation_stack) == 3

        # Verify updated content
        note = app.get_note_by_id(nid)
        assert note.title == "Updated Title"
        assert note.content == "Updated Content"

    def test_folder_navigation_flow(self, env_with_note: StateAwareEnvironmentWrapper) -> None:
        """Integration: NoteList(Inbox) -> list_folders -> FolderList -> open(Work) -> NoteList(Work)."""
        app = env_with_note.get_app_with_class(StatefulNotesApp)

        # Start at NoteList(Inbox)
        assert isinstance(app.current_state, NoteList)
        assert app.current_state.folder == "Inbox"

        # Step 1: list_folders -> FolderList
        _note_list_state(app).list_folders()
        assert isinstance(app.current_state, FolderList)
        assert len(app.navigation_stack) == 1

        # Step 2: open(Work) -> NoteList(Work)
        _folder_list_state(app).open("Work")
        assert isinstance(app.current_state, NoteList)
        assert app.current_state.folder == "Work"
        assert len(app.navigation_stack) == 2

    def test_duplicate_note_flow(self, env_with_note: StateAwareEnvironmentWrapper) -> None:
        """Integration: NoteList -> open -> NoteDetail -> duplicate -> NoteDetail(new)."""
        app = env_with_note.get_app_with_class(StatefulNotesApp)

        # Setup: create a note
        nid = app.create_note("Inbox", title="Original", content="Content")

        # Step 1: open -> NoteDetail
        _note_list_state(app).open(nid)
        assert isinstance(app.current_state, NoteDetail)
        original_note_id = app.current_state.note_id

        # Step 2: duplicate -> NoteDetail(new)
        new_id = _note_detail_state(app).duplicate()
        assert isinstance(app.current_state, NoteDetail)
        assert app.current_state.note_id == new_id
        assert new_id != original_note_id

        # Verify new note has "Copy of" prefix
        new_note = app.get_note_by_id(new_id)
        assert new_note.title.startswith("Copy of")

    def test_move_note_flow(self, env_with_note: StateAwareEnvironmentWrapper) -> None:
        """Integration: NoteList(Inbox) -> open -> NoteDetail -> move(Work) -> NoteList(Work)."""
        app = env_with_note.get_app_with_class(StatefulNotesApp)

        # Setup: create a note in Inbox
        nid = app.create_note("Inbox", title="Test", content="Content")

        # Step 1: open -> NoteDetail
        _note_list_state(app).open(nid)
        assert isinstance(app.current_state, NoteDetail)

        # Step 2: move(Work) -> NoteList(Work)
        _note_detail_state(app).move("Work")
        assert isinstance(app.current_state, NoteList)
        assert app.current_state.folder == "Work"

        # Verify note is in Work folder
        work_notes = app.folders["Work"].notes
        inbox_notes = app.folders["Inbox"].notes
        assert nid in work_notes
        assert nid not in inbox_notes

    def test_go_back_from_note_detail(self, env_with_note: StateAwareEnvironmentWrapper) -> None:
        """Integration: NoteList -> open -> NoteDetail -> go_back -> NoteList."""
        app = env_with_note.get_app_with_class(StatefulNotesApp)

        # Setup: create a note
        nid = app.create_note("Inbox", title="Test", content="Content")

        # Step 1: open -> NoteDetail
        _note_list_state(app).open(nid)
        assert isinstance(app.current_state, NoteDetail)
        assert len(app.navigation_stack) == 1

        # Step 2: go_back -> NoteList
        app.go_back()
        assert isinstance(app.current_state, NoteList)
        assert len(app.navigation_stack) == 0

    def test_go_back_from_edit_note(self, env_with_note: StateAwareEnvironmentWrapper) -> None:
        """Integration: NoteList -> open -> NoteDetail -> edit -> EditNote -> go_back -> NoteDetail."""
        app = env_with_note.get_app_with_class(StatefulNotesApp)

        # Setup: create a note
        nid = app.create_note("Inbox", title="Test", content="Content")

        # Navigate to EditNote
        _note_list_state(app).open(nid)
        _note_detail_state(app).edit()
        assert isinstance(app.current_state, EditNote)
        assert len(app.navigation_stack) == 2

        # go_back -> NoteDetail (NOT NoteList)
        app.go_back()
        assert isinstance(app.current_state, NoteDetail)
        assert len(app.navigation_stack) == 1

    def test_go_back_chain(self, env_with_note: StateAwareEnvironmentWrapper) -> None:
        """Integration: NoteList -> open -> NoteDetail -> edit -> EditNote -> go_back -> go_back -> NoteList."""
        app = env_with_note.get_app_with_class(StatefulNotesApp)

        # Setup: create a note
        nid = app.create_note("Inbox", title="Test", content="Content")

        # Build navigation stack
        _note_list_state(app).open(nid)  # -> NoteDetail
        _note_detail_state(app).edit()  # -> EditNote
        assert len(app.navigation_stack) == 2

        # Chain of go_back
        app.go_back()  # -> NoteDetail
        assert isinstance(app.current_state, NoteDetail)
        assert len(app.navigation_stack) == 1

        app.go_back()  # -> NoteList
        assert isinstance(app.current_state, NoteList)
        assert len(app.navigation_stack) == 0

    def test_delete_returns_to_previous(self, env_with_note: StateAwareEnvironmentWrapper) -> None:
        """Integration: NoteList -> open -> NoteDetail -> delete -> NoteList."""
        app = env_with_note.get_app_with_class(StatefulNotesApp)

        # Setup: create a note
        nid = app.create_note("Inbox", title="Test", content="Content")

        # Navigate to NoteDetail
        _note_list_state(app).open(nid)
        assert isinstance(app.current_state, NoteDetail)
        assert len(app.navigation_stack) == 1

        # delete -> NoteList (pops stack)
        _note_detail_state(app).delete()
        assert isinstance(app.current_state, NoteList)
        assert len(app.navigation_stack) == 0

        # Verify note is deleted
        with pytest.raises(KeyError):
            app.get_note_by_id(nid)


# =============================================================================
# State Initialization Tests
# =============================================================================


def test_note_list_initialization() -> None:
    """NoteList stores folder context correctly."""
    state = NoteList("Work")
    assert state.folder == "Work"

    state_default = NoteList()
    assert state_default.folder == "Inbox"


def test_note_detail_initialization(note_app: StatefulNotesApp) -> None:
    """NoteDetail stores note_id and loads note on_enter."""
    nid = note_app.create_note("Inbox", title="Test", content="Content")
    state = NoteDetail(nid)
    state.bind_to_app(note_app)

    # Before on_enter, _note should be None
    assert state.note_id == nid
    assert state._note is None

    # After on_enter, _note should be populated
    state.on_enter()
    assert state._note is not None
    assert state._note.note_id == nid


def test_edit_note_initialization(note_app: StatefulNotesApp) -> None:
    """EditNote stores note_id and loads note on_enter."""
    nid = note_app.create_note("Inbox", title="Test", content="Content")
    state = EditNote(nid)
    state.bind_to_app(note_app)

    # Before on_enter, _note should be None
    assert state.note_id == nid
    assert state._note is None

    # After on_enter, _note should be populated
    state.on_enter()
    assert state._note is not None
    assert state._note.note_id == nid


# =============================================================================
# Edge Case Tests
# =============================================================================


def test_go_back_with_empty_stack(note_app: StatefulNotesApp) -> None:
    """go_back with empty stack should handle gracefully."""
    assert isinstance(note_app.current_state, NoteList)
    assert len(note_app.navigation_stack) == 0

    # go_back should not crash
    result = note_app.go_back()
    assert "Already at the initial state" in result

    # Should remain in NoteList
    assert isinstance(note_app.current_state, NoteList)
    assert len(note_app.navigation_stack) == 0


def test_delete_with_empty_stack(note_app: StatefulNotesApp) -> None:
    """Delete when navigation stack is empty should handle gracefully."""
    # Create note directly in NoteDetail without going through NoteList
    nid = note_app.create_note("Inbox", title="Test", content="Content")

    # Manually set state to NoteDetail without building stack
    detail_state = NoteDetail(nid)
    detail_state.bind_to_app(note_app)
    detail_state.on_enter()
    note_app.current_state = detail_state
    # Stack is empty

    assert isinstance(note_app.current_state, NoteDetail)
    assert len(note_app.navigation_stack) == 0

    # Delete should work but not crash on empty stack
    event = _make_event(note_app, detail_state.delete, return_value=nid)
    event.action._function_name = "delete"
    note_app.handle_state_transition(event)

    # State should remain unchanged (handler checks for navigation_stack)
    assert isinstance(note_app.current_state, NoteDetail)


def test_new_note_in_different_folder(note_app: StatefulNotesApp) -> None:
    """Create note in Work folder, not Inbox."""
    # Navigate to Work folder's NoteList
    note_app.set_current_state(NoteList("Work"))

    # Create new note
    nid = note_app.current_state.new_note()

    # Verify note was created in Work folder
    assert nid in note_app.folders["Work"].notes
    assert nid not in note_app.folders["Inbox"].notes


def test_open_nonexistent_note(note_app: StatefulNotesApp) -> None:
    """Try to open a note that doesn't exist."""
    assert isinstance(note_app.current_state, NoteList)

    with pytest.raises(KeyError):
        note_app.current_state.open("nonexistent-note-id")
