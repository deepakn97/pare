from __future__ import annotations

import base64
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from are.simulation.apps.app import Protocol
from are.simulation.tool_utils import OperationType, app_tool, data_tool, env_tool
from are.simulation.types import EventType, disable_events
from are.simulation.utils import get_state_dict, uuid_hex
from are.simulation.utils.type_utils import type_check

if TYPE_CHECKING:
    from are.simulation.types import CompletedEvent

from are.simulation.apps import SandboxLocalFileSystem, VirtualFileSystem

from pare.apps.core import StatefulApp
from pare.apps.note.states import EditNote, FolderList, NoteDetail, NoteList
from pare.apps.note.types import Note, ReturnedNotes
from pare.apps.tool_decorators import pare_event_registered

logger = logging.getLogger(__name__)


class NotesFolder:
    """Container managing notes within a single folder."""

    def __init__(self, folder_name: str) -> None:
        """Initialize a note folder.

        Args:
            folder_name (str): Name of the folder.
        """
        self.folder_name = folder_name
        self.notes: dict[str, Note] = {}

    def add_note(self, note: Note) -> None:
        """Add a note and sort by timestamp.

        Args:
            note (Note): Note to add.
        """
        if not isinstance(note, Note):
            raise TypeError(f"Note must be an instance of Note, got {type(note)}.")
        self.notes[note.note_id] = note

    def remove_note(self, note_id: str) -> bool:
        """Remove a note by ID.

        Args:
            note_id (str): ID of note to remove.

        Returns:
            bool: True if removed, False if not found.
        """
        if note_id not in self.notes:
            return False
        del self.notes[note_id]
        return True

    def get_notes(self, offset: int = 0, limit: int = 5) -> ReturnedNotes:
        """Retrieve paginated notes with the most recently updated notes first.

        Args:
            offset (int): Starting index.
            limit (int): Maximum number of notes to return.

        Returns:
            ReturnedNotes: Paginated result container.
        """
        if not isinstance(offset, int):
            raise TypeError(f"Offset must be an integer, got {type(offset)}.")
        if offset < 0:
            raise ValueError("Offset must be non-negative.")
        if offset > len(self.notes):
            raise ValueError("Offset must be less than the number of notes.")

        total = len(self.notes)
        end = min(offset + limit, total)
        returned = list(self.notes.values())[offset:end]
        returned = sorted(returned, key=lambda n: n.updated_at, reverse=True)

        return ReturnedNotes(
            notes=returned, notes_range=(offset, end), total_returned_notes=len(returned), total_notes=total
        )

    def get_note(self, idx: int) -> Note:
        """Get a note by index.

        Args:
            idx (int): Index of the note.

        Returns:
            Note: The note at the given index.
        """
        if not isinstance(idx, int):
            raise TypeError(f"Index must be an integer, got {type(idx)}.")
        if idx < 0:
            raise ValueError("Index must be non-negative.")
        if int(idx) >= len(self.notes):
            raise ValueError(f"Index {idx} is out of range.")
        return list(self.notes.values())[idx]

    def get_note_by_id(self, note_id: str) -> Note | None:
        """Lookup a note by ID.

        Args:
            note_id (str): Target note ID.

        Returns:
            Note: Found note.
        """
        if note_id not in self.notes:
            return None
        return self.notes[note_id]

    def search_notes(self, query: str) -> list[Note]:
        """Search notes within this folder using a query string.

        Args:
            query (str): Search query.

        Returns:
            list[Note]: Matched notes.
        """
        query_lower = query.lower()
        return [n for n in self.notes.values() if query_lower in n.title.lower() or query_lower in n.content.lower()]

    def get_state(self) -> dict[str, Any]:
        """Serialize folder state.

        Returns:
            dict[str, Any]: Serialized state.
        """
        return get_state_dict(self, ["folder_name", "notes"])

    def load_state(self, state_dict: dict[str, Any]) -> None:
        """Deserialize folder state.

        Args:
            state_dict (dict[str, Any]): State to load.
        """
        self.folder_name = state_dict["folder_name"]
        self.notes = {note_id: Note(**note_data) for note_id, note_data in state_dict["notes"].items()}
        self.notes = dict(sorted(self.notes.items(), key=lambda item: item[1].updated_at, reverse=True))


@dataclass
class StatefulNotesApp(StatefulApp):
    """A Notes application that manages user's notes and folder organization. This class provides comprehensive functionality for handling notes including creating, updating, deleting, and searching notes.

    This app maintains the notes in different folders. Default folders are "Inbox", "Personal", and "Work". New folders can be created by the user.

    Key Features:
    - Note Management: Create, update, move and delete notes
    - Folder Management: Create, delete, and search folders (Default folders cannot be deleted)
    - Attachment Management: Handle note attachments (upload and download)
    - Search Functionality: Search notes across folders with text-based queries
    - State Management: Save and load application state

    Key Components:
    - Folders: Each NotesFolder instance maintains its own collection of notes
    - View Limits: Configurable limit for note viewing and pagination
    - Event Registration: All operations are tracked through event registration

    Notes:
    - Note IDs are automatically generated when creating new notes.
    - Attachments are handled using base64 encoding.
    - Search operations are case-insensitive.
    - All notes operations maintain folder integrity.
    """

    name: str | None = None
    view_limit: int = 5
    folders: dict[str, NotesFolder] = field(default_factory=dict)
    internal_fs: SandboxLocalFileSystem | VirtualFileSystem | None = None

    def __post_init__(self) -> None:
        """Initialize app with default folders."""
        super().__init__(self.name or "note")

        # Initialize default folders
        self.default_folders = ["Inbox", "Personal", "Work"]
        for folder_name in self.default_folders:
            if folder_name not in self.folders:
                self.folders[folder_name] = NotesFolder(folder_name)

        self.load_root_state()

    def connect_to_protocols(self, protocols: dict[Protocol, Any]) -> None:
        """Connect to the given list of protocols.

        Args:
            protocols (dict[Protocol, Any]): Dictionary of protocols.
        """
        file_system = protocols.get(Protocol.FILE_SYSTEM)
        if isinstance(file_system, (SandboxLocalFileSystem, VirtualFileSystem)):
            self.internal_fs = file_system

    def create_root_state(self) -> NoteList:
        """Return the root navigation state.

        Returns:
            NoteList: Default folder view.
        """
        return NoteList("Inbox")

    def get_state(self) -> dict[str, Any]:
        """Serialize app state.

        Returns:
            dict[str, Any]: Complete app state.
        """
        return {
            "view_limit": self.view_limit,
            "folders": {k: v.get_state() for k, v in self.folders.items()},
        }

    def load_state(self, state_dict: dict[str, Any]) -> None:
        """Deserialize app state.

        Args:
            state_dict (dict[str, Any]): State to restore.
        """
        self.view_limit = state_dict["view_limit"]
        self.folders.clear()
        for folder_name, folder_state in state_dict.get("folders", {}).items():
            folder = NotesFolder(folder_name)
            folder.load_state(folder_state)
            self.folders[folder_name] = folder

    def reset(self) -> None:
        """Reset the app to empty state."""
        super().reset()
        for folder in self.folders:
            self.folders[folder].notes.clear()

    def _get_note_from_any_folder(self, note_id: str) -> tuple[str, Note] | None:
        """Find a note across all folders.

        Args:
            note_id (str): Note ID to find.

        Returns:
            tuple[str, Note] | None: Folder Name and Note object if found, None otherwise.
        """
        for name, folder in self.folders.items():
            note = folder.get_note_by_id(note_id)
            if note is not None:
                return (name, note)
        return None

    def open_folder(self, folder: str) -> list[Note]:
        """Open a folder and return the notes in the folder.

        Args:
            folder (str): Name of the folder to open.

        Returns:
            list[Note]: List of notes in the folder.

        Raises:
            KeyError: If folder does not exist.
            ValueError: If folder name is empty.
        """
        if folder not in self.folders:
            raise KeyError(f"Folder {folder} does not exist")
        if len(folder) == 0:
            raise ValueError("Folder name must be non-empty")
        return list(self.folders[folder].notes.values())

    @type_check
    @app_tool()
    @pare_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def new_folder(self, folder_name: str) -> str:
        """Create a new empty folder with the given name.

        Args:
            folder_name (str): Name of the new folder.

        Returns:
            str: Name of the newly created folder.

        Raises:
            KeyError: If folder already exists.
        """
        if folder_name in self.folders:
            raise KeyError(f"Folder {folder_name} already exists")
        self.folders[folder_name] = NotesFolder(folder_name)
        return folder_name

    @type_check
    @env_tool()
    @app_tool()
    @pare_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def delete_folder(self, folder_name: str) -> str:
        """Delete a folder and all it's notes. Default folders "Inbox", "Personal", and "Work" cannot be deleted.

        Args:
            folder_name (str): Name of the folder to delete.

        Returns:
            str: Name of the deleted folder if successful.

        Raises:
            KeyError: If folder does not exist, or if the folder to be deleted is one of the default folders.
        """
        if folder_name not in self.folders:
            raise KeyError(f"Folder {folder_name} does not exist")
        if folder_name in self.default_folders:
            raise KeyError(f"Cannot delete default folder {folder_name}")

        self.folders[folder_name].notes.clear()
        del self.folders[folder_name]
        logger.debug(f"Deleted folder {folder_name}")
        return folder_name

    @type_check
    @app_tool()
    @pare_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def rename_folder(self, folder: str, new_folder: str) -> str:
        """Rename an already existing folder. Default folders "Inbox", "Personal", and "Work" cannot be renamed.

        Args:
            folder (str): Name of the folder to rename.
            new_folder(str): New name for the folder.

        Returns:
            str: Name of the renamed folder.

        Raises:
            KeyError: If folder_name does not exist, a folder with the new name already exists or if the folder to be renamed is one of the default folders.
        """
        if folder not in self.folders:
            raise KeyError(f"Folder {folder} does not exist")
        if new_folder in self.folders:
            raise KeyError(f"Folder {new_folder} already exists")
        if folder in self.default_folders:
            raise KeyError(f"Cannot rename default folder {folder}")
        self.folders[new_folder] = deepcopy(self.folders[folder])
        self.folders[new_folder].folder_name = new_folder
        del self.folders[folder]
        logger.debug(f"Renamed folder {folder} to {new_folder}")
        return new_folder

    @data_tool()
    @pare_event_registered(operation_type=OperationType.WRITE)
    def create_note_with_time(
        self,
        folder: str = "Inbox",
        title: str = "",
        content: str = "",
        pinned: bool = False,
        created_at: str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        updated_at: str | None = None,
    ) -> str:
        """Create a new note with title and content at a specific time. If title string is empty, it will be set to the first 50 characters of the content. If specified folder is not found, a new folder will be created.

        Args:
            folder (str): Folder to create the note under.
            title (str): Title of the note.
            content (str): Content of the note.
            pinned (bool): Whether the note should be pinned.
            created_at (str): Time of the note creation. Defaults to the current time.
            updated_at (str): Time of the note update. Defaults to the creation time.

        Returns:
            str: ID of the newly created note.

        Raises:
            ValueError: If creation or update time is invalid, or if updated time is before creation time.
        """
        try:
            creation_time = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).timestamp()
        except ValueError as e:
            raise ValueError("Invalid datetime format for the creation time. Please use YYYY-MM-DD HH:MM:SS") from e
        if updated_at is not None:
            try:
                update_time = datetime.strptime(updated_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).timestamp()
            except ValueError as e:
                raise ValueError("Invalid datetime format for the update time. Please use YYYY-MM-DD HH:MM:SS") from e
        else:
            update_time = creation_time

        if folder not in self.folders:
            with disable_events():
                self.new_folder(folder)

        if update_time < creation_time:
            raise ValueError(
                "Updated time cannot be before creation time. Creation Time: {creation_time}, Updated Time: {update_time}"
            )
        note_id = uuid_hex(self.rng)
        note = Note(
            note_id=note_id,
            title=title,
            content=content,
            pinned=pinned,
            created_at=creation_time,
            updated_at=update_time,
        )
        self.folders[folder].add_note(note)
        return note.note_id

    @type_check
    @app_tool()
    @pare_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def create_note(self, folder: str = "Inbox", title: str = "", content: str = "", pinned: bool = False) -> str:
        """Create a new note with title and content. If title string is empty, it will be set to the first 50 characters of the content.

        Args:
            folder (str): Folder to create the note under.
            title (str): Title of the note.
            content (str): Content of the note.
            pinned (bool): Whether the note should be pinned.

        Returns:
            str: ID of the newly created note.

        Raises:
            KeyError: If specified folder is not found.
        """
        if folder not in self.folders:
            raise KeyError(f"Folder {folder} does not exist")
        if title is None or len(title.strip()) == 0:
            title = content[:50]
        note_id = uuid_hex(self.rng)
        note = Note(
            note_id=note_id,
            title=title,
            content=content,
            pinned=False,
            created_at=self.time_manager.time(),
            updated_at=self.time_manager.time(),
        )
        self.folders[folder].add_note(note)
        return note.note_id

    @type_check
    @data_tool()
    @app_tool()
    @pare_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def get_note_by_id(self, note_id: str) -> Note:
        """Retrieve a note by ID.

        Args:
            note_id (str): Target note ID.

        Returns:
            Note: The retrieved note object.

        Raises:
            KeyError: If note not found.
        """
        if not isinstance(note_id, str):
            raise TypeError(f"Note ID must be a string, got {type(note_id)}.")
        if len(note_id) == 0:
            raise ValueError("Note ID must be non-empty.")
        result = self._get_note_from_any_folder(note_id)
        if result is None:
            raise KeyError(f"Note {note_id} not found")
        return result[1]

    @type_check
    @app_tool()
    @pare_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def update_note(self, note_id: str, title: str | None = None, content: str | None = None) -> str:
        """Update the title or the content of the note. At least one of title or content must be provided.

        Notes:
        - If both title and content are provided, both will be updated.
        - If the note has no title and new title is provided, the title will be set to the new title.
        - If the note has no title and content is provided, the title will be set to the first 50 characters of the content.

        Args:
            note_id (str): Target note ID.
            title (str | None): New title for the note.
            content (str | None): New content for the note.

        Returns:
            str: Note ID of the updated note.

        Raises:
            KeyError: If note not found.
            ValueError: If both title and content are empty.
        """
        result = self._get_note_from_any_folder(note_id)
        if result is None:
            raise KeyError(f"Note {note_id} not found")

        folder, note = result

        if (title is None or len(title.strip()) == 0) and (content is None or len(content.strip()) == 0):
            raise ValueError(
                "Both title and content cannot be empty. At least one of title or content must be provided."
            )

        if title is not None and len(title.strip()) > 0:
            note.title = title

        # Title was not provided, content was provided
        if content is not None and len(content.strip()) > 0:
            if note.title is None or len(note.title.strip()) == 0:
                note.title = content[:50]
            note.content = content

        note.updated_at = self.time_manager.time()
        self.folders[folder].notes[note.note_id] = note

        return note_id

    @type_check
    @app_tool()
    @pare_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def delete_note(self, note_id: str) -> str:
        """Delete a note with the specified ID. Deleted Note ID is returned.

        Args:
            note_id (str): ID of note to delete.

        Returns:
            str: ID of the deleted note.

        Raises:
            TypeError: If note ID is not a string.
            ValueError: If note ID is empty.
            KeyError: If note not found.
        """
        if not isinstance(note_id, str):
            raise TypeError(f"Note ID must be a string, got {type(note_id)}.")
        if len(note_id) == 0:
            raise ValueError("Note ID must be non-empty.")
        result = self._get_note_from_any_folder(note_id)
        if result is None:
            raise KeyError(f"Note {note_id} not found")
        folder, _ = result
        self.folders[folder].remove_note(note_id)
        return note_id

    @type_check
    @app_tool()
    @pare_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def list_notes(self, folder: str, offset: int = 0, limit: int = 10) -> ReturnedNotes:
        """List notes in the specific folder with a specified offset.

        Args:
            folder (str): The folder to list notes from.
            offset (int): The offset of the first note to return.
            limit (int): The maximum number of notes to return.

        Returns:
            ReturnedNotes: Notes with additional metadata about the range of notes retrieved and total number of notes
        """
        if folder not in self.folders:
            raise ValueError(f"Folder {folder} not found")

        return self.folders[folder].get_notes(offset, limit)

    @type_check
    @app_tool()
    @pare_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def list_folders(self) -> list[str]:
        """List all folder names.

        Returns:
            list[str]: Folder list.
        """
        return list(self.folders.keys())

    @type_check
    @app_tool()
    @pare_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def move_note(self, note_id: str, source_folder_name: str = "Inbox", dest_folder_name: str = "Personal") -> str:
        """Move a note with the specified ID to the specified folder.

        Args:
            note_id (str): The ID of the note to move.
            source_folder_name (str): The folder to move the note from. Defaults to Inbox.
            dest_folder_name (str): The folder to move the note to. Defaults to Personal.

        Returns:
            str: The ID of the moved note

        Raises:
            KeyError: If source or destination folder not found or note not found in source folder.
        """
        if source_folder_name not in self.folders:
            raise KeyError(f"Folder {source_folder_name} not found.")
        if dest_folder_name not in self.folders:
            raise KeyError(f"Folder {dest_folder_name} not found.")
        note = self.folders[source_folder_name].get_note_by_id(note_id)
        if note is None:
            raise KeyError(f"Note {note_id} not found in folder {source_folder_name}.")
        self.folders[dest_folder_name].add_note(note)
        self.folders[source_folder_name].remove_note(note_id)
        return note_id

    @type_check
    @app_tool()
    @pare_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def duplicate_note(self, folder_name: str, note_id: str) -> str:
        """Create a duplicated copy of a note. The new note is added to the same folder as the original note and the title is "Copy of <original title>".

        Args:
            folder_name (str): The folder of the original note. Defaults to Inbox.
            note_id (str): The ID of the note to copy.

        Returns:
            str: The ID of the newly created duplicate.

        Raises:
            KeyError: If folder not found or note not found in folder.
        """
        if folder_name not in self.folders:
            raise KeyError(f"Folder {folder_name} not found.")
        current_note = self.folders[folder_name].get_note_by_id(note_id)
        if current_note is None:
            raise KeyError(f"Note {note_id} not found in folder {folder_name}.")

        new_note_id = uuid_hex(self.rng)
        new_note = Note(
            note_id=new_note_id,
            title=f"Copy of {current_note.title}",
            content=current_note.content,
            pinned=False,
            attachments=deepcopy(current_note.attachments),
        )
        self.folders[folder_name].add_note(new_note)

        return new_note_id

    @type_check
    @app_tool()
    @pare_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def search_notes(self, query: str) -> list[Note]:
        """Search for notes across all folders based on a query string. The search looks for partial matches in title, and content.

        Args:
            query (str): The search query string.

        Returns:
            list[Note]: A list of notes that match the query.
        """
        results = []
        for folder in self.folders:
            results.extend(self.folders[folder].search_notes(query))
        return results

    @type_check
    @app_tool()
    @pare_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def search_notes_in_folder(self, query: str, folder_name: str) -> list[Note]:
        """Search for notes in a specific folder based on a query string. The search looks for partial matches in title, and content.

        Args:
            query (str): The search query string.
            folder_name (str): The folder to search in. Defaults to Inbox.

        Returns:
            list[Note]: A list of notes that match the query.

        Raises:
            KeyError: If folder not found.
        """
        if folder_name not in self.folders:
            raise KeyError(f"Folder {folder_name} not found.")
        return self.folders[folder_name].search_notes(query)

    def add_attachment(self, note: Note, attachment_path: str) -> Note:
        """Add a file attachment to a note.

        Args:
            note (Note): The note to add the attachment to.
            attachment_path (str): The path to the attachment to add.

        Returns:
            Note: The updated note object.

        Raises:
            ValueError: If file does not exist.
        """
        if self.internal_fs is not None:
            if not self.internal_fs.exists(attachment_path):
                raise ValueError(f"File does not exist: {attachment_path}")
            with disable_events(), self.internal_fs.open(attachment_path, "rb") as f:
                file_content = base64.b64encode(f.read())
                file_name = Path(attachment_path).name
                if not note.attachments:
                    note.attachments = {}
                note.attachments[file_name] = file_content
        else:
            note.add_attachment(attachment_path)

        return note

    @type_check
    @app_tool()
    @pare_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def add_attachment_to_note(self, note_id: str, attachment_path: str) -> str:
        """Add a file attachment to a note.

        Args:
            note_id (str): The ID of the note to add the attachment to.
            attachment_path (str): The path to the attachment to add.

        Returns:
            str: The ID of the note that the attachment was added to.
        """
        result = self._get_note_from_any_folder(note_id)
        if result is None:
            raise KeyError(f"Note {note_id} not found in any folder.")
        folder_name, note = result
        note = self.add_attachment(note, attachment_path)
        note.updated_at = self.time_manager.time()
        self.folders[folder_name].notes[note.note_id] = note
        return note.note_id

    @type_check
    @app_tool()
    @pare_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def remove_attachment(self, note_id: str, attachment: str) -> str:
        """Remove an attachment from a note.

        Args:
            note_id (str): Target note ID.
            attachment (str): Attachment to remove.

        Returns:
            str: The ID of the note that the attachment was removed from.

        Raises:
            KeyError: If note not found in any folder or attachment not found in note.
        """
        result = self._get_note_from_any_folder(note_id)
        if result is None:
            raise KeyError(f"Note {note_id} not found in any folder.")
        folder_name, note = result
        # code path is not reachable
        if note.attachments is None:
            raise KeyError(f"Note {note_id} has no attachments.")

        if attachment not in note.attachments:
            raise KeyError(f"Attachment {attachment} not found in note {note_id}")

        del note.attachments[attachment]
        note.updated_at = self.time_manager.time()
        self.folders[folder_name].notes[note.note_id] = note

        return note.note_id

    @type_check
    @app_tool()
    @pare_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def list_attachments(self, note_id: str) -> list[str]:
        """List attachment identifiers for a note.

        Args:
            note_id (str): Target note ID.

        Returns:
            list[str]: Attachment list.

        Raises:
            KeyError: If note not found.
        """
        result = self._get_note_from_any_folder(note_id)
        if result is None:
            raise KeyError(f"Note {note_id} not found")
        _, note = result
        # code path is not reachable
        if note.attachments is None:
            return []

        return list(note.attachments.keys())

    def _resolve_note_id(self, args: dict[str, Any], metadata: object | None) -> str | None:
        """Extract note_id from args or metadata. Assumes that note_id is either in args or return value of the completed event.

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
        if fname == "new_note":
            note_id = self._resolve_note_id(args, metadata)
            if note_id:
                self.set_current_state(EditNote(note_id))
            return

        if fname == "open":
            note_id = self._resolve_note_id(args, metadata)
            if note_id:
                self.set_current_state(NoteDetail(note_id))
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

        if fname == "delete" and self.navigation_stack:
            with disable_events():
                self.go_back()
            return

        if fname == "duplicate":
            note_id = self._resolve_note_id(args, metadata)
            if note_id:
                self.set_current_state(NoteDetail(note_id))
            return

        if fname == "move":
            dest = args.get("dest_folder_name")
            if isinstance(dest, str):
                self.set_current_state(NoteList(dest))

    def _handle_edit_note_transition(self, fname: str, args: dict[str, Any], metadata: object | None) -> None:
        """Process transitions from the edit note view."""
        if fname == "update":
            note_id = self._resolve_note_id(args, metadata)
            if note_id:
                self.set_current_state(NoteDetail(note_id))

    def _handle_folder_list_transition(self, fname: str, args: dict[str, Any], metadata: object | None) -> None:
        """Process transitions from the folder list view."""
        if fname == "open":
            folder = args.get("folder")
            if isinstance(folder, str):
                self.set_current_state(NoteList(folder))
