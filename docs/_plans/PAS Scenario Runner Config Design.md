# PAS Scenario Runner Config Design

## Overview

This document outlines the design for PAS-specific scenario runner configurations (`PASScenarioRunnerConfig` and `PASMultiScenarioRunnerConfig`) for the two-agent proactive system.

## Design Decisions

1. **Standalone config classes**: `PASScenarioRunnerConfig` is a standalone Pydantic model (not extending Meta-ARE's `ScenarioRunnerConfig`). Only includes fields PAS actually uses.

2. **Separate models for observe/execute**: Support independent LLM configuration for user, observe, and execute agents via `LLMEngineConfig`.

3. **Standalone validation result classes**: `PASScenarioValidationResult` is a standalone dataclass (not extending Meta-ARE's `ScenarioValidationResult`) to avoid dataclass inheritance issues. Mirrors base fields from Meta-ARE and adds PAS-specific fields.

4. **LLM-focused config, not agent-focused**: The runner config defines LLM settings (engine configs, max_iterations) but is agnostic to agent implementation. Different agent architectures can interpret these configs differently via an agent builder (future).

5. **Consolidate to output_dir only**: Removed `traces_dir`. Use `output_dir` for all output (traces, logs). Experiment names can be specified in the path (e.g., `--output-dir traces/experiment-1`).

6. **No experiment_name field**: Removed from config. Use `output_dir` path for organization.

7. **No max_time_scenario_duration**: PAS doesn't have time-tagged scenarios like GAIA. Only `max_scenario_duration` is needed.

8. **num_runs is CLI-only**: Like Meta-ARE, `num_runs` is a CLI parameter handled at execution layer, not in config. `run_number` is set dynamically on scenario copies.

9. **Simple caching with enable_caching**: Single `enable_caching` flag controls both read and write. No need for separate flags since config hash handles different configurations automatically.

10. **Integrated evaluation pipeline**: Metrics (proposal_rate, acceptance_rate) are computed from stored fields in `PASScenarioValidationResult`. No separate metrics CLI needed since validation results contain all necessary data. Caching preserves these metrics across runs.

11. **Agent architecture in config**: `agent_type` field specifies which proactive agent implementation to use. Currently only `"observe-execute"` is supported. Future implementations may include single-agent or rule-based approaches.

12. **No build_*_agent_config() in runner config**: Agent creation is handled by factory functions in `pas/agents/factory.py`, not by the config class. Config is just data; factories use that data to build agents.

13. **JSON report as source of truth**: `generate_json_stats_report()` computes all statistics and returns structured data. `generate_validation_report()` renders this JSON as human-readable text. This ensures consistency between machine-readable and human-readable outputs.

14. **Multi-config aggregation**: Results from multiple configs (different models, noise levels) can be combined into a single DataFrame via `combine_results_to_dataframe()`. Reports show per-config statistics with STD/SEM across runs within each config.

15. **Proactive model identifier**: The `proactive_model` field is derived as `{agent_type}_{observe_model}_{execute_model}` for aggregation and reporting purposes.

16. **Registry-based scenario loading first**: Start with loading scenarios from PAS's scenario registry (Python classes). JSON/HuggingFace loading will be added later when scenarios are stable and ready for publication.

17. **Two-function config hash design**: `get_config_hash()` (short, for cache filenames) excludes output-related fields to enable cache reuse across experiments. `_generate_config_hash()` (longer, for validation) catches hash collisions. Output fields excluded: `output_dir`, `export`, `trace_dump_format`, `logs_dir`, `log_to_file`, `use_custom_logger`, `enable_caching`, `experiment_name`.

18. **Future JSON/HuggingFace export**: When ready to publish scenarios, use meta-ARE's `JsonScenarioExporter` as base (may need PAS adaptations for StatefulApp serialization). Export scenarios in oracle mode to generate completed_events, then upload to HuggingFace.

## Proposed Design

### `PASScenarioRunnerConfig`

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from are.simulation.agents.are_simulation_agent_config import LLMEngineConfig
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from are.simulation.scenarios.utils.scenario_expander import EnvEventsConfig
    from are.simulation.types import ToolAugmentationConfig

MAX_SCENARIO_DURATION = 600  # 10 minutes


class PASScenarioRunnerConfig(BaseModel):
    """Configuration for running a single PAS scenario."""

    # =========================================================================
    # User Agent LLM Configuration
    # =========================================================================
    user_engine_config: LLMEngineConfig = Field(
        default_factory=lambda: LLMEngineConfig(model_name="gpt-4o-mini", provider="openai")
    )
    user_max_iterations: int | None = 1

    # =========================================================================
    # Proactive Observe Agent LLM Configuration
    # =========================================================================
    observe_engine_config: LLMEngineConfig = Field(
        default_factory=lambda: LLMEngineConfig(model_name="gpt-4o-mini", provider="openai")
    )
    observe_max_iterations: int | None = 10

    # =========================================================================
    # Proactive Execute Agent LLM Configuration
    # =========================================================================
    execute_engine_config: LLMEngineConfig = Field(
        default_factory=lambda: LLMEngineConfig(model_name="gpt-4o-mini", provider="openai")
    )
    execute_max_iterations: int | None = 10

    # =========================================================================
    # Scenario Execution
    # =========================================================================
    oracle: bool = False
    max_turns: int | None = 10
    max_scenario_duration: int = MAX_SCENARIO_DURATION

    # =========================================================================
    # Output Configuration
    # =========================================================================
    export: bool = False
    output_dir: str | None = None
    trace_dump_format: str = "hf"

    # =========================================================================
    # Noise/Augmentation Configuration
    # =========================================================================
    tool_augmentation_config: ToolAugmentationConfig | None = None
    env_events_config: EnvEventsConfig | None = None

    # =========================================================================
    # Judge Configuration
    # =========================================================================
    judge_engine_config: LLMEngineConfig | None = None
    judge_only: bool = False
```

### `PASMultiScenarioRunnerConfig`

```python
class PASMultiScenarioRunnerConfig(PASScenarioRunnerConfig):
    """Configuration for running multiple PAS scenarios."""

    # =========================================================================
    # Experiment Identification
    # =========================================================================
    experiment_name: str | None = None  # Used to build full logs_dir path

    # =========================================================================
    # Multi-Scenario Execution Options
    # =========================================================================
    max_concurrent_scenarios: int | None = None
    timeout_seconds: int | None = None
    executor_type: str = "thread"  # "sequential", "thread", "process"

    # =========================================================================
    # Caching
    # =========================================================================
    enable_caching: bool = False

    # =========================================================================
    # Logging Options
    # =========================================================================
    log_level: str = "INFO"
    log_to_file: bool = True
    logs_dir: str = "logs"

    # =========================================================================
    # Execution Behavior
    # =========================================================================
    stop_on_failure: bool = False
```

### Fields NOT in Config (CLI-only)

| Field | Reason |
|-------|--------|
| `num_runs` | CLI parameter, handled at execution layer |
| `run_number` | Set dynamically on scenario copies |

## Caching Design

### Cache Location

- Default: `~/.cache/pas/scenario_results/`
- Configurable via `PAS_CACHE_DIR` environment variable

### Cache Key Format

```
{scenario_id}_run_{run_number}_{config_hash}
```

Example: `email_notification_run_1_a3f2b1c9`

### Config Hash Includes

All fields that affect scenario execution results:
- `user_engine_config` (model_name, provider, endpoint)
- `observe_engine_config` (model_name, provider, endpoint)
- `execute_engine_config` (model_name, provider, endpoint)
- `user_max_iterations`, `observe_max_iterations`, `execute_max_iterations`
- `max_turns`, `oracle`
- `tool_augmentation_config`, `env_events_config`

### Cache Behavior

| `enable_caching` | Behavior |
|------------------|----------|
| `True` | Check cache before running; write results to cache |
| `False` | Ignore cache entirely (don't read, don't write) |

Different configs automatically get different cache keys via `config_hash`, so:
- Same scenario + different model → different cache entry
- Same scenario + different noise config → different cache entry
- Same scenario + more runs → runs 1-N cached, new runs execute

## Validation Result Design

### `PASScenarioValidationResult`

**File**: `pas/scenarios/validation_result.py`

**Status**: ✅ Complete

Standalone dataclass with PAS-specific metrics (not extending Meta-ARE's `ScenarioValidationResult` to avoid dataclass inheritance issues):

```python
from dataclasses import dataclass

@dataclass
class PASScenarioValidationResult:
    """PAS-specific scenario validation result with proactive agent metrics."""

    # Base fields (mirrored from Meta-ARE's ScenarioValidationResult):
    success: bool | None
    exception: Exception | None = None
    export_path: str | None = None
    rationale: str | None = None
    duration: float | None = None

    # PAS-specific stored fields
    proposal_count: int = 0
    acceptance_count: int = 0
    read_only_actions: int = 0
    write_actions: int = 0
    number_of_turns: int = 0

    # Derived metrics (computed properties)
    @property
    def proposal_rate(self) -> float:
        """Proposals per turn."""
        ...

    @property
    def acceptance_rate(self) -> float:
        """Accepted proposals / total proposals."""
        ...
```

### `PASMultiScenarioValidationResult`

**Status**: ✅ Complete

Aggregates multiple scenario results with PAS-specific metrics:

```python
@dataclass
class PASMultiScenarioValidationResult:
    """Aggregated validation results for multiple PAS scenarios."""

    run_config: MultiScenarioRunnerConfig
    scenario_results: dict[tuple[str, int | None], PASScenarioValidationResult] = field(default_factory=dict)
    duration: float = 0.0
    successful_count: int = 0
    failed_count: int = 0
    exception_count: int = 0
    no_validation_count: int = 0

    # Aggregate properties (computed from scenario_results)
    @property
    def total_proposals(self) -> int: ...
    @property
    def total_acceptances(self) -> int: ...
    @property
    def total_turns(self) -> int: ...
    @property
    def total_read_only_actions(self) -> int: ...
    @property
    def total_write_actions(self) -> int: ...
    @property
    def aggregate_proposal_rate(self) -> float: ...
    @property
    def aggregate_acceptance_rate(self) -> float: ...
    @property
    def success_rate(self) -> float: ...

    def add_result(self, result, scenario_id, run_number=None) -> None:
        """Add a scenario result and update counts."""
        ...

    def to_polars(self, extra_columns: dict[str, str] | None = None) -> pl.DataFrame:
        """Convert to polars DataFrame for analysis."""
        ...
```

### `PAS_RESULT_SCHEMA`

**Status**: ✅ Complete

Module-level constant defining the DataFrame schema for `to_polars()` output:

```python
PAS_RESULT_SCHEMA: dict[str, type[pl.DataType]] = {
    # Scenario identification
    "base_scenario_id": pl.Utf8,
    "run_number": pl.Int64,
    # Success fields
    "success_numeric": pl.Float64,
    "success_bool": pl.Boolean,
    "status": pl.Utf8,
    # Exception fields
    "has_exception": pl.Boolean,
    "exception_type": pl.Utf8,
    "exception_message": pl.Utf8,
    # Other base fields
    "rationale": pl.Utf8,
    "export_path": pl.Utf8,
    "run_duration": pl.Float64,
    "job_duration": pl.Float64,
    # Model configuration
    "user_model": pl.Utf8,
    "user_provider": pl.Utf8,
    "observe_model": pl.Utf8,
    "observe_provider": pl.Utf8,
    "execute_model": pl.Utf8,
    "execute_provider": pl.Utf8,
    # Aggregation key fields
    "agent_type": pl.Utf8,
    "proactive_model": pl.Utf8,  # Derived: {agent_type}_{observe_model}_{execute_model}
    "tool_failure_probability": pl.Float64,
    "num_env_events_per_minute": pl.Int64,
    # PAS-specific metrics
    "proposal_count": pl.Int64,
    "acceptance_count": pl.Int64,
    "read_only_actions": pl.Int64,
    "write_actions": pl.Int64,
    "number_of_turns": pl.Int64,
    "proposal_rate": pl.Float64,
    "acceptance_rate": pl.Float64,
}
```

### Why Store Raw Counts, Not Rates?

- **Rates are derived**: `proposal_rate = proposal_count / number_of_turns`
- **Aggregation requires counts**: Can't average rates correctly without knowing sample sizes
- **Caching stores counts**: Cached results preserve raw data; rates computed on-demand

### Metric Extraction Strategy

Metrics are extracted from agent logs after scenario execution in `run_pas_scenario_with_config()`. No changes to agent classes required.

```python
from are.simulation.agents.agent_log import ToolCallLog

# After _run_with_two_agents() returns (validation_result, user_agent, proactive_agent):

# 1. proposal_count - observe agent calls send_message_to_user
observe_logs = proactive_agent.observe_agent.get_agent_logs()
proposal_count = sum(
    1 for log in observe_logs
    if isinstance(log, ToolCallLog) and "send_message_to_user" in log.tool_name
)

# 2. acceptance_count - user agent sends [ACCEPT] via send_message_to_agent
user_logs = user_agent.react_agent.get_agent_logs()
acceptance_count = sum(
    1 for log in user_logs
    if isinstance(log, ToolCallLog)
    and "send_message_to_agent" in log.tool_name
    and "[ACCEPT]" in str(log.tool_arguments)
)

# 3. read_only/write actions - iterate all agent logs, check tool operation_type
# Map tool_name back to tool registry to get __operation_type__

# 4. number_of_turns - already tracked as turn_count in _run_with_two_agents()
```

| Metric | Source | Extraction Method |
|--------|--------|-------------------|
| `proposal_count` | `proactive_agent.observe_agent.get_agent_logs()` | Count `ToolCallLog` with `send_message_to_user` |
| `acceptance_count` | `user_agent.react_agent.get_agent_logs()` | Count `ToolCallLog` with `send_message_to_agent` + `[ACCEPT]` |
| `read_only_actions` | All agent logs | Count by `OperationType.READ` |
| `write_actions` | All agent logs | Count by `OperationType.WRITE` |
| `number_of_turns` | `TwoAgentScenarioRunner` | Already tracked as `turn_count` |

### File Location

`pas/scenarios/validation_result.py`

## Multi-Run Support

Like Meta-ARE, multiple runs are handled at the execution layer:

1. CLI passes `--num-runs 4`
2. `multiply_scenarios()` creates deep copies with `scenario.run_number = 1, 2, 3, 4`
3. Each copy has unique cache key: `{scenario_id}_run_{run_number}_{config_hash}`
4. Caching skips already-completed runs automatically

## Evaluation Pipeline

### Architecture

```
Run Benchmark CLI
├── Executes scenarios (with optional caching + multi-run)
├── Stores results in PASScenarioValidationResult
│   ├── success/failure status
│   ├── proposal_count, acceptance_count
│   ├── read_only_actions, write_actions
│   └── number_of_turns
├── Aggregates into PASMultiScenarioValidationResult
│   ├── Per-scenario results
│   ├── Aggregate counts and rates
│   └── to_polars() for DataFrame export
├── Caches results (PASScenarioValidationResult preserved)
├── Exports rich traces to output_dir
└── Outputs metrics summary via description()
```

### Why Integrated?

- **No re-evaluation needed**: Metrics computed from stored counts
- **Caching preserves metrics**: Cached results include all PAS-specific fields
- **Single CLI**: Benchmark CLI outputs metrics directly
- **Traces still available**: Rich traces exported for detailed analysis if needed

## Scenario Loading Strategy

### Current Approach: Registry-Based

PAS scenarios are defined as Python classes and registered via `@register_scenario` decorator. The benchmark pipeline loads scenarios directly from the registry.

```python
def load_scenarios_from_registry(
    scenario_ids: list[str] | None = None,
    limit: int | None = None,
    tags: list[str] | None = None,
) -> list[PASScenario]:
    """Load scenarios from PAS registry.

    Args:
        scenario_ids: Specific scenario IDs to load. If None, loads all.
        limit: Maximum number of scenarios to load.
        tags: Filter by scenario tags (e.g., ["is_benchmark_ready"]).

    Returns:
        List of instantiated PASScenario objects.
    """
```

**File**: `pas/benchmark/scenario_loader.py`

### Benchmark Pipeline Flow

```
1. CLI: pas benchmark --num-runs 3 --split full --output-dir results/
   │
2. load_scenarios_from_registry(tags=["is_benchmark_ready"])
   │
3. multiply_scenarios(scenarios, num_runs=3)
   │  └── Creates copies with run_number = 1, 2, 3
   │
4. For each (scenario, run_number):
   │  ├── Check cache: maybe_load_cached_result()
   │  │   └── If hit: use cached PASScenarioValidationResult
   │  │
   │  ├── If miss: run_pas_scenario_with_config(scenario, config)
   │  │   └── Returns PASScenarioValidationResult with metrics
   │  │
   │  └── Write cache: write_cached_result()
   │
5. Aggregate into PASMultiScenarioValidationResult
   │
6. Generate reports via generate_validation_report()
```

### Future: JSON/HuggingFace Loading

When scenarios are stable and ready for publication:

1. **Export to JSON**: Run scenarios in oracle mode, use `JsonScenarioExporter` (may need PAS adaptations for `StatefulApp` serialization)
2. **Upload to HuggingFace**: Store as dataset with scenario JSON per row
3. **Add loaders**: Implement `local_loader.py` and `huggingface_loader.py` (adapt from meta-are)
4. **Unified entry point**: `setup_scenarios_iterator()` routes to registry, local, or HuggingFace loader

**Key Challenge**: `StatefulApp` has `current_state` and `navigation_stack` that need custom serialization. Also, `validate()` methods contain Python code that can't be serialized directly - need to rely on oracle-generated completed_events for offline validation.

## Future Work: Proactive Agent Architecture (Pluggable Design)

> **Note**: This section describes future work. Current implementation uses flat config structure with hardcoded observe/execute agent. Implement this when adding new proactive agent types.

### Current State

- Flat config with `observe_engine_config`, `execute_engine_config`, etc.
- `TwoAgentScenarioRunner._run_with_two_agents()` builds configs using builders but is **hardcoded to specific agent types**:
  - User agent: always builds `"default"` via `user_agent_config_builder.build("default")`
  - Proactive agent: always builds `"observe-execute"` via `proactive_agent_config_builder.build("observe-execute")`
- The method signature accepts raw LLM params (`user_engine_config`, `observe_engine_config`, `execute_engine_config`) which only make sense for the observe-execute architecture
- **Limitation**: To support different agent types (e.g., single-agent proactive, rule-based), we need to make `_run_with_two_agents()` generic by accepting agent type as a parameter and dynamically determining which params are needed

### Design Challenge: Different Agent Types Need Different Params

The core problem is that different agent architectures require different configuration parameters:

| Agent Type | Required Params |
|------------|-----------------|
| `observe-execute` | `observe_engine_config`, `execute_engine_config`, `observe_max_iterations`, `execute_max_iterations` |
| `single` (future) | `engine_config`, `max_iterations` |
| `rule-based` (future) | `rules_config`, no LLM config needed |

**Rejected approaches:**

1. **Discriminated union in config**: `proactive_config: ObserveExecuteConfig | SingleConfig`
   - Problem: Requires modifying `ScenarioRunnerConfig` every time a new agent type is added
   - Violates open-closed principle

2. **Flat config with all optional fields**: All possible params as optional fields
   - Problem: Unclear which fields apply to which agent type, manual validation

**Chosen approach: Registry-based dynamic validation**

### Future State (When Adding New Agent Types)

When we add a second proactive agent type (e.g., single-agent, rule-based), we'll refactor to a registry-based architecture that allows new agent types to be added without modifying core code.

#### Key Principle: Open for Extension, Closed for Modification

- New agent types register themselves with the registry
- `ScenarioRunnerConfig` uses `agent_type: str` + `proactive_params: dict` (not a union type)
- Runtime validation uses registry to validate params against the registered config class
- No changes to `ScenarioRunnerConfig` or `TwoAgentScenarioRunner` when adding new agents

#### Agent Registry Pattern

```python
class ProactiveAgentRegistry:
    """Registry for proactive agent types.

    Users can register custom agents without modifying core code:
        ProactiveAgentRegistry.register(
            "my_agent",
            MyAgentConfig,
            my_agent_builder
        )
    """

    _configs: dict[str, type[BaseModel]] = {}
    _builders: dict[str, Callable] = {}

    @classmethod
    def register(cls, name: str, config_class: type, builder: Callable) -> None:
        """Register a new proactive agent type."""
        cls._configs[name] = config_class
        cls._builders[name] = builder

    @classmethod
    def get_config_class(cls, name: str) -> type:
        """Get config class for an agent type (for validation)."""
        return cls._configs[name]

    @classmethod
    def validate_params(cls, agent_type: str, params: dict) -> BaseModel:
        """Validate params dict against registered config class."""
        config_class = cls._configs[agent_type]
        return config_class.model_validate(params)

    @classmethod
    def build(cls, agent_type: str, config: BaseModel, env: Any) -> ProactiveAgentProtocol:
        """Build a proactive agent from validated config."""
        return cls._builders[agent_type](config, env)

    @classmethod
    def list_agents(cls) -> list[str]:
        """List all registered agent types (for CLI --help)."""
        return list(cls._configs.keys())
```

#### ScenarioRunnerConfig with Dynamic Validation

```python
class ScenarioRunnerConfig(BaseModel):
    """Config that works with any registered agent type."""

    # User agent config (can also be registry-based in future)
    user_engine_config: LLMEngineConfig
    user_max_iterations: int = 1

    # Proactive agent - type + params validated at runtime
    agent_type: str = "observe-execute"
    proactive_params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_proactive_params(self) -> Self:
        """Validate proactive_params against registered config class."""
        ProactiveAgentRegistry.validate_params(self.agent_type, self.proactive_params)
        return self

    def get_proactive_config(self) -> BaseModel:
        """Get validated proactive agent config."""
        return ProactiveAgentRegistry.validate_params(self.agent_type, self.proactive_params)
```

#### Example: Registering a New Agent Type

```python
# In pas/agents/proactive/single_agent/config.py
class SingleAgentConfig(BaseModel):
    """Config for single-agent proactive architecture."""

    engine_config: LLMEngineConfig
    max_iterations: int = 10
    system_prompt: str = DEFAULT_SINGLE_AGENT_PROMPT


def build_single_agent(config: SingleAgentConfig, env: StateAwareEnvironmentWrapper) -> SingleProactiveAgent:
    """Build a single proactive agent."""
    # ... implementation


# Register at module load time
ProactiveAgentRegistry.register("single", SingleAgentConfig, build_single_agent)
```

#### Usage in TwoAgentScenarioRunner

```python
def _run_with_two_agents(self, config: ScenarioRunnerConfig, scenario: PASScenario, env: ...):
    # Get validated proactive config from registry
    proactive_config = config.get_proactive_config()

    # Build agent using registry (knows which builder to use based on agent_type)
    proactive_agent = ProactiveAgentRegistry.build(
        config.agent_type,
        proactive_config,
        env
    )

    # ... rest of execution (agent implements ProactiveAgentProtocol)
```

#### ProactiveAgentProtocol (ABC)

```python
from typing import Protocol

class ProactiveAgentProtocol(Protocol):
    """Protocol that all proactive agent implementations must follow."""

    @property
    def agent_framework(self) -> str:
        """Name of the agent framework for tracing."""
        ...

    @property
    def model_info(self) -> dict[str, str]:
        """Model information for tracing. Keys vary by implementation."""
        ...

    @property
    def status(self) -> str:
        """Current agent status (e.g., 'observe', 'execute', 'idle')."""
        ...

    def prepare_proactive_agent_run(
        self,
        scenario: Scenario,
        notification_system: BaseNotificationSystem | None = None,
    ) -> None:
        """Prepare the agent for a scenario run."""
        ...

    def agent_loop(
        self,
        initial_task: str | None = None,
        reset: bool = True,
    ) -> str | MMObservation | None:
        """Execute one proactive agent turn."""
        ...
```

#### ProactiveAgentConfigProtocol (ABC)

```python
class ProactiveAgentConfigProtocol(Protocol):
    """Protocol for proactive agent configurations."""

    def get_agent_type(self) -> str:
        """Return the agent type identifier."""
        ...
```

#### Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────────────┐
│                     ProactiveAgentProtocol (ABC)                    │
│  - prepare_proactive_agent_run(scenario, notification_system)       │
│  - agent_loop(reset) -> result                                      │
│  - status: str                                                      │
│  - model_info: dict[str, str]                                       │
│  - agent_framework: str                                             │
└─────────────────────────────────────────────────────────────────────┘
                                   ▲
                                   │ implements
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
┌───────┴───────┐    ┌─────────────┴──────────────┐    ┌──────┴───────┐
│ ProactiveAgent │    │ SingleAgentProactive       │    │ RuleBasedPA  │
│ (observe/exec) │    │ (future)                   │    │ (future)     │
└────────────────┘    └────────────────────────────┘    └──────────────┘
        │                          │                          │
        │ registers                │ registers                │ registers
        ▼                          ▼                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     ProactiveAgentRegistry                          │
│  - _configs: dict[str, type[BaseModel]]                             │
│  - _builders: dict[str, Callable]                                   │
│  - register(name, config_class, builder)                            │
│  - validate_params(agent_type, params) -> config                    │
│  - build(agent_type, config, env) -> agent                          │
└─────────────────────────────────────────────────────────────────────┘
```

### What Changes When Implementing Registry

| Component | Current | After Registry Implementation |
| --------- | ------- | ----------------------------- |
| `ScenarioRunnerConfig` | Flat fields: `observe_engine_config`, `execute_engine_config` | `agent_type: str` + `proactive_params: dict` with runtime validation |
| `TwoAgentScenarioRunner` | Hardcoded `"default"` and `"observe-execute"` strings | Uses `config.agent_type` and `ProactiveAgentRegistry.build()` |
| Agent creation | Inline in `_run_with_two_agents()` | Via `ProactiveAgentRegistry.build()` |
| Adding new agent | Modify `_run_with_two_agents()`, `ScenarioRunnerConfig` | Just register: `ProactiveAgentRegistry.register(...)` |
| Trace export | Hardcoded observe/execute model fields | Generic `proactive_agent.model_info` dict |
| `get_config_hash()` | Lists observe/execute fields explicitly | Hashes `agent_type` + `proactive_params` |

### Files to Create/Modify (Future)

| File | Action | Description |
| ---- | ------ | ----------- |
| `pas/agents/registry.py` | Create | `ProactiveAgentRegistry` class |
| `pas/agents/protocols.py` | Create | `ProactiveAgentProtocol` ABC |
| `pas/agents/proactive/observe_execute/config.py` | Create | `ObserveExecuteAgentConfig` + registration |
| `pas/agents/proactive/agent.py` | Modify | Implement `ProactiveAgentProtocol` |
| `pas/scenario_runner.py` | Modify | Use registry instead of hardcoded agent types |
| `pas/scenarios/config.py` | Modify | Change to `agent_type` + `proactive_params` |

## Implementation Plan

### Phase 1: Complete PAS Config Classes ✅

**File**: `pas/scenarios/config.py`

**Status**: Complete

**Implemented**:
1. `ScenarioRunnerConfig` class with all LLM engine configs
2. `MultiScenarioRunnerConfig` extending base config
3. `get_config_hash()` method

### Phase 2: Implement Caching Utilities ✅

**File**: `pas/scenarios/utils/caching.py`

**Status**: Complete

**Implemented**:
1. `CachedScenarioResult` dataclass
2. `maybe_load_cached_result()` and `write_cached_result()`
3. `_generate_config_hash()` and `_generate_scenario_hash()`
4. `PAS_CACHE_DIR` environment variable support
5. `clear_cache()` and `get_cache_stats()` utilities

### Phase 3: Implement Validation Result Classes ✅

**File**: `pas/scenarios/validation_result.py`

**Status**: Complete

**Implemented**:
1. `PASScenarioValidationResult` standalone dataclass with PAS-specific fields
2. `PASMultiScenarioValidationResult` with aggregate metrics
3. `PAS_RESULT_SCHEMA` module-level constant for DataFrame schema
4. `add_result()` method
5. `to_polars()` method with aggregation key columns (proactive_model, tool_failure_probability, etc.)

**File**: `pas/benchmark/report_stats.py`

**Status**: Complete

**Implemented**:
1. `combine_results_to_dataframe()` - combines multiple results into single DataFrame
2. `generate_json_stats_report()` - structured JSON report with per-config stats
3. `generate_validation_report()` - human-readable text report
4. `calculate_statistics()` - computes all metrics with STD/SEM
5. Helper functions for each metric type

**Caching Update** (Complete):
1. ✅ Updated `CachedScenarioResult` to include PAS fields (duration, proposal_count, acceptance_count, read_only_actions, write_actions, number_of_turns)
2. ✅ Updated `from_scenario_result()` and `to_scenario_result()` methods
3. ✅ Added `agent_type` to `_generate_config_hash()` for validation
4. ✅ Updated `get_config_hash()` to exclude output-related fields for cross-experiment cache reuse

### Phase 4: Implement Scenario Loading and Multi-Run Support ✅

**Files**: `pas/benchmark/scenario_loader.py`, `pas/benchmark/scenario_executor.py`

**Status**: Complete

**Implemented**:
1. `load_scenario_ids_from_file()` - loads scenario IDs from file
2. `load_scenarios_from_registry()` - returns `CountableIterator[PASScenario]`
3. `multiply_scenarios_iterator()` - creates copies with `run_number` using generator pattern

### Phase 5: Refactor TwoAgentScenarioRunner to Standalone ✅

**File**: `pas/scenario_runner.py`

**Status**: Complete

Refactored `TwoAgentScenarioRunner` to be a standalone class instead of extending Meta-ARE's `ScenarioRunner`. This provides cleaner architecture with explicit dependencies.

**Why Standalone?**
- We only use `_run_without_agent()` from the base class (4 lines of code)
- We don't use the inherited `run()`, `_run_with_agent()`, `_export_trace()`, or agent builder infra
- Avoids confusion about which `ScenarioRunnerConfig` type is expected
- Allows returning `PASScenarioValidationResult` directly

**Completed Tasks**:
1. ✅ Removed `extends ScenarioRunner` inheritance
2. ✅ Added our own `_run_without_agent()` method (simple: `env.join()` + `scenario.validate(env)`)
3. ✅ Added `run(config: ScenarioRunnerConfig, scenario: PASScenario) -> ScenarioValidationResult`
4. ✅ Updated `_run_pas_scenario()` to take `ScenarioRunnerConfig` directly
5. ✅ Updated `_run_with_two_agents()` to accept raw params and build configs internally
6. ✅ Constructor accepts optional agent config builders and agent builders for extensibility

**Pending (Future Work)**:
- Extract PAS-specific metrics from agent logs after execution (proposal_count, acceptance_count, etc.)
- Return `PASScenarioValidationResult` instead of base `ScenarioValidationResult`

### Phase 6: Implement MultiScenarioRunner

**File**: `pas/multi_scenario_runner.py`

**Status**: ✅ Complete

Implemented a standalone multi-scenario execution engine (not extending Meta-ARE's `MultiScenarioRunner`). Uses composition instead of inheritance.

**Why Standalone?**
- Meta-ARE's `run_with_events()` is tightly coupled to `process_scenario`, `MultiScenarioValidationResult`, and tuple input format
- Would need to override ~150 lines anyway
- Cleaner to use `stream_pool` directly via composition

**Implemented Components**:

1. **`_create_scenario_runner_config()`** ✅ - Config conversion helper
   - Converts `MultiScenarioRunnerConfig` to `ScenarioRunnerConfig`
   - Excludes multi-scenario specific fields
   - Handles scenario-specific overrides (e.g., `nb_turns`)

2. **`process_scenario()`** ✅ - Worker function for thread/process pool
   - Takes `PASScenario` and `MultiScenarioRunnerConfig` plus all four builders
   - Re-establishes logging in worker thread/process
   - Creates `TwoAgentScenarioRunner` instance with builders
   - Calls `maybe_run_scenario()`
   - Returns `PASScenarioValidationResult`

3. **`maybe_run_scenario()`** ✅ - Caching wrapper
   - Takes `ScenarioRunnerConfig` (single config) and `enable_caching` parameter
   - Checks cache via `maybe_load_cached_result()`
   - If cache miss, runs scenario via `TwoAgentScenarioRunner.run()`
   - Writes result to cache via `write_cached_result()`
   - Returns `PASScenarioValidationResult`

4. **`MultiScenarioRunner` class** ✅ - standalone, uses composition
   - `__init__()` - stores four builders, sets up signal handlers
   - `_setup_signal_handlers()` - handles Ctrl+C gracefully
   - `run()` - simple entry point for list of scenarios
   - `run_with_scenarios()` - main entry point using `stream_pool`
     - Output directory setup
     - Worker count determination
     - tqdm progress bar with success rate
     - Handles timeouts and errors gracefully
     - Aggregates results into `PASMultiScenarioValidationResult`

**Key Design Decisions**:
- Standalone class using composition (imports `stream_pool` from meta-ARE)
- Input is `CountableIterator[PASScenario]` (simpler than meta-ARE's tuple format)
- No JSON string scenario support (registry-based only for now)
- Uses PAS-specific config classes (`ScenarioRunnerConfig`, `MultiScenarioRunnerConfig`)
- Returns `PASMultiScenarioValidationResult`
- Accepts all four builders (user config, user agent, proactive config, proactive agent) for future-proofing

### Phase 7: Build CLI Commands with Typer

**Files**: `pas/cli/run.py`, `pas/cli/benchmark.py`

**Status**: Not Started

CLI commands built with Typer (which uses Click under the hood).

#### 7.1: Run Command (Single/Multiple Scenario Execution)

For running individual scenarios or small sets during development/debugging.

**Tasks**:
1. Create Typer CLI for running scenarios
2. Support multiple input modes:
   - `--scenario-id <id>` for single scenario
   - `--scenario-ids <id1> <id2> ...` for multiple scenarios
   - `--scenario-file <path>` for file with scenario IDs (one per line)
3. Support `--oracle` mode for generating ground truth
4. Implement `--output-dir`, `--export` flags
5. Uses `PASMultiScenarioRunner` internally (even for single scenarios)

**CLI Usage**:
```bash
# Run a single scenario
pas run --scenario-id add_missing_group_contacts --oracle --output-dir traces/

# Run multiple scenarios
pas run --scenario-ids scenario1 scenario2 scenario3 --output-dir traces/

# Run scenarios from file
pas run --scenario-file scenarios.txt --output-dir traces/

# Run with specific config
pas run --scenario-id my_scenario --config config.yaml
```

#### 7.2: Benchmark Command (Full Benchmark Suite)

For running full benchmark suites with config sweeps, multiple runs, caching, and reporting.

**File**: `pas/cli/benchmark.py`

**Status**: In Progress

**Design Decisions**:
1. **CLI flags first, YAML config later** - Current implementation uses CLI flags only. YAML config file support is future work.
2. **Config sweeps via CLI lists** - `--observe-model` and `--execute-model` are lists (zipped together), noise params are lists (crossed with model pairs)
3. **Mutually exclusive scenario selection** - Either `--scenarios` OR `--split`, not both
4. **Mutually exclusive noise params** - Either `--tool-failure-probability` OR `--env-events-per-min`, not both
5. **Separate results-dir and output-dir** - `--results-dir` for JSON results, `--output-dir` for trace exports

**Directory Structure**:

Results and traces use a two-level structure separating fixed params from swept params:

```
{results_dir}/
└── {base_dir_name}/                           # Fixed params (not swept)
    ├── {config_descriptor}.json               # Swept params per config
    ├── {config_descriptor}.json
    └── combined.json                          # All configs combined

{output_dir}/
└── {base_dir_name}/                           # Fixed params (not swept)
    ├── {config_descriptor}/                   # Swept params per config
    │   └── {scenario_id}/run_{n}/...
    └── {config_descriptor}/
        └── ...
```

Where:
- `base_dir_name`: `{experiment_name}_{split}_user_{user_model}_mt_{max_turns}_umi_{user_max_iterations}_omi_{observe_max_iterations}_emi_{execute_max_iterations}`
- `config_descriptor`: `obs_{observe_model}_exec_{execute_model}_enmi_{env_events_per_min}_es_{env_events_seed}_tfp_{tool_failure_prob}`

**Helper Functions**:

| Function | Description |
|----------|-------------|
| `parse_scenarios_arg(scenarios_str)` | Parse comma-separated scenario IDs from CLI |
| `build_base_dir_name(config, split)` | Build parent dir name with fixed params |
| `build_config_descriptor(config, env_events_seed)` | Build swept params string |
| `build_results_path(results_dir, base_dir_name, config_descriptor)` | Full path: `{results_dir}/{base_dir_name}/{config_descriptor}.json` |
| `build_output_dir(output_dir, base_dir_name, config_descriptor)` | Full path: `{output_dir}/{base_dir_name}/{config_descriptor}/` |
| `generate_config_sweep(base_config, observe_models, execute_models, ...)` | Generate all config combinations for sweep |

**CLI Flags**:

| Flag | Type | Description |
|------|------|-------------|
| `--scenarios` / `-s` | `str` | Comma-separated scenario IDs (mutually exclusive with --split) |
| `--split` | `Split` | Benchmark split: full or ablation (mutually exclusive with --scenarios) |
| `--observe-model` / `-om` | `list[str]` | Observe model(s) for sweep (zipped with --execute-model) |
| `--execute-model` / `-em` | `list[str]` | Execute model(s) for sweep (zipped with --observe-model) |
| `--user-model` / `-um` | `str` | User agent model |
| `--max-turns` / `-mt` | `int` | Max turns per scenario |
| `--observe-max-iterations` / `-omi` | `int` | Max iterations for observe agent |
| `--execute-max-iterations` / `-emi` | `int` | Max iterations for execute agent |
| `--user-max-iterations` / `-umi` | `int` | Max iterations for user agent |
| `--tool-failure-probability` / `-tfp` | `list[float]` | Tool failure prob(s) for sweep (mutually exclusive with --env-events-per-min) |
| `--env-events-per-min` / `-epm` | `list[int]` | Env events per min for sweep (mutually exclusive with --tool-failure-probability) |
| `--env-events-seed` | `int` | Seed for env events generation |
| `--runs` / `-r` | `int` | Number of runs per scenario |
| `--max-concurrent` / `-c` | `int` | Max concurrent scenarios |
| `--timeout` / `-t` | `int` | Timeout per scenario in seconds |
| `--executor-type` | `str` | Executor: sequential, thread, process |
| `--results-dir` | `Path` | Directory for JSON results |
| `--output-dir` | `Path` | Directory for trace exports |
| `--export` / `--no-export` | `bool` | Whether to export traces |
| `--export-format` | `str` | Trace format: hf or lite |
| `--experiment-name` / `-n` | `str` | Experiment name |
| `--log-level` | `str` | Logging level |
| `--no-cache` | `bool` | Disable result caching |
| `--limit` / `-l` | `int` | Limit number of scenarios |

**CLI Usage**:
```bash
# Run benchmark with single model pair
pas benchmark --split full --observe-model gpt-5 --execute-model gpt-5 --runs 3

# Run benchmark with model sweep (zipped pairs)
pas benchmark --split full \
  --observe-model gpt-5 --observe-model claude-4.5-sonnet \
  --execute-model gpt-5 --execute-model claude-4.5-sonnet \
  --runs 3

# Run benchmark with noise sweep
pas benchmark --split full \
  --observe-model gpt-5 --execute-model gpt-5 \
  --tool-failure-probability 0.0 --tool-failure-probability 0.1 --tool-failure-probability 0.2 \
  --runs 3

# Full benchmark with exports
pas benchmark --split full \
  --observe-model gpt-5 --execute-model gpt-5 \
  --runs 3 --export --output-dir traces/ --results-dir results/ \
  --experiment-name paper_draft
```

**Execution Flow**:
```
1. Parse CLI args, validate mutually exclusive options
2. Load scenarios (from --scenarios or --split)
3. Multiply scenarios for --runs
4. Generate config sweep from CLI params
5. Build base_dir_name from fixed params
6. For each config in sweep:
   a. Build config_descriptor from swept params
   b. Set output_dir if --export
   c. Run scenarios via MultiScenarioRunner
   d. Save individual result to {results_dir}/{base_dir_name}/{config_descriptor}.json
7. Save combined results to {results_dir}/{base_dir_name}/combined.json
8. Print summary
```

**Future Work**:
- YAML config file support (`--config config.yaml`)

#### 7.3: Live Terminal UI for Parallel Execution

**Library**: Rich (Python library for rich text and live displays)

**Status**: Not Started

Display a live-updating terminal UI showing scenario execution progress. The UI is portable across CLI commands (`pas benchmark sweep`, `pas run`).

**Display Layout**:

```
                              obs_gpt-5_exec_gpt-5_tfp_0.0
Sweep Progress [████████████░░░░░░░░░░░░░]  1/5  20%  0:05:23  eta: 0:21:32
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                  Turn 2/10: User Agent                              │
│ ⠋ scenario_contacts_001_run_1  [████████░░░░░░░░░░░░░░░░░░░░░░]              0:01:18 │
│                                  Turn 1/10: Proactive (observe)                     │
│ ⠙ scenario_email_042_run_2     [████░░░░░░░░░░░░░░░░░░░░░░░░░░]              0:00:45 │
│                                  Success                                            │
│ ✓ scenario_calendar_015_run_1  [██████████████████████████████]              0:02:30 │
│                                  Initializing...                                    │
│ ⠹ scenario_messaging_008_run_1 [░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]              0:00:02 │
└─────────────────────────────────────────────────────────────────────────────────────┘
Config Progress [████████░░░░░░░░░░░░░]  8/30  27%  0:05:23  eta: 0:14:37  | Success: 6 (75.0%) | Fail: 2
```

Display structure:
- **Line 1**: Config descriptor for current sweep (centered above progress bar)
- **Line 2 (Sweep Progress)**: Progress bar with position (1/5), percentage, elapsed time, ETA
- **Scenario Box**: Each scenario uses 2 lines:
  - Status line: The scenario run status (agent type/mode, or completion status)
  - Info line: Spinner, scenario_id_run_N, turn progress bar, elapsed time
- **Bottom (Config Progress)**: Scenarios completed within current config, percentage, elapsed, ETA, success/fail stats

**Responsive Design**:

The UI must adapt to different terminal sizes. Use `Console.size` to detect dimensions and adjust layout accordingly.

| Terminal Width | Behavior |
|----------------|----------|
| Wide (120+ cols) | Full layout with all elements |
| Medium (80-119 cols) | Truncate scenario IDs, shorter progress bars |
| Narrow (60-79 cols) | Compact mode: hide ETA on sweep progress, shorter bars |
| Very narrow (<60 cols) | Minimal mode: hide stats, very short bars |

**Dynamic Width Allocation**:

```python
def _calculate_widths(self) -> dict[str, int]:
    """Calculate column widths based on terminal width."""
    width = self._console.size.width

    # Fixed widths
    spinner_width = 2
    time_width = 8

    # Remaining space for scenario ID and progress bar
    remaining = width - spinner_width - time_width - 6  # 6 for padding/borders

    if width >= 120:
        scenario_width = 35
        progress_width = remaining - scenario_width
    elif width >= 80:
        scenario_width = 28
        progress_width = remaining - scenario_width
    elif width >= 60:
        scenario_width = 20
        progress_width = remaining - scenario_width
    else:
        scenario_width = 15
        progress_width = max(10, remaining - scenario_width)

    return {
        "spinner": spinner_width,
        "scenario": scenario_width,
        "progress": progress_width,
        "time": time_width,
    }
```

**Truncation Strategy**:

```python
def _truncate_text(self, text: str, max_width: int, suffix: str = "...") -> str:
    """Truncate text to fit within max_width, adding suffix if truncated."""
    if len(text) <= max_width:
        return text
    return text[:max_width - len(suffix)] + suffix
```

**Progress Bar Scaling**:

Progress bars scale to available width:
```python
def _render_turn_progress(self, turn: int, max_turns: int, bar_width: int) -> str:
    """Render turn progress bar with dynamic width."""
    if max_turns <= 0:
        return "[" + "░" * bar_width + "]"
    filled = int((turn / max_turns) * bar_width)
    empty = bar_width - filled
    return f"[{'█' * filled}{'░' * empty}]"
```

**Resize Handling**:

Rich's `Live` context handles terminal resize events automatically. The `_render()` method recalculates widths on each refresh (4 times/second), so layout adapts immediately when terminal is resized.

**Key Features**:

1. **Config sweep progress bar** (top): Shows current config position (Config 1/5) with config descriptor
2. **Scenario box**: Shows `max_concurrent_scenarios` active scenarios (or 1 for sequential)
3. **Per-scenario display**:
   - Spinner animation (⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏) for running scenarios
   - Scenario ID with run number (truncated if too long)
   - Turn progress (Turn 2/10) with discrete bar
   - Status text (agent type, mode)
   - Elapsed time
4. **Config progress bar** (bottom): Completed scenarios, success rate, failed count, elapsed time
5. **Completion display**: Show result status (Success/Failed/Exception) for 1-2 seconds before removing

**Status Lifecycle**:

| Status Code | Display Text | When |
|-------------|--------------|------|
| `initializing` | "Initializing..." | Scenario setup, environment creation |
| `turn_N_user` | "Turn N/M: User Agent" | User agent turn active |
| `turn_N_observe` | "Turn N/M: Proactive (observe)" | Observe agent active |
| `turn_N_execute` | "Turn N/M: Proactive (execute)" | Execute agent active |
| `validating` | "Validating..." | Running scenario.validate() |
| `saving` | "Saving results..." | Writing cache/traces |
| `done_success` | "Success" (green ✓) | Completed successfully |
| `done_failed` | "Failed" (red ✗) | Validation failed |
| `done_exception` | "Exception" (red ✗) | Exception occurred |

**File Structure**:

```
pas/cli/live_display/
├── __init__.py           # Exports LiveDisplay, StatusReporter
├── types.py              # StatusUpdate, ScenarioDisplayState dataclasses
├── reporter.py           # StatusReporter protocol, ThreadSafeReporter, QueueReporter
├── display.py            # LiveDisplay class using Rich
└── utils.py              # format_elapsed_time, truncate_scenario_id
```

**Data Structures** (`types.py`):

```python
from dataclasses import dataclass, field
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pas.scenarios.validation_result import PASScenarioValidationResult


@dataclass(frozen=True)
class StatusUpdate:
    """Immutable status update message passed via queue/dict."""

    scenario_id: str
    run_number: int | None
    status: str  # e.g., "turn_2_user", "validating", "done_success"
    turn: int | None = None
    max_turns: int | None = None
    timestamp: float = field(default_factory=time.time)
    result: PASScenarioValidationResult | None = None  # Only when done


@dataclass
class ScenarioDisplayState:
    """Mutable display state for a scenario slot in the UI."""

    scenario_id: str
    run_number: int | None
    status: str
    turn: int
    max_turns: int
    start_time: float
    result: PASScenarioValidationResult | None = None
    done_at: float | None = None  # When completed (for brief 1-2s display)
```

**Reporter Protocol** (`reporter.py`):

```python
from typing import Protocol
import threading
import multiprocessing
from .types import StatusUpdate


class StatusReporter(Protocol):
    """Protocol for reporting scenario status updates."""

    def report(self, update: StatusUpdate) -> None:
        """Report a status update."""
        ...

    def close(self) -> None:
        """Close the reporter (cleanup)."""
        ...


class ThreadSafeReporter:
    """Reporter using threading.Lock for thread executor."""

    def __init__(
        self,
        state_dict: dict[str, ScenarioDisplayState],
        lock: threading.Lock,
    ) -> None:
        self._state = state_dict
        self._lock = lock

    def report(self, update: StatusUpdate) -> None:
        key = f"{update.scenario_id}_run_{update.run_number or 1}"
        with self._lock:
            # Create or update state
            if key not in self._state:
                self._state[key] = ScenarioDisplayState(
                    scenario_id=update.scenario_id,
                    run_number=update.run_number,
                    status=update.status,
                    turn=update.turn or 0,
                    max_turns=update.max_turns or 10,
                    start_time=update.timestamp,
                )
            else:
                state = self._state[key]
                state.status = update.status
                if update.turn is not None:
                    state.turn = update.turn
                if update.result is not None:
                    state.result = update.result
                    state.done_at = update.timestamp

    def close(self) -> None:
        pass


class QueueReporter:
    """Reporter using multiprocessing.Queue for process executor."""

    def __init__(self, queue: multiprocessing.Queue) -> None:
        self._queue = queue

    def report(self, update: StatusUpdate) -> None:
        self._queue.put(update)

    def close(self) -> None:
        pass  # Queue cleanup handled by main process
```

**LiveDisplay Class** (`display.py`):

```python
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text
import threading
import time
from .types import StatusUpdate, ScenarioDisplayState


class LiveDisplay:
    """Manages the Rich live terminal display."""

    COMPLETION_DISPLAY_DURATION = 1.5  # seconds to show result before removing

    def __init__(
        self,
        total_scenarios: int,
        max_concurrent: int,
        total_configs: int = 1,
        current_config: int = 1,
        config_descriptor: str = "",
    ) -> None:
        self._total_scenarios = total_scenarios
        self._max_concurrent = max_concurrent
        self._total_configs = total_configs
        self._current_config = current_config
        self._config_descriptor = config_descriptor

        self._console = Console()
        self._live: Live | None = None

        # Scenario state tracking
        self._state_lock = threading.Lock()
        self._scenario_states: dict[str, ScenarioDisplayState] = {}

        # Counters
        self._completed = 0
        self._success = 0
        self._failed = 0
        self._start_time = time.time()

    def start(self) -> None:
        """Start the live display."""
        self._live = Live(
            self._render(),
            console=self._console,
            refresh_per_second=4,
            transient=False,
        )
        self._live.start()

    def stop(self) -> None:
        """Stop the live display."""
        if self._live:
            self._live.stop()

    def update_from_queue(self, queue: multiprocessing.Queue, timeout: float = 0.1) -> None:
        """Poll queue for updates (for process executor)."""
        try:
            while True:
                update = queue.get(timeout=timeout)
                self._process_update(update)
        except:  # queue.Empty
            pass

    def _process_update(self, update: StatusUpdate) -> None:
        """Process a status update."""
        key = f"{update.scenario_id}_run_{update.run_number or 1}"

        with self._state_lock:
            if update.status.startswith("done_"):
                # Completed - update counters
                self._completed += 1
                if update.status == "done_success":
                    self._success += 1
                else:
                    self._failed += 1

            # Update state
            if key not in self._scenario_states:
                self._scenario_states[key] = ScenarioDisplayState(
                    scenario_id=update.scenario_id,
                    run_number=update.run_number,
                    status=update.status,
                    turn=update.turn or 0,
                    max_turns=update.max_turns or 10,
                    start_time=update.timestamp,
                )
            else:
                state = self._scenario_states[key]
                state.status = update.status
                if update.turn is not None:
                    state.turn = update.turn
                if update.result is not None:
                    state.result = update.result
                    state.done_at = update.timestamp

        # Refresh display
        if self._live:
            self._live.update(self._render())

    def _render(self) -> Group:
        """Render the full display."""
        components = []

        # Config descriptor (centered above sweep progress)
        if self._config_descriptor:
            components.append(Text(self._config_descriptor, justify="center"))

        # Sweep progress (if multiple configs)
        if self._total_configs > 1:
            sweep_elapsed = time.time() - self._sweep_start_time
            sweep_eta = self._calculate_eta(self._current_config, self._total_configs, sweep_elapsed)
            sweep_pct = int(self._current_config / self._total_configs * 100)

            sweep_progress = Progress(
                TextColumn("Sweep Progress"),
                BarColumn(),
                TextColumn(f"{self._current_config}/{self._total_configs}"),
                TextColumn(f"{sweep_pct}%"),
                TextColumn(self._format_time(sweep_elapsed)),
                TextColumn(f"eta: {self._format_time(sweep_eta)}"),
            )
            sweep_progress.add_task("", completed=self._current_config, total=self._total_configs)
            components.append(sweep_progress)

        # Scenario table in panel
        table = self._render_scenario_table()
        components.append(Panel(table, border_style="blue"))

        # Config progress bar (bottom)
        elapsed = time.time() - self._start_time
        eta = self._calculate_eta(self._completed, self._total_scenarios, elapsed)
        success_pct = (self._success / self._completed * 100) if self._completed > 0 else 0.0
        config_pct = int(self._completed / self._total_scenarios * 100) if self._total_scenarios > 0 else 0

        config_bar = Progress(
            TextColumn("Config Progress"),
            BarColumn(),
            TextColumn(f"{self._completed}/{self._total_scenarios}"),
            TextColumn(f"{config_pct}%"),
            TextColumn(self._format_time(elapsed)),
            TextColumn(f"eta: {self._format_time(eta)}"),
            TextColumn(f"| Success: {self._success} ({success_pct:.1f}%) | Fail: {self._failed}"),
        )
        config_bar.add_task("", completed=self._completed, total=self._total_scenarios)
        components.append(config_bar)

        return Group(*components)

    def _calculate_eta(self, completed: int, total: int, elapsed: float) -> float:
        """Calculate estimated time remaining."""
        if completed == 0:
            return 0.0
        avg_time_per_item = elapsed / completed
        remaining = total - completed
        return avg_time_per_item * remaining

    def _render_scenario_table(self) -> Table:
        """Render the scenario status table.

        Each scenario uses 2 lines:
        - Line 1 (status): Status text centered/right-aligned
        - Line 2 (info): Spinner | scenario_id | progress_bar | elapsed_time
        """
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Spinner", width=2)
        table.add_column("Scenario", width=28)
        table.add_column("Progress", width=32)
        table.add_column("Time", width=8, justify="right")

        now = time.time()

        with self._state_lock:
            # Get active scenarios (not yet removed after completion display)
            active = []
            to_remove = []

            for key, state in self._scenario_states.items():
                if state.done_at is not None:
                    if now - state.done_at > self.COMPLETION_DISPLAY_DURATION:
                        to_remove.append(key)
                        continue
                active.append(state)

            # Remove expired completed scenarios
            for key in to_remove:
                del self._scenario_states[key]

            # Sort by start time, show up to max_concurrent
            active.sort(key=lambda s: s.start_time)
            displayed = active[:self._max_concurrent]

        for state in displayed:
            spinner = self._get_spinner(state.status)
            scenario_text = self._format_scenario_id(state.scenario_id, state.run_number)
            status_text = self._format_status(state)
            progress_bar = self._render_turn_progress(state.turn, state.max_turns)
            elapsed = self._format_time(now - state.start_time)

            # Line 1: Status (spans middle columns)
            table.add_row("", "", status_text, "")
            # Line 2: Spinner | Scenario ID | Progress Bar | Elapsed
            table.add_row(spinner, scenario_text, progress_bar, elapsed)

        return table

    def _get_spinner(self, status: str) -> Text:
        """Get spinner or result icon based on status."""
        if status == "done_success":
            return Text("✓", style="green")
        elif status.startswith("done_"):
            return Text("✗", style="red")
        else:
            return Text("⠋", style="cyan")  # Static, actual spinner via Rich Spinner

    def _format_scenario_id(self, scenario_id: str, run_number: int | None) -> str:
        """Format scenario ID with run number, truncated if needed."""
        full_id = f"{scenario_id}_run_{run_number or 1}"
        if len(full_id) > 28:
            return full_id[:25] + "..."
        return full_id

    def _format_status(self, state: ScenarioDisplayState) -> Text:
        """Format status text with styling."""
        status = state.status

        if status == "initializing":
            return Text("Initializing...", style="dim")
        elif status == "validating":
            return Text("Validating...", style="yellow")
        elif status == "saving":
            return Text("Saving results...", style="yellow")
        elif status == "done_success":
            return Text("Success", style="bold green")
        elif status == "done_failed":
            return Text("Failed", style="bold red")
        elif status == "done_exception":
            return Text("Exception", style="bold red")
        elif status.startswith("turn_"):
            parts = status.split("_")
            turn = parts[1] if len(parts) > 1 else "?"
            agent = "_".join(parts[2:]) if len(parts) > 2 else "unknown"
            agent_display = {
                "user": "User Agent",
                "observe": "Proactive (observe)",
                "execute": "Proactive (execute)",
            }.get(agent, agent)
            return Text(f"Turn {turn}/{state.max_turns}: {agent_display}")
        else:
            return Text(status)

    def _render_turn_progress(self, turn: int, max_turns: int) -> str:
        """Render a simple turn progress bar."""
        filled = int((turn / max_turns) * 30) if max_turns > 0 else 0
        empty = 30 - filled
        return f"[{'█' * filled}{'░' * empty}]"

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format elapsed time as H:MM:SS or M:SS."""
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"
```

**Thread vs Process Executor Flow**:

**Thread Executor**:
```
Main Thread                    Worker Threads
     │                              │
     ├─ Create shared dict + lock   │
     ├─ Create LiveDisplay          │
     ├─ Start Live context          │
     │                              │
     │  ┌─────────────────────────┐ │
     │  │ Rich Live refresh loop  │ │
     │  │ (reads shared dict)     │ │
     │  └─────────────────────────┘ │
     │                              ├─ Worker 1: ThreadSafeReporter.report()
     │                              │             (writes to shared dict with lock)
     │                              ├─ Worker 2: ThreadSafeReporter.report()
     │                              └─ Worker N: ThreadSafeReporter.report()
     │
     └─ Stop Live, print summary
```

**Process Executor**:
```
Main Process                   Worker Processes
     │                              │
     ├─ Create Queue                │
     ├─ Create LiveDisplay          │
     ├─ Start queue poll thread ────┼─────────────────┐
     ├─ Start Live context          │                 │
     │                              │    Queue        │
     │  ┌─────────────────────────┐ │      ▲         │
     │  │ Rich Live refresh loop  │ │      │         │
     │  │ (reads from display     │ │      │         │
     │  │  state updated by poll) │ │      │         │
     │  └─────────────────────────┘ │      │         │
     │                              ├─ W1: queue.put(StatusUpdate)
     │  ┌─────────────────────────┐ │      │
     │  │ Poll thread reads queue │◄┼──────┘
     │  │ Updates LiveDisplay     │ ├─ W2: queue.put(StatusUpdate)
     │  └─────────────────────────┘ └─ WN: queue.put(StatusUpdate)
     │
     └─ Stop poll thread, stop Live
```

**Integration Changes**:

1. **TwoAgentScenarioRunner** - Add status_reporter parameter:

```python
class TwoAgentScenarioRunner:
    def run(
        self,
        config: ScenarioRunnerConfig,
        scenario: PASScenario,
        status_reporter: StatusReporter | None = None,  # NEW
    ) -> PASScenarioValidationResult:
        # Report: initializing
        if status_reporter:
            status_reporter.report(StatusUpdate(
                scenario_id=scenario.scenario_id,
                run_number=getattr(scenario, "run_number", None),
                status="initializing",
                max_turns=config.max_turns,
            ))

        # ... setup environment ...

        result = self._run_with_two_agents(config, scenario, env, status_reporter)

        # Report: validating
        if status_reporter:
            status_reporter.report(StatusUpdate(..., status="validating"))

        validation_result = scenario.validate(env)

        # Report: saving (if export)
        if config.export and status_reporter:
            status_reporter.report(StatusUpdate(..., status="saving"))

        # Report: done
        if status_reporter:
            done_status = "done_success" if validation_result.success else "done_failed"
            status_reporter.report(StatusUpdate(..., status=done_status, result=validation_result))

        return validation_result
```

2. **_run_with_two_agents** - Report turn/agent status:

```python
def _run_with_two_agents(
    self,
    config: ScenarioRunnerConfig,
    scenario: PASScenario,
    env: StateAwareEnvironmentWrapper,
    status_reporter: StatusReporter | None = None,  # NEW
) -> PASScenarioValidationResult:
    turn_count = 0

    while turn_count < config.max_turns:
        turn_count += 1

        # Report: user agent turn
        if status_reporter:
            status_reporter.report(StatusUpdate(
                ..., status=f"turn_{turn_count}_user", turn=turn_count
            ))

        # User agent action
        user_result = user_agent.agent_loop(...)

        # Report: observe agent
        if status_reporter:
            status_reporter.report(StatusUpdate(
                ..., status=f"turn_{turn_count}_observe", turn=turn_count
            ))

        # Proactive observe
        observe_result = proactive_agent.observe_agent.agent_loop(...)

        # Report: execute agent (if proposal made)
        if proposal_made and status_reporter:
            status_reporter.report(StatusUpdate(
                ..., status=f"turn_{turn_count}_execute", turn=turn_count
            ))

        # Proactive execute
        execute_result = proactive_agent.execute_agent.agent_loop(...)
```

3. **process_scenario()** - Accept and pass reporter:

```python
def process_scenario(
    scenario: PASScenario | str,
    config: MultiScenarioRunnerConfig,
    ...,
    status_queue: multiprocessing.Queue | None = None,  # NEW
) -> PASScenarioValidationResult:
    reporter = QueueReporter(status_queue) if status_queue else None

    runner = TwoAgentScenarioRunner(...)
    return maybe_run_scenario(runner, runner_config, scenario, config.enable_caching, reporter)
```

4. **MultiScenarioRunner.run_with_scenarios()** - Manage display:

```python
def run_with_scenarios(
    self,
    config: MultiScenarioRunnerConfig,
    scenarios: CountableIterator[PASScenario],
    show_ui: bool = True,  # NEW - controlled by --no-ui flag
    total_configs: int = 1,  # NEW - for sweep progress
    current_config: int = 1,  # NEW
    config_descriptor: str = "",  # NEW
) -> PASMultiScenarioValidationResult:
    if not show_ui:
        # Silent mode - no output at all
        return self._run_without_ui(config, scenarios)

    # Create display
    display = LiveDisplay(
        total_scenarios=len(scenarios),
        max_concurrent=max_workers,
        total_configs=total_configs,
        current_config=current_config,
        config_descriptor=config_descriptor,
    )

    if config.executor_type == "process":
        status_queue = multiprocessing.Queue()
        # Start poll thread
        poll_thread = threading.Thread(
            target=self._poll_queue_loop,
            args=(status_queue, display),
            daemon=True,
        )
        poll_thread.start()
    else:
        status_queue = None
        # Thread executor uses shared state directly

    display.start()
    try:
        # ... existing stream_pool logic with status_queue passed to workers ...
    finally:
        display.stop()
```

**CLI Changes**:

Add `--no-ui` flag to `sweep` command:

```python
@app.command()
def sweep(
    ...,
    no_ui: Annotated[
        bool,
        typer.Option("--no-ui", help="Disable live terminal UI (silent mode)"),
    ] = False,
) -> None:
    ...
    for i, config in enumerate(configs, 1):
        _, result = run_single_config(
            config=config,
            ...,
            show_ui=not no_ui,
            total_configs=len(configs),
            current_config=i,
            config_descriptor=build_config_descriptor(config),
        )
```

**Sequential Executor Special Case**:

When `executor_type="sequential"` or `max_concurrent_scenarios=1`:
- Show only 1 scenario row in the box
- Same display format, just single row
- No threading/queue complexity needed

**Tasks**:

| Task | Description |
|------|-------------|
| 7.3.1 | Add Rich as dependency in pyproject.toml |
| 7.3.2 | Create `pas/cli/live_display/types.py` with StatusUpdate, ScenarioDisplayState |
| 7.3.3 | Create `pas/cli/live_display/reporter.py` with StatusReporter protocol and implementations |
| 7.3.4 | Create `pas/cli/live_display/display.py` with LiveDisplay class |
| 7.3.5 | Create `pas/cli/live_display/utils.py` with helper functions |
| 7.3.6 | Update `TwoAgentScenarioRunner.run()` to accept and use status_reporter |
| 7.3.7 | Update `TwoAgentScenarioRunner._run_with_two_agents()` to report turn/agent status |
| 7.3.8 | Update `process_scenario()` to accept status_queue parameter |
| 7.3.9 | Update `MultiScenarioRunner.run_with_scenarios()` to manage LiveDisplay |
| 7.3.10 | Add `--no-ui` flag to CLI commands |
| 7.3.11 | Update `run_single_config()` to pass display context |
| 7.3.12 | Write tests for LiveDisplay rendering |
| 7.3.13 | Write tests for ThreadSafeReporter and QueueReporter |

#### 7.4: Thread-Safe Per-Scenario Logging

**Problem**: When running scenarios in parallel, multiple workers writing to the same log files causes issues:
- `executor_type="thread"`: Threads share memory space. `configure_logging()` clears handlers, affecting all threads.
- `executor_type="process"`: Each process has isolated memory, but shared files still cause interleaving.

**Solution**: Per-scenario log files with nested directory structure, and skip file logging for thread executor.

**Directory Structure**:
```
{logs_dir}/                                    # Built by config.build_logs_dir()
├── {experiment_name}_{config_params}/         # e.g., exp1_user_gpt-4o_mt_10_...
│   └── {proactive_model}_{timestamp}/         # e.g., gpt-4o_20250126_143000
│       ├── {scenario_id}/
│       │   ├── pas/
│       │   │   ├── run_1.log
│       │   │   └── run_2.log
│       │   └── agent/
│       │       ├── run_1.log
│       │       └── run_2.log
│       └── {scenario_id2}/
│           ├── pas/
│           │   └── run_1.log
│           └── agent/
│               └── run_1.log
```

**Thread-Safety Analysis**:

| Executor Type | Console Logging | File Logging |
|--------------|-----------------|--------------|
| `sequential` | Safe | Safe (single thread) |
| `thread` | Safe (TqdmHandler has locks) | **Disabled** (handler clearing race condition) |
| `process` | Safe (`tqdm.write`) | Safe (isolated processes, separate files) |

**Key Design Decisions**:

1. **Thread executor skips file logging**: Due to race condition where `configure_logging()` clears handlers affecting all threads. Show warning to user.

2. **`experiment_name` in `MultiScenarioRunnerConfig`**: New field for organizing logs across experiments. Used in `build_logs_dir()`.

3. **`build_logs_dir()` method**: Builds full logs directory path from config parameters. Can be auto-triggered via `@model_validator` when `experiment_name` is set at creation, or called explicitly.

4. **`experiment_name` excluded from cache hash**: It's an organizational concern, not an execution parameter.

**MultiScenarioRunnerConfig Changes**:

```python
class MultiScenarioRunnerConfig(ScenarioRunnerConfig):
    # New field
    experiment_name: str | None = None

    # Existing fields
    logs_dir: str = "logs"
    log_to_file: bool = True
    log_level: str = "INFO"
    executor_type: str = "thread"

    @model_validator(mode="after")
    def maybe_build_logs_dir(self) -> Self:
        """Auto-build logs_dir if experiment_name is set."""
        if self.experiment_name and not getattr(self, "_logs_dir_built", False):
            self._build_logs_dir_internal()
        return self

    def build_logs_dir(self, experiment_name: str | None = None) -> None:
        """Explicitly build full logs_dir path. Call before running scenarios.

        Args:
            experiment_name: Optional experiment name. If provided, sets self.experiment_name.
        """
        if experiment_name:
            self.experiment_name = experiment_name
        if not self.experiment_name:
            raise ValueError("experiment_name must be set before building logs_dir")
        self._build_logs_dir_internal()

    def _build_logs_dir_internal(self) -> None:
        """Internal method to build the full logs directory path."""
        from datetime import datetime
        from pathlib import Path

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        config_suffix = (
            f"{self.experiment_name}"
            f"_user_{self.user_engine_config.model_name}"
            f"_mt_{self.max_turns}"
            f"_umi_{self.user_max_iterations}"
            f"_omi_{self.observe_max_iterations}"
            f"_emi_{self.execute_max_iterations}"
        )
        # Add noise params if set
        if self.tool_augmentation_config:
            tfp = getattr(self.tool_augmentation_config, "failure_probability", 0.0)
            if tfp > 0:
                config_suffix += f"_tfp_{tfp}"
        if self.env_events_config:
            epm = getattr(self.env_events_config, "events_per_minute", 0)
            if epm > 0:
                config_suffix += f"_epm_{epm}"

        proactive_model = self.observe_engine_config.model_name
        full_path = Path(self.logs_dir) / config_suffix / f"{proactive_model}_{timestamp}"
        self.logs_dir = str(full_path)
        self._logs_dir_built = True
```

**configure_logging() Changes**:

```python
def configure_logging(
    level: int = logging.INFO,
    use_tqdm: bool = False,
    log_dir: Path | None = None,
    scenario_id: str | None = None,
    run_number: int | None = None,
) -> None:
    """Configure logging for PAS application.

    Args:
        level: The logging level.
        use_tqdm: Whether to use tqdm-compatible logging.
        log_dir: Base directory for logs. If None, only console logging.
        scenario_id: Scenario ID for per-scenario log files.
        run_number: Run number for per-scenario log files.
    """
    # ... console handler setup (unchanged) ...

    if log_dir is not None and scenario_id is not None:
        # Per-scenario log files: {log_dir}/{scenario_id}/pas/run_{n}.log
        run_suffix = f"run_{run_number}" if run_number is not None else "run_1"

        pas_log_dir = log_dir / scenario_id / "pas"
        agent_log_dir = log_dir / scenario_id / "agent"
        pas_log_dir.mkdir(parents=True, exist_ok=True)
        agent_log_dir.mkdir(parents=True, exist_ok=True)

        pas_log_path = pas_log_dir / f"{run_suffix}.log"
        agent_log_path = agent_log_dir / f"{run_suffix}.log"

        # ... file handler setup ...
```

**process_scenario() Changes**:

```python
def process_scenario(...) -> PASScenarioValidationResult:
    # ... existing setup ...

    # Configure logging - skip file logging for thread executor
    if config.log_to_file and config.executor_type != "thread":
        configure_logging(
            level=numeric_level,
            use_tqdm=config.executor_type != "process",
            log_dir=Path(config.logs_dir),
            scenario_id=scenario.scenario_id,
            run_number=run_number,
        )
    else:
        if config.log_to_file and config.executor_type == "thread":
            logger.warning("File logging disabled for thread executor mode due to thread-safety concerns")
        configure_logging(
            level=numeric_level,
            use_tqdm=config.executor_type != "process",
        )

    # ... rest of function ...
```

**Tasks**:
1. Add `experiment_name` field to `MultiScenarioRunnerConfig`
2. Add `@model_validator` and `build_logs_dir()` method to `MultiScenarioRunnerConfig`
3. Add `experiment_name` to exclude fields in `get_config_hash()`
4. Update `configure_logging()` signature to accept `scenario_id` and `run_number`
5. Update `configure_logging()` to create nested directory structure
6. Update `process_scenario()` to skip file logging for thread executor with warning
7. Update `process_scenario()` to pass scenario info to logging setup

## Helper Methods (for PASScenarioRunnerConfig)

```python
def get_config_hash(self) -> str:
    """Generate hash of config for caching."""
    import hashlib
    import json

    # Include all fields that affect execution results
    config_dict = {
        "user_engine": self.user_engine_config.model_dump(),
        "user_max_iterations": self.user_max_iterations,
        "observe_engine": self.observe_engine_config.model_dump(),
        "observe_max_iterations": self.observe_max_iterations,
        "execute_engine": self.execute_engine_config.model_dump(),
        "execute_max_iterations": self.execute_max_iterations,
        "oracle": self.oracle,
        "max_turns": self.max_turns,
        "tool_augmentation": (
            self.tool_augmentation_config.model_dump()
            if self.tool_augmentation_config else None
        ),
        "env_events": (
            self.env_events_config.model_dump()
            if self.env_events_config else None
        ),
    }
    config_str = json.dumps(config_dict, sort_keys=True, default=str)
    return hashlib.md5(config_str.encode()).hexdigest()[:8]
```

## Statistics and Reporting

**File**: `pas/benchmark/report_stats.py`

**Status**: ✅ Complete

### Architecture

```
Results Collection
├── Run benchmark(s) → PASMultiScenarioValidationResult per config
├── Collect in dict: {(user_model, proactive_model, tool_fail, env_events): result}
│
Combine Results
├── combine_results_to_dataframe(results) → single DataFrame
│   └── Calls to_polars() on each result, concatenates
│
Generate Reports
├── generate_json_stats_report(df, split, weight_per_app_class)
│   ├── For each unique config in df:
│   │   ├── Filter to config
│   │   └── calculate_statistics() → full stats with STD/SEM
│   └── Returns {"metadata": {...}, "per_config_results": [...]}
│
└── generate_validation_report(df, split, weight_per_app_class)
    ├── Calls generate_json_stats_report() (source of truth)
    └── Formats as human-readable text
```

### Multi-Config Aggregation Key

Results are aggregated by:
```python
# Key: (user_model, proactive_model, tool_failure_probability, num_env_events_per_minute)
results: dict[tuple[str, str, float, int], PASMultiScenarioValidationResult]
```

Where `proactive_model = f"{agent_type}_{observe_model}_{execute_model}"`.

**Important**: `tool_failure_probability` and `num_env_events_per_minute` are never both non-zero together (ablation is one at a time).

### Report Functions

| Function | Description |
|----------|-------------|
| `combine_results_to_dataframe(results)` | Combines multiple `PASMultiScenarioValidationResult` into single DataFrame |
| `generate_json_stats_report(df, split, weight_per_app_class)` | Returns structured dict with per-config statistics |
| `generate_validation_report(df, split, weight_per_app_class)` | Returns human-readable text report |
| `calculate_statistics(df)` | Computes all metrics for a single config's DataFrame |

### Helper Functions (Internal)

| Function | Description |
|----------|-------------|
| `_count_runs_by_type(df)` | Count total, validated, success, failed, exception, no_validation runs |
| `_calculate_success_rate_stats(df)` | Success rate with STD/SEM across run-level means |
| `_calculate_pass_at_k_stats(df)` | Pass@k and Pass^k statistics |
| `_calculate_run_duration_stats(df)` | Average duration with STD |
| `_calculate_pas_totals(df)` | Total proposals, acceptances, turns, actions |
| `_calculate_proposal_rate_stats(df)` | Proposal rate with STD/SEM across run-level means |
| `_calculate_acceptance_rate_stats(df)` | Acceptance rate with STD/SEM across run-level means |
| `_calculate_action_stats(df)` | Avg read/write actions per scenario with STD/SEM |
| `_format_config_header(config)` | Format config identifier line |
| `_format_config_content(config)` | Format Metadata and Metrics sections |

### Report Structure

```
=== PAS Validation Report ===
Split: full
Weight per app class: {"ContactsApp": 1.0, "EmailApp": 1.0, ...}
Generated: 2025-01-25T12:00:00

=== Config: gpt-4o-mini | observe-execute_gpt-4o_gpt-4o | tool_fail=0.0 | env_events=0 ===

=== Metadata ===
  - Scenarios: 50 unique (150 total runs)
  - Validated runs (counted in success rate): 148
  - Exception runs (counted as failures): 2

=== Metrics ===
  - Success rate: 75.2% +/- 2.1% (STD: 3.6%)
  - Pass@3: 45 scenarios (90.0%)
  - Pass^3: 30 scenarios (60.0%)
  - Avg run duration: 45.2s (STD: 12.3s)
  - Job duration: 1234.5s
  - Total proposals: 450
  - Total acceptances: 380
  - Total turns: 750
  - Proposal rate: 0.600 +/- 0.030 (STD: 0.052)
  - Acceptance rate: 84.4% +/- 2.1% (STD: 3.6%)
  - Avg read-only actions: 12.5 +/- 1.2 (STD: 2.1)
  - Avg write actions: 8.3 +/- 0.9 (STD: 1.5)

=== Config: gpt-4o-mini | observe-execute_gpt-4o_gpt-4o | tool_fail=0.1 | env_events=0 ===
...
```

### JSON Report Structure

```python
{
    "metadata": {
        "split": "full",
        "timestamp": "2025-01-25T12:00:00",
        "report_version": "1.0",
        "weight_per_app_class": {"ContactsApp": 1.0, ...}
    },
    "per_config_results": [
        {
            "user_model": "gpt-4o-mini",
            "proactive_model": "observe-execute_gpt-4o_gpt-4o",
            "tool_failure_probability": 0.0,
            "num_env_events_per_minute": 0,
            # All metrics from calculate_statistics()
            "total_runs": 150,
            "success_rate": 75.2,
            "success_rate_std": 3.6,
            "success_rate_sem": 2.1,
            ...
        },
        ...
    ]
}
```

### Future Stats (when scenario categories exist)

| Stat | Description |
|------|-------------|
| Per-scenario metrics breakdown | Proposal/acceptance rates grouped by scenario category |
| Action type distribution | Ratio of read vs write actions, breakdown by app |
| Macro success rate | Unweighted average across scenario categories |
| Micro success rate | Weighted average by run count per category |
| Proposal efficiency | Acceptances per proposal, proposals needed per successful task |

## Files Summary

### Completed

| File | Status | Description |
|------|--------|-------------|
| `pas/scenarios/config.py` | ✅ Done | `ScenarioRunnerConfig`, `MultiScenarioRunnerConfig` with `agent_type` field, updated `get_config_hash()` |
| `pas/scenarios/utils/caching.py` | ✅ Done | Caching utilities with PAS fields, updated hash functions |
| `pas/scenarios/validation_result.py` | ✅ Done | `PASScenarioValidationResult`, `PASMultiScenarioValidationResult`, `PAS_RESULT_SCHEMA` |
| `pas/benchmark/report_stats.py` | ✅ Done | Statistics calculation and report generation |
| `pas/benchmark/scenario_loader.py` | ✅ Done | `load_scenarios_from_registry()`, `load_scenario_ids_from_file()` with `CountableIterator` |
| `pas/benchmark/scenario_executor.py` | ✅ Done | `multiply_scenarios_iterator()` with generator pattern |

### Current Implementation

| File | Action | Status | Description |
|------|--------|--------|-------------|
| `pas/scenario_runner.py` | Refactor | ✅ Done | Made `TwoAgentScenarioRunner` standalone (removed inheritance), added `run(config, scenario)` method |
| `pas/multi_scenario_runner.py` | Create | ✅ Done | `_create_scenario_runner_config()`, `process_scenario()`, `maybe_run_scenario()`, `MultiScenarioRunner` class |
| `pas/cli/run.py` | Create | Not Started | Typer CLI for running individual/multiple scenarios |
| `pas/cli/benchmark.py` | Create | Not Started | Typer CLI for full benchmark suite with reporting |

### Future Work (JSON/HuggingFace Export)

| File | Action | Description |
|------|--------|-------------|
| `pas/data_handler/exporter.py` | Create | PAS-specific scenario exporter (adapt from meta-are) |
| `pas/data_handler/importer.py` | Create | PAS-specific scenario importer |
| `pas/data_handler/models.py` | Create | Pydantic models for PAS trace format |
| `pas/benchmark/local_loader.py` | Create | Load scenarios from local JSON files |
| `pas/benchmark/huggingface_loader.py` | Create | Load scenarios from HuggingFace datasets |

### Future Work (Agent Registry)

| File | Action | Description |
|------|--------|-------------|
| `pas/agents/registry.py` | Create | Agent registry for extensibility |
| `pas/agents/configs.py` | Create | UserAgentConfig, ObserveExecuteAgentConfig |
| `pas/agents/factory.py` | Create | Factory functions for building agents |
| `pas/agents/protocols.py` | Create | ProactiveAgentProtocol ABC |

### Future Work (CLI Parameter Groups)

Organize CLI options into reusable parameter groups (inspired by meta-are's `shared_params.py`). Groups are purely for code organization - users see a flat list of options.

**Benefits**:
- Reusability across multiple CLI commands (`pas run`, `pas benchmark run`)
- Consistency in option names, help text, and defaults
- Simplified command function signatures
- Single point of maintenance for each option

**File**: `pas/cli/shared_params.py`

**Proposed Parameter Groups**:

| Group | Options | Description |
|-------|---------|-------------|
| `user_agent_options()` | `--user-model`, `--user-provider`, `--user-max-iterations`, `--user-type` | User agent LLM configuration |
| `observe_agent_options()` | `--observe-model`, `--observe-provider`, `--observe-max-iterations` | Observe agent LLM configuration |
| `execute_agent_options()` | `--execute-model`, `--execute-provider`, `--execute-max-iterations` | Execute agent LLM configuration |
| `scenario_options()` | `--scenarios`, `--split`, `--limit` | Scenario selection |
| `execution_options()` | `--max-concurrent`, `--timeout`, `--executor-type`, `--max-turns`, `--max-scenario-duration` | Execution parameters |
| `output_options()` | `--export`, `--output-dir`, `--results-dir`, `--trace-dump-format` | Output configuration |
| `logging_options()` | `--log-level`, `--log-to-file`, `--logs-dir` | Logging configuration |
| `noise_options()` | `--tool-failure-probability`, `--env-events-per-min`, `--env-events-seed` | Noise augmentation |
| `caching_options()` | `--no-cache` | Caching control |
| `oracle_options()` | `--oracle`, `--judge-only` | Oracle/judge mode |

**Individual Option Functions**:

```python
# User agent options
def user_model_option() -> typer.Option: ...
def user_provider_option() -> typer.Option: ...
def user_max_iterations_option() -> typer.Option: ...
def user_type_option() -> typer.Option: ...

# Observe agent options
def observe_model_option() -> typer.Option: ...
def observe_provider_option() -> typer.Option: ...
def observe_max_iterations_option() -> typer.Option: ...

# Execute agent options
def execute_model_option() -> typer.Option: ...
def execute_provider_option() -> typer.Option: ...
def execute_max_iterations_option() -> typer.Option: ...

# Scenario options
def scenarios_option() -> typer.Option: ...
def split_option() -> typer.Option: ...
def limit_option() -> typer.Option: ...

# Execution options
def max_concurrent_option() -> typer.Option: ...
def timeout_option() -> typer.Option: ...
def executor_type_option() -> typer.Option: ...
def max_turns_option() -> typer.Option: ...
def max_scenario_duration_option() -> typer.Option: ...

# Output options
def export_option() -> typer.Option: ...
def output_dir_option() -> typer.Option: ...
def results_dir_option() -> typer.Option: ...
def trace_dump_format_option() -> typer.Option: ...

# Logging options
def log_level_option() -> typer.Option: ...
def log_to_file_option() -> typer.Option: ...
def logs_dir_option() -> typer.Option: ...

# Noise options
def tool_failure_probability_option() -> typer.Option: ...
def env_events_per_min_option() -> typer.Option: ...
def env_events_seed_option() -> typer.Option: ...

# Caching options
def no_cache_option() -> typer.Option: ...

# Oracle/judge options
def oracle_option() -> typer.Option: ...
def judge_only_option() -> typer.Option: ...
```

**Composite Group Decorators**:

```python
def user_agent_options():
    """Decorator that adds user agent configuration options."""
    def decorator(func):
        func = user_model_option()(func)
        func = user_provider_option()(func)
        func = user_max_iterations_option()(func)
        func = user_type_option()(func)
        return func
    return decorator

# Similar pattern for other groups...
```

**Usage in CLI Commands**:

```python
@app.command()
@user_agent_options()
@observe_agent_options()
@execute_agent_options()
@scenario_options()
@output_options()
def run(**kwargs):
    # Extract options from kwargs
    ...
```

**Implementation Considerations**:

1. **Typer vs Click**: Meta-are uses Click; Typer wraps Click but has different decorator patterns. May need to use `typer.Option` with `Annotated` types or callback-based approach.

2. **List options for sweeps**: `--observe-model` and `--execute-model` in benchmark command accept lists for sweeping. Single-value options for `pas run`, list options for `pas benchmark run`.

3. **Mutually exclusive options**: Some options are mutually exclusive (e.g., `--scenarios` vs `--split`, `--tool-failure-probability` vs `--env-events-per-min`). Validation can be in the group decorator or command function.

**Files to Create**:

| File | Description |
|------|-------------|
| `pas/cli/shared_params.py` | Individual option functions and composite group decorators |

**Commands to Refactor**:

| Command | Current | After |
|---------|---------|-------|
| `pas benchmark run` | 25+ explicit parameters | 8-10 group decorators |
| `pas run` (future) | TBD | Reuses same groups |

## Known Issues

### macOS: Process-Based Execution Fails with FileNotFoundError

**Issue**: When using `--executor-type process` on macOS, child processes fail to start with:

```text
FileNotFoundError: [Errno 2] No such file or directory
```

The error occurs during `SemLock._rebuild(*state)` in `multiprocessing/synchronize.py` when the child process tries to unpickle data from the parent.

**Root Cause**: macOS uses 'spawn' as the default multiprocessing start method. The `TerminableProcessPoolExecutor` in meta-ARE's `streaming_utils.py` creates `multiprocessing.Queue` objects which have internal semaphores. When spawning child processes, these semaphore file references can fail to be reconstructed in the child process.

**Current Workaround**: Use `--executor-type thread` (the default) instead of `--executor-type process` on macOS.

**Potential Fixes**:

1. **Use 'fork' start method** (not recommended)
   - Add `multiprocessing.set_start_method('fork')` early in CLI entry point
   - Pros: Simple fix
   - Cons: Fork is unsafe with threads on macOS, can cause deadlocks
   - Risk: High - not recommended by Python documentation for macOS

2. **Use 'forkserver' start method**
   - Add `multiprocessing.set_start_method('forkserver', force=True)` early in CLI entry point
   - Pros: Safer than fork, works with threads
   - Cons: Requires initialization early in program, has own quirks with dynamically loaded code
   - Risk: Medium - may require additional setup
   - Implementation:
     ```python
     # In pas/cli/main.py (before any other imports that use multiprocessing)
     import multiprocessing
     if __name__ == "__main__":
         multiprocessing.set_start_method('forkserver', force=True)
     ```

3. **Fix TerminableProcessPoolExecutor in meta-ARE** (recommended long-term)
   - Modify `TerminableProcessPoolExecutor` to use proper multiprocessing context
   - Change `self._mp_context = multiprocessing` to `self._mp_context = multiprocessing.get_context('forkserver')`
   - Pros: Fixes the issue at the source
   - Cons: Requires changes to meta-ARE codebase
   - Implementation: Upstream PR to meta-ARE

**Recommendation**: For now, document that process-based execution may have issues on macOS and recommend using thread-based execution. Long-term, fix the meta-ARE `TerminableProcessPoolExecutor` to use proper multiprocessing context.

### Caching: Failed Scenarios Are Not Retried

**Issue**: When a scenario fails with an exception (e.g., `NameError`, network timeout, rate limit), the failure is cached. On subsequent runs, the cached failure is returned without retrying the scenario.

**Current Behavior**:
- `write_cached_result()` writes ALL results to cache, including those with exceptions
- `maybe_load_cached_result()` loads cached results regardless of success/failure status
- Failed scenarios are treated as "completed" and skipped on re-runs

**Problem**: This is problematic for:
- Transient errors (network issues, API rate limits, temporary outages)
- Bugs that have been fixed in the code (e.g., the `NameError` type hint issue)
- Users expect failed scenarios to be retried after fixing issues

**Required Fix**: Modify `maybe_load_cached_result()` in `pas/scenarios/utils/caching.py` to:

1. Check if the cached result has an exception stored (`exception_type` is not None)
2. If exception exists, log a message informing the user that the scenario will be retried
3. Return `None` to trigger a fresh run instead of returning the cached failure

**Implementation**:
```python
def maybe_load_cached_result(
    runner_config: ScenarioRunnerConfig,
    scenario: PASScenario,
) -> PASScenarioValidationResult | None:
    """Try to load a cached result for the scenario and configuration."""
    try:
        # ... existing cache loading logic ...

        # Check if cached result has an exception - retry instead of using cache
        if cached_result.exception_type is not None:
            logger.info(
                f"Cached result for {scenario.scenario_id} has exception "
                f"({cached_result.exception_type}), retrying scenario"
            )
            return None

        logger.info(f"Loading cached result for scenario {scenario.scenario_id}")
        return cached_result.to_scenario_result()
    except Exception as e:
        # ... existing error handling ...
```

**Optional Enhancement**: Add a `--use-cached-failures` CLI flag to allow using cached failures when explicitly requested (e.g., for analyzing past failures without re-running).

## References

- Meta-ARE config: `are/simulation/scenarios/config.py`
- Meta-ARE caching: `are/simulation/scenarios/utils/caching.py`
- Meta-ARE scenario executor: `are/simulation/benchmark/scenario_executor.py`
- Meta-ARE multi-scenario runner: `are/simulation/multi_scenario_runner.py`
- Meta-ARE validation result: `are/simulation/scenarios/validation_result.py`
- Meta-ARE report stats: `are/simulation/benchmark/report_stats.py`
- Meta-ARE countable iterator: `are/simulation/utils/countable_iterator.py`
