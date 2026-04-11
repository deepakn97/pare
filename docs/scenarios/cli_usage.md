# `pare scenarios` CLI Usage

This project exposes `pare scenarios` (implemented in `pare/cli/scenarios.py`) to:

- list registered scenarios from `pare/scenarios/`
- inspect benchmark split files and validate scenario ID lists
- generate new scenarios with the multi-step generator pipeline

If `pare` is not available in your shell, run via the module entrypoint:

```bash
uv run python -m pare.main scenarios --help
```

## List Scenarios

`pare scenarios list` queries the PARE registry. By default, scenario-loading commands read `PARE_SCENARIOS_DIR`; if it is unset, they fall back to `benchmark`.

Accepted directory values are relative to `pare/scenarios/`, for example:

- `benchmark`
- `generator`
- `benchmark,generator`

### Examples

```bash
# List all benchmark scenarios
pare scenarios list

# Root shortcut for the list command
pare scenarios --list

# Explicitly choose scenario directories
pare scenarios list --scenarios-dir benchmark,generator

# Require all listed apps (repeatable flags)
pare scenarios list --apps StatefulEmailApp --apps StatefulCalendarApp

# Require all listed apps (comma-separated)
pare scenarios list --apps StatefulEmailApp,StatefulCalendarApp

# Filter by scenario_id substring
pare scenarios list --id-contains meeting

# Limit output
pare scenarios list --limit 10

# JSON output
pare scenarios list --json
```

### Flags

- `--scenarios-dir, --benchmark-dir TEXT`: override scenario directories to inspect; repeatable and/or comma-separated. Defaults to `PARE_SCENARIOS_DIR` or `benchmark`.
- `--apps, -a TEXT`: required-app filter; repeatable and/or comma-separated. All listed apps must be present in the scenario.
- `--id-contains TEXT`: substring match on scenario IDs
- `--limit INT`: max number of rows
- `--json`: emit JSON output

## Benchmark Split Helpers

These commands reuse the benchmark-loading helpers in `pare/benchmark/scenario_loader.py`.

### Examples

```bash
# Show the active splits directory and available split files
pare scenarios splits

# List scenarios referenced by the full split
pare scenarios split --split full

# List scenarios referenced by the ablation split as JSON
pare scenarios split --split ablation --json

# Validate a scenario-id file against registered scenarios
pare scenarios check-ids-file data/splits/full.txt

# Validate against other directories under pare/scenarios/
pare scenarios check-ids-file my_ids.txt --scenarios-dir generator

# Override the split directory used by the loader
PARE_BENCHMARK_SPLITS_DIR=data/splits pare scenarios split --split full
```

### Commands

- `pare scenarios splits`: show the active benchmark splits directory and available `.txt` split files
- `pare scenarios split --split {full|ablation}`: load scenarios via the benchmark split helpers and print their metadata
- `pare scenarios check-ids-file FILE`: read one scenario ID per line and report which IDs are present or missing in the selected scenario directories

### Relevant Flags

- `pare scenarios split --scenarios-dir TEXT`: override scenario directories used during split resolution. Defaults to `PARE_SCENARIOS_DIR` or `benchmark`.
- `pare scenarios split --limit INT`: limit the number of listed scenarios
- `pare scenarios split --json`: output as JSON
- `pare scenarios check-ids-file --scenarios-dir TEXT`: validate IDs against different scenario directories under `pare/scenarios/`
- `pare scenarios check-ids-file --json`: output validation results as JSON and exit nonzero if any IDs are missing

## Generate Scenarios

`pare scenarios generate` runs `ScenarioGeneratingAgentOrchestrator`.

### Examples

```bash
# Generate one scenario
pare scenarios generate

# Generate multiple scenarios
pare scenarios generate --num-scenarios 3

# Write intermediate artifacts to a chosen directory
pare scenarios generate --output-dir /path/to/output_dir

# Choose trajectory directory (or base dir for multiple runs)
pare scenarios generate --trajectory-dir /path/to/trajectory_dir

# Restrict allowed apps (repeatable)
pare scenarios generate --apps StatefulEmailApp --apps StatefulContactsApp

# Restrict allowed apps (comma-separated)
pare scenarios generate --apps StatefulEmailApp,StatefulContactsApp

# Resume pipeline from step 3
pare scenarios generate --resume-from-step step3

# Print prompts without LLM execution
pare scenarios generate --debug-prompts

# JSON output (compact)
pare scenarios generate --json

# JSON output with full step payloads
pare scenarios generate --json --full-json
```

### Flags

- `--output-dir PATH`: directory for intermediate step files
- `--trajectory-dir PATH`: trajectory directory or base dir for multi-run generation
- `--num-scenarios INT`: number of scenarios to generate
- `--max-iterations INT`: retry budget per step
- `--resume-from-step TEXT`: `step2`, `step3`, or `step4`
- `--resume-from-step2`: deprecated alias for `--resume-from-step step2`
- `--debug-prompts`: skip LLM calls and print prompts
- `--apps, -a TEXT`: app allowlist for prompt context
- `--json`: compact JSON result output
- `--full-json`: include large fields when used with `--json`
