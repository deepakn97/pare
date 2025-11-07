"""PAS-specific agent log types."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from are.simulation.agents.agent_log import (
    ActionLog,
    AgentUserInterfaceLog,
    BaseAgentLog,
    EndTaskLog,
    EnvironmentNotificationLog,
    ErrorLog,
    FactsLog,
    FinalAnswerLog,
    HintLog,
    LLMInputLog,
    LLMOutputFactsLog,
    LLMOutputPlanLog,
    LLMOutputThoughtActionLog,
    ObservationLog,
    PlanLog,
    RationaleLog,
    RefactsLog,
    ReplanLog,
    StepLog,
    StopLog,
    SubagentLog,
    SystemPromptLog,
    TaskLog,
    TaskReminderLog,
    ThoughtLog,
    ToolCallLog,
)

if TYPE_CHECKING:
    from are.simulation.agents.multimodal import Attachment


@dataclass
class PASAgentLog(BaseAgentLog):
    """Base class for all PAS Agent Logs."""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PASAgentLog:
        """Create a PASAgentLog from a dictionary."""
        log_type = d.pop("log_type", None)
        log_id = d.pop("id", str(uuid.uuid4().hex))
        if log_type is None:
            raise ValueError("Log type is not specified")

        log_type_map = {
            "system_prompt": SystemPromptLog,
            "task": TaskLog,
            "llm_input": LLMInputLog,
            "llm_output": LLMOutputThoughtActionLog,
            "llm_output_thought_action": LLMOutputThoughtActionLog,
            "rationale": RationaleLog,
            "tool_call": ToolCallLog,
            "observation": ObservationLog,
            "step": StepLog,
            "subagent": SubagentLog,
            "final_answer": FinalAnswerLog,
            "error": ErrorLog,
            "thought": ThoughtLog,
            "plan": PlanLog,
            "facts": FactsLog,
            "replan": ReplanLog,
            "refacts": RefactsLog,
            "stop": StopLog,
            "action": ActionLog,
            "end_task": EndTaskLog,
            "raw_plan": LLMOutputPlanLog,
            "llm_output_plan": LLMOutputPlanLog,
            "raw_facts": LLMOutputFactsLog,
            "llm_output_facts": LLMOutputFactsLog,
            "agent_user_interface": AgentUserInterfaceLog,
            "available_tools": AvailableToolsLog,
            "current_app_state": CurrentAppStateLog,
            "agent_message": AgentMessageLog,
            "user_action": UserActionLog,
            "environment_notifications": EnvironmentNotificationLog,
            "hint": HintLog,
            "task_reminder": TaskReminderLog,
        }

        log_class = log_type_map.get(log_type)
        if log_class is not None:
            log = log_class(**d)
            if log_type == "subagent":
                log.children = [PASAgentLog.from_dict(child) for child in d["children"]]
            log.id = log_id
            return log

        raise ValueError(f"Unknown agent log type: {log_type}")


@dataclass
class AgentMessageLog(BaseAgentLog):
    """Log entry for messages from ProactiveAgent to UserAgent.

    Used by UserAgent preprocessing to store AGENT_MESSAGE notifications.
    These are proposals/messages sent via send_message_to_user tool.
    """

    content: str
    attachments: list[Attachment] = field(default_factory=list)

    def get_content_for_llm(self) -> str | None:
        """Return content to be sent to LLM."""
        return self.content

    def get_content_for_llm_no_attachment(self) -> str | None:
        """Return content without attachment placeholders."""
        content = re.sub(r"<\|attachment:(\d+)\|>", "", self.content)
        return content

    def get_attachments_for_llm(self) -> list[Attachment]:
        """Return attachments for LLM."""
        return self.attachments

    def get_type(self) -> str:
        """Return log type identifier."""
        return "agent_message"


@dataclass
class AvailableToolsLog(BaseAgentLog):
    """Log entry for all available tools for user agent at the current state.

    Used by UserAgent preprocessing to store AVAILABLE_TOOLS notifications.
    These are tools that are available to the user agent at the current state.
    """

    content: str

    def get_content_for_llm(self) -> str | None:
        """Return content to be sent to LLM."""
        return self.content

    def get_type(self) -> str:
        """Return log type identifier."""
        return "available_tools"


@dataclass
class UserActionLog(BaseAgentLog):
    """Log entry for user actions observed by the proactive agent.

    Each log represents a list of user actions since the last step.
    Multiple logs accumulate in the agent history to show full action sequence.
    """

    content: str

    def get_content_for_llm(self) -> str | None:
        """Return content to be sent to LLM."""
        return self.content

    def get_type(self) -> str:
        """Return log type identifier."""
        return "user_action"


@dataclass
class CurrentAppStateLog(BaseAgentLog):
    """Log entry for the current app state for user agent at the current state.

    Used by UserAgent preprocessing to store CURRENT_APP_STATE notifications.
    These are the current state of the app at the current state.
    """

    content: str

    def get_content_for_llm(self) -> str | None:
        """Return content to be sent to LLM."""
        return self.content

    def get_type(self) -> str:
        """Return log type identifier."""
        return "current_app_state"
