# `pas scenarios` CLI Usage

This project exposes `pas scenarios` (implemented in `pas/cli/scenarios.py`) for two primary tasks:

- list benchmark scenarios under `pas/scenarios/benchmark/`
- generate new scenarios using the multi-step generator pipeline

If `pas` is not available in your shell, run via module entrypoint:

```bash
uv run python -m pas.main scenarios --help
```

## List Scenarios

`pas scenarios list` scans benchmark modules for `@register_scenario("...")`.

### Examples

```bash
# List all benchmark scenarios
pas scenarios list

# Require all listed apps (repeatable flags)
pas scenarios list --apps StatefulEmailApp --apps StatefulCalendarApp

# Require all listed apps (comma-separated)
pas scenarios list --apps StatefulEmailApp,StatefulCalendarApp

# Filter by scenario_id substring
pas scenarios list --id-contains meeting

# Limit output
pas scenarios list --limit 10

# JSON output
pas scenarios list --json
```

### Flags

- `--benchmark-dir PATH`: override benchmark directory (default `pas/scenarios/benchmark`)
- `--apps, -a TEXT`: required-app filter (repeatable and/or comma-separated)
- `--id-contains TEXT`: substring match on scenario IDs
- `--limit INT`: max number of rows
- `--json`: emit JSON output

## Generate Scenarios

`pas scenarios generate` runs `ScenarioGeneratingAgentOrchestrator`.

### Examples

```bash
# Generate one scenario
pas scenarios generate

# Generate multiple scenarios
pas scenarios generate --num-scenarios 3

# Write intermediate artifacts to a chosen directory
pas scenarios generate --output-dir /path/to/output_dir

# Choose trajectory directory (or base dir for multiple runs)
pas scenarios generate --trajectory-dir /path/to/trajectory_dir

# Restrict allowed apps (repeatable)
pas scenarios generate --apps StatefulEmailApp --apps StatefulContactsApp

# Restrict allowed apps (comma-separated)
pas scenarios generate --apps StatefulEmailApp,StatefulContactsApp

# Resume pipeline from step 3
pas scenarios generate --resume-from-step step3

# Print prompts without LLM execution
pas scenarios generate --debug-prompts

# JSON output (compact)
pas scenarios generate --json

# JSON output with full step payloads
pas scenarios generate --json --full-json
```

### Flags

- `--output-dir PATH`: directory for intermediate step files
- `--trajectory-dir PATH`: trajectory directory (or base dir for multi-run)
- `--num-scenarios INT`: number of scenarios to generate
- `--max-iterations INT`: retry budget per step
- `--resume-from-step TEXT`: `step2`, `step3`, or `step4`
- `--resume-from-step2`: deprecated alias for `--resume-from-step step2`
- `--debug-prompts`: skip LLM calls and print prompts
- `--apps, -a TEXT`: app allowlist for prompt context
- `--json`: compact JSON result output
- `--full-json`: include large fields when used with `--json`
