"""Type definitions for the Note app.

These are separated to avoid circular imports between app.py and states.py.
"""

from __future__ import annotations

import base64
import textwrap
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class Note:
    """Simple note data container."""

    note_id: str
    title: str
    content: str
    pinned: bool = False
    attachments: dict[str, bytes] | None = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: time.time())
    updated_at: float = field(default_factory=lambda: time.time())

    def __str__(self) -> str:
        return textwrap.dedent(
            f"""
            ID: {self.note_id}
            Title: {self.title}
            Content: {self.content}
            Pinned: {self.pinned}
            Created At: {datetime.fromtimestamp(self.created_at, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")}
            Updated At: {datetime.fromtimestamp(self.updated_at, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")}
            """
        )

    def __post_init__(self) -> None:
        if self.note_id is None or len(self.note_id) == 0:
            self.note_id = uuid.uuid4().hex

        if self.attachments is None:
            self.attachments = {}

    def add_attachment(self, path: str) -> None:
        """Add an attachment to the note.

        Args:
            path (str): Path to the attachment.
        """
        if not isinstance(path, str):
            raise TypeError(f"Path must be a string, got {type(path)}.")
        if len(path) == 0:
            raise ValueError("Path must be non-empty.")
        if not Path(path).exists():
            raise ValueError(f"File does not exist: {path}")
        with open(path, "rb") as f:
            file_content = base64.b64encode(f.read())
            file_name = Path(path).name
            if not self.attachments:
                self.attachments = {}
            self.attachments[file_name] = file_content


@dataclass
class ReturnedNotes:
    """Container for paginated note results."""

    notes: list[Note]
    notes_range: tuple[int, int]
    total_returned_notes: int
    total_notes: int
