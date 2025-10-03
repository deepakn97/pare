# User Proxy Implementation Guide

This document is the *only* reference a user-proxy developer needs. When you
finish the implementation described here, the component will plug into PAS and
Meta-ARE without any additional coordination.

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
        summary_style: Literal["plain", "structured"] = "plain",
        greeting: str = "Hi! How can I help you today?",
        logger: logging.Logger | None = None,
    ) -> None: ...

    def init_conversation(self) -> str: ...
    def reply(self, message: str) -> str: ...
```

### 2.1 Constructor semantics

- `env`: shared environment. Access apps via `env.get_app("contacts")`, never
  instantiate new apps.
- `notification_system`: subscribe for `CompletedEvent` notifications.
- `max_user_turns`: number of successful replies before raising
  `TurnLimitReached`. Initialise an internal counter at 0; increment after each
  successful `reply` return.
- `summary_style`: choose output format (see §4).
- `greeting`: text returned by `init_conversation()`.
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
self._summary_style: Literal["plain", "structured"]
self._greeting: str
self._logger: logging.Logger
```

### 2.3 `init_conversation()` implementation

1. Reset `self._recent_events` and `self._turns_taken` to 0.
2. Append `{"role": "user", "content": greeting}` to the transcript.
3. Return the greeting string. **No** tool calls or environment mutation.

### 2.4 `reply(message)` workflow

1. If `self._turns_taken >= max_user_turns`, raise `TurnLimitReached`.
2. Append `{"role": "agent", "content": message}` to the transcript.
3. Call `_plan_actions(message)` → returns `list[ToolInvocation]`.
   - Minimal viable implementation: pattern-match against a handful of
     scenario phrases. E.g. “Add Eve to my contacts” → `[{name:"create_contact", ...}]`
   - If no plan is possible, raise `UserActionFailed("Unsupported request")`.
4. For each planned invocation:
   - Fetch the owning app via `env.get_app(app_name)`.
   - Ensure the required tool is in `current_state.get_available_actions()`.
   - Execute the tool and collect `CompletedEvent` from `_recent_events`. If an
     event is not received within a timeout (default 2 seconds), raise
     `UserActionFailed("Tool did not complete")`.
   - Store the `ToolInvocation` in a local list with the actual result.
5. Produce reply text using `_summarise(invocations)`.
6. Append `{"role": "user", "content": reply}` to the transcript.
7. Increment `_turns_taken` and return the reply.

### 2.5 Helper requirements

Implement at least these private methods:

```python
def _plan_actions(self, message: str) -> list[ToolInvocation]: ...
def _await_event(self, expected_tool: str, timeout: float = 2.0) -> CompletedEvent: ...
def _summarise(self, invocations: list[ToolInvocation]) -> str: ...
def _on_event(self, event: CompletedEvent) -> None: ...
```

`_await_event` pops from `self._recent_events` until it finds a matching
function name (`event.function_name() == expected_tool`).

## 3. Tool execution rules

- Always call tools on the current navigation state: `app.current_state` must
  expose the method. If not, raise `UserActionFailed` immediately; never call
  tools on inactive states.
- After each action, allow the environment transition to complete before
  executing the next action. `_await_event` provides this synchronisation.
- Do **not** catch `RuntimeError`s emitted by the app unless you intend to
  convert them into a user-facing message – let them propagate as
  `UserActionFailed`.

## 4. Reply format

### Plain style

Return a single sentence summarising the outcome:

```python
return "I added Eve to tomorrow's sync meeting."
```

### Structured style

Return a fenced block with language hint `pas` plus an optional summary line:

```
```pas
action: add_attendee
input:  email="eve@example.com"
result: success

action: send_email
input:  subject="Agenda"
result: error: smtp timeout
```
summary: Added Eve, email failed (see above).
```

When errors occur, the proxy still sends the structured block, but must add a
summary explaining what failed.

## 5. Error handling

- **`UserActionFailed`** → stop processing, do not increment turn count, let the
  caller decide whether to retry.
- **`TurnLimitReached`** → indicates the conversation is over. Scenarios should
  catch it and transition control back to the main agent.

## 6. Testing checklist

Before handing off, verify:

1. `init_conversation()` returns the greeting and leaves navigation untouched.
2. `reply()` executes planned tools in sequence and updates transcript. If you
   stub `_plan_actions` to return `[]`, it should raise `UserActionFailed`.
3. Structured replies contain one `action` block per tool.
4. When the environment emits unexpected events, `_await_event` times out and
   raises `UserActionFailed`.
5. Turn limit triggers `TurnLimitReached`.

With these rules implemented, no further context is needed to interoperate with
scenarios or proactive agents.
