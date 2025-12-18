# Duplicate Dynamic Logs Fix Design

**GitHub Issue**: #33 - Duplicate dynamic logs in agent history polluting LLM context
**Status**: Planning

## Summary

Dynamic context logs (`AvailableToolsLog`, `CurrentAppStateLog`, `AgentMessageLog`) are appended to agent history on every turn, causing LLM context pollution. Multiple copies of the same information accumulate in the agent's history, wasting tokens and degrading performance.

---

## Root Cause Analysis

### Problem 1: Dynamic logs accumulate

In `pas/agents/user/steps.py:67-94`, `pull_notifications_and_tools()` is called as a pre-step before EVERY agent iteration. It appends:
- `AvailableToolsLog` (lines 72-78) - tool descriptions for current state
- `CurrentAppStateLog` (lines 88-94) - current app/state info
- `AgentMessageLog` (lines 50-56) - proactive agent proposals

These log types are in `role_dict` (`agent.py:49-54`), so `build_history_from_logs()` includes ALL of them in LLM context.

**Result**: Turn 10 has 10 copies of each dynamic log type in the LLM prompt.

### Problem 2: Agent messages appear twice

Flow in `UserAgent.agent_loop()`:
1. `get_notifications()` pulls agent_messages and puts them BACK into the queue (line 256-262)
2. `build_task_from_notifications(agent_messages)` builds a task string from these messages
3. `react_agent.run(task=task, ...)` is called - this creates a `TaskLog` with the task content
4. Meanwhile, the pre-step `pull_notifications_and_tools()` pulls the SAME messages and creates `AgentMessageLog`

**Result**: Same agent message content appears as both `TaskLog` AND `AgentMessageLog`.

---

## Proposed Solution

### Approach: Filter dynamic logs in-place in pre-step functions

Filter out old dynamic logs directly in `steps.py` at the START of each pre-step function, before appending new logs. This ensures only the latest instance of each dynamic log type exists when `build_history_from_logs()` is called.

**Key insight**: The pre-step has direct access to `agent.logs` (a simple list). By filtering at the start of the pre-step, we ensure the logs list only contains the latest dynamic logs by the time `step()` calls `build_history_from_logs()`.

**Flow**:
1. Pre-step runs → first removes old dynamic logs from `agent.logs`
2. Pre-step continues → appends new dynamic logs
3. `step()` runs → `build_history_from_logs()` sees only latest dynamic logs

**Note on debugging**: Full history is preserved in the LLM prompts logged at each turn, so debugging remains possible even though we filter in place.

---

## Design Decisions

1. **`UserActionLog` handling**: Full history of `UserActionLog` should be shown to the ProactiveAgent (not filtered). User actions form a timeline the agent needs to reason about.

2. **Filtering location**: Filter directly in `steps.py` pre-step functions. No wrapper around LLM engine needed.

3. **Scope**: PAS-only fix. No changes to meta-are codebase.

---

## Implementation Plan

### Phase 1: Define Dynamic Log Types

**File**: `pas/agents/agent_log.py`

Add a constant to identify "dynamic" logs that should only show their latest instance:

```python
# Log types where only the latest instance should appear in LLM context
USER_AGENT_DYNAMIC_LOG_TYPES = {"available_tools", "current_app_state", "agent_message"}
```

Note: `UserActionLog` is intentionally NOT included - ProactiveAgent needs full user action history.

### Phase 2: Update UserAgent Pre-Step

**File**: `pas/agents/user/steps.py`

Modify `pull_notifications_and_tools()` to filter old dynamic logs at the start:

```python
from pas.agents.agent_log import USER_AGENT_DYNAMIC_LOG_TYPES

def pull_notifications_and_tools(agent: BaseAgent) -> None:
    """Pull AGENT_MESSAGE and ENVIRONMENT_NOTIFICATION from notification system."""

    # Remove old dynamic logs before appending new ones
    # This ensures only the latest instance of each dynamic log type exists
    agent.logs = [
        log for log in agent.logs
        if log.get_type() not in USER_AGENT_DYNAMIC_LOG_TYPES
    ]

    # ... rest of existing code that pulls notifications and appends new logs ...
```

### Phase 3: Fix Agent Message Duplication

**File**: `pas/agents/user/agent.py`

Modify `agent_loop()` to not include agent_messages in the task string. Let the pre-step's `AgentMessageLog` be the only source.

Current flow creates duplication:
- `task = self.build_task_from_notifications(agent_messages)` → creates TaskLog
- Pre-step pulls same messages → creates AgentMessageLog

**Fix**: Pass empty task or don't include agent_messages in task building.

### Phase 4: Update ProactiveAgent Pre-Step (if needed)

**File**: `pas/agents/proactive/steps.py`

Review `pull_proactive_agent_messages()` for similar issues. Currently it appends:
- `EnvironmentNotificationLog`
- `UserActionLog`

`UserActionLog` should accumulate (full history needed), but check if `EnvironmentNotificationLog` needs similar treatment.

### Phase 5: Testing

- Add unit tests for the filtering behavior
- Verify LLM context doesn't have duplicate dynamic logs
- Verify `UserActionLog` history is preserved for ProactiveAgent

---

## Files to Modify

| File | Action | Description |
|------|--------|-------------|
| `pas/agents/agent_log.py` | Modify | Add `USER_AGENT_DYNAMIC_LOG_TYPES` constant |
| `pas/agents/user/steps.py` | Modify | Filter old dynamic logs at start of pre-step |
| `pas/agents/user/agent.py` | Modify | Fix agent message duplication in task building |
| `pas/agents/proactive/steps.py` | Review | Check if similar filtering needed |
| `tests/agents/user/test_steps.py` | Create/Modify | Tests for filtering behavior |

---

## Implementation Order

1. [ ] Add `USER_AGENT_DYNAMIC_LOG_TYPES` constant to `agent_log.py`
2. [ ] Update `pull_notifications_and_tools()` in `user/steps.py` to filter old dynamic logs
3. [ ] Fix agent message duplication in `user/agent.py`
4. [ ] Review and update `proactive/steps.py` if needed
5. [ ] Add tests for filtering behavior
6. [ ] Manual testing with demo scenario
