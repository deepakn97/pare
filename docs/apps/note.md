# Note App State & Tool Specification

---

## NoteList

State representing a list of notes within a folder or search mode.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list(offset=0, limit=10)` | `StatefulNoteApp.list_notes(folder=self.folder, offset, limit)` | `ReturnedNotes` | No transition (remains in `NoteList(folder)`) |
| `open(note_id)` | `StatefulNoteApp.get_note(note_id)` | `Note` | → `NoteDetail(note_id)` |
| `new()` | `StatefulNoteApp.create_note(folder=self.folder)` | `note_id: str` | → `EditNote(note_id)` |
| `search(keyword)` | `StatefulNoteApp.search_notes(keyword, folder=self.folder)` | `list[Note]` | → `NoteList(search_mode=True)` |
| `folders()` | `StatefulNoteApp.list_folders()` | `list[str]` | → `FolderList()` |

---

## NoteDetail

State showing detailed view of a single note.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `refresh()` | `StatefulNoteApp.get_note(note_id)` | `Note` | No transition (remains in `NoteDetail`) |
| `attachments()` | `StatefulNoteApp.list_attachments(note_id)` | `list[str]` | No transition |
| `add_attachment(attachment)` | `StatefulNoteApp.add_attachment(note_id, attachment)` | `"OK"` | No transition |
| `remove_attachment(attachment)` | `StatefulNoteApp.remove_attachment(note_id, attachment)` | `"OK"` | No transition |
| `delete()` | `StatefulNoteApp.delete_note(note_id)` | `"OK"` | → `NoteList("All")` |
| `edit()` | Frontend-only (no backend call) | `str` | → `EditNote(note_id)` |

---

## EditNote

State enabling editing capabilities for an existing note.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `update(title, content)` | `StatefulNoteApp.update_note(note_id, title, content)` | `note_id: str` | → `NoteDetail(note_id)` |

---

## FolderList

State displaying all available folders.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_folders()` | `StatefulNoteApp.list_folders()` | `list[str]` | No transition (remains in `FolderList`) |
| `open(folder)` | Frontend-only (no backend call) | `str` | → `NoteList(folder)` |

---

## Backend-only Operations

Operations not directly exposed as UI tools but participating in navigation.

| Backend method | Returns | Navigation effect |
| --- | --- | --- |
| `move_note(note_id, new_folder)` | `"OK"` | → `NoteList(new_folder)` |
| `duplicate_note(note_id)` | `note_id: str` | → `NoteDetail(note_id)` |
| `get_note(note_id)` | `Note` | → `NoteDetail(note_id)` |
| `list_notes(folder, offset, limit)` | `ReturnedNotes` | → `NoteList(folder)` |
| `list_folders()` | `list[str]` | → `FolderList()` |

---

## Navigation Rules

- Navigation is driven by `CompletedEvent` and `_transition_<function>` handlers.
- Return values do not directly trigger navigation.
- Frontend-only tools still emit PAS events.
- `disable_events()` prevents nested event emission within state tools.
