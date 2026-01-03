# PAS Scenario Runner Config Design

## Overview

This document outlines the design for PAS-specific scenario runner configurations (`PASScenarioRunnerConfig` and `PASMultiScenarioRunnerConfig`) that extend Meta-ARE's configuration classes while adding PAS-specific parameters for the two-agent proactive system.

## Current State Analysis

### Meta-ARE Configuration Classes

**Location**: `are/simulation/scenarios/config.py`

#### `ScenarioRunnerConfig` (Pydantic BaseModel)

Core fields for single scenario execution:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `model` | `str` | `DEFAULT_MODEL` | Model for scenario execution |
| `model_provider` | `str \| None` | `DEFAULT_PROVIDER` | Model provider |
| `agent` | `str \| None` | `None` | Agent to use |
| `oracle` | `bool` | `False` | Run in oracle mode |
| `export` | `bool` | `False` | Export traces to JSON |
| `output_dir` | `str \| None` | `None` | Output directory |
| `max_turns` | `int \| None` | `1` | Max conversation turns |
| `tool_augmentation_config` | `ToolAugmentationConfig \| None` | `None` | Noise injection config |
| `env_events_config` | `EnvEventsConfig \| None` | `None` | Environment events config |
| `use_custom_logger` | `bool` | `True` | Use custom logger |
| `trace_dump_format` | `str` | `"hf"` | Trace export format |
| ... | ... | ... | (other fields for a2a, scenario params, etc.) |

Key method:
- `get_config_hash() -> str`: Generates hash of config for caching

#### `MultiScenarioRunnerConfig` (extends `ScenarioRunnerConfig`)

Additional fields for multi-scenario execution:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_concurrent_scenarios` | `int \| None` | `None` | Max parallel scenarios |
| `timeout_seconds` | `int \| None` | `None` | Per-scenario timeout |
| `executor_type` | `str` | `"thread"` | Executor type: sequential/thread/process |
| `log_level` | `str` | `"INFO"` | Logging level |
| `enable_caching` | `bool` | `True` | Skip re-running identical scenarios |

### Meta-ARE Validation Result Classes

**Location**: `are/simulation/scenarios/validation_result.py`

#### `ScenarioValidationResult` (dataclass)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `success` | `bool \| None` | - | Validation success (None = exception) |
| `exception` | `Exception \| None` | `None` | Exception if any |
| `export_path` | `str \| None` | `None` | Trace export path |
| `rationale` | `str \| None` | `None` | Validation rationale |
| `duration` | `float \| None` | `None` | Run duration in seconds |

#### `MultiScenarioValidationResult` (dataclass)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `run_config` | `MultiScenarioRunnerConfig` | - | The config used |
| `scenario_results` | `dict[tuple[str, int \| None], ScenarioValidationResult]` | `{}` | Results by (scenario_id, run_number) |
| `duration` | `float` | `0.0` | Total duration |
| `successful_count` | `int` | `0` | Count of successful runs |
| `failed_count` | `int` | `0` | Count of failed runs |
| `exception_count` | `int` | `0` | Count of exceptions |
| `no_validation_count` | `int` | `0` | Count of no-validation |

Key methods:
- `add_result(result, scenario_id, run_number)`: Add a scenario result
- `success_rate() -> float`: Calculate success percentage
- `to_polars(extra_columns) -> pl.DataFrame`: Convert to Polars DataFrame
- `description() -> str`: Generate detailed text report

### Current PAS Implementation

**Location**: `pas/scenario_runner.py`

`TwoAgentScenarioRunner.run_pas_scenario()` currently accepts individual parameters:

```python
def run_pas_scenario(
    self,
    scenario: Scenario,
    user_config: ARESimulationReactBaseAgentConfig,
    proactive_observe_config: ARESimulationReactBaseAgentConfig,
    proactive_execute_config: ARESimulationReactBaseAgentConfig,
    max_turns: int | None = None,
    oracle_mode: bool = False,
    traces_dir: str = "traces/demo",
) -> ScenarioValidationResult:
```

There's a TODO comment indicating the need for a config object:
```python
# ! TODO: Accept a config object instead of individual arguments. See ScenarioRunnerConfig for reference.
```

## PAS-Specific Requirements

### Additional Fields Needed

PAS has a two-agent architecture (UserAgent + ProactiveAgent with observe/execute sub-agents) that requires:

1. **User Agent Configuration**
   - `user_model`: Model for user agent
   - `user_model_provider`: Provider for user model
   - `user_max_iterations`: Max iterations per turn

2. **Proactive Agent Configuration**
   - `proactive_model`: Model for proactive agents (observe + execute)
   - `proactive_model_provider`: Provider for proactive model
   - `observe_max_iterations`: Max iterations for observe agent
   - `execute_max_iterations`: Max iterations for execute agent

3. **Experiment Metadata**
   - `experiment_name`: Name for organizing outputs

## Proposed Design

### `PASScenarioRunnerConfig`

```python
from pydantic import BaseModel
from are.simulation.scenarios.config import ScenarioRunnerConfig
from are.simulation.scenarios.utils.scenario_expander import EnvEventsConfig
from are.simulation.types import ToolAugmentationConfig


class PASScenarioRunnerConfig(BaseModel):
    """Configuration for running a single PAS scenario with two-agent system."""

    # User Agent Configuration
    user_model: str = "gpt-4o-mini"
    user_model_provider: str = "openai"
    user_max_iterations: int = 1

    # Proactive Agent Configuration (shared model for observe + execute)
    proactive_model: str = "gpt-4o-mini"
    proactive_model_provider: str = "openai"
    observe_max_iterations: int = 10
    execute_max_iterations: int = 10

    # Scenario Execution
    max_turns: int | None = 10
    oracle_mode: bool = False

    # Output Configuration
    traces_dir: str = "traces"
    export: bool = True
    trace_dump_format: str = "hf"

    # Noise/Augmentation Configuration
    tool_failure_prob: float = 0.0
    env_events_per_min: float = 0.0
    env_events_seed: int = 42

    # Experiment Metadata
    experiment_name: str = "pas_run"

    def get_config_hash(self) -> str:
        """Generate hash for config-based caching."""
        # Similar to Meta-ARE implementation
        ...

    def get_tool_augmentation_config(self) -> ToolAugmentationConfig | None:
        """Build ToolAugmentationConfig if tool_failure_prob > 0."""
        if self.tool_failure_prob > 0:
            return ToolAugmentationConfig(
                tool_failure_probability=self.tool_failure_prob,
                apply_tool_name_augmentation=False,
                apply_tool_description_augmentation=False,
            )
        return None

    def get_env_events_config(self) -> EnvEventsConfig | None:
        """Build EnvEventsConfig if env_events_per_min > 0."""
        if self.env_events_per_min > 0:
            return EnvEventsConfig(
                num_env_events_per_minute=int(self.env_events_per_min),
                env_events_seed=self.env_events_seed,
                weight_per_app_class=default_weight_per_app_class(),
            )
        return None

    def get_output_dir_suffix(self) -> str:
        """Generate directory suffix for organizing outputs."""
        return (
            f"{self.experiment_name}_user_{self.user_model}_proactive_{self.proactive_model}"
            f"_mt_{self.max_turns}_umi_{self.user_max_iterations}"
            f"_omi_{self.observe_max_iterations}_emi_{self.execute_max_iterations}"
            f"_enmi_{self.env_events_per_min}_es_{self.env_events_seed}"
            f"_tfp_{self.tool_failure_prob}"
        )
```

### `PASMultiScenarioRunnerConfig`

```python
class PASMultiScenarioRunnerConfig(PASScenarioRunnerConfig):
    """Configuration for running multiple PAS scenarios."""

    # Multi-scenario execution options
    max_concurrent_scenarios: int | None = None
    timeout_seconds: int | None = None
    executor_type: str = "sequential"  # sequential, thread, process

    # Logging
    log_level: str = "INFO"
    log_to_file: bool = True
    logs_dir: str = "logs"

    # Behavior on failure
    stop_on_failure: bool = False

    # Caching
    enable_caching: bool = False  # Disabled by default for PAS
```

### Using `MultiScenarioValidationResult`

Instead of creating custom `ResultsSummary` and `ScenarioResult` dataclasses, use Meta-ARE's `MultiScenarioValidationResult`:

```python
from are.simulation.scenarios.validation_result import (
    MultiScenarioValidationResult,
    ScenarioValidationResult,
)
from are.simulation.scenarios.config import MultiScenarioRunnerConfig

def run_all_scenarios(config: PASMultiScenarioRunnerConfig) -> MultiScenarioValidationResult:
    # Create a MultiScenarioRunnerConfig for the result (compatibility)
    # This is needed because MultiScenarioValidationResult expects it
    meta_config = MultiScenarioRunnerConfig(
        model=f"user:{config.user_model}|proactive:{config.proactive_model}",
        model_provider=config.user_model_provider,
        # ... map other fields
    )

    result = MultiScenarioValidationResult(run_config=meta_config)

    for scenario_name in scenarios:
        validation = run_scenario(scenario_name, config)
        result.add_result(validation, scenario_name, run_number=None)

    return result
```

#### JSON Serialization

`MultiScenarioValidationResult` doesn't have a built-in `to_json()` method. We need to create a serialization helper:

```python
def serialize_multi_result(result: MultiScenarioValidationResult) -> dict:
    """Serialize MultiScenarioValidationResult to JSON-compatible dict."""
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "config": result.run_config.model_dump(),
        "duration": result.duration,
        "successful_count": result.successful_count,
        "failed_count": result.failed_count,
        "exception_count": result.exception_count,
        "no_validation_count": result.no_validation_count,
        "success_rate": result.success_rate(),
        "scenario_results": {
            f"{scenario_id}_{run_num or 0}": {
                "success": r.success,
                "exception": str(r.exception) if r.exception else None,
                "rationale": r.rationale,
                "export_path": r.export_path,
                "duration": r.duration,
            }
            for (scenario_id, run_num), r in result.scenario_results.items()
        },
    }
```

## Immediate Implementation (Current)

For the immediate need of running all scenarios, we use simple custom dataclasses in `scripts/run_all_scenarios.py`:

```python
@dataclass
class ScenarioResult:
    """Result of running a single scenario."""
    scenario_name: str
    success: bool
    rationale: str | None = None
    exception: str | None = None
    duration_seconds: float = 0.0
    export_path: str | None = None


@dataclass
class ResultsSummary:
    """Summary of all scenario runs."""
    timestamp: str
    config: dict[str, Any] = field(default_factory=dict)
    total_scenarios: int = 0
    passed: int = 0
    failed: int = 0
    results: list[ScenarioResult] = field(default_factory=list)
```

This allows us to get up and running quickly. The full config system will replace these in a future iteration.

## Implementation Plan

### Phase 1: Create PAS Config Classes

**File**: `pas/configs/scenario_runner_config.py`

1. Create `PASScenarioRunnerConfig` with all PAS-specific fields
2. Create `PASMultiScenarioRunnerConfig` extending it
3. Add helper methods for building augmentation configs and directory paths
4. Add `get_config_hash()` for caching support

### Phase 2: Update TwoAgentScenarioRunner

**File**: `pas/scenario_runner.py`

The `TwoAgentScenarioRunner` should be updated to use the new config classes:

1. Add new method `run_pas_scenario_with_config(scenario, config: PASScenarioRunnerConfig)`:
   ```python
   def run_pas_scenario_with_config(
       self,
       scenario: Scenario,
       config: PASScenarioRunnerConfig,
   ) -> ScenarioValidationResult:
       """Run a PAS scenario using a config object.

       Args:
           scenario: The scenario to run.
           config: The PAS scenario runner configuration.

       Returns:
           ScenarioValidationResult: The validation result.
       """
       # Build agent configs from PAS config
       user_config = ARESimulationReactBaseAgentConfig(
           llm_engine_config=LLMEngineConfig(
               model_name=config.user_model,
               provider=config.user_model_provider,
           ),
           max_iterations=config.user_max_iterations,
           use_custom_logger=False,
       )

       proactive_observe_config = ARESimulationReactBaseAgentConfig(
           llm_engine_config=LLMEngineConfig(
               model_name=config.proactive_model,
               provider=config.proactive_model_provider,
           ),
           max_iterations=config.observe_max_iterations,
           use_custom_logger=False,
       )

       proactive_execute_config = ARESimulationReactBaseAgentConfig(
           llm_engine_config=LLMEngineConfig(
               model_name=config.proactive_model,
               provider=config.proactive_model_provider,
           ),
           max_iterations=config.execute_max_iterations,
           use_custom_logger=False,
       )

       # Apply tool augmentation if configured
       if config.tool_failure_prob > 0:
           scenario.tool_augmentation_config = config.get_tool_augmentation_config()

       # Apply env events if configured
       if config.env_events_per_min > 0:
           scenario.env_events_config = config.get_env_events_config()

       return self.run_pas_scenario(
           scenario=scenario,
           user_config=user_config,
           proactive_observe_config=proactive_observe_config,
           proactive_execute_config=proactive_execute_config,
           max_turns=config.max_turns,
           oracle_mode=config.oracle_mode,
           traces_dir=config.traces_dir,
       )
   ```

2. Keep existing `run_pas_scenario()` for backwards compatibility (mark as deprecated)

3. Refactor internal `_run_pas_scenario()` to optionally accept config object

### Phase 3: Update Scripts to Use Configs

**Files**: `scripts/run_single_scenario.py`, `scripts/run_all_scenarios.py`

1. Build `PASScenarioRunnerConfig` from CLI args
2. Pass config object to `runner.run_pas_scenario_with_config()`
3. Replace custom `ScenarioResult`/`ResultsSummary` with `MultiScenarioValidationResult`

### Phase 4: Add Serialization Utilities

**File**: `pas/configs/serialization.py` (or add to existing utils)

1. Create `serialize_multi_result()` for JSON export
2. Create `deserialize_multi_result()` for loading saved results
3. Update `run_all_scenarios.py` to use these utilities

## Open Questions

1. **Separate models for observe/execute?**: Currently both use `proactive_model`. Should we support separate models for observe and execute agents?

2. **Config file support?**: Should we support loading configs from YAML/JSON files in addition to CLI args?

3. **Config inheritance from Meta-ARE?**: Should `PASScenarioRunnerConfig` extend `ScenarioRunnerConfig` or be standalone?
   - Pros of extending: Reuse existing fields, compatibility
   - Cons: Many fields not relevant to PAS (a2a, scenario_creation_params, etc.)

4. **Compatibility with Meta-ARE's MultiScenarioRunner?**: Should we aim to be compatible with Meta-ARE's parallel execution infrastructure, or build our own?

## Dependencies

- `pydantic` (already a dependency via Meta-ARE)
- `polars` (optional, for `to_polars()` functionality)

## References

- Meta-ARE config: `are/simulation/scenarios/config.py`
- Meta-ARE validation result: `are/simulation/scenarios/validation_result.py`
- Current PAS runner: `pas/scenario_runner.py`
- Current PAS scripts: `scripts/run_single_scenario.py`, `scripts/run_all_scenarios.py`
