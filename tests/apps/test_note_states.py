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
    """Utility to create a minimal CompletedEvent for testing."""
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
    """Create a fresh note app."""
    return StatefulNoteApp(name="note")


def test_starts_in_list(note_app: StatefulNoteApp):
    """App should start in NoteList."""
    assert isinstance(note_app.current_state, NoteList)
    assert note_app.navigation_stack == []


def test_create_note_opens_edit(note_app: StatefulNoteApp):
    """create_note should transition to EditNote."""
    # Trigger tool
    nid = note_app.current_state.new()
    event = _make_event(
        note_app,
        note_app.current_state.new,
        return_value=nid,
    )
    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, EditNote)
    assert note_app.current_state.note_id == nid


def test_edit_save_transitions_to_detail(note_app: StatefulNoteApp):
    """Saving a note should go to NoteDetail."""
    # Create a new note
    nid = note_app.create_note("All")
    note_app.set_current_state(EditNote(nid))

    # Update note
    note_app.current_state.update("My Title", "Hello world")
    event = _make_event(
        note_app,
        note_app.update_note,
        note_id=nid,
    )
    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, NoteDetail)
    assert note_app.current_state.note_id == nid


def test_get_note_opens_detail(note_app: StatefulNoteApp):
    """get_note should show NoteDetail."""
    # Add note
    nid = note_app.create_note("All")

    # Trigger get_note
    note_app.current_state.open(nid)
    event = _make_event(
        note_app,
        note_app.current_state.open,
        note_id=nid,
    )
    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, NoteDetail)
    assert note_app.current_state.note_id == nid


def test_delete_note_transitions_back_to_list(note_app: StatefulNoteApp):
    """Deleting a note should return to NoteList."""
    nid = note_app.create_note("All")
    note_app.set_current_state(NoteDetail(nid))

    # Delete
    note_app.current_state.delete()
    event = _make_event(
        note_app,
        note_app.delete_note,
        note_id=nid,
    )
    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, NoteList)
    assert note_app.current_state.folder == "All"


def test_move_note_transitions_to_folder(note_app: StatefulNoteApp):
    """move_note should switch to NoteList of the target folder."""
    nid = note_app.create_note("All")
    new_folder = "Work"

    note_app.set_current_state(NoteDetail(nid))
    note_app.current_state.app.move_note(nid, new_folder)
    event = _make_event(
        note_app,
        note_app.move_note,
        note_id=nid,
        new_folder=new_folder,
    )
    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, NoteList)
    assert note_app.current_state.folder == new_folder


def test_duplicate_note_opens_detail(note_app: StatefulNoteApp):
    """duplicate_note should open the duplicated note's detail view."""
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
    """search_notes should open NoteList(search_mode=True)."""
    # Trigger search
    note_app.current_state.search("hello")
    event = _make_event(
        note_app,
        note_app.current_state.search,
        keyword="hello",
    )
    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, NoteList)
    assert note_app.current_state.search_mode is True



# Attachment tests
def test_add_attachment_keeps_detail(note_app: StatefulNoteApp):
    """add_attachment should remain in NoteDetail."""
    nid = note_app.create_note("All")
    note_app.set_current_state(NoteDetail(nid))

    # Add attachment
    note_app.current_state.add_attachment("file1.png")
    event = _make_event(
        note_app,
        note_app.add_attachment,
        note_id=nid,
        attachment="file1.png",
    )
    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, NoteDetail)
    assert note_app.current_state.note_id == nid
    assert "file1.png" in note_app.notes[nid].attachments


def test_remove_attachment_keeps_detail(note_app: StatefulNoteApp):
    """remove_attachment should remain in NoteDetail."""
    nid = note_app.create_note("All")
    note_app.notes[nid].attachments.append("doc.pdf")  # pre-add
    note_app.set_current_state(NoteDetail(nid))

    note_app.current_state.remove_attachment("doc.pdf")
    event = _make_event(
        note_app,
        note_app.remove_attachment,
        note_id=nid,
        attachment="doc.pdf",
    )
    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, NoteDetail)
    assert "doc.pdf" not in note_app.notes[nid].attachments


def test_list_attachments_keeps_detail(note_app: StatefulNoteApp):
    """list_attachments should remain in detail view."""
    nid = note_app.create_note("All")
    note_app.notes[nid].attachments.extend(["a.png", "b.png"])
    note_app.set_current_state(NoteDetail(nid))

    note_app.current_state.attachments()
    event = _make_event(
        note_app,
        note_app.list_attachments,
        note_id=nid,
    )
    note_app.handle_state_transition(event)

    assert isinstance(note_app.current_state, NoteDetail)
    assert note_app.current_state.note_id == nid
