from __future__ import annotations

from typing import TYPE_CHECKING, cast

from are.simulation.types import OperationType, disable_events

from pas.apps.core import AppState
from pas.apps.tool_decorators import pas_event_registered, user_tool

if TYPE_CHECKING:
    from pas.apps.note.app import Note, ReturnedNotes, StatefulNoteApp


class NoteList(AppState):
    """State representing a list of notes within a folder or search mode."""

    def __init__(self, folder: str = "All", search_mode: bool = False) -> None:
        """Initialize the list view.

        Args:
            folder (str): Folder name to filter notes.
            search_mode (bool): Whether the view is in search mode.
        """
        super().__init__()
        self.folder = folder
        self.search_mode = search_mode

    def on_enter(self) -> None:
        """Lifecycle hook when entering NoteList."""
        pass

    def on_exit(self) -> None:
        """Lifecycle hook when leaving NoteList."""
        pass

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
            return cast("StatefulNoteApp", self.app).list_notes(self.folder, offset, limit)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def open(self, note_id: str) -> Note:
        """Open a note detail view.

        Args:
            note_id (str): ID of the note to open.

        Returns:
            Note: Note object from backend.
        """
        with disable_events():
            return cast("StatefulNoteApp", self.app).get_note(note_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def new(self) -> str:
        """Create a new note in the current folder.

        Returns:
            str: ID of newly created note.
        """
        with disable_events():
            return cast("StatefulNoteApp", self.app).create_note(self.folder)

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
            return cast("StatefulNoteApp", self.app).search_notes(keyword, self.folder)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def folders(self) -> list[str]:
        """List all folders.

        Returns:
            list[str]: Folder names.
        """
        with disable_events():
            return cast("StatefulNoteApp", self.app).list_folders()


class NoteDetail(AppState):
    """State showing detailed view of a single note."""

    def __init__(self, note_id: str) -> None:
        """Initialize NoteDetail.

        Args:
            note_id (str): ID of the note being viewed.
        """
        super().__init__()
        self.note_id = note_id

    def on_enter(self) -> None:
        """Lifecycle hook when entering NoteDetail."""
        pass

    def on_exit(self) -> None:
        """Lifecycle hook when leaving NoteDetail."""
        pass

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def refresh(self) -> Note:
        """Reload the note content.

        Returns:
            Note: Updated note object.
        """
        with disable_events():
            return cast("StatefulNoteApp", self.app).get_note(self.note_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def attachments(self) -> list[str]:
        """List attachments associated with the note.

        Returns:
            list[str]: Attachment names.
        """
        with disable_events():
            return cast("StatefulNoteApp", self.app).list_attachments(self.note_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def add_attachment(self, attachment: str) -> str:
        """Add an attachment to the note.

        Args:
            attachment (str): Attachment identifier.

        Returns:
            str: Backend confirmation "OK".
        """
        with disable_events():
            return cast("StatefulNoteApp", self.app).add_attachment(self.note_id, attachment)

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
            return cast("StatefulNoteApp", self.app).remove_attachment(self.note_id, attachment)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def delete(self) -> str:
        """Delete the note.

        Returns:
            str: Backend deletion confirmation "OK".
        """
        with disable_events():
            return cast("StatefulNoteApp", self.app).delete_note(self.note_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def edit(self) -> str:
        """Open edit mode for this note.

        Returns:
            str: Confirmation message that edit mode is activated.
        """
        with disable_events():
            return f"Edit mode activated for note {self.note_id}"


class EditNote(AppState):
    """State enabling editing capabilities for an existing note."""

    def __init__(self, note_id: str) -> None:
        """Initialize editing.

        Args:
            note_id (str): The note to modify.
        """
        super().__init__()
        self.note_id = note_id

    def on_enter(self) -> None:
        """Lifecycle hook when entering EditNote."""
        pass

    def on_exit(self) -> None:
        """Lifecycle hook when leaving EditNote."""
        pass

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
            return cast("StatefulNoteApp", self.app).update_note(self.note_id, title, content)


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
    def list_folders(self) -> list[str]:
        """Return all folders.

        Returns:
            list[str]: Folder names.
        """
        with disable_events():
            return cast("StatefulNoteApp", self.app).list_folders()

    @user_tool()
    @pas_event_registered(operation_type=OperationType.READ)
    def open(self, folder: str) -> str:
        """Open the selected folder.

        Args:
            folder (str): Folder name.

        Returns:
            str: Confirmation message that folder is opened.
        """
        with disable_events():
            return f"Opened folder: {folder}"
