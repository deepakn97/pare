# Scenario Authoring Guide

This guide reflects the current PARE scenario stack under `pare/scenarios`.

## Authoring Model

Scenarios are class-based definitions extending `PAREScenario`:

- Base class: `pare.scenarios.scenario.PAREScenario`
- Registration: `pare.scenarios.utils.registry.register_scenario`
- Discovery: `pare.scenarios.registration`

In the current stack, scenario authors normally implement:

- `init_and_populate_apps(...)` for app initialization and seeded state
- `build_events_flow()` for oracle/environment event structure
- `validate(env)` for success/failure checks

You usually do **not** override `initialize()` itself; `PAREScenario.initialize()` calls `init_and_populate_apps(...)`, applies augmentation/noise config, preserves initial app state, and then calls `build_events_flow()`.

## Minimal Structure

```python
from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment

from pare.apps import HomeScreenSystemApp, PAREAgentUserInterface, StatefulCalendarApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("example_scenario_id")
class ExampleScenario(PAREScenario):
    start_time = datetime(2025, 1, 1, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.apps = [self.agent_ui, self.system_app, self.calendar]

    def build_events_flow(self) -> None:
        self.events = []

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        return ScenarioValidationResult(success=True)
```

## Recommended Workflow

1. Add scenario file under `pare/scenarios/benchmark/`.
2. Register it with `@register_scenario("...")`.
3. Run oracle validation first:

```bash
uv run python scripts/run_scenarios.py --scenarios your_scenario_id --oracle
```

4. Run agent mode checks:

```bash
uv run pare benchmark sweep --scenarios your_scenario_id --observe-model gpt-5 --execute-model gpt-5
```

5. If needed, update scenario metadata in `pare/scenarios/scenario_metadata.json` through generation/review workflows.

## Practical Notes

- Use benchmark scenarios under `pare/scenarios/benchmark/` as the source of truth for current scenario style.
- `validate(env)` should return `ScenarioValidationResult`, typically by inspecting `env.event_log`.
- If your scenario needs app state, seed it in `init_and_populate_apps(...)` before registering `self.apps`.
- If your scenario is meant for benchmark use, keep the class self-contained and explicit about success criteria.

## Scenario Review

Use guidance in `pare/scenarios/benchmark/scenario_review_guidelines.md` for quality checks and anti-patterns.
