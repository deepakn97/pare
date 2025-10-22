# Proactive Agent Sandbox (PAS)

[![Release](https://img.shields.io/github/v/release/deepakn97/pas)](https://img.shields.io/github/v/release/deepakn97/pas)
[![Build status](https://img.shields.io/github/actions/workflow/status/deepakn97/pas/main.yml?branch=main)](https://github.com/deepakn97/pas/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/deepakn97/proactiveGoalInference/branch/main/graph/badge.svg)](https://codecov.io/gh/deepakn97/pas)
[![Commit activity](https://img.shields.io/github/commit-activity/m/deepakn97/pas)](https://img.shields.io/github/commit-activity/m/deepakn97/pas)
[![License](https://img.shields.io/github/license/deepakn97/pas)](https://img.shields.io/github/license/deepakn97/pas)

This repository contains code for the Proactive Goal Inference Agent project in collaboration with Apple.

PAS extends [Meta-ARE](https://github.com/deepakn97/meta-are) with state-based navigation architecture for mobile app simulation, enabling proactive agent research with context-aware action spaces.

- **Github repository**: <https://github.com/deepakn97/pas/>
- **Documentation**: <https://deepakn97.github.io/pas/>

## Setup

### Prerequisites

- Python 3.12 or higher
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

1. Clone the repository:
```bash
git clone git@github.com:deepakn97/proactiveGoalInference.git
cd proactiveGoalInference
```

2. Install the environment and pre-commit hooks:
```bash
make install
```

This will:
- Create a virtual environment using uv
- Install all dependencies from `pyproject.toml`
- Install pre-commit hooks for code quality checks

3. Verify installation:
```bash
make check  # Run linting, type checking, and dependency checks
make test   # Run test suite
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

- `pas/` – main package containing stateful apps, environment wrapper,
  proactive agent orchestration, scenarios, and user proxy implementations
- `tests/` – unit tests covering navigation states, adapters, planners, and
  demos
- `docs/` – developer documentation and app API references

### Running The Demos

PAS includes demo scenarios that showcase the proactive agent system. All demos require a valid `OPENAI_API_KEY` in your environment (loaded automatically via `dotenv`).

#### Quick Start: Contacts Follow-up Demo

The contacts demo simulates a proactive assistant that monitors user activity and suggests helpful actions:

```bash
# Create a .env file with your API key
echo "OPENAI_API_KEY=your-key-here" > .env

# Run the contacts follow-up scenario
uv run python -m pas.scripts.run_contacts_demo
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
uv run python -m pas.scripts.run_meta_tutorial_demo

# Generic runner with custom scenario
uv run python -m pas.scripts.run_demo \
  --builder pas.scenarios.contacts_followup.build_contacts_followup_components
```

#### Output and Logs

Each demo prints:
- The initial user action (e.g., reading a message)
- The proposed proactive goal
- Execution result and summary
- Log file locations

Logs are written to `logs/pas/`:
- `user_proxy.log` – User agent ReAct reasoning and tool executions
- `proactive_agent.log` – Proactive agent observations and decisions
- `events.log` – Complete event stream for audit

All demos use oracle expectations to validate that the proactive agent correctly completes the intended task. If oracle criteria aren't met, the session raises an error rather than silently accepting a partial result.

### Scenario Integration Options

- **Meta-authored scenarios** – use `pas.meta_adapter.build_meta_scenario_components`
  to convert any Meta ARE `Scenario` (e.g. `ScenarioTutorial`) into the PAS
  runtime stack. The adapter preserves Meta’s apps, events, and oracles, so the
  proactive session will enforce the same validation rules.
- **PAS-authored scenarios** – build directly with `pas.scenarios.contacts_followup.build_contacts_followup_components`
  (or your own builder). This path gives full control over seeding the PAS
  stateful apps while still supplying `OracleAction` entries for validation.

In practice new scenarios should follow Meta’s format whenever possible: emit a
standard `Scenario` with events + oracle expectations, then reuse the adapter to
obtain a PAS environment. This keeps the codebase minimal and lets us leverage
Meta’s judge ecosystem while adding PAS-specific UX (stateful navigation,
decision prompts, etc.). If a scenario truly needs bespoke PAS state, use the
contacts example as a template and provide matching oracle actions so the loop
still detects success.
