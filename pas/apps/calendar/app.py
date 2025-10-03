"""Stateful calendar app combining Meta-ARE calendar backend with PAS navigation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from are.simulation.apps.calendar import CalendarEvent, DATETIME_FORMAT
from are.simulation.apps.calendar_v2 import CalendarV2
from are.simulation.types import CompletedEvent

from pas.apps.core import StatefulApp
from pas.apps.calendar.states import AgendaView, EditDraft, EditEvent, EventDetail


class StatefulCalendarApp(StatefulApp, CalendarV2):
    """Calendar client with navigation-aware user tool exposure."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        start, end = self._default_day_range()
        self.set_current_state(AgendaView(start_datetime=start, end_datetime=end))

    def _default_day_range(self) -> tuple[str, str]:
        """Derive the UTC day range surrounding the current simulated time."""

        now = datetime.fromtimestamp(self.time_manager.time(), tz=timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        return (
            start_of_day.strftime(DATETIME_FORMAT),
            end_of_day.strftime(DATETIME_FORMAT),
        )

    def _resolve_event_id(self, args: dict[str, Any], metadata: object | None) -> str | None:
        event_id = args.get("event_id")
        if isinstance(event_id, str):
            return event_id
        if isinstance(metadata, CalendarEvent):
            return metadata.event_id
        if isinstance(metadata, dict):
            candidate = metadata.get("event")
            if isinstance(candidate, CalendarEvent):
                return candidate.event_id
        return None

    @staticmethod
    def _draft_from_metadata(metadata_value: object | None) -> EditDraft | None:
        if not isinstance(metadata_value, dict):
            return None
        draft_data = metadata_value.get("draft")
        if isinstance(draft_data, EditDraft):
            return draft_data
        if isinstance(draft_data, dict):
            return EditDraft(
                event_id=draft_data.get("event_id"),
                title=draft_data.get("title", "Event"),
                start_datetime=draft_data.get("start_datetime"),
                end_datetime=draft_data.get("end_datetime"),
                tag=draft_data.get("tag"),
                description=draft_data.get("description"),
                location=draft_data.get("location"),
                attendees=list(draft_data.get("attendees", [])),
            )
        return None

    # pylint: disable=too-many-branches
    def handle_state_transition(self, event: CompletedEvent) -> None:
        """Update navigation state in response to user tool completions."""

        current_state = self.current_state
        function_name = event.function_name()

        if current_state is None or function_name is None:  # pragma: no cover - defensive
            return

        args = event.action.resolved_args or event.action.args
        metadata_value = event.metadata.return_value if event.metadata else None

        if isinstance(current_state, AgendaView):
            if function_name in {"open_event_by_id", "open_event_by_index"}:
                event_id = self._resolve_event_id(args, metadata_value)
                if event_id:
                    self.set_current_state(EventDetail(event_id=event_id))
                return

            if function_name == "start_create_event":
                self.set_current_state(EditEvent(draft=EditDraft()))
                return

            if function_name == "filter_by_tag":
                tag = args.get("tag")
                self.set_current_state(
                    AgendaView(
                        start_datetime=current_state.start_datetime,
                        end_datetime=current_state.end_datetime,
                        tag_filter=tag,
                        attendee_filter=current_state.attendee_filter,
                    )
                )
                return

            if function_name == "filter_by_attendee":
                attendee = args.get("attendee") or args.get("name")
                self.set_current_state(
                    AgendaView(
                        start_datetime=current_state.start_datetime,
                        end_datetime=current_state.end_datetime,
                        tag_filter=current_state.tag_filter,
                        attendee_filter=attendee,
                    )
                )
                return

            if function_name == "set_day":
                if isinstance(metadata_value, dict):
                    start = metadata_value.get("start_datetime")
                    end = metadata_value.get("end_datetime")
                    if isinstance(start, str) and isinstance(end, str):
                        self.set_current_state(
                            AgendaView(
                                start_datetime=start,
                                end_datetime=end,
                                tag_filter=current_state.tag_filter,
                                attendee_filter=current_state.attendee_filter,
                            )
                        )
                return

        if isinstance(current_state, EventDetail):
            if function_name == "edit_event":
                draft = self._draft_from_metadata(metadata_value)
                self.set_current_state(EditEvent(draft=draft))
                return

            if function_name in {"delete", "delete_by_attendee"}:
                if self.navigation_stack:
                    self.go_back()
                return

        if isinstance(current_state, EditEvent):
            if function_name == "save":
                event_id = metadata_value if isinstance(metadata_value, str) else None
                previous = self.navigation_stack[-1] if self.navigation_stack else None
                if isinstance(previous, EventDetail):
                    if event_id:
                        previous.event_id = event_id
                    previous.refresh()
                if self.navigation_stack:
                    self.go_back()
                else:  # pragma: no cover - defensive fallback
                    start, end = self._default_day_range()
                    self.set_current_state(
                        AgendaView(start_datetime=start, end_datetime=end)
                    )
                return

            if function_name == "discard":
                if self.navigation_stack:
                    self.go_back()
                else:  # pragma: no cover - defensive fallback
                    start, end = self._default_day_range()
                    self.set_current_state(
                        AgendaView(start_datetime=start, end_datetime=end)
                    )
                return

    def get_state_graph(self) -> dict[str, list[str]]:
        raise NotImplementedError

    def get_reachable_states(self, from_state):  # pragma: no cover - placeholder
        raise NotImplementedError
