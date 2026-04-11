# Scenarios Overview

If you mainly want to use the benchmark, this is the most important section. The scenarios subsystem has two parts:

- **Benchmark scenarios**: curated, registered scenarios used for evaluation.
- **Scenario generator**: multi-step pipeline that produces new candidate scenarios.

## Most Common Tasks

### List available benchmark scenarios

```bash
uv run pare scenarios list
```

### Inspect benchmark split files

```bash
uv run pare scenarios splits
uv run pare scenarios split --split full
```

### Filter scenarios by app usage

```bash
uv run pare scenarios list --apps StatefulEmailApp --apps StatefulCalendarApp
```

### Run the benchmark

```bash
uv run pare benchmark sweep --split full --observe-model gpt-5 --execute-model gpt-5
```

### Generate additional scenarios

```bash
uv run pare scenarios generate --num-scenarios 3
```

## Benchmark Scenarios

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

## Scenario Generator

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
- [Scenario Authoring Guide](authoring.md)
- [Scenarios CLI Usage](cli_usage.md)
- [Multi-Step Scenario Generator Flow](scenario_generator_flow.md)
