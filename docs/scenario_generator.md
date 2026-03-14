# Scenario Generation

The active generator is implemented in:

- `pare/scenarios/generator/scenario_generator.py`
- `pare/scenarios/generator/agent/scenario_generating_agent_orchestrator.py`

It uses a multi-step pipeline to produce benchmark-style scenarios and validate them incrementally.

## Recommended CLI

Prefer the unified PARE CLI via the `pare` command:

```bash
uv run pare scenarios generate --num-scenarios 1
```

For full command examples and flag details, see [Scenarios CLI Usage](scenarios/cli_usage.md).

Useful options:

- `--apps/-a`: constrain selected app classes
- `--max-iterations`: retries per step
- `--resume-from-step`: resume at `step2|step3|step4`
- `--trajectory-dir`: reuse or set trajectory folder
- `--json` / `--full-json`: machine-readable output

## Direct Module Entry

You can also run the module directly:

```bash
uv run python -m pare.scenarios.generator.scenario_generator --num-scenarios 1
```

## Outputs

- Working scenario file: `pare/scenarios/default_generation_output/editable_seed_scenario.py`
- Final generated scenarios: `pare/scenarios/default_generation_output/*.py`
- Per-run trajectories: `pare/scenarios/generator/step_trajectory/trajectory_*/`
- Metadata ledger: `pare/scenarios/scenario_metadata.json`

## Pipeline Summary

1. Build prompt context from `ScenarioWithAllPAREApps`.
2. Step 1 generates scenario narrative + uniqueness checks.
3. Step 2 writes app/data setup.
4. Step 3 writes event flow.
5. Step 4 writes validation.
6. Runtime checks execute after steps to gate progression.

For step-by-step internals, see [Multi-Step Scenario Generator Flow](scenario_generator_flow.md).
