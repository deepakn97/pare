from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from are.simulation.agents.are_simulation_agent_config import ARESimulationReactBaseAgentConfig
from pydantic import BaseModel, Field


class PASAgentConfig(ABC):
    """Abstract class for PAS agent configurations."""

    @abstractmethod
    def get_agent_name(self) -> str | None:
        """Get the name of the agent."""
        pass

    @abstractmethod
    def get_model_dump(self) -> dict[str, Any]:
        """Get the model dump of the agent configuration."""
        pass

    @abstractmethod
    def get_base_agent_configs(self) -> dict[str, ARESimulationReactBaseAgentConfig]:
        """Get the base agent configurations."""
        pass

    @abstractmethod
    def get_model_json_schema(self) -> dict[str, Any]:
        """Get the JSON schema of the agent configuration."""
        pass

    @abstractmethod
    def validate_model(self, agent_config_dict: dict[str, Any]) -> PASAgentConfig:
        """Validate the agent configuration model."""
        pass


class UserDefaultAgentConfig(BaseModel, PASAgentConfig):
    """User agent configuration for PAS."""

    agent_name: str = Field(default="default")
    base_agent_config: ARESimulationReactBaseAgentConfig = Field(
        default_factory=lambda: ARESimulationReactBaseAgentConfig(max_iterations=1)
    )
    max_turns: int | None = Field(default=None)

    def get_agent_name(self) -> str | None:
        """Get the name of the agent."""
        return self.agent_name

    def get_base_agent_configs(self) -> dict[str, ARESimulationReactBaseAgentConfig]:
        """Get the base agent configurations for the user agent."""
        return {"user": self.base_agent_config}

    def get_model_dump(self) -> dict[str, Any]:
        """Docstring for get_model_dump."""
        return self.model_dump()

    def get_model_json_schema(self) -> dict[str, Any]:
        """Docstring for get_model_json_schema."""
        return self.model_json_schema()

    def validate_model(self, agent_config_dict: dict[str, Any]) -> PASAgentConfig:
        """Docstring for validate_model."""
        return type(self).model_validate(agent_config_dict)


class ProactiveObserveExecuteAgentConfig(BaseModel, PASAgentConfig):
    """Proactive agent configuration for PAS."""

    agent_name: str = Field(default="observe-execute")
    observe_base_agent_config: ARESimulationReactBaseAgentConfig = Field(
        default_factory=lambda: ARESimulationReactBaseAgentConfig(max_iterations=5)
    )
    execute_base_agent_config: ARESimulationReactBaseAgentConfig = Field(
        default_factory=lambda: ARESimulationReactBaseAgentConfig(max_iterations=10)
    )
    max_turns: int | None = Field(default=None)

    def get_agent_name(self) -> str | None:
        """Get the name of the agent."""
        return self.agent_name

    def get_base_agent_configs(self) -> dict[str, ARESimulationReactBaseAgentConfig]:
        """Get the base agent configurations for the observe and execute agents."""
        return {"observe": self.observe_base_agent_config, "execute": self.execute_base_agent_config}

    def get_model_dump(self) -> dict[str, Any]:
        """Docstring for get_model_dump."""
        return self.model_dump()

    def get_model_json_schema(self) -> dict[str, Any]:
        """Docstring for get_model_json_schema."""
        return self.model_json_schema()

    def validate_model(self, agent_config_dict: dict[str, Any]) -> PASAgentConfig:
        """Docstring for validate_model."""
        return type(self).model_validate(agent_config_dict)
