# Benchmark Scenarios

Benchmark scenarios are Python classes registered with `@register_scenario(...)` and loaded from `pare/scenarios/benchmark/`.

## Where They Live

- `pare/scenarios/benchmark/*.py`: benchmark scenario files.
- `pare/scenarios/registration.py`: registration/discovery logic.
- `pare/scenarios/scenario.py`: base scenario lifecycle and helpers.

## How to Inspect and Run

List scenarios:

```bash
uv run pare scenarios list
```

Run benchmark sweeps:

```bash
uv run pare benchmark sweep --split full --observe-model gpt-5 --execute-model gpt-5
```

Run custom subset by IDs:

```bash
uv run pare benchmark sweep --scenarios scenario_a,scenario_b --observe-model gpt-5 --execute-model gpt-5
```

## Review and Curation

- Review guidance: `pare/scenarios/benchmark/scenario_review_guidelines.md`
- Metadata ledger: `pare/scenarios/scenario_metadata.json`
- Reviewer assignment workflows can be managed through `scripts/create_review_csvs.py`

## Runtime Details

For execution-specific details beyond scenario authoring, see:

- [Runtime Execution Config](../runtime_execution.md)
- [Trace Export Semantics](../trace_export.md)
