# Meta-ARE Repository Understanding Notes

## Core Architecture Overview

### Scenario and Environment Flow

**A scenario supplies apps and events**
- Scenarios define both the applications (apps) and the sequence of events that will occur
- Apps provide the interface and functionality that agents can interact with
- Events define the timeline and triggers for the simulation

**The environment registers the scenario's apps and schedules the scenario's events, then runs the event loop**
- Environment acts as the runtime container for scenario execution
- **1 env per scenario run** - Each scenario gets its own isolated environment
- Event loop starts with the **root event** and processes events in the scheduled order
- Environment manages the lifecycle of apps and coordinates event timing

**Overall flow for one scenario class:**
```
Scenario = initialize -> apps -> eventDAG -> validation
```

### Scenario Runner

**Scenario runner constructs an env, then builds the agent and runs it**
- Main orchestration component that manages the entire scenario execution lifecycle
- Creates the environment, initializes apps, schedules events
- Builds and configures the agent with appropriate settings
- Manages the execution loop and handles results

### Agent Architecture

**Two agent loops:**

1. **Outer "iterations" loop**: The ReAct step loop (Thought → Action → Observation)
   - Repeats until termination condition is met
   - Termination conditions: agent emits `final_answer`, termination rule fires, or hits `max_iterations` (default: 80)
   - This is the main reasoning loop where the agent plans and acts

2. **Inner "formatting retry" loop**: Within each `step()`
   - If model's output isn't in required JSON Action format, retries up to `BASE_AGENT_INVALID_FORMAT_RETRIES` (default: 10)
   - Handles parsing errors and malformed responses gracefully
   - Ensures robust communication between agent and environment

### Entry Points

**The entry point to build the agent is here**
- Agent construction and configuration happens through the agent builder pattern
- Configures model, tools, memory, and behavioral parameters
- link: https://github.com/facebookresearch/meta-agents-research-environments/blob/main/are/simulation/agents/agent_builder.py#L64

**We need to build the config before building each agent, and the config builder for default agent is here**
- Configuration-first approach ensures proper agent setup
- Config builder centralizes agent configuration logic
- Allows for different agent types with shared configuration patterns
- link: https://github.com/facebookresearch/meta-agents-research-environments/blob/main/are/simulation/agents/agent_config_builder.py#L67

**The entry point to run the ReAct step loop of an agent is here**
- Main execution method that implements the ReAct (Reasoning + Acting) pattern
- Handles the Thought → Action → Observation cycle
- Manages state transitions and decision making
- link: https://github.com/facebookresearch/meta-agents-research-environments/blob/main/are/simulation/agents/default_agent/are_simulation_main.py#L99

**Cmd line entry point: main.py**
- Primary command-line interface for running scenarios
- Provides user-friendly access to the entire simulation framework
- Handles argument parsing, scenario selection, and execution control

### Ground Truth and Validation

**Oracle events => ground truth**
- Oracle events represent the ideal or expected behavior in a scenario
- Used as reference points for evaluating agent performance
- Ground truth data for training, validation, and testing

**Scenario validation**
- Ensures scenarios are well-formed and executable
- Validates app configurations, event sequences, and dependencies
- Checks for logical consistency and completeness

### Implementation Notes

**Q: run_scenario of are_simulation_agent is not implemented?**
- `ARESimulationAgent` inherits `RunnableARESimulationAgent` (only declares, no implementation)
- Indicates a potential abstraction layer or interface definition
- May require concrete implementation in subclasses or through composition

## Key Components Relationship

```
Command Line (main.py)
    ↓
Scenario Runner
    ↓
Environment (1 per scenario)
    ↓
Agent (with dual loops)
    ↓
Apps + Events → Validation
```

## Design Patterns

- **Environment Pattern**: Isolated execution contexts per scenario
- **Builder Pattern**: Configuration-driven agent construction
- **ReAct Pattern**: Reasoning + Acting cycles for decision making
- **Retry Pattern**: Robust error handling and format validation
- **Event-Driven Architecture**: Scenario events drive simulation flow
