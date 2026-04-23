# Benchmark Scenarios

Benchmark scenarios are Python classes registered with `@register_scenario(...)` and loaded from `pare/scenarios/benchmark/`.

This is the part of the docs most users need for day-to-day benchmark usage: how to inspect scenarios, choose subsets, and run them.

## Where They Live

- `pare/scenarios/benchmark/*.py`: benchmark scenario files.
- `pare/scenarios/registration.py`: registration/discovery logic.
- `pare/scenarios/scenario.py`: base scenario lifecycle and helpers.

## How to Inspect and Run

List scenarios:

```bash
uv run pare scenarios list
```

Run the benchmark with a single model configuration:

```bash
uv run pare benchmark run --split full --observe-model gpt-5 --execute-model gpt-5
```

Run custom subset by IDs:

```bash
uv run pare benchmark run --scenarios scenario_a,scenario_b --observe-model gpt-5 --execute-model gpt-5
```

To compare multiple models, run `pare benchmark run` once per configuration -- result files live alongside each other in the same parent directory and `pare benchmark report` aggregates them.

## Review and Curation

- Review guidance: `pare/scenarios/benchmark/scenario_review_guidelines.md`
- Metadata ledger: `pare/scenarios/scenario_metadata.json`
- Reviewer assignment workflows can be managed through `scripts/create_review_csvs.py`

## Runtime Details

For execution-specific details beyond scenario authoring, see:

- [Runtime Execution Config](../runtime_execution.md)
- [Trace Export Semantics](../trace_export.md)
