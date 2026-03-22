"""Configuration helpers for the annotation module."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003


def ensure_extension(path: Path, ext: str) -> Path:
    """Ensure a file path has the correct extension.

    Strips any existing extension and replaces with the specified one.

    Args:
        path: The file path.
        ext: The desired extension (e.g., '.parquet', '.csv').

    Returns:
        Path with the correct extension.
    """
    if not ext.startswith("."):
        ext = f".{ext}"
    return path.with_suffix(ext)
