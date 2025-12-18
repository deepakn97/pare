# Trajectory Exporter Improvements Plan

## Overview

Two improvements to the trajectory exporter:
1. **Export world_logs**: Create `PASJsonScenarioExporter` that properly exports agent logs
2. **Add proactive_mode metadata**: Enrich CompletedEvent metadata with proactive agent state

---

## Change 1: PAS-Specific Exporter with world_logs

### Problem
- `JsonScenarioExporter.export_to_json()` takes `world_logs` as optional parameter (defaults to `[]`)
- `export_to_json_file()` doesn't pass `world_logs` through for "hf" format
- Result: `world_logs: []` in all exported traces

### Solution
Create `PASJsonScenarioExporter` in `pas/data_handler/exporter.py`

### Implementation Steps

#### Step 1: Create exporter module structure
```
pas/
  data_handler/
    __init__.py
    exporter.py
    models.py  # PAS-specific export models
```

#### Step 2: Implement PASJsonScenarioExporter

```python
# pas/data_handler/exporter.py

class PASJsonScenarioExporter(JsonScenarioExporter):
    """PAS-specific exporter that includes world_logs and proactive context."""

    def export_to_json_file(
        self,
        env: Environment,
        scenario: Scenario,
        ...
        proactive_context: ProactiveExportContext | None = None,  # NEW
    ) -> tuple[bool, str | None]:
        """Override to pass world_logs from env."""
        # For "hf" format, call export_to_json directly with world_logs
        json_str = self.export_to_json(
            env,
            scenario,
            ...
            world_logs=env.get_world_logs(),  # KEY FIX
            proactive_context=proactive_context,
        )
        # Handle file writing ourselves
        ...
```

#### Step 3: Update scenario_runner.py to use new exporter

```python
# In _export_pas_trace()
from pas.data_handler.exporter import PASJsonScenarioExporter

scenario_exporter = PASJsonScenarioExporter()
success, export_path = scenario_exporter.export_to_json_file(
    env,
    scenario,
    ...
    proactive_context=proactive_context,  # from agent tracking
)
```

---

## Change 2: Add proactive_mode to Event Metadata

### Problem
- `ProactiveAgentMode` (OBSERVE | AWAITING_CONFIRMATION | EXECUTE) is runtime state
- Not captured in `CompletedEvent.metadata`
- Cannot determine which sub-agent (observe vs execute) performed each action

### Solution
Track proactive context during execution, inject during export.

### Implementation Steps

#### Step 1: Create PAS export models

```python
# pas/data_handler/models.py

from pydantic import BaseModel
from are.simulation.data_handler.models import ExportedEventMetadata

class PASExportedEventMetadata(ExportedEventMetadata):
    """Extended metadata with proactive agent context."""
    proactive_mode: str | None = None  # "observe" | "awaiting_confirmation" | "execute"
    active_agent: str | None = None    # "observe_agent" | "execute_agent" | None (for USER/ENV)
    turn_number: int | None = None

class ProactiveEventContext(BaseModel):
    """Context for a single event during proactive execution."""
    event_id: str
    proactive_mode: str
    active_agent: str
    turn_number: int

class ProactiveExportContext(BaseModel):
    """Collection of proactive context for all events in a scenario run."""
    events: dict[str, ProactiveEventContext] = {}  # event_id -> context
```

#### Step 2: Track context during execution

Option A: Track in ProactiveAgent and pass to exporter
```python
# pas/agents/proactive/agent.py

class ProactiveAgent:
    def __init__(self, ...):
        ...
        self.event_context: dict[str, ProactiveEventContext] = {}
        self.current_turn: int = 0

    def _record_event_context(self, event_id: str) -> None:
        """Called after each tool execution to record context."""
        self.event_context[event_id] = ProactiveEventContext(
            event_id=event_id,
            proactive_mode=self.mode.value,
            active_agent="observe_agent" if self.mode == ProactiveAgentMode.OBSERVE else "execute_agent",
            turn_number=self.current_turn,
        )
```

Option B: Use a callback/hook in the environment (cleaner separation)
```python
# pas/environment.py

class StateAwareEnvironmentWrapper:
    def __init__(self, ...):
        ...
        self.proactive_context: dict[str, ProactiveEventContext] = {}
        self._current_proactive_mode: ProactiveAgentMode | None = None
        self._current_agent: str | None = None

    def set_proactive_context(self, mode: ProactiveAgentMode, agent: str) -> None:
        """Called by scenario_runner before each agent turn."""
        self._current_proactive_mode = mode
        self._current_agent = agent

    def add_to_log(self, events: CompletedEvent | list[CompletedEvent]) -> None:
        """Override to capture proactive context."""
        # ... existing logic ...
        # After adding event, record context
        if self._current_proactive_mode:
            self.proactive_context[event.event_id] = ProactiveEventContext(...)
```

**Recommendation**: Option B is cleaner - environment tracks context, exporter reads it.

#### Step 3: Override convert_completed_event in exporter

```python
# pas/data_handler/exporter.py

class PASJsonScenarioExporter(JsonScenarioExporter):

    def convert_completed_event(
        self,
        event: CompletedEvent,
        proactive_context: dict[str, ProactiveEventContext] | None = None,
    ) -> ExportedCompletedEvent:
        """Override to inject proactive metadata."""
        base_exported = super().convert_completed_event(event)

        # Enrich with proactive context if available
        if proactive_context and event.event_id in proactive_context:
            ctx = proactive_context[event.event_id]
            base_exported.metadata = PASExportedEventMetadata(
                **base_exported.metadata.model_dump(),
                proactive_mode=ctx.proactive_mode,
                active_agent=ctx.active_agent,
                turn_number=ctx.turn_number,
            )

        return base_exported
```

#### Step 4: Update _get_trace to use enriched conversion

```python
# pas/data_handler/exporter.py

def _get_trace(self, ..., proactive_context=None) -> ExportedTraceBase:
    # ... existing logic ...

    completed_events = [
        self.convert_completed_event(event, proactive_context)
        for event in env.event_log.list_view()
        if event.event_type != EventType.VALIDATION
    ]

    # ... rest of method ...
```

---

## Expected Trace Output After Changes

```json
{
  "completed_events": [
    {
      "class_name": "CompletedEvent",
      "event_type": "AGENT",
      "event_id": "AGENT-Emails.list_emails-xxx",
      "metadata": {
        "return_value": "...",
        "return_value_type": "ReturnedEmails",
        "exception": null,
        "proactive_mode": "observe",
        "active_agent": "observe_agent",
        "turn_number": 0
      }
    },
    {
      "event_type": "AGENT",
      "event_id": "AGENT-PASAgentUserInterface.send_message_to_user-xxx",
      "metadata": {
        "proactive_mode": "observe",
        "active_agent": "observe_agent",
        "turn_number": 0
      }
    },
    {
      "event_type": "USER",
      "event_id": "USER-PASAgentUserInterface.accept_proposal-xxx",
      "metadata": {
        "proactive_mode": "awaiting_confirmation",
        "active_agent": null,
        "turn_number": 1
      }
    },
    {
      "event_type": "AGENT",
      "event_id": "AGENT-Calendar.add_calendar_event-xxx",
      "metadata": {
        "proactive_mode": "execute",
        "active_agent": "execute_agent",
        "turn_number": 1
      }
    }
  ],
  "world_logs": [
    {"type": "task", "agent_id": "observe_base_agent", ...},
    {"type": "llm_output", "agent_id": "observe_base_agent", ...},
    {"type": "tool_call", "agent_id": "observe_base_agent", ...}
  ]
}
```

---

## File Changes Summary

| File | Change |
|------|--------|
| `pas/data_handler/__init__.py` | New - exports |
| `pas/data_handler/exporter.py` | New - `PASJsonScenarioExporter` |
| `pas/data_handler/models.py` | New - `PASExportedEventMetadata`, `ProactiveEventContext` |
| `pas/environment.py` | Add proactive context tracking |
| `pas/scenario_runner.py` | Use new exporter, set proactive context before agent turns |

---

## Implementation Order

1. Create `pas/data_handler/` module with models
2. Implement `PASJsonScenarioExporter` with world_logs fix
3. Update `scenario_runner.py` to use new exporter (verify world_logs exports)
4. Add proactive context tracking to environment
5. Update scenario_runner to set context before each agent turn
6. Update exporter to inject proactive metadata
7. Test with existing demo scenarios
