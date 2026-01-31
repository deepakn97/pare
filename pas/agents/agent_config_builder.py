from __future__ import annotations

from abc import ABC, abstractmethod

from are.simulation.agents.are_simulation_agent_config import ARESimulationReactBaseAgentConfig

from pas.agents.pas_agent_config import PASAgentConfig, ProactiveObserveExecuteAgentConfig, UserDefaultAgentConfig
from pas.agents.proactive.prompts.execute_prompt import DEFAULT_PROACTIVE_EXECUTE_PROMPT_WITH_HINTS
from pas.agents.proactive.prompts.observe_prompt import DEFAULT_PROACTIVE_OBSERVE_PROMPT_WITH_HINTS
from pas.agents.user.prompts.system_prompt import DEFAULT_USER_AGENT_SYSTEM_PROMPT


class AbstractAgentConfigBuilder(ABC):
    """Abstract class for building agent configs."""

    @abstractmethod
    def build(
        self,
        agent_name: str,
    ) -> PASAgentConfig:
        """Build a config for the specified agent.

        Args:
            agent_name: Name of the agent that affects the config type.

        Returns:
            An instance of the config.
        """


class UserAgentConfigBuilder(AbstractAgentConfigBuilder):
    """Builder for UserAgentConfig."""

    def build(
        self,
        agent_name: str,
    ) -> PASAgentConfig:
        """Build the correct UserAgentConfig based on the agent name.

        Args:
            agent_name: Name of the user agent type.

        Returns:
            A configured UserDefaultAgentConfig instance.

        Raises:
            ValueError: If the agent name is not recognized.
        """
        match agent_name:
            case "default":
                return UserDefaultAgentConfig(
                    agent_name=agent_name,
                    base_agent_config=ARESimulationReactBaseAgentConfig(
                        system_prompt=str(DEFAULT_USER_AGENT_SYSTEM_PROMPT),
                        max_iterations=1,
                    ),
                )

            case _:
                raise ValueError(f"Unknown user agent type: {agent_name}")


class ProactiveAgentConfigBuilder(AbstractAgentConfigBuilder):
    """Builder for ProactiveAgentConfig."""

    def build(
        self,
        agent_name: str,
    ) -> PASAgentConfig:
        """Build the correct ProactiveAgentConfig based on the agent name.

        Args:
            agent_name: Name of the proactive agent type.

        Returns:
            A configured ProactiveObserveExecuteAgentConfig instance.

        Raises:
            ValueError: If the agent name is not recognized.
        """
        match agent_name:
            case "observe-execute":
                return ProactiveObserveExecuteAgentConfig(
                    agent_name=agent_name,
                    observe_base_agent_config=ARESimulationReactBaseAgentConfig(
                        system_prompt=str(DEFAULT_PROACTIVE_OBSERVE_PROMPT_WITH_HINTS),
                        max_iterations=5,
                    ),
                    execute_base_agent_config=ARESimulationReactBaseAgentConfig(
                        system_prompt=str(DEFAULT_PROACTIVE_EXECUTE_PROMPT_WITH_HINTS),
                        max_iterations=10,
                    ),
                )

            case _:
                raise ValueError(f"Unknown proactive agent type: {agent_name}")
