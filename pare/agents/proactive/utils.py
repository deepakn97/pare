from __future__ import annotations

from enum import Enum

from are.simulation.agents.default_agent.base_agent import DEFAULT_STEP_2_MESSAGE, DEFAULT_STEP_2_ROLE
from are.simulation.agents.llm.types import MessageRole


class ProactiveAgentMode(Enum):
    """Runtime state of the Proactive Agent."""

    OBSERVE = "observe"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTE = "execute"  # Execute the confirmed goal


def _get_default_proactive_step_2_role() -> dict[str, str]:
    """Get the default step 2 role for the proactive agent."""
    DEFAULT_PROACTIVE_STEP_2_ROLE = DEFAULT_STEP_2_ROLE.copy()
    DEFAULT_PROACTIVE_STEP_2_ROLE["user_action"] = MessageRole.USER
    return DEFAULT_PROACTIVE_STEP_2_ROLE


def _get_default_proactive_step_2_message() -> dict[str, str]:
    """Get the default step 2 message for the proactive agent."""
    DEFAULT_PROACTIVE_STEP_2_MESSAGE = DEFAULT_STEP_2_MESSAGE.copy()
    DEFAULT_PROACTIVE_STEP_2_MESSAGE["user_action"] = "[User Actions]:\n***\n{content}\n***\n"
    return DEFAULT_PROACTIVE_STEP_2_MESSAGE


DEFAULT_PROACTIVE_STEP_2_ROLE = _get_default_proactive_step_2_role()
DEFAULT_PROACTIVE_STEP_2_MESSAGE = _get_default_proactive_step_2_message()
