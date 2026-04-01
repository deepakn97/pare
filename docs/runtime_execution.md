# Runtime Execution Config

This page explains how PARE execution is configured, how result caching works, and how runtime noise is injected.

## Core Config Models

- `pare.scenarios.config.ScenarioRunnerConfig`: configuration for one scenario run
- `pare.scenarios.config.MultiScenarioRunnerConfig`: batch/sweep configuration for multiple scenarios

## Single-Scenario Controls

`ScenarioRunnerConfig` controls the execution behavior that changes scenario results:

- user / observe / execute model configs
- per-agent iteration limits
- `oracle` mode
- `max_turns`
- `tool_augmentation_config`
- `env_events_config`
- simulated generation-time behavior

It also includes output-oriented settings such as:

- `output_dir`
- `export`
- `trace_dump_format`

These affect artifacts, but not necessarily the logical scenario result itself.

## Batch Controls

`MultiScenarioRunnerConfig` extends the single-scenario config with batch execution settings:

- `max_concurrent_scenarios`
- `timeout_seconds`
- `executor_type`
- `log_level`
- `log_to_file`
- `logs_dir`
- `enable_caching`
- `experiment_name`

`MultiScenarioRunner` derives a per-scenario `ScenarioRunnerConfig` from the shared multi-scenario config before each run.

## Caching Semantics

Caching is handled in `pare/scenarios/utils/caching.py`.

### What determines cache identity

Cache entries are keyed by:

- scenario id (and optional run number)
- execution-relevant config hash
- scenario hash

The config hash intentionally includes fields that change scenario behavior, such as:

- logical model aliases
- iteration limits
- `oracle`
- `max_turns`
- tool augmentation settings
- environmental event settings

The config hash intentionally ignores fields that should not invalidate results, such as:

- output directory
- export location / trace format
- logging options
- parallelism settings

That means you can usually reuse cached logical results across different output layouts or experiment folders.

### Cache storage location

Priority order:

1. `PARE_CACHE_DIR`
2. configured cache dir in `~/.config/pare/config.json`
3. default: `~/.cache/pare/scenario_results`

User-facing cache management is available through:

```bash
uv run pare cache status
uv run pare cache invalidate
uv run pare cache set /path/to/cache
```

## Noise Injection

PARE currently documents two main runtime noise channels:

### Tool augmentation noise

`tool_augmentation_config` modifies tool behavior, primarily via tool failure probability.

This is applied during scenario initialization in `PAREScenario.apply_augmentation_configs()`.

### Environmental event noise

`env_events_config` injects environmental events into the scenario through `PAREEnvEventsExpander`.

When environmental noise is enabled, the scenario initialization flow loads augmentation data from:

- `ENV_AUGMENTATION_DATA_PATH`, or
- `data/metaare_augmentation_data.json`

This means environment noise is part of the scenario expansion step, not just a post-processing flag on the runner.

## Oracle vs Agent Mode

- `oracle=True`: environment executes oracle events without the user/proactive agents
- `oracle=False`: `TwoAgentScenarioRunner` runs the full user + proactive interaction loop

Oracle mode is primarily used to validate scenario structure and event logic independently of model behavior.
