from __future__ import annotations

from typing import TYPE_CHECKING, cast

from are.simulation.types import OperationType, disable_events

from pas.apps.core import AppState
from pas.apps.tool_decorators import pas_event_registered, user_tool

if TYPE_CHECKING:
    from pas.apps.note.app import Note, ReturnedNotes, StatefulNotesApp


class NoteList(AppState):
    """State representing a list of notes within a folder or search mode."""

    def __init__(self, folder: str = "Inbox") -> None:
        """Initialize the list view.

        Args:
            folder (str): Folder name to filter notes.
        """
        super().__init__()
        self.folder = folder

    def on_enter(self) -> None:
        """Lifecycle hook when entering NoteList."""
        pass

    def on_exit(self) -> None:
        """Lifecycle hook when leaving NoteList."""
        pass

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def go_back(self) -> None:
        """Navigate back to the previous state."""
        return None

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def list_notes(self, offset: int = 0, limit: int = 10) -> ReturnedNotes:
        """Return paginated notes under the current folder.

        Args:
            offset (int): Starting index for pagination.
            limit (int): Maximum number of notes to return.

        Returns:
            ReturnedNotes: Paginated notes container.
        """
        with disable_events():
            return cast("StatefulNotesApp", self.app).list_notes(self.folder, offset, limit)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def open(self, note_id: str) -> Note:
        """Open a note by ID.

        Args:
            note_id (str): ID of the note to open.

        Returns:
            Note: Note object from backend.
        """
        with disable_events():
            return cast("StatefulNotesApp", self.app).get_note_by_id(note_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def new_note(self) -> str:
        """Create a new note in the current folder.

        Returns:
            str: ID of newly created note.
        """
        with disable_events():
            return cast("StatefulNotesApp", self.app).create_note(folder=self.folder)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def search(self, keyword: str) -> list[Note]:
        """Search notes by keyword.

        Args:
            keyword (str): Search keyword.

        Returns:
            list[Note]: List of matched notes.
        """
        with disable_events():
            return cast("StatefulNotesApp", self.app).search_notes_in_folder(keyword, self.folder)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def list_folders(self) -> list[str]:
        """List all folders.

        Returns:
            list[str]: Folder names.
        """
        with disable_events():
            return cast("StatefulNotesApp", self.app).list_folders()


class NoteDetail(AppState):
    """State showing detailed view of a single note."""

    def __init__(self, note_id: str) -> None:
        """Initialize NoteDetail.

        Args:
            note_id (str): ID of the note being viewed.
        """
        super().__init__()
        self.note_id = note_id
        self._note: Note | None = None

    def on_enter(self) -> None:
        """Lifecycle hook when entering NoteDetail."""
        with disable_events():
            self._note = self.app.get_note_by_id(self.note_id)

    def on_exit(self) -> None:
        """Lifecycle hook when leaving NoteDetail."""
        pass

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def go_back(self) -> None:
        """Navigate back to the previous state."""
        return None

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def refresh(self) -> Note:
        """Reload the note content.

        Returns:
            Note: Updated note object.
        """
        with disable_events():
            _refreshed_note = cast("StatefulNotesApp", self.app).get_note_by_id(self.note_id)
        self._note = _refreshed_note
        return self._note

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def list_attachments(self) -> list[str]:
        """List attachments associated with the note.

        Returns:
            list[str]: Attachment names.
        """
        with disable_events():
            return cast("StatefulNotesApp", self.app).list_attachments(self.note_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def add_attachment(self, attachment_path: str) -> str:
        """Add a file attachment to the note.

        Args:
            attachment_path (str): Path to the attachment to add.

        Returns:
            str: Backend confirmation "OK".
        """
        with disable_events():
            return cast("StatefulNotesApp", self.app).add_attachment_to_note(self.note_id, attachment_path)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def remove_attachment(self, attachment: str) -> str:
        """Remove an attachment from the note.

        Args:
            attachment (str): Attachment identifier.

        Returns:
            str: Backend confirmation "OK".
        """
        with disable_events():
            return cast("StatefulNotesApp", self.app).remove_attachment(self.note_id, attachment)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def delete(self) -> str:
        """Delete the note.

        Returns:
            str: Backend deletion confirmation "OK".
        """
        with disable_events():
            return cast("StatefulNotesApp", self.app).delete_note(self.note_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def edit(self) -> str:
        """Open edit mode for this note.

        Returns:
            str: Confirmation message that edit mode is activated.
        """
        with disable_events():
            return f"Edit mode activated for note {self.note_id}"

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def duplicate(self) -> str:
        """Create a duplicate copy of this note in the same folder.

        Returns:
            str: Note ID of the newly created duplicate.
        """
        with disable_events():
            # Get the current note's folder
            result = cast("StatefulNotesApp", self.app)._get_note_from_any_folder(self.note_id)
            if result is None:
                raise KeyError(f"Note {self.note_id} not found")
            folder_name, _ = result
            return cast("StatefulNotesApp", self.app).duplicate_note(folder_name, self.note_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def move(self, dest_folder_name: str) -> str:
        """Move this note to another folder.

        Args:
            dest_folder_name (str): The destination folder name.

        Returns:
            str: Note ID of the moved note.
        """
        with disable_events():
            # Get the current note's folder
            result = cast("StatefulNotesApp", self.app)._get_note_from_any_folder(self.note_id)
            if result is None:
                raise KeyError(f"Note {self.note_id} not found")
            source_folder_name, _ = result
            return cast("StatefulNotesApp", self.app).move_note(self.note_id, source_folder_name, dest_folder_name)


class EditNote(AppState):
    """State enabling editing capabilities for an existing note."""

    def __init__(self, note_id: str) -> None:
        """Initialize editing.

        Args:
            note_id (str): The note to modify.
        """
        super().__init__()
        self.note_id = note_id
        self._note: Note | None = None

    def on_enter(self) -> None:
        """Lifecycle hook when entering EditNote."""
        with disable_events():
            self._note = self.app.get_note_by_id(self.note_id)

    def on_exit(self) -> None:
        """Lifecycle hook when leaving EditNote."""
        pass

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def go_back(self) -> None:
        """Navigate back to the previous state."""
        return None

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def update(self, title: str, content: str) -> str:
        """Update note content and title.

        Args:
            title (str): Updated title.
            content (str): Updated content.

        Returns:
            str: Note ID of the updated note.
        """
        with disable_events():
            return cast("StatefulNotesApp", self.app).update_note(self.note_id, title, content)


class FolderList(AppState):
    """State displaying the list of folders."""

    def on_enter(self) -> None:
        """Lifecycle hook when entering FolderList."""
        pass

    def on_exit(self) -> None:
        """Lifecycle hook when leaving FolderList."""
        pass

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def go_back(self) -> None:
        """Navigate back to the previous state."""
        return None

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def list_folders(self) -> list[str]:
        """Return all folders.

        Returns:
            list[str]: Folder names.
        """
        with disable_events():
            return cast("StatefulNotesApp", self.app).list_folders()

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def open(self, folder: str) -> list[Note]:
        """Open the selected folder.

        Args:
            folder (str): Folder name.

        Returns:
            str: Confirmation message that folder is opened.
        """
        return cast("StatefulNotesApp", self.app).open_folder(folder)
