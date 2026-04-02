# Contributing to PARE

## Development Setup

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager
- [Git](https://git-scm.com/)

### Getting Started

1. Fork the [PARE repo](https://github.com/deepakn97/pare) on GitHub.

2. Clone your fork locally:

```bash
git clone git@github.com:YOUR_NAME/pare.git
cd pare
```

3. Install the environment and pre-commit hooks:

```bash
make install
```

This will:
- Create a virtual environment using uv
- Install all dependencies from `pyproject.toml`
- Install pre-commit hooks for code quality checks

4. Create a branch for your work:

```bash
git checkout -b name-of-your-bugfix-or-feature
```

## Development Workflow

### Running Code Quality Checks

```bash
make check
```

This runs:
- `uv lock --locked` -- verify lock file consistency
- `pre-commit run -a` -- run all pre-commit hooks (ruff linting and formatting)
- `mypy` -- static type checking (strict mode)
- `deptry` -- check for dependency issues

### Running Tests

```bash
make test
```

Run tests with a detailed coverage report:

```bash
uv run pytest --cov --cov-report=html --cov-report=term-missing
open htmlcov/index.html  # View coverage in browser
```

### Building Documentation

```bash
make docs-test    # Build docs and check for warnings/errors
make docs-serve   # Serve docs locally at http://127.0.0.1:8000
```

## Project Structure

```
pare/
  agents/          # User and proactive agent implementations
  apps/            # 9 domain apps + 2 core system apps (FSM-based)
  annotation/      # Human evaluation pipeline
  benchmark/       # Benchmark execution and reporting
  cli/             # CLI commands (benchmark, annotation, cache)
  data_handler/    # Trace export
  scenarios/       # 143 benchmark scenarios + scenario infrastructure
  scenario_generator/  # LLM-driven scenario generation
tests/             # Unit and integration tests
docs/              # MkDocs documentation source
data/              # Benchmark splits and augmentation data
```

## Code Style Guidelines

### Python

- **Use f-strings** for all string formatting (never `%` or `.format()`)
- **Google-style docstrings** for all public functions and classes
- **Type annotations** on all function signatures -- avoid `Any`, use precise types (`object`, `TypedDict`, etc.)
- Follow existing patterns in the codebase for consistency

### Linting and Formatting

PARE uses [ruff](https://github.com/astral-sh/ruff) for linting and formatting, and [mypy](https://mypy-lang.org/) for static type checking. Both are enforced by pre-commit hooks and CI.

Key ruff settings:
- Line length: 120 characters
- Target: Python 3.12+
- Docstring convention: Google style

### Commit Messages

Follow the [Conventional Commits](https://www.conventionalcommits.org/) format with module-level scopes:

```
feat(benchmark): add oracle-only execution mode
fix(apps): handle missing navigation stack in go_back
refactor(agents): simplify observe-execute state transitions
docs(scenarios): document scenario metadata schema
```

Common scopes: `core`, `cli`, `apps`, `agents`, `benchmark`, `scenarios`, `annotation`, `cache`, `docs`.

## Pull Request Guidelines

1. The pull request should include tests for new functionality.
2. If the pull request adds functionality, update the relevant documentation.
3. Ensure all checks pass before requesting review:

```bash
make check
make test
```

4. Follow the pull request template when creating your PR.
