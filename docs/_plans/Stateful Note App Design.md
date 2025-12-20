# Stateful Note App Design

This document describes the implementation of the Stateful Notes App in PAS.

## Overview

The Notes app is a standalone PAS app (no Meta-ARE counterpart) that manages user notes organized into folders. It follows the PAS stateful app pattern with state-based navigation and event registration.

## Architecture

### Data Model

```
StatefulNotesApp
    folders: dict[str, NotesFolder]
        NotesFolder
            folder_name: str
            notes: dict[str, Note]
                Note
                    note_id: str
                    title: str
                    content: str
                    pinned: bool
                    attachments: dict[str, bytes]
                    created_at: float
                    updated_at: float
```

### Navigation States

```
NoteList (root)
    |-- open(note_id) --> NoteDetail
    |-- new_note() --> EditNote
    |-- search(keyword) --> NoteList (search_mode=True)
    |-- list_folders() --> FolderList

NoteDetail
    |-- edit() --> EditNote
    |-- delete() --> go_back to NoteList
    |-- refresh(), list_attachments(), add_attachment(), remove_attachment() --> stay

EditNote
    |-- update() --> go_back to NoteDetail (or NoteDetail if no stack)

FolderList
    |-- open(folder) --> NoteList(folder)
    |-- list_folders() --> stay
```

## Implementation Details

### Class: `Note` (dataclass)

Simple data container for a note.

| Field | Type | Description |
|-------|------|-------------|
| `note_id` | `str` | Unique identifier (auto-generated if empty) |
| `title` | `str` | Note title |
| `content` | `str` | Note content |
| `pinned` | `bool` | Whether note is pinned (default: False) |
| `attachments` | `dict[str, bytes] \| None` | Base64-encoded file attachments keyed by filename |
| `created_at` | `float` | Unix timestamp of creation |
| `updated_at` | `float` | Unix timestamp of last update |

Methods:
- `add_attachment(path: str)` - Read file from path, base64 encode, store in attachments dict

### Class: `NotesFolder`

Container managing notes within a single folder.

| Field | Type | Description |
|-------|------|-------------|
| `folder_name` | `str` | Name of the folder |
| `notes` | `dict[str, Note]` | Notes keyed by note_id |

Methods:
- `add_note(note)` - Add note to folder
- `remove_note(note_id)` - Remove note by ID, returns bool
- `get_notes(offset, limit)` - Paginated retrieval sorted by updated_at desc
- `get_note(idx)` - Get note by index
- `get_note_by_id(note_id)` - Lookup by ID, returns None if not found
- `search_notes(query)` - Case-insensitive search in title/content
- `get_state()` / `load_state()` - Serialization

### Class: `StatefulNotesApp` (dataclass)

Main app class extending `StatefulApp`.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str \| None` | App name (default: "note") |
| `view_limit` | `int` | Pagination limit (default: 5) |
| `folders` | `dict[str, NotesFolder]` | Folders keyed by name |
| `internal_fs` | `SandboxLocalFileSystem \| VirtualFileSystem \| None` | Filesystem protocol |
| `default_folders` | `list[str]` | Protected folders: ["Inbox", "Personal", "Work"] |

### App Tools

#### Folder Management

| Tool | Decorator | Description |
|------|-----------|-------------|
| `new_folder(folder_name)` | `@app_tool` | Create new folder |
| `delete_folder(folder_name)` | `@env_tool`, `@app_tool` | Delete folder (not default folders) |
| `rename_folder(folder, new_folder)` | `@app_tool` | Rename folder (not default folders) |
| `list_folders()` | `@app_tool` | List all folder names |
| `open_folder(folder)` | (no decorator) | Internal validation helper |

#### Note Management

| Tool | Decorator | Description |
|------|-----------|-------------|
| `create_note(folder, title, content, pinned)` | `@app_tool` | Create note in folder |
| `create_note_with_time(...)` | `@data_tool` | Create with custom timestamps (for scenarios) |
| `get_note_by_id(note_id)` | `@data_tool`, `@app_tool` | Retrieve note |
| `update_note(note_id, title, content)` | `@app_tool` | Update title/content |
| `delete_note(note_id)` | `@app_tool` | Delete note |
| `list_notes(folder, offset, limit)` | `@app_tool` | Paginated list |
| `move_note(note_id, source, dest)` | `@app_tool` | Move between folders |
| `duplicate_note(folder_name, note_id)` | `@app_tool` | Copy note |

#### Search

| Tool | Decorator | Description |
|------|-----------|-------------|
| `search_notes(query)` | `@app_tool` | Search all folders |
| `search_notes_in_folder(query, folder_name)` | `@app_tool` | Search single folder |

#### Attachments

| Tool | Decorator | Description |
|------|-----------|-------------|
| `add_attachment_to_note(note_id, path)` | `@app_tool` | Add file attachment |
| `remove_attachment(note_id, attachment)` | `@app_tool` | Remove attachment |
| `list_attachments(note_id)` | `@app_tool` | List attachment names |

### User Tools (on States)

#### NoteList State

| Tool | Operation | Backend Call |
|------|-----------|--------------|
| `list_notes(offset, limit)` | READ | `app.list_notes(self.folder, ...)` |
| `open(note_id)` | READ | `app.get_note_by_id(note_id)` |
| `new_note()` | WRITE | `app.create_note(folder=self.folder)` |
| `search(keyword)` | READ | `app.search_notes_in_folder(keyword, self.folder)` |
| `list_folders()` | READ | `app.list_folders()` |

#### NoteDetail State

| Tool | Operation | Backend Call |
|------|-----------|--------------|
| `refresh()` | READ | `app.get_note_by_id(self.note_id)` |
| `list_attachments()` | READ | `app.list_attachments(self.note_id)` |
| `add_attachment(path)` | WRITE | `app.add_attachment_to_note(self.note_id, path)` |
| `remove_attachment(attachment)` | WRITE | `app.remove_attachment(self.note_id, attachment)` |
| `delete()` | WRITE | `app.delete_note(self.note_id)` |
| `edit()` | WRITE | Returns confirmation string (no backend) |

#### EditNote State

| Tool | Operation | Backend Call |
|------|-----------|--------------|
| `update(title, content)` | WRITE | `app.update_note(self.note_id, title, content)` |

#### FolderList State

| Tool | Operation | Backend Call |
|------|-----------|--------------|
| `list_folders()` | READ | `app.list_folders()` |
| `open(folder)` | READ | `app.open_folder(folder)` |

### State Transition Handlers

The app uses state-first `isinstance` checks (Pattern B from the inconsistencies doc):

```python
def handle_state_transition(self, event: CompletedEvent) -> None:
    if isinstance(current_state, NoteList):
        self._handle_note_list_transition(fname, args, metadata_value)
    elif isinstance(current_state, NoteDetail):
        self._handle_note_detail_transition(fname, args, metadata_value)
    elif isinstance(current_state, EditNote):
        self._handle_edit_note_transition(fname, args, metadata_value)
    elif isinstance(current_state, FolderList):
        self._handle_folder_list_transition(fname, args, metadata_value)
```

Transitions match user tool function names (not app tool names).

## Known Issues / TODOs

### Missing `go_back` User Tool

States don't expose a `go_back` user action. Users cannot navigate back without performing another action that triggers a transition.

### Search Mode Folder Context

When user searches from a folder, the transition creates `NoteList(search_mode=True)` but loses the original folder context:

```python
if fname == "search":
    self.set_current_state(NoteList(search_mode=True))  # Should preserve folder
```

### Orphan Transition Handlers

`_handle_note_detail_transition` has handlers for `duplicate_note` and `move_note` but NoteDetail state has no corresponding user tools. These transitions can only be triggered by direct app tool calls (agent actions).

### Dead Code in FolderList Transitions

`_handle_folder_list_transition` checks for `list_notes` but FolderList state has no `list_notes` user tool.

### `edit()` Doesn't Call Backend

`NoteDetail.edit()` returns a confirmation string but doesn't call any backend method. This is inconsistent with other user tools that delegate to `self.app.*()`. The transition still works because it matches the function name.

## Event Registration

All user tools use the `@pas_event_registered` decorator which handles both AppState and App instances:

```python
@user_tool()
@pas_event_registered(operation_type=OperationType.READ)
def list_notes(self, offset: int = 0, limit: int = 10) -> ReturnedNotes:
    with disable_events():
        return cast("StatefulNotesApp", self.app).list_notes(self.folder, offset, limit)
```

App tools use `EventType.AGENT` since they're meant for agent (not user) actions:

```python
@app_tool()
@pas_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
def create_note(self, folder: str = "Inbox", ...) -> str:
```

## State Lifecycle

`on_enter()` hooks fetch current note data with `disable_events()` to avoid registering spurious events:

```python
def on_enter(self) -> None:
    with disable_events():
        self._note = self.app.get_note_by_id(self.note_id)
```

## Environment Integration

State transitions are only triggered for `EventType.USER` events (fixed in `environment.py`):

```python
if event.event_type == EventType.USER:
    app = self.get_app(event.app_name())
    if isinstance(app, StatefulApp):
        app.handle_state_transition(event)
```

This ensures agent actions (`EventType.AGENT`) don't cause unintended navigation.
