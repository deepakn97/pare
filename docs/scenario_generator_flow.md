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

## Resume Behavior

`--resume-from-step` can continue from:

- `step2`: reuse Step 1 result
- `step3`: reuse Steps 1-2 results
- `step4`: reuse Steps 1-3 results

## Files Written During Runs

- `pare/scenarios/default_generation_output/editable_seed_scenario.py`
- `pare/scenarios/default_generation_output/<GeneratedClassName>.py`
- `pare/scenarios/generator/step_trajectory/trajectory_*/steps.jsonl`
- `pare/scenarios/generator/step_trajectory/trajectory_*/editable_seed_scenario_step*.py`
- `pare/scenarios/scenario_metadata.json`

## Related Modules

- `pare/scenarios/generator/agent/scenario_uniqueness_agent.py`
- `pare/scenarios/generator/agent/claude_backend.py`
- `pare/scenarios/generator/prompt/scenario_generating_agent_prompts.py`
- `pare/scenarios/generator/utils/apps_init_instructions.py`
