# Trace Export Semantics

This page documents what PARE exports after scenario execution and how trace formats differ.

## Export Entry Point

Trace export is handled by:

- `pare.data_handler.exporter.PAREJsonScenarioExporter`

`TwoAgentScenarioRunner` calls the exporter after validation and stores the returned path on the validation result.

## What PARE Adds

Compared with the base exporter, PARE adds:

- PARE-specific completed-event metadata
- proactive context fields such as proactive mode and turn number
- world logs for richer execution traces

## Supported Formats

`trace_dump_format` supports:

- `hf`
- `lite`
- `both`

## Format Differences

### `hf`

The HuggingFace-oriented format is the richer trace:

- includes `world_logs`
- includes converted PARE completed events
- suitable for uploadable / analysis-friendly trace workflows

### `lite`

The lite format is a smaller export path:

- intended for local analysis/debugging
- explicitly warned as not uploadable to HuggingFace

### `both`

When `both` is selected:

- the exporter writes two files
- one under `output_dir/hf/`
- one under `output_dir/lite/`
- both share the same run-id-based filename

For backward compatibility, the exporter returns the **HF file path** as the primary `export_path`.

## File Naming

Export filenames are derived from `get_run_id(scenario, runner_config)`.

That means filenames reflect:

- scenario id
- optional run number
- config hash suffix when applicable

## Output Location

- if `output_dir` is provided, traces are written there
- otherwise the system falls back to the OS temp directory

## App State Export Behavior

The runner can suppress app-state export in some cases, notably when a scenario already provides `hf_metadata`.

So exported traces may differ slightly depending on scenario metadata and export settings.

## Where Exported Traces Are Used

Exported traces feed into:

- benchmark result analysis
- annotation sampling and review
- debugging failed or surprising runs
- scenario artifact inspection during experiments
