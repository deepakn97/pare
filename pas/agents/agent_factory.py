"""Factory functions for creating PAS agents.

This module contains factory functions that create BaseAgent instances
with the appropriate prompts, presteps, and configurations, then wrap
them in UserAgent or ProactiveAgent wrappers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from are.simulation.agents.default_agent.base_agent import BaseAgent
from are.simulation.agents.default_agent.tools.json_action_executor import JsonActionExecutor

from pas.agents.proactive.agent import ProactiveAgent
from pas.agents.proactive.steps import get_proactive_agent_pre_step
from pas.agents.user.agent import UserAgent
from pas.agents.user.steps import get_user_agent_pre_step

if TYPE_CHECKING:
    from are.simulation.agents.llm.llm_engine import LLMEngine

    from pas.agents.pas_agent_config import ProactiveObserveExecuteAgentConfig, UserDefaultAgentConfig
    from pas.environment import StateAwareEnvironmentWrapper


def create_default_user_agent(
    agent_config: UserDefaultAgentConfig,
    env: StateAwareEnvironmentWrapper,
    llm_engine: LLMEngine,
) -> UserAgent:
    """Create a default UserAgent with the given configuration.

    Args:
        agent_config: Configuration for the user agent.
        env: Environment in which the agent will operate.
        llm_engine: Pre-built LLM engine for the agent.

    Returns:
        A configured UserAgent instance.
    """
    base_agent_config = agent_config.get_base_agent_configs()["user"]

    user_base_agent = BaseAgent(
        llm_engine=llm_engine,
        tools={},  # Will be set by UserAgent.init_tools()
        max_iterations=base_agent_config.max_iterations,
        conditional_pre_steps=[get_user_agent_pre_step()],
        action_executor=JsonActionExecutor(
            tools={},
            use_custom_logger=base_agent_config.use_custom_logger,
        ),
        system_prompts={"system_prompt": str(base_agent_config.system_prompt)},
        use_custom_logger=base_agent_config.use_custom_logger,
    )

    return UserAgent(
        log_callback=env.append_to_world_logs,
        pause_env=env.pause,
        resume_env=env.resume_with_offset,
        llm_engine=llm_engine,
        base_agent=user_base_agent,
        time_manager=env.time_manager,
        max_iterations=base_agent_config.max_iterations,
        max_turns=agent_config.max_turns,
        simulated_generation_time_config=base_agent_config.simulated_generation_time_config,
    )


def create_observe_execute_proactive_agent(
    agent_config: ProactiveObserveExecuteAgentConfig,
    env: StateAwareEnvironmentWrapper,
    observe_llm_engine: LLMEngine,
    execute_llm_engine: LLMEngine,
) -> ProactiveAgent:
    """Create an observe-execute ProactiveAgent with the given configuration.

    Args:
        agent_config: Configuration for the proactive agent.
        env: Environment in which the agent will operate.
        observe_llm_engine: Pre-built LLM engine for the observe agent.
        execute_llm_engine: Pre-built LLM engine for the execute agent.

    Returns:
        A configured ProactiveAgent instance.
    """
    base_agent_configs = agent_config.get_base_agent_configs()
    observe_config = base_agent_configs["observe"]
    execute_config = base_agent_configs["execute"]

    observe_base_agent = BaseAgent(
        llm_engine=observe_llm_engine,
        tools={},  # Will be set by ProactiveAgent.init_tools()
        max_iterations=observe_config.max_iterations,
        conditional_pre_steps=[get_proactive_agent_pre_step()],
        action_executor=JsonActionExecutor(
            tools={},
            use_custom_logger=observe_config.use_custom_logger,
        ),
        system_prompts={"system_prompt": str(observe_config.system_prompt)},
        use_custom_logger=observe_config.use_custom_logger,
    )

    execute_base_agent = BaseAgent(
        llm_engine=execute_llm_engine,
        tools={},  # Will be set by ProactiveAgent.init_tools()
        max_iterations=execute_config.max_iterations,
        conditional_pre_steps=[get_proactive_agent_pre_step()],
        action_executor=JsonActionExecutor(
            tools={},
            use_custom_logger=execute_config.use_custom_logger,
        ),
        system_prompts={"system_prompt": str(execute_config.system_prompt)},
        use_custom_logger=execute_config.use_custom_logger,
    )

    return ProactiveAgent(
        log_callback=env.append_to_world_logs,
        pause_env=env.pause,
        resume_env=env.resume_with_offset,
        observe_llm_engine=observe_llm_engine,
        observe_agent=observe_base_agent,
        execute_llm_engine=execute_llm_engine,
        execute_agent=execute_base_agent,
        time_manager=env.time_manager,
        tools=[],
        observe_max_iterations=observe_config.max_iterations,
        execute_max_iterations=execute_config.max_iterations,
        max_turns=agent_config.max_turns,
        simulated_generation_time_config=observe_config.simulated_generation_time_config,
    )
