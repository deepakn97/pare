# `pare scenarios` CLI Usage

This project exposes `pare scenarios` (implemented in `pare/cli/scenarios.py`) for two primary tasks:

- list benchmark scenarios under `pare/scenarios/benchmark/`
- generate new scenarios using the multi-step generator pipeline

If `pare` is not available in your shell, run via module entrypoint:

```bash
uv run python -m pare.main scenarios --help
```

## List Scenarios

`pare scenarios list` scans benchmark modules for `@register_scenario("...")`.

### Examples

```bash
# List all benchmark scenarios
pare scenarios list

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

- `--benchmark-dir PATH`: override benchmark directory (default `pare/scenarios/benchmark`)
- `--apps, -a TEXT`: required-app filter (repeatable and/or comma-separated)
- `--id-contains TEXT`: substring match on scenario IDs
- `--limit INT`: max number of rows
- `--json`: emit JSON output

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
- `--trajectory-dir PATH`: trajectory directory (or base dir for multi-run)
- `--num-scenarios INT`: number of scenarios to generate
- `--max-iterations INT`: retry budget per step
- `--resume-from-step TEXT`: `step2`, `step3`, or `step4`
- `--resume-from-step2`: deprecated alias for `--resume-from-step step2`
- `--debug-prompts`: skip LLM calls and print prompts
- `--apps, -a TEXT`: app allowlist for prompt context
- `--json`: compact JSON result output
- `--full-json`: include large fields when used with `--json`
