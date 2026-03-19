# Agents Overview

Most benchmark users do not need to modify agent internals. This section is mainly for understanding which model does what during a run and where to look if you want to tune behavior.

PARE uses two agent roles:

- **User agent** (`pare.agents.user.agent.UserAgent`) acts as the simulated user and uses app tools.
- **Proactive agent** (`pare.agents.proactive.agent.ProactiveAgent`) observes the environment, decides when to intervene, and executes accepted actions.

## How To Use This In Practice

For normal benchmark runs, the main choice is which models power the proactive agent's observe and execute phases:

```bash
uv run pare benchmark sweep --split full --observe-model gpt-5 --execute-model gpt-5
```

Read this section when you want to:

- understand why benchmark runs use two agent roles
- inspect prompt/config builders
- change iteration limits or model-specific settings
- trace how agent decisions move through the runtime

## Key Modules

- `pare/agents/pare_agent_config.py`: typed config models for user/proactive agents.
- `pare/agents/agent_config_builder.py`: default config builders for prompts and iteration limits.
- `pare/agents/agent_factory.py`: low-level construction of wrapped Meta-ARE agents.
- `pare/agents/agent_builder.py`: high-level builder used by runner paths.

## Where Agents Fit In The Benchmark

1. A scenario from `pare/scenarios/benchmark/` is loaded.
2. The runner builds user and proactive agents from config.
3. The user agent advances the task while the proactive agent observes and optionally intervenes.
4. The run ends with traces that can be analyzed or annotated.

See also:

- [Agent Interaction Lifecycle](interaction_lifecycle.md)
- [Runtime Execution Flow](../runtime_execution_flow.md)
- [Agents API](../api/agents.md)
