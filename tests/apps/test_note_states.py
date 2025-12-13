"""Tests for the stateful note app navigation flow."""

from typing import Any
import pytest

from are.simulation.types import (
    Action,
    CompletedEvent,
    EventMetadata,
    EventType,
)

from pas.apps.note.app import StatefulNoteApp
from pas.apps.note.states import (
    NoteList,
    NoteDetail,
    EditNote,
    FolderList,
)


def _make_event(app: StatefulNoteApp, func: callable, return_value: Any = None, **kwargs: Any) -> CompletedEvent:
    action = Action(function=func, args={"self": app, **kwargs}, app=app)
    metadata = EventMetadata()
    metadata.return_value = return_value
    return CompletedEvent(
        event_type=EventType.USER,
        action=action,
        metadata=metadata,
        event_time=0,
        event_id="note-test-event",
    )


@pytest.fixture
def note_app() -> StatefulNoteApp:
    return StatefulNoteApp(name="note")


def test_starts_in_list(note_app: StatefulNoteApp):
    assert isinstance(note_app.current_state, NoteList)
    assert note_app.navigation_stack == []


def test_create_note_opens_edit(note_app: StatefulNoteApp):
    nid = note_app.current_state.new()

    event = _make_event(
        note_app,
        note_app.create_note,
        return_value=nid,
        folder="All",
    )
    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, EditNote)
    assert note_app.current_state.note_id == nid


def test_edit_save_transitions_to_detail(note_app: StatefulNoteApp):
    nid = note_app.create_note("All")
    note_app.set_current_state(EditNote(nid))

    note_app.current_state.update("My Title", "Hello world")

    event = _make_event(
        note_app,
        note_app.update_note,
        return_value=nid,
        note_id=nid,
        title="My Title",
        content="Hello world",
    )
    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, NoteDetail)
    assert note_app.current_state.note_id == nid


def test_open_note_shows_detail(note_app: StatefulNoteApp):
    nid = note_app.create_note("All")

    note_app.current_state.open(nid)

    event = _make_event(
        note_app,
        note_app.get_note,
        note_id=nid,
    )
    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, NoteDetail)
    assert note_app.current_state.note_id == nid


def test_delete_note_transitions_back_to_list(note_app: StatefulNoteApp):
    nid = note_app.create_note("All")
    note_app.set_current_state(NoteDetail(nid))

    note_app.current_state.delete()

    event = _make_event(
        note_app,
        note_app.delete_note,
        return_value="OK",
        note_id=nid,
    )
    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, NoteList)
    assert note_app.current_state.folder == "All"


def test_move_note_transitions_to_folder(note_app: StatefulNoteApp):
    nid = note_app.create_note("All")
    note_app.set_current_state(NoteDetail(nid))

    note_app.move_note(nid, "Work")

    event = _make_event(
        note_app,
        note_app.move_note,
        return_value="OK",
        note_id=nid,
        new_folder="Work",
    )
    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, NoteList)
    assert note_app.current_state.folder == "Work"


def test_duplicate_note_opens_detail(note_app: StatefulNoteApp):
    nid = note_app.create_note("All")
    new_id = note_app.duplicate_note(nid)

    event = _make_event(
        note_app,
        note_app.duplicate_note,
        return_value=new_id,
        note_id=nid,
    )
    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, NoteDetail)
    assert note_app.current_state.note_id == new_id


def test_search_notes_transitions_to_search_list(note_app: StatefulNoteApp):
    note_app.current_state.search("hello")

    event = _make_event(
        note_app,
        note_app.search_notes,
        keyword="hello",
    )
    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, NoteList)
    assert note_app.current_state.search_mode is True


def test_list_folders_transitions_to_folder_list(note_app: StatefulNoteApp):
    note_app.current_state.folders()

    event = _make_event(
        note_app,
        note_app.list_folders,
    )
    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, FolderList)


def test_list_notes_pagination(note_app: StatefulNoteApp):
    for _ in range(12):
        note_app.create_note("All")

    result = note_app.list_notes("All")

    assert isinstance(result, list)
    assert len(result) == 12

def test_get_and_load_state_preserves_folders(note_app: StatefulNoteApp):
    note_app.create_note("Personal")
    note_app.create_note("Work")

    state = note_app.get_state()

    new_app = StatefulNoteApp(name="note")
    new_app.load_state(state)

    folders = new_app.list_folders()
    assert set(folders) == {"All", "Personal", "Work"}
