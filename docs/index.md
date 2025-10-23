# Proactive Agent Sandbox

This documentation set describes the PAS runtime used in our proactive goal
inference experiments. It builds on Meta-ARE and adds stateful navigation,
user-proxy orchestration, and proactive planning layers.

## Quick Start

### Prerequisites

- Python 3.12 or higher
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

1. Clone the repository:
```bash
git clone git@github.com:deepakn97/pas.git
cd pas
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

### Running The Demos

Two runnable scripts exercise the sandbox end-to-end. They require a valid
`OPENAI_API_KEY` (loaded automatically via `dotenv`).

```bash
uv run python -m pas.scripts.run_contacts_demo
uv run python -m pas.scripts.run_meta_tutorial_demo
# generic runner example
uv run python -m pas.scripts.run_demo \
  --builder pas.scenarios.contacts_followup.build_contacts_followup_components
```

Each script prints the proposed goal, execution summary, and the locations of
the generated logs under `logs/pas/`. Both demos rely on oracle expectations to
ensure the agent truly forwards the target email; if a run completes without
meeting the oracle criteria the session raises an error instead of silently
accepting a partial result.

## Contributing

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

### Scenario Integration Options

- **Meta-authored scenarios** – use `pas.meta_adapter.build_meta_scenario_components`
  to convert any Meta ARE `Scenario` (e.g. `ScenarioTutorial`) into the PAS
  runtime stack. The adapter preserves Meta's apps, events, and oracles, so the
  proactive session will enforce the same validation rules.
- **PAS-authored scenarios** – build directly with `pas.scenarios.contacts_followup.build_contacts_followup_components`
  (or your own builder). This path gives full control over seeding the PAS
  stateful apps while still supplying `OracleAction` entries for validation.

In practice new scenarios should follow Meta's format whenever possible: emit a
standard `Scenario` with events + oracle expectations, then reuse the adapter to
obtain a PAS environment. This keeps the codebase minimal and lets us leverage
Meta's judge ecosystem while adding PAS-specific UX (stateful navigation,
decision prompts, etc.). If a scenario truly needs bespoke PAS state, use the
contacts example as a template and provide matching oracle actions so the loop
still detects success.
