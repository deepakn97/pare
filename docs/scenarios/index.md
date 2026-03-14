# Scenarios Overview

The scenarios subsystem has two parts:

- **Benchmark scenarios**: curated, registered scenarios used for evaluation.
- **Scenario generator**: multi-step pipeline that produces new candidate scenarios.

## Benchmark Side

Core modules:

- `pare/scenarios/scenario.py`: `PAREScenario` base class.
- `pare/scenarios/registration.py`: scenario discovery and registration.
- `pare/scenarios/config.py`: runner configs.
- `pare/scenarios/benchmark/`: benchmark scenario implementations.

CLI entrypoints:

- `pare scenarios list`
- `pare benchmark sweep`

Execution/runtime details:

- [Runtime Execution Config](../runtime_execution.md)
- [Trace Export Semantics](../trace_export.md)

## Generator Side

Core modules:

- `pare/scenarios/generator/scenario_generator.py`: generator CLI/utilities.
- `pare/scenarios/generator/agent/scenario_generating_agent_orchestrator.py`: step orchestration.
- `pare/scenarios/generator/agent/step_agents.py`: step-specific LLM agents.
- `pare/scenarios/scenario_metadata.json`: metadata used for listing and uniqueness checks.

Outputs:

- Working file: `pare/scenarios/default_generation_output/editable_seed_scenario.py`
- Final generated scenarios: `pare/scenarios/default_generation_output/`
- Step trajectory snapshots: `pare/scenarios/generator/step_trajectory/`

See:

- [Benchmark Scenarios](benchmark.md)
- [Scenario Generation](../scenario_generator.md)
- [Multi-Step Scenario Generator Flow](../scenario_generator_flow.md)
