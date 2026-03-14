# Annotation Workflow

The annotation subsystem supports human evaluation of proactive agent decisions using sampled trace decision points.

## Components

- `pare/annotation/sampler.py`: balanced sample creation from trace directories.
- `pare/annotation/server.py`: FastAPI service and UI for annotation.
- `pare/annotation/metrics.py`: agreement and reliability metrics.
- `pare/annotation/trace_parser.py`: extracts decision points from traces.
- `pare/annotation/models.py`: shared data models.

## CLI Commands

All entrypoints are under `pare annotation`:

- `sample`: create/append sampled datapoints from traces.
- `launch`: run the annotation web server.
- `status`: view sample and annotation counts.
- `process`: compute agreement metrics.
- `set-dir` / `reset-dir`: configure annotation data directory.
- `invalidate`: clear annotations (and optionally samples).

## Typical Flow

```bash
uv run pare annotation sample --traces-dir traces --sample-size 200 --seed 42
uv run pare annotation launch --annotators-per-sample 2 --port 8000
uv run pare annotation process --n-annotators 2
```

For module-level API docs, see [Annotation API](../api/annotation.md).
