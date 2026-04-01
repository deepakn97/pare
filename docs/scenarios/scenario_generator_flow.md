# Multi-Step Scenario Generator Flow

This page documents the current execution flow of the generator stack.

## Entry Point

Primary entrypoints:

- `pare scenarios generate` (`pare/cli/scenarios.py`)
- `python -m pare.scenarios.generator.scenario_generator`

Both construct and run `ScenarioGeneratingAgentOrchestrator`.

## Core Orchestrator

Main class:

- `pare.scenarios.generator.agent.scenario_generating_agent_orchestrator.ScenarioGeneratingAgentOrchestrator`

Responsibilities:

- initialize trajectory/output paths
- configure Claude SDK runtime constraints for steps
- run the step sequence with retry/check feedback loops
- snapshot step artifacts and persist final outputs

## Prompt Context And Runtime Setup

Before the step loop begins, the generator prepares prompt context from the selected apps and injects that context into the step prompts. In practice, this is where the generator decides which app APIs, import hints, and initialization instructions should appear in the LLM-facing prompt.

The orchestrator also configures Claude runtime constraints for each stage:

- read-only style runtimes for description and uniqueness-oriented work
- read/write runtimes for code-producing steps
- a constrained editable working file so code edits stay within the scenario template flow

This keeps the model-facing workflow narrow: the model proposes step outputs, while the orchestrator owns path setup, file writes, and validation checks.

## Step Sequence

The default sequence is:

1. **Step 1: Description**
   - generate scenario narrative
   - run uniqueness checks against historical metadata
2. **Step 2: Apps and Data**
   - write app initialization/state setup into editable seed file
   - run apps/data runtime checks
3. **Step 3: Events Flow**
   - write event sequence and proactive interactions
   - run event-flow runtime checks
4. **Step 4: Validation**
   - write scenario validation logic
   - run validation check with required success criteria

The step workers are implemented in `pare/scenarios/generator/agent/step_agents.py`.

## How Step Validation Works

Each code-writing step feeds its output back into the orchestrator, which writes the current scenario file and runs a step-specific check:

- **Step 2 check**: verifies app initialization and seeded data setup
- **Step 3 check**: verifies event-flow structure and runtime viability
- **Step 4 check**: verifies validation logic and requires successful validation execution

For Steps 3 and 4, the generator also uses a guardrail against non-code responses. If the model replies with natural-language commentary instead of a complete scenario file, the step fails immediately and retries with corrective feedback.

The important separation of responsibilities is:

- step agents build prompts and retry on feedback
- the orchestrator writes files, runs checks, snapshots artifacts, and decides pass/fail
- the Claude backend only handles model invocation and tool/runtime policy

## Resume Behavior

`--resume-from-step` can continue from:

- `step2`: reuse Step 1 result
- `step3`: reuse Steps 1-2 results
- `step4`: reuse Steps 1-3 results

When resuming, the generator reuses the existing working file and previously completed step outputs from disk instead of regenerating earlier stages.

## Files Written During Runs

- `pare/scenarios/default_generation_output/editable_seed_scenario.py`
- `pare/scenarios/default_generation_output/<GeneratedClassName>.py`
- `pare/scenarios/generator/step_trajectory/trajectory_*/steps.jsonl`
- `pare/scenarios/generator/step_trajectory/trajectory_*/editable_seed_scenario_step*.py`
- `pare/scenarios/scenario_metadata.json`

The step snapshots are useful when debugging failures because they preserve the intermediate scenario file after major transitions such as apps/data setup and event-flow generation.

## Success And Failure Outputs

On success, the final scenario is persisted to the generator output area as a completed scenario file.

On failure, the generator still preserves the working scenario artifact and failure context so you can inspect:

- whether the failure was caused by runtime errors
- whether validation was reached but unsuccessful
- what the last generated scenario file looked like before the run stopped

## Related Modules

- `pare/scenarios/generator/agent/scenario_uniqueness_agent.py`
- `pare/scenarios/generator/agent/claude_backend.py`
- `pare/scenarios/generator/prompt/scenario_generating_agent_prompts.py`
- `pare/scenarios/generator/utils/apps_init_instructions.py`
