"""Tests for the stateful note app navigation flow."""

from typing import Any
import pytest

from are.simulation.types import (
    Action,
    CompletedEvent,
    EventMetadata,
    EventType,
)

from pas.apps.note.app import StatefulNotesApp, ReturnedNotes
from pas.apps.note.states import (
    NoteList,
    NoteDetail,
    EditNote,
    FolderList,
)


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
