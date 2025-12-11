# Stateful Note App

`pas.apps.note.app.StatefulNoteApp` pairs PAS navigation with an in-memory note backend.
It starts in `NoteList("All")` and pushes additional states for note detail, editing, and folder selection.

---

## Navigation States

---

## NoteList

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list()` | `StatefulNoteApp.list_notes(folder=self.folder)` | `list[Note]` | Remains in `NoteList(folder)` |
| `open(note_id)` | `StatefulNoteApp.get_note(note_id)` | `Note` | Completed event transitions to `NoteDetail(note_id)` |
| `new()` | `StatefulNoteApp.create_note(folder=self.folder)` | Newly created note id | Completed event transitions to `EditNote(new_id)` |
| `search(keyword)` | `StatefulNoteApp.search_notes(keyword)` | `list[Note]` | Completed event transitions to `NoteList(search_mode=True)` |
| `folders()` | `StatefulNoteApp.list_folders()` | `list[str]` | Completed event transitions to `FolderList()` |

---

## NoteDetail

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `refresh()` | `StatefulNoteApp.get_note(note_id)` | Updated `Note` | Remains in `NoteDetail` |
| `attachments()` | `StatefulNoteApp.list_attachments(note_id)` | `list[str]` | Remains in `NoteDetail` |
| `add_attachment(path)` | `StatefulNoteApp.add_attachment(note_id, path)` | `"OK"` | Remains in `NoteDetail` |
| `remove_attachment(path)` | `StatefulNoteApp.remove_attachment(note_id, path)` | `"OK"` | Remains in `NoteDetail` |
| `delete()` | `StatefulNoteApp.delete_note(note_id)` | `"OK"` | Completed event transitions back to `NoteList("All")` |
| `edit()` | *Frontend op only* — returns `EditNote(note_id)` | `EditNote` | Completed event transitions to `EditNote(note_id)` |

---

## EditNote

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `update(title, content)` | `StatefulNoteApp.update_note(note_id, title, content)` | Updated note id | Completed event transitions to `NoteDetail(note_id)` |

---

## FolderList

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list()` | `StatefulNoteApp.list_folders()` | `list[str]` | Remains in `FolderList` |
| `open(folder)` | *Frontend op only* — returns `NoteList(folder)` | `NoteList(folder)` | Completed event transitions to `NoteList(folder)` |

---

## Navigation Helpers (App-Level)

- Creating a note (`new`, `create_note`) always transitions into the editing screen.
- Opening a note (`open`, `get_note`) transitions into `NoteDetail`.
- Updating a note returns the user to `NoteDetail`.
- Deleting a note returns the user to `NoteList("All")`.
- Listing folders transitions to `FolderList`.
- Selecting a folder transitions to the corresponding `NoteList(folder)`.
- Searching transitions into `NoteList(search_mode=True)` regardless of original folder.

---

## Summary

The Stateful Note App follows a simple CRUD-driven navigation model:

- **NoteList** → list, open, create, search, folders
- **NoteDetail** → view, refresh, delete, attachments, edit
- **EditNote** → update and return
- **FolderList** → choose a folder to enter its NoteList

PAS Completed Events fully control state transitions based on the backend operation invoked.
