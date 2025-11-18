# Feature Request: Integrate Meta-ARE Noise System into PAS

## Feature Summary

Add support for Meta-ARE's noise systems in PAS to test agent robustness under realistic conditions. This includes:
1. **Tool Failure Probability**: Agent actions fail with configurable probability to simulate unreliable APIs
2. **Environmental Event Noise**: Random notifications/messages inject distractions during scenario execution

## Motivation and Use Case

**Problem**: Current PAS scenarios run in ideal conditions where every tool succeeds and no distracting events occur. Real-world proactive agents must handle:
- API failures and timeouts
- Irrelevant notifications competing for attention
- Noisy user environments with multiple simultaneous events

**Who Benefits**:
- Researchers evaluating agent robustness and error recovery strategies
- Developers testing proactive agents under realistic conditions
- Benchmark creators designing challenging evaluation scenarios

**Use Cases**:
1. Test if proactive agent gracefully handles failed calendar API calls
2. Evaluate user agent behavior when distracted by irrelevant notifications
3. Measure agent performance degradation as noise levels increase
4. Compare error recovery strategies across different agent architectures

## Proposed Solution

### Overview

Integrate Meta-ARE's existing noise infrastructure (`ToolAugmentationConfig` and `EnvEventsConfig`) into PAS's scenario runner and configuration layer.

### Key Components to Integrate

**Meta-ARE Implementation** (for reference):
- `are/simulation/types.py:1546` - `ToolAugmentationConfig` class
- `are/simulation/tool_utils.py:56` - `AppTool` with failure probability logic
- `are/simulation/scenarios/utils/scenario_expander.py:55` - `EnvEventsConfig` and `EnvEventsExpander`
- `are/simulation/scenario_runner.py` - Configuration application in `run_scenario()`

### Integration Architecture

```python
# 1. Add noise configuration to TwoAgentScenarioRunner
# File: pas/scenario_runner.py

class TwoAgentScenarioRunner(ScenarioRunner):
    def run(
        self,
        scenario: Scenario,
        user_config: ARESimulationReactBaseAgentConfig,
        proactive_observe_config: ARESimulationReactBaseAgentConfig,
        proactive_execute_config: ARESimulationReactBaseAgentConfig,
        max_turns: int | None = None,
        oracle_mode: bool = False,
        # NEW: Add noise configuration parameters
        tool_augmentation_config: ToolAugmentationConfig | None = None,
        env_events_config: EnvEventsConfig | None = None,
    ) -> ScenarioValidationResult:
        """
        tool_augmentation_config: Tool failure probability settings
        env_events_config: Environmental noise event settings
        """
        # Apply tool failure probability to all apps in scenario
        if tool_augmentation_config:
            scenario.initialize(tool_augmentation_config=tool_augmentation_config)

        # Inject environmental noise events into scenario
        if env_events_config:
            expander = EnvEventsExpander(env_events_config)
            scenario = expander.expand(scenario)

        # Continue with normal execution...
```

```python
# 2. Add CLI flags to demo scripts
# File: pas/scripts/run_two_agent_demo.py

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()

    # Existing arguments...

    # NEW: Add noise configuration arguments
    parser.add_argument(
        "--tool-failure-prob",
        type=float,
        default=0.0,
        help="Probability (0.0-1.0) that agent tools fail",
    )
    parser.add_argument(
        "--env-events-per-min",
        type=float,
        default=0.0,
        help="Average number of environmental noise events per minute",
    )
    parser.add_argument(
        "--noise-seed",
        type=int,
        help="Random seed for reproducible noise generation",
    )

    args = parser.parse_args(argv)

    # Create noise configurations if enabled
    tool_aug_config = None
    if args.tool_failure_prob > 0:
        tool_aug_config = ToolAugmentationConfig(
            tool_failure_probability=args.tool_failure_prob,
            tool_failure_seed=args.noise_seed,
        )

    env_events_config = None
    if args.env_events_per_min > 0:
        env_events_config = EnvEventsConfig(
            num_env_events_per_minute=args.env_events_per_min,
            env_events_seed=args.noise_seed,
            # Configure which apps can generate noise
            weight_per_app_class={
                "StatefulEmailApp": 0.4,
                "StatefulMessagingApp": 0.3,
                "StatefulCalendarApp": 0.2,
                "StatefulContactsApp": 0.1,
            },
        )

    # Pass to runner
    result = runner.run(
        scenario=scenario,
        user_config=user_config,
        proactive_observe_config=proactive_observe_config,
        proactive_execute_config=proactive_execute_config,
        max_turns=max_turns,
        oracle_mode=args.oracle,
        tool_augmentation_config=tool_aug_config,  # NEW
        env_events_config=env_events_config,        # NEW
    )
```

```python
# 3. Ensure PAS apps support failure probability
# Files: pas/apps/*/app.py

# All PAS StatefulApp classes already inherit from Meta-ARE's App base class,
# which implements set_failure_probability(). No changes needed to apps.

# The tool_utils.AppTool decorator handles failure injection automatically:
# - When tool is called, checks if rng.random() < failure_probability
# - If true, raises ToolException with "This tool call failed" message
# - Agents must handle this exception in their action execution loop
```

### Agent Error Handling

**How Tool Failures Work:**

1. Tool fails: `AppTool.__call__()` raises `Exception` with message `"Calling {name} failed with error: Internal error - Retry again later"`
2. Meta-ARE wraps it in `JsonExecutionAgentError` with tool description
3. `BaseAgent.execute_agent_loop()` catches exception and logs as `ErrorLog`
4. Agent continues executing (doesn't crash)
5. Error appears in agent's observation history for next LLM prompt

**No PAS Code Changes Required:**
- PAS agents inherit `BaseAgent` which already handles tool failures gracefully
- Errors automatically logged and presented to LLM in observation history
- Agent can reason about errors and adapt strategy based on error messages

**Optional Advanced Recovery Strategies:**
- Retry with exponential backoff (track failures in `custom_state`)
- Try alternative tools when primary tool fails
- Notify user for critical failures via `send_message_to_user`
- Graceful degradation: skip non-critical tasks, continue workflow
- Implement via custom agent post-processing steps or enhanced system prompts

### Environmental Noise Behavior

```python
# 5. Environmental events inject distractions
# Meta-ARE's EnvEventsExpander automatically:
# - Generates random emails, messages, calendar invites based on scenario data
# - Schedules via Poisson process (realistic timing distribution)
# - Adds events to scenario.events list before execution
# - PAS agents see these as normal notifications in their event stream

# Example: During "email_calendar_meeting_request" scenario with noise:
# - Original: User receives 1 meeting request email
# - With noise: User also receives 2-3 random emails, 1-2 messages
# - Agent must filter relevant vs irrelevant notifications
# - Tests agent's attention and prioritization mechanisms
```

## Alternatives Considered

### Alternative 1: Build Custom Noise System
- **Pros**: Full control over PAS-specific noise patterns
- **Cons**: Duplicate effort, incompatible with Meta-ARE benchmarks, maintenance burden
- **Verdict**: Rejected - Meta-ARE's system is proven and compatible

### Alternative 2: Hardcode Noise in Scenarios
- **Pros**: Simple, no configuration needed
- **Cons**: Not reusable, can't adjust noise levels dynamically, no randomization
- **Verdict**: Rejected - Not flexible enough for research experimentation

### Alternative 3: Post-hoc Event Injection
- **Pros**: Could inject noise after scenario creation
- **Cons**: Harder to maintain consistency, timing issues, doesn't integrate with tool failure
- **Verdict**: Rejected - Meta-ARE's design is cleaner

## Component

**Core** (affects `scenario_runner.py`, `environment.py`, and demo scripts)

## Priority

**High** - Would significantly improve experimental evaluation capabilities

## Example Usage

### Basic Tool Failure Test

```python
from pas.scenario_runner import TwoAgentScenarioRunner
from are.simulation.types import ToolAugmentationConfig
from pas.scenarios.registry import registry

# Get scenario
scenario = registry.get_scenario("email_calendar_meeting_request")()

# Configure 20% tool failure rate
tool_config = ToolAugmentationConfig(
    tool_failure_probability=0.2,
    tool_failure_seed=42,  # Reproducible
)

# Run with noise
runner = TwoAgentScenarioRunner(config=runner_config)
result = runner.run(
    scenario=scenario,
    user_config=user_config,
    proactive_observe_config=proactive_obs_config,
    proactive_execute_config=proactive_exec_config,
    tool_augmentation_config=tool_config,
)

# Result shows agent's robustness to failures
print(f"Success: {result.success}")
print(f"Failed tool calls: {count_failed_actions(result)}")
```

### Environmental Noise Test

```python
from are.simulation.scenarios.utils.scenario_expander import EnvEventsConfig

# Configure moderate environmental noise
env_config = EnvEventsConfig(
    num_env_events_per_minute=2.0,  # 2 events/minute average
    env_events_seed=42,
    max_num_messages_per_conversation=5,
    weight_per_app_class={
        "StatefulEmailApp": 0.5,      # 50% emails
        "StatefulMessagingApp": 0.3,  # 30% messages
        "StatefulCalendarApp": 0.2,   # 20% calendar invites
    },
)

# Run same scenario with environmental distractions
result = runner.run(
    scenario=scenario,
    user_config=user_config,
    proactive_observe_config=proactive_obs_config,
    proactive_execute_config=proactive_exec_config,
    env_events_config=env_config,
)

# Compare agent performance with/without noise
```

### CLI Usage

```bash
# Run demo with 15% tool failure and moderate noise
uv run python -m pas.scripts.run_two_agent_demo \
    --scenario email_calendar_meeting_request \
    --tool-failure-prob 0.15 \
    --env-events-per-min 1.5 \
    --noise-seed 42

# Run in oracle mode with noise (test scenario validity)
uv run python -m pas.scripts.run_two_agent_demo \
    --scenario contact_update_from_new_number \
    --oracle \
    --tool-failure-prob 0.1

# Stress test with high noise
uv run python -m pas.scripts.run_two_agent_demo \
    --scenario calendar_conflict_urgent_reschedule \
    --tool-failure-prob 0.3 \
    --env-events-per-min 5.0
```

## Related Work

### Meta-ARE Noise System Design
- **Reference Implementation**: `meta-are/are/simulation/scenario_runner.py`, `meta-are/are/simulation/types.py`
- Meta-ARE uses this for benchmark robustness testing
- Poisson process for realistic event timing (exponential distribution)
- Seeded RNG for reproducibility in experiments

### Research Context
- Robustness testing is standard in agent evaluation (WebArena, AgentBench)
- Tool failures simulate real API reliability issues (rate limits, timeouts, network errors)
- Environmental noise tests agent attention mechanisms and filtering
- Related to multi-task learning and distraction resistance

### Similar Systems
- **Gymnasium**: Observation/action noise in RL environments
- **AgentBench**: Environmental perturbations for agent evaluation
- **AndroidEnv**: System event injection for Android agent testing

## Additional Context

### Implementation Considerations

1. **Agent Error Recovery**: Current PAS agent implementations (in development) need error handling logic
   - User agent should inform user when actions fail
   - Proactive agent should retry or find alternatives
   - Both agents should log failures for analysis

2. **Oracle Mode Compatibility**: Environmental noise works with oracle mode, but tool failures don't (oracles assume success)
   - Consider: Should oracle mode disable tool failures?
   - Or: Should oracle mode test scenario robustness to failures?

3. **Notification System Integration**: PAS already has `PASNotificationSystem` (extends Meta-ARE's)
   - Environmental events automatically flow through notification system
   - No additional integration needed for agent views

4. **Testing Strategy**:
   - Unit tests: Verify noise configs applied correctly
   - Integration tests: Run scenarios with noise, check expected behaviors
   - Regression tests: Ensure noise doesn't break existing scenarios
   - Robustness benchmarks: Measure agent performance across noise levels

### Configuration Recommendations

**Tool Failure Rates** (based on Meta-ARE usage):
- **Light**: 5-10% (occasional failures)
- **Moderate**: 15-25% (realistic API reliability)
- **Heavy**: 30-50% (stress testing)

**Environmental Event Rates**:
- **Light**: 0.5-1.0 events/min (occasional distraction)
- **Moderate**: 1.5-3.0 events/min (busy user)
- **Heavy**: 4.0-6.0 events/min (very noisy environment)

### Future Enhancements

1. **Per-App Failure Rates**: Configure different failure rates for different apps
2. **Time-Varying Noise**: Increase noise levels during specific scenario phases
3. **Conditional Noise**: Trigger environmental events based on agent actions
4. **Noise Visualization**: Dashboard showing noise events in trace viewer

### File References

**Meta-ARE Files** (read-only reference):
- `meta-are/are/simulation/types.py:1546` - `ToolAugmentationConfig` definition
- `meta-are/are/simulation/tool_utils.py:56` - `AppTool` failure logic
- `meta-are/are/simulation/scenarios/utils/scenario_expander.py:55` - `EnvEventsConfig`, `EnvEventsExpander`
- `meta-are/are/simulation/scenario_runner.py:156` - Configuration application in `run_scenario()`

**PAS Files** (to modify):
- `pas/scenario_runner.py` - Add noise config parameters to `TwoAgentScenarioRunner.run()`
- `pas/scripts/run_two_agent_demo.py` - Add CLI flags for noise configuration
- `pas/apps/core.py` - Ensure `StatefulApp` supports failure probability (already inherited)

**PAS Files** (future - agent error handling):
- `pas/agents/user/*.py` - Add ToolException handling in user agent
- `pas/agents/proactive/*.py` - Add ToolException handling in proactive agent

## Pre-submission Checklist

- [x] I have searched existing issues and discussions to ensure this is not a duplicate
- [x] I have considered how this feature fits with PAS's research goals (agent robustness evaluation)
- [ ] I am willing to contribute to implementing this feature

---

## Working Notes

### Meta-ARE Noise Infrastructure Review (Step 1 Completed)

**Key Findings from Code Analysis:**

#### 1. ToolAugmentationConfig (are/simulation/types.py:1546-1551)

```python
@dataclass
class ToolAugmentationConfig:
    tool_failure_probability: float = 0.1
    # Mapping from original tool name to the new tool name
    apply_tool_name_augmentation: bool = True
    apply_tool_description_augmentation: bool = True
```

**Purpose**: Configures tool failure rate and optional tool name/description obfuscation.

**How It Works**:
- Stored in `scenario.tool_augmentation_config` (set during preprocessing)
- Applied via `scenario.apply_augmentation_configs()` method (are/simulation/scenarios/scenario.py:1258)
- Calls `app.set_failure_probability(config.tool_failure_probability)` on each app
- `App.set_failure_probability()` (are/simulation/apps/app.py:108):
  - Sets `self.failure_probability` attribute
  - Resets tool registries to force re-decoration with new failure rate
- Tool execution checks failure via `AppTool` decorator logic
- If `rng.random() < failure_probability`, raises `ToolException("This tool call failed")`

#### 2. EnvEventsConfig (are/simulation/scenarios/utils/scenario_expander.py:56-96)

```python
@dataclass
class EnvEventsConfig:
    num_env_events_per_minute: int = 10
    env_events_seed: int = 0
    n_message_events_per_conversation: int = 4
    n_item_events_per_product: int = 2
    weight_per_app_class: dict[str, float] = field(default_factory=default_weight_per_app_class)
```

**Purpose**: Controls background event generation (emails, messages, calendar invites, etc.).

**How It Works**:
- Stored in `scenario.env_events_config` (set during preprocessing)
- Applied via `EnvEventsExpander.add_env_events_to_scenario()` during `scenario.initialize()` (are/simulation/scenarios/scenario.py:175-177)
- Uses Poisson process (exponential inter-arrival times) for realistic event timing
- Samples from `scenario.augmentation_data` to generate noise events
- Adds new `Event` objects to `scenario.events` list with dependency chains
- Events tagged with `ENV_EVENT_EXPANSION_TAG` prefix for tracking

#### 3. Integration Pattern in Meta-ARE ScenarioRunner

**Config Storage** (are/simulation/scenarios/config.py:104-108):
```python
class ScenarioRunnerConfig(BaseModel):
    # ...
    tool_augmentation_config: ToolAugmentationConfig | None = None
    env_events_config: EnvEventsConfig | None = None
```

**Application Flow** (are/simulation/scenarios/scenario_imported_from_json/utils.py:43-82):
```python
def preprocess_scenario(
    scenario: BenchmarkScenarioImportedFromJson,
    tool_augmentation_config: ToolAugmentationConfig | None = None,
    env_events_config: EnvEventsConfig | None = None,
):
    # ...
    # Step 1: Attach configs to scenario
    scenario.tool_augmentation_config = tool_augmentation_config  # Line 78
    scenario.env_events_config = env_events_config                # Line 79

    # Step 2: Initialize scenario (applies configs)
    scenario.initialize()  # Line 82
    # This calls:
    #   - scenario.apply_augmentation_configs() for tool failures
    #   - EnvEventsExpander.add_env_events_to_scenario() for environmental noise
```

**ScenarioRunner Integration**:
- Configs passed from `ScenarioRunnerConfig` to `preprocess_scenario()`
- In `load_and_preprocess_scenario_str()` helper function
- Called by `ScenarioRunner.run()` when loading scenarios from JSON

#### 4. Key Implementation Details

**Tool Failure Mechanism**:
- `App.failure_probability` attribute (default 0.0)
- `App.set_failure_probability(prob)` updates all tool registries
- Tools decorated with failure check in `AppTool.__call__()`
- Agents see `ToolException` when tool fails
- Exception includes message: "This tool call failed"

**Environmental Event Scheduling**:
- Uses `numpy.random.default_rng(seed)` for Poisson sampling
- Uses `random.Random(seed)` for event selection
- Events scheduled with `event.depends_on(start_event, delay_seconds=tick)`
- Tick times computed via `np.cumsum(np_rng.exponential(scale=1/rate, size=n))`
- Supports multiple app types: Messaging, Email, Shopping, Apartment listings

**Augmentation Data Requirements**:
- Environmental noise requires `scenario.augmentation_data` with app states
- Contains conversation histories, email templates, product catalogs
- EnvEventsExpander samples from this data to generate realistic noise
- If augmentation_data missing, env noise cannot be generated

#### 5. PAS Integration Strategy

Based on Meta-ARE's implementation, PAS integration should:

1. **In `scenario_runner.py` (TwoAgentScenarioRunner.run())**:
   - Accept `tool_augmentation_config` and `env_events_config` parameters
   - Attach to `scenario` object before initialization
   - Call `scenario.initialize()` to apply configs
   - No need to manually call `apply_augmentation_configs()` or `EnvEventsExpander` (handled in `initialize()`)

2. **In `scripts/run_two_agent_demo.py`**:
   - Add CLI flags: `--tool-failure-prob`, `--env-events-per-min`, `--noise-seed`
   - Construct `ToolAugmentationConfig` and `EnvEventsConfig` from args
   - Pass to `runner.run()` method

3. **PAS Apps Compatibility**:
   - All `StatefulApp` classes inherit from `meta_are.App`
   - Therefore already support `set_failure_probability()`
   - No changes needed to app implementations
   - Tool failures handled automatically by Meta-ARE's `AppTool` decorator

4. **Agent Error Handling** (future work):
   - User agent and proactive agent need `try/except ToolException` blocks
   - Should log failures and implement retry/recovery strategies
   - Document best practices for error handling in agent implementations

#### 6. Open Questions

1. **Oracle Mode Behavior**: ✅ **DECISION MADE**
   - **Do NOT disable tool failures in oracle mode**
   - Keep default `tool_failure_probability = 0.0` so oracle runs cleanly by default
   - Users can explicitly set `--tool-failure-prob > 0` to test oracle robustness
   - This allows testing scenarios with failures when needed

2. **Augmentation Data for PAS**: ✅ **CONFIRMED - PAS scenarios do NOT have `augmentation_data`**
   - Searched PAS codebase - no references to `augmentation_data` found
   - Examined scenario structure (e.g., `email_calendar_meeting_request.py`) - no augmentation data present
   - Base `Scenario` class from Meta-ARE defines `augmentation_data: dict[str, Any] = field(default_factory=dict)`
   - **Structure required by EnvEventsExpander**:
     ```python
     augmentation_data = {
         "apps": [
             {
                 "name": "StatefulMessagingApp",  # Must match app instance name
                 "app_state": {
                     "conversations": {
                         "conv_id": {
                             "conversation_id": "conv_id",
                             "messages": [
                                 {"sender": "Alice", "content": "..."},
                                 # More messages for noise generation
                             ]
                         }
                     }
                 }
             },
             {
                 "name": "StatefulEmailApp",
                 "app_state": {
                     "folders": {
                         "INBOX": {
                             "emails": [
                                 {
                                     "email_id": "...",
                                     "sender": "...",
                                     "recipients": [...],
                                     "subject": "...",
                                     "content": "..."
                                 }
                             ]
                         }
                     }
                 }
             }
         ]
     }
     ```
   - **Decision**: Environmental noise feature requires implementing augmentation data generation for PAS scenarios

3. **App Class Names**: EnvEventsExpander uses hardcoded app class names
   - Meta-ARE: `MessagingApp`, `EmailClientApp`, etc.
   - PAS: `StatefulMessagingApp`, `StatefulEmailApp`, etc.
   - **Potential issue**: Name mismatch may prevent noise generation
   - **Solution**: May need to configure `weight_per_app_class` with PAS app names

4. **Scenario Duration**: EnvEventsExpander requires `scenario.duration`
   - Defaults to 360 seconds if not set
   - PAS scenarios should set this explicitly

### Next Steps (Steps 2-8)

**Step 2**: Add noise config parameters to `TwoAgentScenarioRunner.run()`
- Add two optional parameters to method signature
- Store in scenario before calling initialization

**Step 3**: Implement tool augmentation application
- Verify `scenario.initialize()` calls `apply_augmentation_configs()`
- Test that tool failures occur with configured probability

**Step 4**: Implement env events expansion
- Verify `scenario.initialize()` calls `EnvEventsExpander`
- Check if PAS scenarios have required `augmentation_data`
- Test noise event generation

**Step 5**: Add CLI flags
- `--tool-failure-prob` (float, 0.0-1.0)
- `--env-events-per-min` (float, >= 0)
- `--noise-seed` (int, for reproducibility)

**Step 6**: Verify app inheritance
- Confirm `StatefulApp` → `meta_are.App` inheritance chain
- Test `set_failure_probability()` on PAS apps
- Verify tool failure injection works

**Step 7**: Integration testing
- Run existing scenarios with tool failures enabled
- Run with environmental noise enabled
- Verify agents receive failure exceptions
- Check noise events appear in logs

**Step 8**: Document agent requirements
- Document ToolException handling patterns
- Provide example error recovery strategies
- Update agent development guidelines
