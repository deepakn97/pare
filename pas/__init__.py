"""Core modules for the Proactive Agent System."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

__all__: list[str] = ["PROJECT_ROOT"]
__version__ = "0.1.0"
