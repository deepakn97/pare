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

```python
# 4. Ensure agents handle ToolException gracefully
# Files: pas/agents/user/*.py and pas/agents/proactive/*.py (future work)

# In agent's action execution loop:
try:
    result = tool.execute(**args)
except ToolException as e:
    # Log the failure
    logger.warning(f"Tool {tool_name} failed: {e}")

    # Agent should:
    # 1. Inform user of failure (if user-facing action)
    # 2. Attempt retry or alternative approach
    # 3. Update internal state to track failures
    # 4. Continue with remaining tasks

    # Example recovery strategies:
    # - Retry with exponential backoff
    # - Try alternative tool/approach
    # - Notify user and request manual intervention
    # - Skip non-critical task and continue
```

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
