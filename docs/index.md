# Proactive Agent Research Environment

This documentation covers the current PARE architecture for:

- `pare/agents` (user/proactive agent system)
- `pare/apps` (stateful mobile app abstractions)
- `pare/scenarios` (benchmark scenarios + scenario generator)
- `scripts` (experiment and analysis utilities)
- `pare/annotation` (human evaluation pipeline)

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

## Core CLI Entrypoints

PARE exposes a unified CLI through the `pare` command from `pare/main.py`:

```bash
uv run pare scenarios list
uv run pare scenarios generate --num-scenarios 1
uv run pare benchmark sweep --split full --observe-model gpt-5 --execute-model gpt-5
uv run pare annotation status
uv run pare cache status
```

## Documentation Map

- **Architecture**: system overview, runtime spine, and DEC-POMDP framing.
- **Agents**: architecture and APIs for user/proactive agent construction.
- **Apps**: stateful app model and app-specific tool surfaces.
- **Scenarios**: benchmark catalog and generation pipeline.
- **Scripts**: operational wrappers for experiments and analysis.
- **Annotation**: human review workflow and agreement metrics.
