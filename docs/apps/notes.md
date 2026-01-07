# Stateful Notes App

`pas.apps.note.app.StatefulNotesApp` extends PAS with folder-based note management.
It launches in `NoteList("Inbox")` and transitions between list, detail, edit, and folder views
based on completed note operations.

---

## State Transition Diagram

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                                                      │
│  ┌────────────────────────────┐        new_note         ┌────────────────────────────┐                               │
│  │          NoteList          │ ──────────────────────► │          EditNote          │                               │
│  │        (ROOT STATE)        │                         │                            │                               │
│  │                            │                         │     context: note_id       │                               │
│  │ context: folder            │ ◄────────── move ────── └────────────────────────────┘                               │
│  │          (def "Inbox")     │                                      │                                               │
│  └────────────────────────────┘                                      │ update                                        │
│       │              │      │                                        │                                               │
│       │              │      │                                        ▼                                               │
│       │         open │      │ list_folders         ┌────────────────────────────┐                                    │
│       │              │      │                      │         NoteDetail         │ ◄──────────────┐                   │
│       │              │      │                      │                            │                │                   │
│       │              │      │                      │     context: note_id       │ ─── duplicate ─┘                   │
│       │              │      │                      └────────────────────────────┘                                    │
│       │              │      │                           │          │        │                                        │
│       │              │      │                           │          │        │                                        │
│       │              │      │                      edit │          │        │ delete                                 │
│       │              │      │                           │          │        │                                        │
│       │              │      │                           ▼          │        ▼                                        │
│       │              │      │         ┌────────────────────────────┐│  ┌─────────────────┐                           │
│       │              │      │         │          EditNote          ││  │ Previous State  │                           │
│       │              │      │         │                            ││  │  (stack pop)    │                           │
│       │              │      │         │     context: note_id       ││  └─────────────────┘                           │
│       │              │      │         └────────────────────────────┘│                                                │
│       │              │      │                                       │                                                │
│       │              ▼      │                     refresh ──────────┼──► ○                                           │
│       │   ┌────────────────────────────┐                            │                                                │
│       │   │         NoteDetail         │     list_attachments ──────┼──► ○                                           │
│       │   │                            │                            │                                                │
│       │   │     context: note_id       │      add_attachment ───────┼──► ○                                           │
│       │   └────────────────────────────┘                            │                                                │
│       │                                    remove_attachment ───────┴──► ○                                           │
│       │                                                                                                              │
│  list_notes ──► ○                                                                                                    │
│       │                                                                                                              │
│  search ──────► ○                           ┌────────────────────────────┐                                           │
│       │                                     │         FolderList         │                                           │
│       │                                     │                            │                                           │
│       └──────── list_folders ─────────────► │       context: —           │ ─── list_folders ──► ○                    │
│                                             └────────────────────────────┘                                           │
│                                                          │                                                           │
│                      ┌────────────────────────────┐      │ open                                                      │
│                      │          NoteList          │ ◄────┘                                                           │
│                      │                            │                                                                  │
│                      │     context: folder        │                                                                  │
│                      └────────────────────────────┘                                                                  │
│                                                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Navigation States

---

### NoteList

State representing a list of notes within a folder.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_notes(offset, limit)` | `StatefulNotesApp.list_notes(folder, offset, limit)` | `ReturnedNotes` | Remains in `NoteList` |
| `open(note_id)` | `StatefulNotesApp.get_note_by_id(note_id)` | `Note` | → `NoteDetail(note_id)` |
| `new_note()` | `StatefulNotesApp.create_note(folder)` | `str` (note_id) | → `EditNote(note_id)` |
| `search(keyword)` | `StatefulNotesApp.search_notes_in_folder(keyword, folder)` | `list[Note]` | Remains in `NoteList` |
| `list_folders()` | `StatefulNotesApp.list_folders()` | `list[str]` | → `FolderList` |

---

### NoteDetail

State showing detailed view of a single note.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `refresh()` | `StatefulNotesApp.get_note_by_id(note_id)` | `Note` | Remains in `NoteDetail` |
| `list_attachments()` | `StatefulNotesApp.list_attachments(note_id)` | `list[str]` | Remains in `NoteDetail` |
| `add_attachment(path)` | `StatefulNotesApp.add_attachment_to_note(note_id, path)` | `str` (note_id) | Remains in `NoteDetail` |
| `remove_attachment(attachment)` | `StatefulNotesApp.remove_attachment(note_id, attachment)` | `str` (note_id) | Remains in `NoteDetail` |
| `delete()` | `StatefulNotesApp.delete_note(note_id)` | `str` (note_id) | → Previous State (stack pop) |
| `edit()` | — (frontend-only) | `str` | → `EditNote(note_id)` |
| `duplicate()` | `StatefulNotesApp.duplicate_note(folder, note_id)` | `str` (new_note_id) | → `NoteDetail(new_note_id)` |
| `move(dest_folder_name)` | `StatefulNotesApp.move_note(note_id, source, dest)` | `str` (note_id) | → `NoteList(dest_folder_name)` |

---

### EditNote

State enabling editing capabilities for an existing note.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `update(title, content)` | `StatefulNotesApp.update_note(note_id, title, content)` | `str` (note_id) | → `NoteDetail(note_id)` |

---

### FolderList

State displaying all available folders.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_folders()` | `StatefulNotesApp.list_folders()` | `list[str]` | Remains in `FolderList` |
| `open(folder)` | `StatefulNotesApp.open_folder(folder)` | `list[Note]` | → `NoteList(folder)` |

---

## Summary Table

| State | Context | Transitions Out | Self-Loops |
|-------|---------|-----------------|------------|
| **NoteList** | folder | `new_note` → EditNote, `open` → NoteDetail, `list_folders` → FolderList | `list_notes`, `search` |
| **NoteDetail** | note_id | `edit` → EditNote, `delete` → Previous, `duplicate` → NoteDetail(new), `move` → NoteList(dest) | `refresh`, `list_attachments`, `add_attachment`, `remove_attachment` |
| **EditNote** | note_id | `update` → NoteDetail | — |
| **FolderList** | — | `open` → NoteList(folder) | `list_folders` |

---

## Navigation Helpers

- Navigation transitions are handled in `StatefulNotesApp.handle_state_transition`
  based on the completed backend tool name.
- `open` from NoteList transitions to `NoteDetail` using the provided `note_id`.
- `new_note` creates a note and transitions to `EditNote` for immediate editing.
- `update` from EditNote always transitions to `NoteDetail` to view the updated note.
- `delete` pops the navigation stack to return to the previous state.
- `duplicate` creates a copy and transitions to `NoteDetail` for the new note.
- `move` transitions to `NoteList` showing the destination folder.
