# Proactive Agent Sandbox (PAS)

This repository hosts the Proactive Agent Sandbox used to explore proactive goal
inference on top of Meta-ARE. PAS layers stateful navigation, user proxies, and
proactive agents on the simulated mobile apps shipped with Meta-ARE.

PAS extends [Meta-ARE](https://github.com/deepakn97/meta-are) with state-based
navigation architecture for mobile app simulation, enabling proactive agent
research with context-aware action spaces.

## Setup

### Prerequisites

- Python 3.12 or higher
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

1. Clone the repository:
```bash
git clone <your-repository-url> scenario-setup
cd scenario-setup
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

Two runnable scripts exercise the sandbox end-to-end. They require a valid
`OPENAI_API_KEY` (loaded automatically via `dotenv`).

```bash
uv run python -m pas.scripts.run_contacts_demo
uv run python -m pas.scripts.run_meta_tutorial_demo
# generic runner example
uv run python -m pas.scripts.run_demo \
  --builder pas.scenarios.contacts_followup.build_contacts_followup_components \
  --primary-app messaging
```

Each script prints the proposed goal, execution summary, and the locations of
the generated logs under `logs/pas/`. Both demos rely on oracle expectations to
ensure the agent truly forwards the target email; if a run completes without
meeting the oracle criteria the session raises an error instead of silently
accepting a partial result.

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
