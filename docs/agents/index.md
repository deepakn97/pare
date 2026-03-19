# Agents Overview

PARE agents are split into two roles and orchestrated by the scenario runner:

- **User agent** (`pare.agents.user.agent.UserAgent`) executes user-side actions with app tools.
- **Proactive agent** (`pare.agents.proactive.agent.ProactiveAgent`) observes events, proposes interventions, and executes accepted plans.

## Key Modules

- `pare/agents/pare_agent_config.py`: typed config models for user/proactive agents.
- `pare/agents/agent_config_builder.py`: default config builders for prompts and iteration limits.
- `pare/agents/agent_factory.py`: low-level construction of wrapped Meta-ARE agents.
- `pare/agents/agent_builder.py`: high-level builder used by runner paths.

## Runtime Integration

Agent construction is consumed by the scenario runtime:

- `pare/scenario_runner.py`: single-scenario execution loop (`TwoAgentScenarioRunner`).
- `pare/multi_scenario_runner.py`: parallel/sequential batch orchestration.

See also:

- [Agent Interaction Lifecycle](interaction_lifecycle.md)
- [Runtime Execution Flow](../runtime_execution_flow.md)

## Typical Flow

1. Load scenario definition (`pare.scenarios`).
2. Build user + proactive agents from config.
3. Run turns until validation success, timeout, or turn limit.
4. Export traces for benchmarking and optional annotation workflows.

For API-level docs, see [Agents API](../api/agents.md).
