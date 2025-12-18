"""PAS-specific models for trajectory data."""

from __future__ import annotations

from dataclasses import dataclass

from are.simulation.data_handler.models import (
    ExportedAction,
    ExportedEventMetadata,
    ExportedTraceBase,
    ExportedTraceMetadata,
)
from are.simulation.types import EventMetadata
from pydantic import BaseModel


@dataclass
class PASEventMetadata(EventMetadata):
    """Runtime event metadata with proactive agent context.

    Extends Meta-ARE's EventMetadata to include proactive agent state.
    Used at runtime when events are added to the log.
    """

    proactive_mode: str | None = None  # "observe" | "awaiting_confirmation" | "execute"
    turn_number: int | None = None


class PASExportedEventMetadata(ExportedEventMetadata):
    """Exported event metadata with proactive agent context.

    Extends Meta-ARE's ExportedEventMetadata for JSON serialization.
    Used during trace export.
    """

    proactive_mode: str | None = None  # "observe" | "awaiting_confirmation" | "execute"
    turn_number: int | None = None


class PASExportedCompletedEvent(BaseModel):
    """PAS-specific exported completed event with PASExportedEventMetadata.

    This is needed because Pydantic v2 only serializes fields from the declared
    type annotation, not the actual subclass. By declaring metadata as
    PASExportedEventMetadata, we ensure proactive_mode and turn_number are serialized.
    """

    class_name: str
    event_type: str
    event_time: float
    event_id: str
    dependencies: list[str]
    event_relative_time: float | None
    action: ExportedAction | None = None
    metadata: PASExportedEventMetadata | None = None


class PASExportedTrace(ExportedTraceBase):
    """PAS-specific exported trace with PASExportedCompletedEvent.

    This ensures proactive_mode and turn_number are serialized correctly.
    """

    metadata: ExportedTraceMetadata
    completed_events: list[PASExportedCompletedEvent]
