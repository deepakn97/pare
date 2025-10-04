# User Proxy Implementation Guide

This guide covers everything specific to the user proxy. When the text points
at other components, follow the referenced guides for additional details; once
you satisfy the contracts here, the proxy will plug into PAS and Meta-ARE
without extra coordination.

## 1. Objective

Implement a concrete subclass of `are.simulation.agents.user_proxy.UserProxy`
that:

1. Converts free-form agent requests into Meta-ARE `@user_tool` invocations.
2. Tracks navigation state using PAS’s `StateAwareEnvironmentWrapper` so that
   tool availability is always up to date.
3. Returns textual replies in either conversational (`plain`) or structured
   format, as requested by the scenario.
4. Guarantees at-most-*N* user turns before stopping (to keep scenarios
   bounded).

The class name **must** be `StatefulUserProxy` and live in
`pas/user_proxy/stateful.py`. The module exports only this class and the
exceptions defined below.

> **Planner freedom**
>
> `_plan_actions()` (see §2.5) may use any backend — rule tables, scripted
> heuristics, large language models, or a human-in-the-loop prompt. The rest
> of the system only sees the resulting `ToolInvocation` list. Swapping the
> planner does not require changes outside this module.

## 2. Public API

```python
# pas/user_proxy/stateful.py

@dataclass(slots=True)
class ToolInvocation:
    name: str
    args: dict[str, object]
    result: object | None

class UserActionFailed(RuntimeError):
    """Raised when a user-tool action cannot be completed."""

class TurnLimitReached(RuntimeError):
    """Raised when max_user_turns is exceeded."""

class StatefulUserProxy(UserProxy):
    def __init__(
        self,
        env: StateAwareEnvironmentWrapper,
        notification_system: NotificationSystem,
        *,
        max_user_turns: int = 40,
        logger: logging.Logger | None = None,
    ) -> None: ...

    def init_conversation(self) -> str: ...
    def reply(self, message: str) -> str: ...
```

### 2.1 Constructor semantics

- `env`: shared environment. Access apps via `env.get_app("APPNAME")`, never
  instantiate new apps.
- `notification_system`: subscribe for `CompletedEvent` notifications.
- `max_user_turns`: number of successful replies before raising
  `TurnLimitReached`. Initialise an internal counter at 0; increment after each
  successful `reply` return.
- `logger`: default to `logging.getLogger(__name__)` if `None`.

The constructor must register a callback:

```python
notification_system.subscribe(EventType.ANY, self._on_event)
```

`_on_event` filters events originating from user tools (OperationType.WRITE /
EventType.USER) and appends them to `self._recent_events` so that `_plan()` can
react.

### 2.2 Internal state

Keep the following attributes:

```python
self._transcript: list[dict[str, str]]  # [{'role': 'agent'|'user', 'content': str}, ...]
self._recent_events: deque[CompletedEvent]
self._turns_taken: int
self._logger: logging.Logger
```

### 2.3 `init_conversation()` implementation

1. Reset `self._recent_events` and `self._turns_taken` to 0.
2. Return an empty string (scenarios may immediately send their own greeting via `reply`).
3. **No** tool calls or environment mutation.

### 2.4 `reply(message)` workflow

1. If `self._turns_taken >= max_user_turns`, raise `TurnLimitReached`.
2. Append `{"role": "agent", "content": message}` to the transcript.
3. Call `_plan_actions(message)` → returns `list[ToolInvocation]`.
   - The planner may use any backend (rule engine, LLM, human operator). The
     output must be a concrete list of tool invocations before execution.
   - Minimal viable implementation: pattern-match against a handful of
     scenario phrases. E.g. “Add Eve to my contacts” → `[{name:"create_contact", ...}]`
   - If no plan is possible, raise `UserActionFailed("Unsupported request")`.
4. For each planned invocation:
   - Fetch the owning app via `env.get_app(app_name)`.
   - Ensure the required tool is in `current_state.get_available_actions()`.
   - Execute the tool and collect `CompletedEvent` from `_recent_events`. If an
     event is not received within a timeout (default 2 seconds), raise
     `UserActionFailed(f"Tool did not complete within {timeout}s")` where
     `timeout` matches the configured wait.
   - Store the `ToolInvocation` in a local list with the actual result.
5. Produce a short sentence summarising the overall outcome (success or failure).
6. Append `{"role": "user", "content": reply}` to the transcript.
7. Increment `_turns_taken` and return the reply.

### 2.5 Helper requirements

Implement at least these private methods:

```python
def _plan_actions(self, message: str) -> list[ToolInvocation]: ...
def _on_event(self, event: CompletedEvent) -> None: ...
```

## 3. Tool execution rules

- Always call tools on the current navigation state: `app.current_state` must
  expose the method. If not, raise `UserActionFailed` immediately; never call
  tools on inactive states.
- After each action, allow the environment transition to complete before
  executing the next action. Wait for the corresponding `CompletedEvent` so the navigation state is up to date before issuing the next tool call.
- Do **not** catch `RuntimeError`s emitted by the app unless you intend to
  convert them into a user-facing message – let them propagate as
  `UserActionFailed`.

## 4. Error handling

- **`UserActionFailed`** → stop processing, do not increment turn count, let the
  caller decide whether to retry.
- **`TurnLimitReached`** → indicates the conversation is over. Scenarios should
  catch it and transition control back to the main agent.

## 5. Testing checklist

Before handing off, verify:

1. `init_conversation()` returns an empty string and resets internal state.
2. `reply()` executes planned tools in sequence and updates transcript. If you
   stub `_plan_actions` to return `[]`, it should raise `UserActionFailed`.
3. If the expected `CompletedEvent` never arrives, treat the tool call as failed and raise `UserActionFailed`.
4. Turn limit triggers `TurnLimitReached`.

With these rules implemented, no further context is needed to interoperate with
scenarios or proactive agents.
