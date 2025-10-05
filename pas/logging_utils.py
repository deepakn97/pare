"""Utilities for configuring PAS logging."""

from __future__ import annotations

import logging
import typing
from pathlib import Path


# Historical helper kept for compatibility; callers pass explicit paths now.
def initialise_pas_logs(*, clear_existing: bool, log_paths: typing.Sequence[Path] | None = None) -> None:
    """Prepare PAS log files, optionally clearing previous runs before logging."""
    if log_paths is None:
        return
    for path in log_paths:
        resolved = path if path.is_absolute() else (Path.cwd() / path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        if clear_existing and resolved.exists():
            resolved.unlink()


def get_pas_file_logger(name: str, log_path: Path, level: int = logging.INFO) -> logging.Logger:
    """Return a logger writing to ``log_path`` without duplicating handlers."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    log_path = log_path if log_path.is_absolute() else (Path.cwd() / log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if not _has_handler(logger.handlers, log_path):
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        logger.addHandler(file_handler)
    else:
        for existing_handler in logger.handlers:
            if (
                isinstance(existing_handler, logging.FileHandler)
                and Path(existing_handler.baseFilename).resolve() == log_path.resolve()
            ):
                existing_handler.setLevel(level)
    logger.propagate = False
    return logger


def _has_handler(handlers: typing.Sequence[logging.Handler], log_path: Path) -> bool:
    resolved = log_path.resolve()
    for handler in handlers:
        if isinstance(handler, logging.FileHandler) and Path(handler.baseFilename).resolve() == resolved:
            return True
    return False


__all__ = ["get_pas_file_logger", "initialise_pas_logs"]
