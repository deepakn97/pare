# Proactive Agent Research Environment

This documentation is organized around the most common task in this repo: running and understanding the benchmark.

Most users only need four things:

1. List available scenarios.
2. Run a benchmark sweep with chosen models.
3. Inspect traces or generated scenarios.
4. Optionally annotate traces for human evaluation.

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv)

### Setup

```bash
git clone git@github.com:deepakn97/pare.git
cd pare
make install
make check
make test
```

## Most Common Commands

The installed CLI entrypoint is documented here as `pare` from `pare/main.py`.

```bash
uv run pare scenarios list
uv run pare benchmark sweep --split full --observe-model gpt-5 --execute-model gpt-5
uv run pare scenarios generate --num-scenarios 1
uv run pare annotation status
uv run pare cache status
```

## Benchmark Workflow

### 1. Inspect the benchmark

Use `pare scenarios list` to see what scenarios are available and filter by app usage.

```bash
uv run pare scenarios list --apps StatefulEmailApp
```

### 2. Run a benchmark sweep

Choose the observe and execute models, then run a split or a custom subset.

```bash
uv run pare benchmark sweep --split full --observe-model gpt-5 --execute-model gpt-5
```

### 3. Generate new scenarios if needed

Use the scenario generator when you want additional candidate tasks beyond the curated benchmark.

```bash
uv run pare scenarios generate --num-scenarios 3
```

### 4. Review traces or annotate results

After benchmark runs complete, use the annotation commands to sample decision points and launch the review UI.

```bash
uv run pare annotation sample --traces-dir traces --sample-size 200
uv run pare annotation launch --annotators-per-sample 2 --port 8000
```

## Section Guide

- **Agents**: how model roles are split and how to configure user/proactive agents for benchmark runs.
- **Apps**: what tool surfaces each app exposes and how to tell which scenarios use them.
- **Scenarios**: how to list, run, author, and generate benchmark scenarios.
- **Scripts**: helper scripts for batch runs, review set creation, and analysis.
- **Annotation**: the human evaluation workflow for exported traces.
- **Architecture**: deeper runtime details if you need implementation internals.
