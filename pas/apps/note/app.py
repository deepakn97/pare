from __future__ import annotations

import time
import uuid

from are.simulation.types import CompletedEvent, OperationType

from pas.apps.core import StatefulApp
from pas.apps.note.states import EditNote, FolderList, NoteDetail, NoteList
from pas.apps.tool_decorators import pas_event_registered, user_tool


class Note:
    """Simple note data container."""

    def __init__(self, note_id: str, title: str, content: str, folder: str) -> None:
        """Initialize a note object.

        Args:
            note_id (str): Unique identifier of the note.
            title (str): Title text.
            content (str): Full note content.
            folder (str): Folder/category name.
        """
        self.note_id = note_id
        self.title = title
        self.content = content
        self.folder = folder
        self.pinned = False
        self.attachments: list[str] = []
        self.created_at = time.time()
        self.updated_at = time.time()


class StatefulNoteApp(StatefulApp):
    """Stateful note-taking application with PAS navigation."""

    def __init__(self, name: str = "note") -> None:
        """Initialize the note app and load root state.

        Args:
            name (str): Name of the app instance.
        """
        super().__init__(name=name)
        self.notes: dict[str, Note] = {}
        self.folders: list[str] = ["All", "Personal", "Work"]
        self.load_root_state()

    def create_root_state(self) -> NoteList:
        """Return the root navigation state.

        Returns:
            NoteList: Default folder view.
        """
        return NoteList("All")

    def _gen(self) -> str:
        """Generate a unique note ID.

        Returns:
            str: Newly generated ID.
        """
        return uuid.uuid4().hex

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def create_note(self, folder: str = "All") -> str:
        """Create a new empty note in a given folder.

        Args:
            folder (str): Folder to create the note under.

        Returns:
            str: Newly created note ID.
        """
        nid = self._gen()
        self.notes[nid] = Note(nid, "", "", folder)
        return nid

    @user_tool()
    @pas_event_registered()
    def get_note(self, note_id: str) -> Note:
        """Retrieve a note by ID.

        Args:
            note_id (str): Target note ID.

        Returns:
            Note: The retrieved note object.
        """
        return self.notes[note_id]

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def update_note(self, note_id: str, title: str, content: str) -> str:
        """Update note title and content.

        Args:
            note_id (str): Target note ID.
            title (str): New title.
            content (str): Updated note body.

        Returns:
            str: Same note ID.
        """
        n = self.notes[note_id]
        n.title = title or content[:50]
        n.content = content
        n.updated_at = time.time()
        return note_id

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def delete_note(self, note_id: str) -> str:
        """Delete a note.

        Args:
            note_id (str): ID of note to delete.

        Returns:
            str: Confirmation string ``"OK"``.
        """
        del self.notes[note_id]
        return "OK"

    @user_tool()
    @pas_event_registered()
    def list_notes(self, folder: str) -> list[Note]:
        """List notes under a specific folder.

        Args:
            folder (str): Folder name.

        Returns:
            list[Note]: Filtered notes list.
        """
        if folder == "All":
            return list(self.notes.values())
        return [n for n in self.notes.values() if n.folder == folder]

    @user_tool()
    @pas_event_registered()
    def list_folders(self) -> list[str]:
        """List all folder names.

        Returns:
            list[str]: Folder list.
        """
        return self.folders

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def move_note(self, note_id: str, new_folder: str) -> str:
        """Move a note to another folder.

        Args:
            note_id (str): ID of note to move.
            new_folder (str): Destination folder.

        Returns:
            str: Confirmation ``"OK"``.
        """
        self.notes[note_id].folder = new_folder
        return "OK"

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def duplicate_note(self, note_id: str) -> str:
        """Create a duplicated copy of a note.

        Args:
            note_id (str): ID of the note to copy.

        Returns:
            str: ID of newly created duplicate.
        """
        old = self.notes[note_id]
        nid = self._gen()
        self.notes[nid] = Note(nid, old.title + " Copy", old.content, old.folder)
        return nid

    @user_tool()
    @pas_event_registered()
    def search_notes(self, keyword: str) -> list[Note]:
        """Search notes by keyword in title or body.

        Args:
            keyword (str): Search pattern.

        Returns:
            list[Note]: Matched notes.
        """
        keyword = keyword.lower()
        return [n for n in self.notes.values() if keyword in n.title.lower() or keyword in n.content.lower()]

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def add_attachment(self, note_id: str, attachment: str) -> str:
        """Attach a file reference to a note.

        Args:
            note_id (str): Note to modify.
            attachment (str): Attachment identifier.

        Returns:
            str: ``"OK"``.
        """
        self.notes[note_id].attachments.append(attachment)
        return "OK"

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def remove_attachment(self, note_id: str, attachment: str) -> str:
        """Remove an attachment from a note.

        Args:
            note_id (str): Target note ID.
            attachment (str): Attachment to remove.

        Returns:
            str: ``"OK"``.
        """
        if attachment in self.notes[note_id].attachments:
            self.notes[note_id].attachments.remove(attachment)
        return "OK"

    @user_tool()
    @pas_event_registered()
    def list_attachments(self, note_id: str) -> list[str]:
        """List attachment identifiers for a note.

        Args:
            note_id (str): Target note ID.

        Returns:
            list[str]: Attachment list.
        """
        return self.notes[note_id].attachments


    def _apply_transition(self, func: str, args: dict[str, object], result: str | None) -> None:
        """Apply navigation transition for the given function name."""
        handler = getattr(self, f"_transition_{func}", None)
        if callable(handler):
            handler(args, result)


    def _transition_new(self, args: dict[str, object], result: str | None) -> None:
        if isinstance(result, str):
            self.set_current_state(EditNote(result))

    def _transition_create_note(self, args: dict[str, object], result: str | None) -> None:
        if isinstance(result, str):
            self.set_current_state(EditNote(result))

    def _transition_open(self, args: dict[str, object], result: str | None) -> None:
        nid = args.get("note_id")
        if isinstance(nid, str):
            self.set_current_state(NoteDetail(nid))

    def _transition_edit(self, args: dict[str, object], result: str | None) -> None:
        nid = args.get("note_id")
        if isinstance(nid, str):
            self.set_current_state(EditNote(nid))

    def _transition_search(self, args: dict[str, object], result: str | None) -> None:
        self.set_current_state(NoteList(search_mode=True))

    def _transition_search_notes(self, args: dict[str, object], result: str | None) -> None:
        self.set_current_state(NoteList(search_mode=True))

    def _transition_get_note(self, args: dict[str, object], result: str | None) -> None:
        nid = args.get("note_id")
        if isinstance(nid, str):
            self.set_current_state(NoteDetail(nid))

    def _transition_update_note(self, args: dict[str, object], result: str | None) -> None:
        nid = args.get("note_id")
        if isinstance(nid, str):
            self.set_current_state(NoteDetail(nid))

    def _transition_delete_note(self, args: dict[str, object], result: str | None) -> None:
        self.set_current_state(NoteList("All"))

    def _transition_move_note(self, args: dict[str, object], result: str | None) -> None:
        folder = args.get("new_folder")
        if isinstance(folder, str):
            self.set_current_state(NoteList(folder))

    def _transition_duplicate_note(self, args: dict[str, object], result: str | None) -> None:
        if isinstance(result, str):
            self.set_current_state(NoteDetail(result))

    def _transition_list_notes(self, args: dict[str, object], result: str | None) -> None:
        folder = args.get("folder")
        if isinstance(folder, str):
            self.set_current_state(NoteList(folder))

    def _transition_list_folders(self, args: dict[str, object], result: str | None) -> None:
        self.set_current_state(FolderList())

    def handle_state_transition(self, event: CompletedEvent) -> None:
        """Core navigation handler mapping backend operations to state transitions."""
        func = event.function_name()
        if func is None:
            return

        args = getattr(event.action, "args", {})
        result = event.metadata.return_value

        self._apply_transition(func, args, result)

