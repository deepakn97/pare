"""Proactive Agent User Interface with proposal management."""

from __future__ import annotations

from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.tool_utils import OperationType
from are.simulation.types import EventType, disable_events, event_registered
from are.simulation.utils import type_check

from pas.apps.tool_decorators import user_tool


class PASAgentUserInterface(AgentUserInterface):
    """Agent-user interface extended with proactive proposal acceptance and rejection support.

    Adds tools which the user agent uses to accept or reject the proactive agent's proposal.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the proactive agent-user interface.

        Args:
            args: Arguments to pass to the app
            kwargs: Keyword arguments to pass to the app
        """
        super().__init__(*args, **kwargs)

    @type_check
    @user_tool()
    @event_registered(operation_type=OperationType.WRITE, event_type=EventType.USER)
    def accept_proposal(self, content: str = "") -> str:
        """User accepts the pending proactive proposal.

        Args:
            content: The content of the message to send to the agent

        Returns:
            The message ID that was generated for this message, can be used for tracking
        """
        with disable_events():
            return self.send_message_to_agent(content=content)

    @type_check
    @user_tool()
    @event_registered(operation_type=OperationType.WRITE, event_type=EventType.USER)
    def reject_proposal(self, content: str = "") -> str:
        """User rejects the pending proactive proposal.

        Args:
            content: The content of the message to send to the agent

        Returns:
            The message ID that was generated for this message, can be used for tracking
        """
        with disable_events():
            return self.send_message_to_agent(content=content)
