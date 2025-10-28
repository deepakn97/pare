"""Proactive Agent User Interface with proposal management."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.tool_utils import AppTool, OperationType, app_tool, data_tool
from are.simulation.types import event_registered

from pas.apps.core import StatefulApp
from pas.apps.tool_decorators import pas_event_registered, user_tool

if TYPE_CHECKING:
    from are.simulation.agents.user_proxy import UserProxy

    from pas.apps.agent_ui.states import AgentUIRootState


@dataclass
class ProactiveProposal:
    """Represents a pending proactive proposal from the agent."""

    goal: str
    timestamp: float
    proposal_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class ProactiveAgentUserInterface(AgentUserInterface, StatefulApp):
    """Agent-user interface extended with proactive proposal support.

    This class allows the proactive agent to send proposals to the user,
    which the user can accept or decline as regular tool calls. This removes
    the need for a separate decision-making flow and gives users complete
    freedom to ignore proposals and perform other actions.
    """

    def __init__(self, user_proxy: UserProxy | None = None, name: str | None = None) -> None:
        """Initialize the proactive agent-user interface.

        Args:
            user_proxy: Optional user proxy for simulated responses
            name: Optional name for the app
        """
        AgentUserInterface.__init__(self, user_proxy=user_proxy)
        StatefulApp.__init__(self, name=name)
        self.pending_proposal: ProactiveProposal | None = None
        self.proposal_history: list[tuple[ProactiveProposal, bool]] = []

    def get_user_tools(self) -> list[AppTool]:
        """Expose base AgentUI tools alongside navigation actions."""
        base_tools = list(AgentUserInterface.get_user_tools(self))
        seen = {tool.name for tool in base_tools}
        for tool in StatefulApp.get_user_tools(self):
            if tool.name in seen:
                continue
            base_tools.append(tool)
            seen.add(tool.name)
        return base_tools

    @app_tool()
    @event_registered(operation_type=OperationType.WRITE)
    def send_proposal_to_user(self, goal: str) -> str:
        """Proactive agent sends a proposed action to the user.

        This method allows the proactive agent to suggest an action to the user.
        The proposal appears as a notification, and the user can freely choose to
        accept it, decline it, or ignore it and do something else entirely.

        Args:
            goal: The proposed action description

        Returns:
            Confirmation message
        """
        timestamp = self.time_manager.time()
        self.pending_proposal = ProactiveProposal(goal=goal, timestamp=timestamp)
        return f"Proposed to user: {goal}"

    @user_tool()
    @pas_event_registered()
    def accept_proposal(self) -> str:
        """User accepts the pending proactive proposal.

        Returns:
            Confirmation message or error if no pending proposal
        """
        if not self.pending_proposal:
            return "No pending proposal to accept"
        proposal = self.pending_proposal
        self.proposal_history.append((proposal, True))
        self.pending_proposal = None
        return f"Accepted proposal: {proposal.goal}"

    @user_tool()
    @pas_event_registered()
    def decline_proposal(self, reason: str = "") -> str:
        """User declines the pending proactive proposal.

        Args:
            reason: Optional reason for declining

        Returns:
            Confirmation message or error if no pending proposal
        """
        if not self.pending_proposal:
            return "No pending proposal to decline"
        proposal = self.pending_proposal
        self.proposal_history.append((proposal, False))
        self.pending_proposal = None
        msg = f"Declined proposal: {proposal.goal}"
        if reason:
            msg += f" (Reason: {reason})"
        return msg

    @app_tool()
    @data_tool()
    def get_pending_proposal(self) -> str | None:
        """Get the current pending proposal if any.

        Returns:
            The goal text of the pending proposal, or None if no proposal is pending
        """
        if self.pending_proposal:
            return self.pending_proposal.goal
        return None

    def create_root_state(self) -> AgentUIRootState:
        """Return the root state for this stateful app."""
        from pas.apps.agent_ui.states import AgentUIRootState

        return AgentUIRootState()

    def handle_state_transition(self, event: object) -> None:
        """Handle state transitions for agent UI events."""
        # Agent UI typically doesn't have complex state transitions
        # Proposals are managed through the pending_proposal attribute
        pass
