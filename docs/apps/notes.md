# Notes App State & Tool Specification

---

## Overview

This document defines the navigation states, user-facing tools, backend operations,
and state transition rules for the **Stateful Notes App** built on PAS.

### Design Principles

- Navigation is **state-driven**, not return-value-driven
- Backend methods may participate in navigation **only via transition handlers**
- Return values do **not** directly trigger navigation
- Frontend-only tools still emit PAS events
- `disable_events()` prevents nested event emission inside state tools

---

## NotesList

State representing a list of notes within a folder or search mode.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list(offset=0, limit=10)` | `StatefulNotesApp.list_notes(folder=self.folder, offset, limit)` | `ReturnedNotes` | No transition (remains in `NoteList(folder)`) |
| `open(note_id)` | `StatefulNotesApp.get_note(note_id)` | `Note` | → `NoteDetail(note_id)` |
| `new()` | `StatefulNotesApp.create_note(folder=self.folder)` | `note_id: str` | → `EditNote(note_id)` |
| `search(keyword)` | `StatefulNotesApp.search_notes(keyword, folder=self.folder)` | `list[Note]` | → `NoteList(folder, search_mode=True)` |
| `folders()` | `StatefulNotesApp.list_folders()` | `list[str]` | → `FolderList()` |

---

## NotesDetail

State showing detailed view of a single note.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `refresh()` | `StatefulNotesApp.get_note(note_id)` | `Note` | No transition (remains in `NoteDetail(note_id)`) |
| `attachments()` | `StatefulNotesApp.list_attachments(note_id)` | `list[str]` | No transition |
| `add_attachment(attachment)` | `StatefulNotesApp.add_attachment(note_id, attachment)` | `"OK"` | No transition |
| `remove_attachment(attachment)` | `StatefulNotesApp.remove_attachment(note_id, attachment)` | `"OK"` | No transition |
| `delete()` | `StatefulNotesApp.delete_note(note_id)` | `"OK"` | → `NoteList("All")` |
| `edit()` | Frontend-only (no backend call) | `str` | → `EditNote(note_id)` |

---

## EditNotes

State enabling editing capabilities for an existing note.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `update(title, content)` | `StatefulNotesApp.update_note(note_id, title, content)` | `note_id: str` | → `NoteDetail(note_id)` |

---

## FolderList

State displaying all available folders.

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_folders()` | `StatefulNotesApp.list_folders()` | `list[str]` | No transition (remains in `FolderList`) |
| `open(folder)` | Frontend-only (no backend call) | `str` | → `NoteList(folder)` |

---

## Backend Operations Participating in Navigation

The following backend methods are **not always directly exposed as user-facing tools**,
but may participate in navigation when invoked by tools or transition logic.

**Note:** Navigation effects are determined by state transition handlers reacting to
`CompletedEvent` instances, not directly by backend return values.

| Backend method | Returns | Navigation effect (via transition handler) |
| --- | --- | --- |
| `move_note(note_id, new_folder)` | `"OK"` | → `NoteList(new_folder)` |
| `duplicate_note(note_id)` | `note_id: str` | → `NoteDetail(note_id)` |
| `get_note(note_id)` | `Note` | → `NoteDetail(note_id)` |
| `list_notes(folder, offset, limit)` | `ReturnedNotes` | → `NoteList(folder)` |
| `list_folders()` | `list[str]` | → `FolderList()` |

---

## Navigation Rules

- Navigation is driven by `CompletedEvent` instances and `_transition_<function>` handlers.
- Return values do **not** directly trigger navigation.
- Transition handlers may optionally consume **event metadata** (e.g., returned IDs)
  to determine the target navigation state.
- Frontend-only tools still emit PAS events.
- `disable_events()` prevents nested event emission within state tools.

---

## Summary

This specification intentionally separates:

- **User-facing tools**
- **Backend operations**
- **Navigation logic**

to ensure predictable, testable, and state-driven navigation behavior consistent
with PAS design principles.
