"""PARE-specific tool decorators that extend Meta ARE functionality."""

from __future__ import annotations

import inspect
import traceback
import uuid
from functools import wraps
from typing import TYPE_CHECKING, Any

from are.simulation.tool_utils import APPTOOL_ATTR_NAME, OperationType, user_tool
from are.simulation.types import Action, EventRegisterer, EventType

if TYPE_CHECKING:
    from collections.abc import Callable

# Explicitly declare exports (needed for mypy since we re-export user_tool from Meta-ARE)
__all__ = ["pare_event_registered", "user_tool"]


# NOTE: Keep the default event type as USER since we use the @user_tool + pare_event_registered to register events for the user agent.
def pare_event_registered(
    operation_type: OperationType = OperationType.READ, event_type: EventType = EventType.USER
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """PARE-specific event registration decorator that handles AppState instances.

    This is an adaptation of Meta ARE's native @event_registered decorator to support
    PARE's AppState pattern where methods are defined on state classes that don't have
    direct access to `self.name` or `self.time_manager`, but instead access them via
    `self.app.name` and `self.app.time_manager`.

    The decorator follows Meta ARE's event registration pattern but adapts it for:
    - AppState instances (which have self.app.name and self.app.time_manager)
    - StatefulApp instances (which have self.name and self.time_manager)

    Args:
        operation_type: Whether this is a READ or WRITE operation
        event_type: The type of event to generate (default: EventType.AGENT)

    Example:
        @user_tool()
        @pare_event_registered(operation_type=OperationType.WRITE)
        def forward(self, recipients: list[str]) -> str:
            with disable_events():
                return self.app.forward_email(...)
    """

    def with_event(func: Callable[..., Any]) -> Callable[..., Any]:
        func.__event_registered__ = True  # type: ignore[attr-defined]
        func.__operation_type__ = operation_type  # type: ignore[attr-defined]

        @wraps(func)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
            # Only apply event registration if EventRegisterer is active
            if not EventRegisterer.is_active():
                return func(self, *args, **kwargs)

            # Get the app instance - handle both App (self) and AppState (self.app)
            app = self.app if hasattr(self, "app") else self

            # Create action ID using app name
            action_id = f"{app.name}.{func.__name__}-{uuid.uuid4()}"

            # Bind arguments
            bound_arguments = inspect.signature(func).bind(self, *args, **kwargs)
            bound_arguments.apply_defaults()
            func_args = bound_arguments.arguments

            # Create Action object
            action = Action(app=app, function=func, args=func_args, action_id=action_id, operation_type=operation_type)

            # Check if we're in capture mode
            if EventRegisterer.is_capture_mode():
                # Import here to avoid circular dependencies
                from are.simulation.types import Event

                # In capture mode, return an Event without executing
                return Event(event_id=f"{EventType.ENV.value}-{action_id}", event_type=EventType.ENV, action=action)
            else:
                # Import here to avoid circular dependencies
                from are.simulation.types import CompletedEvent, EventMetadata

                # Execute the function and capture result/exception
                event_metadata = EventMetadata()
                event_time = app.time_manager.time()

                try:
                    result = func(self, *args, **kwargs)
                    event_metadata.return_value = result
                except Exception as e:
                    event_metadata.exception = str(e)
                    event_metadata.exception_stack_trace = traceback.format_exc()
                    raise
                finally:
                    # Create and register the completed event
                    event = CompletedEvent(
                        event_id=f"{event_type.value}-{action_id}",
                        event_type=event_type,
                        action=action,
                        metadata=event_metadata,
                        event_time=event_time,
                    )
                    app.add_event(event)

                return result

        # Propagate AppTool metadata between original function and wrapper
        apptool = getattr(func, APPTOOL_ATTR_NAME, None)
        if apptool is not None:
            setattr(wrapper, APPTOOL_ATTR_NAME, apptool)

        # Add function to set AppTool metadata on both wrapper and original
        def set_apptool(app_tool_instance: Any) -> None:  # noqa: ANN401
            setattr(wrapper, APPTOOL_ATTR_NAME, app_tool_instance)
            setattr(func, APPTOOL_ATTR_NAME, app_tool_instance)

        wrapper.set_apptool = set_apptool  # type: ignore[attr-defined]

        return wrapper

    return with_event
