"""Agent builders for PARE agents.

This module contains builders for creating UserAgent and ProactiveAgent instances
from their respective configurations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from are.simulation.agents.llm.llm_engine_builder import LLMEngineBuilder

from pare.agents.pare_agent_config import PAREAgentConfig, ProactiveObserveExecuteAgentConfig, UserDefaultAgentConfig

if TYPE_CHECKING:
    from pare.agents.proactive.agent import ProactiveAgent
    from pare.agents.user.agent import UserAgent
    from pare.environment import StateAwareEnvironmentWrapper


class AbstractAgentBuilder(ABC):
    """Abstract class for building PARE agents."""

    @abstractmethod
    def list_agents(self) -> list[str]:
        """List all available agent types.

        Returns:
            A list of agent names that this builder can create.
        """

    @abstractmethod
    def build(
        self,
        agent_config: PAREAgentConfig,
        env: StateAwareEnvironmentWrapper | None = None,
        mock_responses: list[str] | None = None,
    ) -> Any:  # noqa: ANN401
        """Build an agent from config.

        Args:
            agent_config: Configuration for the agent to be built.
            env: Optional environment in which the agent will operate.
            mock_responses: Optional list of mock responses for testing.

        Returns:
            An instance of the agent.
        """


class UserAgentBuilder(AbstractAgentBuilder):
    """Builder for UserAgent instances."""

    def __init__(self, llm_engine_builder: LLMEngineBuilder | None = None) -> None:
        """Initialize the UserAgentBuilder.

        Args:
            llm_engine_builder: Optional LLM engine builder. If not provided,
                a default LLMEngineBuilder will be used.
        """
        self.llm_engine_builder = llm_engine_builder or LLMEngineBuilder()

    def list_agents(self) -> list[str]:
        """List all available user agent types.

        Returns:
            A list of user agent names that this builder can create.
        """
        return ["default"]

    def build(
        self,
        agent_config: PAREAgentConfig,
        env: StateAwareEnvironmentWrapper | None = None,
        mock_responses: list[str] | None = None,
    ) -> UserAgent:
        """Build a UserAgent from config.

        Args:
            agent_config: Configuration for the user agent. Must be a UserAgentConfig.
            env: Environment in which the agent will operate.
            mock_responses: Optional list of mock responses for testing.

        Returns:
            A configured UserAgent instance.

        Raises:
            TypeError: If agent_config is not a UserDefaultAgentConfig.
            ValueError: If the agent name is not supported or required environment components are missing.
        """
        match agent_config.get_agent_name():
            case "default":
                from pare.agents.agent_factory import create_default_user_agent

                if env is None:
                    raise ValueError("Environment must be provided")
                if env.time_manager is None:
                    raise ValueError("Time manager must be provided")
                if env.append_to_world_logs is None:
                    raise ValueError("Log callback must be provided")

                base_agent_config = agent_config.get_base_agent_configs()["user"]
                llm_engine = self.llm_engine_builder.create_engine(
                    engine_config=base_agent_config.llm_engine_config,
                    mock_responses=mock_responses,
                )

                if isinstance(agent_config, UserDefaultAgentConfig):
                    return create_default_user_agent(
                        agent_config=agent_config,
                        env=env,
                        llm_engine=llm_engine,
                    )
                else:
                    raise TypeError(f"Agent {agent_config.get_agent_name()} requires a UserDefaultAgentConfig")

            case _:
                raise ValueError(f"Unknown user agent type: {agent_config.get_agent_name()}")


class ProactiveAgentBuilder(AbstractAgentBuilder):
    """Builder for ProactiveAgent instances."""

    def __init__(self, llm_engine_builder: LLMEngineBuilder | None = None) -> None:
        """Initialize the ProactiveAgentBuilder.

        Args:
            llm_engine_builder: Optional LLM engine builder. If not provided,
                a default LLMEngineBuilder will be used.
        """
        self.llm_engine_builder = llm_engine_builder or LLMEngineBuilder()

    def list_agents(self) -> list[str]:
        """List all available proactive agent types.

        Returns:
            A list of proactive agent names that this builder can create.
        """
        return ["observe-execute"]

    def build(
        self,
        agent_config: PAREAgentConfig,
        env: StateAwareEnvironmentWrapper | None = None,
        mock_responses: list[str] | None = None,
    ) -> ProactiveAgent:
        """Build a ProactiveAgent from config.

        Args:
            agent_config: Configuration for the proactive agent.
                Must be a ProactiveObserveExecuteAgentConfig.
            env: Environment in which the agent will operate.
            mock_responses: Optional list of mock responses for testing.

        Returns:
            A configured ProactiveAgent instance.

        Raises:
            TypeError: If agent_config is not a ProactiveObserveExecuteAgentConfig.
            ValueError: If the agent name is not supported or required environment components are missing.
        """
        match agent_config.get_agent_name():
            case "observe-execute":
                from pare.agents.agent_factory import create_observe_execute_proactive_agent

                if env is None:
                    raise ValueError("Environment must be provided")
                if env.time_manager is None:
                    raise ValueError("Time manager must be provided")
                if env.append_to_world_logs is None:
                    raise ValueError("Log callback must be provided")

                base_agent_configs = agent_config.get_base_agent_configs()
                observe_llm_engine = self.llm_engine_builder.create_engine(
                    engine_config=base_agent_configs["observe"].llm_engine_config,
                    mock_responses=mock_responses,
                )
                execute_llm_engine = self.llm_engine_builder.create_engine(
                    engine_config=base_agent_configs["execute"].llm_engine_config,
                    mock_responses=mock_responses,
                )

                if isinstance(agent_config, ProactiveObserveExecuteAgentConfig):
                    return create_observe_execute_proactive_agent(
                        agent_config=agent_config,
                        env=env,
                        observe_llm_engine=observe_llm_engine,
                        execute_llm_engine=execute_llm_engine,
                    )
                else:
                    raise TypeError(
                        f"Agent {agent_config.get_agent_name()} requires a ProactiveObserveExecuteAgentConfig"
                    )

            case _:
                raise ValueError(f"Unknown proactive agent type: {agent_config.get_agent_name()}")
