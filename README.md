# Proactive Agent Sandbox (PARE)

[![Release](https://img.shields.io/github/v/release/deepakn97/pare)](https://img.shields.io/github/v/release/deepakn97/pare)
[![Build status](https://img.shields.io/github/actions/workflow/status/deepakn97/pare/main.yml?branch=main)](https://github.com/deepakn97/pare/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/deepakn97/pare/branch/main/graph/badge.svg)](https://codecov.io/gh/deepakn97/pare)
[![Commit activity](https://img.shields.io/github/commit-activity/m/deepakn97/pare)](https://img.shields.io/github/commit-activity/m/deepakn97/pare)
[![License](https://img.shields.io/github/license/deepakn97/pare)](https://img.shields.io/github/license/deepakn97/pare)

This repository contains code for the Proactive Goal Inference Agent project in collaboration with Apple.

PARE extends [Meta-ARE](https://github.com/deepakn97/meta-are) with state-based navigation architecture for mobile app simulation, enabling proactive agent research with context-aware action spaces.

- **Github repository**: <https://github.com/deepakn97/pare/>
- **Documentation**: <https://deepakn97.github.io/pare/>

## Setup

### Prerequisites

- Python 3.12 or higher
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

1. Clone the repository:
```bash
git clone git@github.com:deepakn97/pare.git
cd pare
```

2. Install the environment and pre-commit hooks:
```bash
make install
```

This will:
- Create a virtual environment using uv
- Install all dependencies from `pyproject.toml`
- Install pre-commit hooks for code quality checks
- Install the `pare` CLI entrypoint into the project environment

3. Verify installation:
```bash
make check  # Run linting, type checking, and dependency checks
make test   # Run test suite
```

4. Run the CLI:
```bash
uv run pare --help
uv run pare scenarios list
```

If you prefer an activated shell instead of `uv run`, use:

```bash
source .venv/bin/activate
pare --help
```

## Development

### Running Code Quality Checks

```bash
make check
```

This runs:
- `uv lock --locked` - Verify lock file consistency
- `pre-commit run -a` - Run all pre-commit hooks (ruff, mypy, etc.)
- `mypy` - Static type checking
- `deptry` - Check for dependency issues

### Running Tests

```bash
make test
```

Run tests with coverage report:
```bash
uv run pytest --cov --cov-report=html --cov-report=term-missing
open htmlcov/index.html  # View coverage in browser
```

This requires the corresponding Python interpreters to be available locally; if
they are missing, rely on the CI job instead.

For detailed contribution guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).

### Project Structure

- `pare/` -- main package containing stateful apps, environment wrapper,
  proactive agent orchestration, scenarios, and user proxy implementations
- `tests/` – unit tests covering navigation states, adapters, planners, and
  demos
- `docs/` – developer documentation and app API references

### Running The Demos

PARE includes demo scenarios that showcase the proactive agent system. All demos require a valid `OPENAI_API_KEY` in your environment (loaded automatically via `dotenv`).

#### Quick Start: Contacts Follow-up Demo

The contacts demo simulates a proactive assistant that monitors user activity and suggests helpful actions:

```bash
# Create a .env file with your API key
echo "OPENAI_API_KEY=your-key-here" > .env

# Run the contacts follow-up scenario
uv run python -m pare.scripts.run_contacts_demo
```

**What happens in this demo:**
1. The user agent receives a notification about a new message
2. The user agent interacts with the messaging app using ReAct reasoning
3. The proactive agent observes the interaction and proposes a helpful goal
4. If accepted, the proactive agent executes the task (e.g., forwarding an email)
5. Control returns to the user with a summary

#### Other Demos

```bash
# Meta ARE tutorial scenario
uv run python -m pare.scripts.run_meta_tutorial_demo

# Generic runner with custom scenario
uv run python -m pare.scripts.run_demo \
  --builder pare.scenarios.contacts_followup.build_contacts_followup_components
```

#### Output and Logs

Each demo prints:
- The initial user action (e.g., reading a message)
- The proposed proactive goal
- Execution result and summary
- Log file locations

Logs are written to `logs/pare/`:
- `user_proxy.log` – User agent ReAct reasoning and tool executions
- `proactive_agent.log` – Proactive agent observations and decisions
- `events.log` – Complete event stream for audit

All demos use oracle expectations to validate that the proactive agent correctly completes the intended task. If oracle criteria aren't met, the session raises an error rather than silently accepting a partial result.

### Running Benchmarks

PARE includes a CLI for running benchmark experiments with config sweeps, multiple runs, caching, and reporting.

#### Quick Start

```bash
# Run a single scenario
pare benchmark sweep --scenarios email_notification --observe-model gpt-5 --execute-model gpt-5

# Run benchmark with specific scenarios (comma-separated or file path)
pare benchmark sweep --scenarios scenario1,scenario2,scenario3 --observe-model gpt-5 --execute-model gpt-5 --runs 3

# Run benchmark with model sweep (zipped pairs)
pare benchmark sweep --split full \
  --observe-model gpt-5 --observe-model claude-4.5-sonnet \
  --execute-model gpt-5 --execute-model claude-4.5-sonnet \
  --runs 3

# Run benchmark with noise sweep
pare benchmark sweep --split full \
  --observe-model gpt-5 --execute-model gpt-5 \
  --tool-failure-probability 0.0 --tool-failure-probability 0.1 \
  --runs 3
```

#### CLI Options

| Flag | Description |
|------|-------------|
| `--scenarios` / `-s` | Scenario IDs: single ID, comma-separated, or file path |
| `--split` | Benchmark split: `full` or `ablation` |
| `--observe-model` / `-om` | Observe model(s) for sweep (zipped with `--execute-model`) |
| `--execute-model` / `-em` | Execute model(s) for sweep (zipped with `--observe-model`) |
| `--user-model` / `-um` | User agent model (default: `gpt-5-mini`) |
| `--max-turns` / `-mt` | Maximum turns per scenario (default: 10) |
| `--runs` / `-r` | Number of runs per scenario (default: 1) |
| `--max-concurrent` / `-c` | Max concurrent scenarios (default: CPU count) |
| `--timeout` / `-t` | Timeout per scenario in seconds |
| `--executor-type` | Executor: `sequential`, `thread`, or `process` (default: `thread`) |
| `--results-dir` | Directory for JSON result files (default: `results`) |
| `--output-dir` | Directory for trace exports (requires `--export`) |
| `--export` / `--no-export` | Export scenario traces |
| `--experiment-name` / `-n` | Name for this experiment |
| `--log-level` | Logging level: DEBUG, INFO, WARNING, ERROR |
| `--no-cache` | Disable result caching |
| `--limit` / `-l` | Limit number of scenarios to load |

See `pare benchmark sweep --help` for full details.

#### Output

Results are saved in a structured directory:

```
results/
└── {experiment}_{split}_user_{model}_mt_{turns}_umi_..._omi_..._emi_.../
    ├── obs_{model}_exec_{model}_enmi_0_es_42_tfp_0.0_result.json
    ├── obs_{model}_exec_{model}_enmi_0_es_42_tfp_0.0_report.txt
    └── combined_report.txt
```

### Platform Notes

#### macOS: Process-Based Execution

On macOS, the `--executor-type process` option may fail with `FileNotFoundError` during process spawn. This is a known issue with Python's multiprocessing 'spawn' method on macOS, where semaphore file handles cannot be properly reconstructed in child processes.

**Workaround**: Use `--executor-type thread` (the default) instead of `--executor-type process` on macOS.

### Scenario Integration Options

- **Meta-authored scenarios** – use `pare.meta_adapter.build_meta_scenario_components`
  to convert any Meta ARE `Scenario` (e.g. `ScenarioTutorial`) into the PARE
  runtime stack. The adapter preserves Meta's apps, events, and oracles, so the
  proactive session will enforce the same validation rules.
- **PARE-authored scenarios** – build directly with `pare.scenarios.contacts_followup.build_contacts_followup_components`
  (or your own builder). This path gives full control over seeding the PARE
  stateful apps while still supplying `OracleAction` entries for validation.

In practice new scenarios should follow Meta's format whenever possible: emit a
standard `Scenario` with events + oracle expectations, then reuse the adapter to
obtain a PARE environment. This keeps the codebase minimal and lets us leverage
Meta's judge ecosystem while adding PARE-specific UX (stateful navigation,
decision prompts, etc.). If a scenario truly needs bespoke PARE state, use the
contacts example as a template and provide matching oracle actions so the loop
still detects success.
