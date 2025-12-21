# Fix: Environmental Noise Notifications Timing

## Issue Summary

**GitHub Issue**: [#57 - Environmental noise notifications always arrive after actual notification](https://github.com/deepakn97/pas/issues/57)

**Problem**: When environmental noise is enabled via `EnvEventsConfig`, noise notifications always arrive after the actual notification. This happens because:
1. `scenario.events[0]` (the actual notification) is captured as the `start_event`
2. All environmental noise events `depends_on(start_event, delay_seconds=tick)` with positive delays
3. Therefore, noise always arrives AFTER the actual notification

**Impact**: This makes the benchmark artificially easy since agents can "cheat" by prioritizing the first notification, which is always the important one.

**Expected Behavior**: Noise events should be interleaved with the actual notification - some arriving before, some after. The agent should need to analyze notification content to determine which one is actionable.

## Root Cause Analysis

### Current Implementation

In `pas/scenarios/utils/scenario_expander.py:98`:

```python
d_events["start_event"] = scenario.events[0]  # Captures actual notification
```

Then all noise events are scheduled relative to this:

```python
# Email events (line 241)
.depends_on(d_events["start_event"], delay_seconds=tick)

# Messaging events (lines 199-200, 203-205)
d_events[...].depends_on(d_events["start_event"], delay_seconds=tick)
```

Since `tick` values are generated from exponential distribution (Poisson process) and are always positive, all noise events are scheduled AFTER the actual notification arrives.

### How Meta-ARE Event Dependencies Work

From `meta-are/are/simulation/types.py:384-405`:

```python
def depends_on(
    self,
    events: "AbstractEvent | list[AbstractEvent] | None" = None,
    delay_seconds: float = 0,
):
    """
    If events is None, the event is scheduled relative to scenario start time.
    If events is provided, the event is scheduled after those events complete.
    """
    self.event_relative_time = delay_seconds
    if events is None or (type(events) is list and len(events) == 0):
        return self  # Event scheduled at t=delay_seconds from scenario start
    # ... rest handles dependencies
```

**Key insight**: `.depends_on(None, delay_seconds=X)` schedules an event at time `X` from scenario start, independent of any other events.

## Proposed Solution

### Approach: Schedule Noise Events from Scenario Start (t=0)

Instead of depending on `scenario.events[0]`, schedule noise events from t=0 using `.depends_on(None, delay_seconds=tick)`. This ensures:

1. Noise events are scheduled independently of actual notifications
2. Some noise may arrive before actual notifications
3. Some noise may arrive after actual notifications
4. The ordering is randomized based on the configured seed

### Implementation Details

#### Step 1: Remove start_event Dependency

**File**: `pas/scenarios/utils/scenario_expander.py`

Remove line 98:
```python
# REMOVE: d_events["start_event"] = scenario.events[0]
```

Remove line 146:
```python
# REMOVE: del d_events["start_event"]
```

#### Step 2: Update Email Event Scheduling

**File**: `pas/scenarios/utils/scenario_expander.py`, `_add_email_events` method (lines 235-241)

Change from:
```python
d_events[f"email_{email['email_id']}"] = app.create_and_add_email(
    sender=email["sender"],
    recipients=email["recipients"],
    subject=email["subject"],
    content=email["content"],
    folder_name="INBOX",
).depends_on(d_events["start_event"], delay_seconds=tick)
```

To:
```python
d_events[f"email_{email['email_id']}"] = app.create_and_add_email(
    sender=email["sender"],
    recipients=email["recipients"],
    subject=email["subject"],
    content=email["content"],
    folder_name="INBOX",
).depends_on(None, delay_seconds=tick)
```

#### Step 3: Update Messaging Event Scheduling

**File**: `pas/scenarios/utils/scenario_expander.py`, `_add_messaging_events` method (lines 193-206)

Change the first message in each conversation from:
```python
if i == 0:
    d_events[f"{app_name}_{conversation['conversation_id']}_{i}"].depends_on(
        d_events["start_event"], delay_seconds=tick
    )
```

To:
```python
if i == 0:
    d_events[f"{app_name}_{conversation['conversation_id']}_{i}"].depends_on(
        None, delay_seconds=tick
    )
```

#### Step 4: Update Shopping Events (Future Implementation)

The shopping events code is currently commented out, but when enabled, update similarly:
```python
# From:
.depends_on(d_events["start_event"], delay_seconds=tick)

# To:
.depends_on(None, delay_seconds=tick)
```

### Test Updates

**File**: `tests/scenarios/test_env_events_expander.py`

#### New Test: Verify Noise Events Can Precede Actual Notification

```python
class TestNoiseEventTiming:
    """Tests for noise event timing relative to actual notifications."""

    def test_noise_events_scheduled_from_t0(self, augmentation_data: list[dict]) -> None:
        """Noise events should be scheduled from t=0, not from first event."""
        scenario = create_mock_scenario(duration=300)

        config = EnvEventsConfig(
            num_env_events_per_minute=2.0,
            env_events_seed=42,
            weight_per_app_class=default_weight_per_app_class(),
        )
        expander = PASEnvEventsExpander(env_events_config=config)

        expander.add_env_events_to_scenario(scenario, augmentation_data)

        # Get the noise events (excluding the mock start event)
        noise_events = scenario.events[1:]  # First is mock start event

        # Verify noise events don't have dependencies (scheduled from t=0)
        for event in noise_events:
            # Events scheduled with depends_on(None) have no dependencies
            assert len(event.dependencies) == 0 or event.dependencies == []

    def test_noise_events_have_varied_timing(self, augmentation_data: list[dict]) -> None:
        """Noise events should have varied delay times from scenario start."""
        scenario = create_mock_scenario(duration=300)

        config = EnvEventsConfig(
            num_env_events_per_minute=2.0,
            env_events_seed=42,
            weight_per_app_class=default_weight_per_app_class(),
        )
        expander = PASEnvEventsExpander(env_events_config=config)

        expander.add_env_events_to_scenario(scenario, augmentation_data)

        # Get the noise events timing
        noise_events = scenario.events[1:]
        relative_times = [e.event_relative_time for e in noise_events]

        # Should have varied timing (some close to 0, some later)
        assert min(relative_times) > 0  # Poisson gives positive values
        assert max(relative_times) > min(relative_times)  # Should be varied
```

#### Update Existing Test Mock

The current mock setup at line 40:
```python
scenario.events = [Mock()]  # Start event
```

This works because we no longer reference `scenario.events[0]` as `start_event`.

## Implementation Phases

### Phase 1: Core Fix

1. **Modify `add_env_events_to_scenario`**: Remove `start_event` capture and cleanup
2. **Modify `_add_email_events`**: Use `.depends_on(None, delay_seconds=tick)`
3. **Modify `_add_messaging_events`**: Use `.depends_on(None, delay_seconds=tick)` for first message

### Phase 2: Testing

1. **Add timing tests**: Verify noise events scheduled from t=0
2. **Verify existing tests still pass**: The mock setup should still work
3. **Integration test**: Run a scenario with noise and verify interleaving

### Phase 3: Documentation

1. **Update feature request doc**: Mark timing issue as resolved
2. **Update any CLI help text**: If there are notes about timing behavior

## Edge Cases and Considerations

### 1. Empty Scenario Events

**Question**: What if `scenario.events` is empty when noise is added?

**Answer**: This is now irrelevant since we don't reference `scenario.events[0]`. Noise events are scheduled from t=0 regardless of existing events.

### 2. Negative Delay Prevention

**Question**: Can noise events have negative timing?

**Answer**: No. The Poisson process generates positive inter-arrival times:
```python
inter_arrival_times = np_rng.exponential(scale=1/average_rate, size=n_events)
ticks = np.cumsum(inter_arrival_times)  # All positive
```

### 3. Seed Reproducibility

**Question**: Does this change affect reproducibility?

**Answer**: No. The same seed still produces the same tick values. Only the dependency chain changes (from depending on `start_event` to depending on nothing/t=0).

### 4. Existing Scenario Behavior

**Question**: Does this affect scenarios without noise?

**Answer**: No. The `add_env_events_to_scenario` method is only called when `env_events_config` is set.

## Files to Modify

| File | Change Type | Description |
|------|-------------|-------------|
| `pas/scenarios/utils/scenario_expander.py` | Fix | Remove start_event, use `.depends_on(None, ...)` |
| `tests/scenarios/test_env_events_expander.py` | Test | Add timing verification tests |

## Verification

After implementation, run:

```bash
# Run existing tests
uv run pytest tests/scenarios/test_env_events_expander.py -v

# Run a scenario with noise and check trace output
uv run python -m pas.scripts.run_single_scenario \
    --scenario email_notification \
    --env-events-per-min 2.0 \
    --oracle
```

Expected output: Event trace should show noise notifications interleaved with the actual notification, not all appearing after it.

## Related Documentation

- `docs/_plans/Noise System Integration Feature Request.md` - Original feature request
- `pas/scenarios/utils/scenario_expander.py` - Implementation file
- `meta-are/are/simulation/types.py:384` - Meta-ARE `depends_on` API
