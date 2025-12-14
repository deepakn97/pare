from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from are.simulation.tool_utils import OperationType, app_tool

if TYPE_CHECKING:
    from are.simulation.types import CompletedEvent

from pas.apps.core import StatefulApp
from pas.apps.note.states import EditNote, FolderList, NoteDetail, NoteList
from pas.apps.tool_decorators import pas_event_registered


@dataclass
class Note:
    """Simple note data container."""

    note_id: str
    title: str
    content: str
    folder: str
    pinned: bool = False
    attachments: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=lambda: time.time())
    updated_at: float = field(default_factory=lambda: time.time())


@dataclass
class ReturnedNotes:
    """Container for paginated note results."""

    notes: list[Note]
    notes_range: tuple[int, int]
    total_returned_notes: int
    total_notes: int


class NoteFolder:
    """Container managing notes within a single folder."""

    def __init__(self, folder_name: str) -> None:
        """Initialize a note folder.

        Args:
            folder_name (str): Name of the folder.
        """
        self.folder_name = folder_name
        self.notes: list[Note] = []

    def add_note(self, note: Note) -> None:
        """Add a note and sort by timestamp.

        Args:
            note (Note): Note to add.
        """
        self.notes.append(note)
        self.notes.sort(key=lambda n: n.updated_at, reverse=True)

    def remove_note(self, note_id: str) -> bool:
        """Remove a note by ID.

        Args:
            note_id (str): ID of note to remove.

        Returns:
            bool: True if removed, False if not found.
        """
        for i, note in enumerate(self.notes):
            if note.note_id == note_id:
                del self.notes[i]
                return True
        return False

    def get_notes(self, offset: int = 0, limit: int = 10) -> ReturnedNotes:
        """Retrieve paginated notes.

        Args:
            offset (int): Starting index.
            limit (int): Maximum number of notes to return.

        Returns:
            ReturnedNotes: Paginated result container.
        """
        total = len(self.notes)
        end = min(offset + limit, total)
        returned = self.notes[offset:end]

        return ReturnedNotes(
            notes=returned, notes_range=(offset, end), total_returned_notes=len(returned), total_notes=total
        )

    def get_note_by_id(self, note_id: str) -> Note | None:
        """Lookup a note by ID.

        Args:
            note_id (str): Target note ID.

        Returns:
            Note | None: Found note or None.
        """
        for note in self.notes:
            if note.note_id == note_id:
                return note
        return None

    def search_notes(self, keyword: str) -> list[Note]:
        """Search notes within this folder.

        Args:
            keyword (str): Search keyword.

        Returns:
            list[Note]: Matched notes.
        """
        keyword_lower = keyword.lower()
        return [n for n in self.notes if keyword_lower in n.title.lower() or keyword_lower in n.content.lower()]

    def get_state(self) -> dict[str, Any]:
        """Serialize folder state.

        Returns:
            dict[str, Any]: Serialized state.
        """
        return {
            "folder_name": self.folder_name,
            "notes": [
                {
                    "note_id": n.note_id,
                    "title": n.title,
                    "content": n.content,
                    "folder": n.folder,
                    "pinned": n.pinned,
                    "attachments": n.attachments,
                    "created_at": n.created_at,
                    "updated_at": n.updated_at,
                }
                for n in self.notes
            ],
        }

    def load_state(self, state_dict: dict[str, Any]) -> None:
        """Deserialize folder state.

        Args:
            state_dict (dict[str, Any]): State to load.
        """
        self.folder_name = state_dict["folder_name"]
        self.notes = [
            Note(
                note_id=n["note_id"],
                title=n["title"],
                content=n["content"],
                folder=n["folder"],
                pinned=n["pinned"],
                attachments=n["attachments"],
                created_at=n["created_at"],
                updated_at=n["updated_at"],
            )
            for n in state_dict["notes"]
        ]
        self.notes.sort(key=lambda n: n.updated_at, reverse=True)


@dataclass
class StatefulNoteApp(StatefulApp):
    """Stateful note-taking application with PAS navigation."""

    name: str | None = None
    folders: dict[str, NoteFolder] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize app with default folders."""
        super().__init__(self.name or "note")

        # Initialize default folders
        default_folders = ["All", "Personal", "Work"]
        for folder_name in default_folders:
            if folder_name not in self.folders:
                self.folders[folder_name] = NoteFolder(folder_name)

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

    def _get_note_from_any_folder(self, note_id: str) -> Note | None:
        """Find a note across all folders.

        Args:
            note_id (str): Note ID to find.

        Returns:
            Note | None: Found note or None.
        """
        for folder in self.folders.values():
            note = folder.get_note_by_id(note_id)
            if note:
                return note
        return None

    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def create_note(self, folder: str = "All") -> str:
        """Create a new empty note in a given folder.

        Args:
            folder (str): Folder to create the note under.

        Returns:
            str: Newly created note ID.
        """
        nid = self._gen()
        note = Note(nid, "", "", folder)

        # Add to specified folder
        if folder in self.folders:
            self.folders[folder].add_note(note)

        if folder != "All" and "All" in self.folders:
            self.folders["All"].add_note(note)

        return nid

    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def get_note(self, note_id: str) -> Note:
        """Retrieve a note by ID.

        Args:
            note_id (str): Target note ID.

        Returns:
            Note: The retrieved note object.

        Raises:
            KeyError: If note not found.
        """
        note = self._get_note_from_any_folder(note_id)
        if note is None:
            raise KeyError(f"Note {note_id} not found")
        return note

    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def update_note(self, note_id: str, title: str, content: str) -> str:
        """Update note title and content.

        Args:
            note_id (str): Target note ID.
            title (str): New title.
            content (str): Updated note body.

        Returns:
            str: Same note ID.

        Raises:
            KeyError: If note not found.
        """
        note = self._get_note_from_any_folder(note_id)
        if note is None:
            raise KeyError(f"Note {note_id} not found")

        note.title = title or content[:50]
        note.content = content
        note.updated_at = time.time()

        for folder in self.folders.values():
            if folder.get_note_by_id(note_id):
                folder.notes.sort(key=lambda n: n.updated_at, reverse=True)

        return note_id

    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def delete_note(self, note_id: str) -> str:
        """Delete a note from all folders.

        Args:
            note_id (str): ID of note to delete.

        Returns:
            str: Confirmation string "OK".
        """
        for folder in self.folders.values():
            folder.remove_note(note_id)
        return "OK"

    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def list_notes(self, folder: str, offset: int = 0, limit: int = 10) -> ReturnedNotes:
        """List notes under a specific folder with pagination.

        Args:
            folder (str): Folder name.
            offset (int): Starting index.
            limit (int): Maximum notes to return.

        Returns:
            ReturnedNotes: Paginated notes result.
        """
        if folder not in self.folders:
            return ReturnedNotes(notes=[], notes_range=(0, 0), total_returned_notes=0, total_notes=0)

        return self.folders[folder].get_notes(offset, limit)

    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def list_folders(self) -> list[str]:
        """List all folder names.

        Returns:
            list[str]: Folder list.
        """
        return list(self.folders.keys())

    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def move_note(self, note_id: str, new_folder: str) -> str:
        """Move a note to another folder.

        Args:
            note_id (str): ID of note to move.
            new_folder (str): Destination folder.

        Returns:
            str: Confirmation "OK".

        Raises:
            KeyError: If note not found.
        """
        note = self._get_note_from_any_folder(note_id)
        if note is None:
            raise KeyError(f"Note {note_id} not found")

        old_folder = note.folder
        note.folder = new_folder

        # Remove from old folder (except "All")
        if old_folder != "All" and old_folder in self.folders:
            self.folders[old_folder].remove_note(note_id)

        # Add to new folder (except "All", it already has it)
        if new_folder != "All" and new_folder in self.folders and not self.folders[new_folder].get_note_by_id(note_id):
            self.folders[new_folder].add_note(note)

        return "OK"

    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def duplicate_note(self, note_id: str) -> str:
        """Create a duplicated copy of a note.

        Args:
            note_id (str): ID of the note to copy.

        Returns:
            str: ID of newly created duplicate.

        Raises:
            KeyError: If note not found.
        """
        old = self._get_note_from_any_folder(note_id)
        if old is None:
            raise KeyError(f"Note {note_id} not found")

        nid = self._gen()
        new_note = Note(
            note_id=nid,
            title=old.title + " Copy",
            content=old.content,
            folder=old.folder,
            pinned=False,
            attachments=old.attachments.copy(),
        )

        # Add to same folders as original
        if old.folder in self.folders:
            self.folders[old.folder].add_note(new_note)

        if old.folder != "All" and "All" in self.folders:
            self.folders["All"].add_note(new_note)

        return nid

    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def search_notes(self, keyword: str, folder: str = "All") -> list[Note]:
        """Search notes by keyword in title or body.

        Args:
            keyword (str): Search pattern.
            folder (str): Folder to search within.

        Returns:
            list[Note]: Matched notes.
        """
        if folder not in self.folders:
            return []

        return self.folders[folder].search_notes(keyword)

    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def add_attachment(self, note_id: str, attachment: str) -> str:
        """Attach a file reference to a note.

        Args:
            note_id (str): Note to modify.
            attachment (str): Attachment identifier.

        Returns:
            str: "OK".

        Raises:
            KeyError: If note not found.
        """
        note = self._get_note_from_any_folder(note_id)
        if note is None:
            raise KeyError(f"Note {note_id} not found")

        note.attachments.append(attachment)
        return "OK"

    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def remove_attachment(self, note_id: str, attachment: str) -> str:
        """Remove an attachment from a note.

        Args:
            note_id (str): Target note ID.
            attachment (str): Attachment to remove.

        Returns:
            str: "OK".

        Raises:
            KeyError: If note not found.
        """
        note = self._get_note_from_any_folder(note_id)
        if note is None:
            raise KeyError(f"Note {note_id} not found")

        if attachment in note.attachments:
            note.attachments.remove(attachment)

        return "OK"

    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def list_attachments(self, note_id: str) -> list[str]:
        """List attachment identifiers for a note.

        Args:
            note_id (str): Target note ID.

        Returns:
            list[str]: Attachment list.

        Raises:
            KeyError: If note not found.
        """
        note = self._get_note_from_any_folder(note_id)
        if note is None:
            raise KeyError(f"Note {note_id} not found")

        return note.attachments

    def get_state(self) -> dict[str, Any]:
        """Serialize app state.

        Returns:
            dict[str, Any]: Complete app state.
        """
        return {
            "folders": {k: v.get_state() for k, v in self.folders.items()},
        }

    def load_state(self, state_dict: dict[str, Any]) -> None:
        """Deserialize app state.

        Args:
            state_dict (dict[str, Any]): State to restore.
        """
        self.folders.clear()
        for folder_name, folder_state in state_dict.get("folders", {}).items():
            folder = NoteFolder(folder_name)
            folder.load_state(folder_state)
            self.folders[folder_name] = folder

    def _resolve_note_id(self, args: dict[str, Any], metadata: object | None) -> str | None:
        """Extract note_id from args or metadata.

        Args:
            args: Function arguments dictionary.
            metadata: Return value from the completed event.

        Returns:
            str | None: Extracted note ID or None.
        """
        note_id = args.get("note_id")
        if isinstance(note_id, str):
            return note_id
        if isinstance(metadata, str):
            return metadata
        return None

    def handle_state_transition(self, event: CompletedEvent) -> None:
        """Core navigation handler mapping backend operations to state transitions."""
        current_state = self.current_state
        fname = event.function_name()

        if current_state is None or fname is None:
            return

        action = event.action
        args = action.resolved_args or action.args

        metadata_value = event.metadata.return_value if event.metadata else None

        if isinstance(current_state, NoteList):
            self._handle_note_list_transition(fname, args, metadata_value)
        elif isinstance(current_state, NoteDetail):
            self._handle_note_detail_transition(fname, args, metadata_value)
        elif isinstance(current_state, EditNote):
            self._handle_edit_note_transition(fname, args, metadata_value)
        elif isinstance(current_state, FolderList):
            self._handle_folder_list_transition(fname, args, metadata_value)

    def _handle_note_list_transition(self, fname: str, args: dict[str, Any], metadata: object | None) -> None:
        """Process transitions from the note list view."""
        if fname in {"create_note", "new"}:
            note_id = self._resolve_note_id(args, metadata)
            if note_id:
                self.set_current_state(EditNote(note_id))
            return

        if fname in {"get_note", "open"}:
            note_id = self._resolve_note_id(args, metadata)
            if note_id:
                self.set_current_state(NoteDetail(note_id))
            return

        if fname in {"search", "search_notes"}:
            self.set_current_state(NoteList(search_mode=True))
            return

        if fname == "list_folders":
            self.set_current_state(FolderList())

    def _handle_note_detail_transition(self, fname: str, args: dict[str, Any], metadata: object | None) -> None:
        """Process transitions from the note detail view."""
        if fname == "edit":
            note_id = self._resolve_note_id(args, metadata)
            if note_id:
                self.set_current_state(EditNote(note_id))
            return

        if fname == "delete_note" and self.navigation_stack:
            self.go_back()
            return

        if fname == "duplicate_note":
            note_id = self._resolve_note_id(args, metadata)
            if note_id:
                self.set_current_state(NoteDetail(note_id))
            return

        if fname == "move_note":
            folder = args.get("new_folder")
            if isinstance(folder, str):
                self.set_current_state(NoteList(folder))

    def _handle_edit_note_transition(self, fname: str, args: dict[str, Any], metadata: object | None) -> None:
        """Process transitions from the edit note view."""
        if fname == "update_note":
            if self.navigation_stack:
                self.go_back()
            else:
                note_id = self._resolve_note_id(args, metadata)
                if note_id:
                    self.set_current_state(NoteDetail(note_id))

    def _handle_folder_list_transition(self, fname: str, args: dict[str, Any], metadata: object | None) -> None:
        """Process transitions from the folder list view."""
        if fname == "list_notes":
            folder = args.get("folder")
            if isinstance(folder, str):
                self.set_current_state(NoteList(folder))
        if fname == "open":
            folder = args.get("folder")
            if isinstance(folder, str):
                self.set_current_state(NoteList(folder))
