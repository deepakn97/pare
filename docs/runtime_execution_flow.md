# Runtime Execution Flow

This page documents the execution path that connects scenarios, environment state, agents, notifications, and trace export.

Related deep dives:

- [Runtime Execution Config](runtime_execution.md)
- [Trace Export Semantics](trace_export.md)
- [Agent Interaction Lifecycle](agents/interaction_lifecycle.md)

## Core Runtime Modules

- `pare/scenario_runner.py`: single-scenario execution via `TwoAgentScenarioRunner`
- `pare/multi_scenario_runner.py`: batch execution, concurrency, timeouts, and caching integration
- `pare/environment.py`: `StateAwareEnvironmentWrapper` for active-app state and event processing
- `pare/notification_system.py`: `PARENotificationSystem` for user/agent-facing notifications
- `pare/data_handler/exporter.py`: PARE-specific trace export with proactive metadata

## Single-Scenario Flow

```mermaid
flowchart LR
    scenario[PAREScenario] --> runner[TwoAgentScenarioRunner]
    runner --> env[StateAwareEnvironmentWrapper]
    env --> user[UserAgent]
    env --> proactive[ProactiveAgent]
    env --> notify[PARENotificationSystem]
    user --> events[Completed Events]
    proactive --> events
    events --> env
    runner --> validate[scenario.validate(env)]
    validate --> export[PAREJsonScenarioExporter]
```

## What the Runner Does

`TwoAgentScenarioRunner` is the main orchestration point for one scenario:

1. build an environment config from the scenario and runner config
2. create `StateAwareEnvironmentWrapper` with `PARENotificationSystem`
3. start the scenario in the environment
4. run either:
   - oracle mode with no agents, or
   - the two-agent loop (`UserAgent` + `ProactiveAgent`)
5. call `scenario.validate(env)`
6. export traces and attach the exported path to the validation result

## Environment Responsibilities

`StateAwareEnvironmentWrapper` extends the base ARE environment with PARE-specific behavior:

- tracks the current active app and background apps
- restricts user tools to the active app plus system/agent UI tools
- exposes all registered tools to the proactive agent
- wires navigation callbacks through `HomeScreenSystemApp`
- injects proactive metadata into completed-event records

## Notification Responsibilities

`PARENotificationSystem` converts completed events into:

- user-facing environment notifications
- agent-facing environment notifications
- proposal/accept/reject message traffic through `PAREAgentUserInterface`

This is what allows the user and proactive agents to observe the same world through different message surfaces.

## Trace Export

`PAREJsonScenarioExporter` writes PARE traces with:

- world logs
- completed events
- PARE-specific event metadata such as proactive mode and turn number

These exported traces are later used by:

- benchmark result analysis
- annotation sampling and metrics
- debugging scenario behavior

## Batch Execution

`MultiScenarioRunner` wraps the single-scenario runner for batch execution within a benchmark run:

- derives `ScenarioRunnerConfig` from a shared multi-scenario config
- runs scenarios sequentially or in parallel
- handles timeouts and worker execution
- optionally loads/writes cached results
- aggregates outputs into `PAREMultiScenarioValidationResult`

## Entry Points

The main user-facing runtime entrypoints are:

- `pare benchmark run`
- `scripts/run_scenarios.py`

The first is the preferred benchmark path; the second remains useful as a direct runner script.
