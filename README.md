# Proactive Agent Sandbox (PAS)

[![Release](https://img.shields.io/github/v/release/deepakn97/proactiveGoalInference)](https://img.shields.io/github/v/release/deepakn97/proactiveGoalInference)
[![Build status](https://img.shields.io/github/actions/workflow/status/deepakn97/proactiveGoalInference/main.yml?branch=main)](https://github.com/deepakn97/proactiveGoalInference/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/deepakn97/proactiveGoalInference/branch/main/graph/badge.svg)](https://codecov.io/gh/deepakn97/proactiveGoalInference)
[![Commit activity](https://img.shields.io/github/commit-activity/m/deepakn97/proactiveGoalInference)](https://img.shields.io/github/commit-activity/m/deepakn97/proactiveGoalInference)
[![License](https://img.shields.io/github/license/deepakn97/proactiveGoalInference)](https://img.shields.io/github/license/deepakn97/proactiveGoalInference)

This repository contains code for the Proactive Goal Inference Agent project in collaboration with Apple.

PAS extends [Meta-ARE](https://github.com/deepakn97/meta-are) with state-based navigation architecture for mobile app simulation, enabling proactive agent research with context-aware action spaces.

- **Github repository**: <https://github.com/deepakn97/proactiveGoalInference/>
- **Documentation**: <https://deepakn97.github.io/proactiveGoalInference/>

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

To validate the package against every supported Python version (mirrors the CI
matrix), run:

```bash
tox
```

This requires the corresponding Python interpreters to be available locally; if
they are missing, you can rely on the CI job instead.

For detailed contribution guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).

### Project Structure

- `pas/` - Main package (Proactive Agent Sandbox)
  - `apps/core.py` - Base classes for stateful apps (AppState, StatefulApp)
  - `apps/messaging/` - Stateful messaging app implementation
  - `environment.py` - Environment wrapper for state transitions
- `tests/` - Test suite
- `docs/_plans/` - Design documentation
