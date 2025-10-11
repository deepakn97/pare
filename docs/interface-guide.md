# PAS Integration Interfaces

This guide is the single source of truth for how the three workstreams interact;
it links out to the component-specific guides when deeper implementation
details are required:
1. **User Proxy** (simulated user / UI driver)
2. **Proactive Agent** (goal inference + intervention)
3. **Scenario Authoring** (task data + wiring)

Every team implements their component independently and relies only on the API defined below.
If a behaviour is not documented here, it is considered unstable and must not be used.

> **Implementation freedom**
> The contracts describe *what* information flows between components, not *how* the decisions are made.
> Teams may plug in rules, LLMs, human operators, or any other backend without notifying others,
> provided the public APIs remain unchanged.

## 0. Scope and Terminology

- **CompletedEvent** – Meta-ARE event emitted after every tool call.
- **@user_tool** – Wrapper around actions the simulated user can perform (tap, type, etc.).
- **@app_tool** – Privileged actions available to proactive agents.
- **StateAwareEnvironmentWrapper** – PAS layer that keeps apps in sync with navigation state.

All interfaces assume Meta-ARE 2024.10.* and the PAS stateful apps checked into this repository.

## 1. Component Responsibilities

| Component        | Owns…                                                                 | Must NOT…                                               |
|------------------|---------------------------------------------------------------------------|---------------------------------------------------------|
| User Proxy       | Mapping agent messages → `@user_tool` calls; textual replies              | Call `@app_tool`s; mutate app state directly            |
| Proactive Agent  | Observing events, hypothesising goals, logging user decisions, executing interventions | Talk to `AgentUserInterface`; call user tools |
| Scenario author  | Building env & apps, wiring proxy + proactive agent, prompting the user, overall task flow | Embed business logic inside the runner |

## 2. Module Layout (default locations)

| File / Class                                   | Responsibility                                         |
|------------------------------------------------|-------------------------------------------------------|
| `pas/user_proxy/stateful.py`                    | Stateful proxy plus `UserActionFailed`/`TurnLimitReached` guards |
| `pas/proactive/agent.py`                        | Reference proactive agent + `ProactiveAgentProtocol`  |
| `pas/oracles.py`                                | Oracle matching and tracking helpers                  |
| `pas/scenarios/base.py`                         | Utilities to assemble PAS runtime stacks              |

Teams may add additional files, but the interfaces exposed here must remain unchanged.

## 3. User Proxy Contract

```python
class StatefulUserProxy(UserProxy):
    def __init__(
        self,
        env: StateAwareEnvironmentWrapper,
        notification_system: BaseNotificationSystem,
        *,
        max_user_turns: int = 40,
        logger: logging.Logger,
        planner: PlannerCallable | None = None,
        event_timeout: float = 2.0,
    ) -> None: ...

    def init_conversation(self) -> str: ...
    def reply(self, message: str) -> str: ...
```

### 3.1 Constructor arguments

- `env`: shared environment wrapper. Proxy must only interact via exposed `@user_tool`s.
- `notification_system`: subscribe to `CompletedEvent`s to update state.
- `max_user_turns`: once reached, `reply()` raises `TurnLimitReached`.
- `logger`: required logger instance for tracking proxy actions.
- `planner`: optional callable that maps messages to tool invocations. If None, proxy behavior depends on implementation.
- `event_timeout`: timeout in seconds when waiting for tool completion events (default 2.0).

### 3.2 Behaviour of `init_conversation()`

- Returns an empty string and must not trigger any tool calls.
- Scenarios may immediately call `reply()` with their preferred greeting.
### 3.3 Behaviour of `reply(message)`

1. Append agent message to transcript (used for context).
2. Plan and execute one or more `@user_tool` calls. For MVP this can be a hard-coded flow; future logic must stay internal.
3. After each tool call, wait for a `CompletedEvent` from the notification system. Use it to update navigation state (`env.get_app(...).current_state`).
4. If a tool fails, raise `UserActionFailed` with an explanatory message.
5. Compose a short textual reply summarising the outcome (success or failure).
6. Record the reply in the transcript and return it.

### 3.4 Transcript + helpers

`StatefulUserProxy` keeps an internal list of dicts with `role` (`agent` / `user`) and `content`. Optionally store the raw tool log (`List[ToolInvocation]`) for debugging or export.

## 4. Proactive Agent Contract

```python
class ProactiveAgentProtocol(Protocol):
    def observe(self, event: CompletedEvent) -> None: ...
    def propose_goal(self) -> str | None: ...
    def record_decision(self, task_guess: str, accepted: bool) -> None: ...
    def execute(self, task_guess: str, env: StateAwareEnvironmentWrapper) -> InterventionResult: ...
    def handoff(self, env: StateAwareEnvironmentWrapper) -> None: ...
```


### 4.1 Semantics

- `observe`: called on *every* completed event (user or agent). Implementation may filter internally. Must be side-effect free except for updating internal state.
- `propose_goal`: returns a human-readable task guess string (or `None` if undecided). Should not mutate the environment.
- `record_decision`: scenario calls this once the user has responded. Use it to log acceptance / rejection and tidy temporary state.
- `execute`: performs the autonomous intervention (only called when the user accepted). Receives the same task guess string.
  - May call `@app_tool`s directly or orchestrate other helpers.
  - Returns an `InterventionResult` containing success status, notes, and optional metadata.
  - Must raise `ProactiveInterventionError` on failure.
- `handoff`: restore a safe state (e.g. return to a neutral screen) and optionally enqueue a summary message for the user proxy to send later.

The proactive agent never calls user tools and never interacts with `AgentUserInterface` directly.

For full constructor options and exception semantics of
`LLMBasedProactiveAgent`/`ProactiveInterventionError`, refer to
`docs/proactive_agent_guide.md`.

## 5. Scenario Authoring Responsibilities

1. **Environment setup** – instantiate `StateAwareEnvironmentWrapper`, register stateful apps.
2. **Instantiate components** – create `StatefulUserProxy` and a `ProactiveAgentProtocol` implementation.
3. **Wire event flow** – subscribe `proactive.observe` to all events:
   ```python
   env.notification_system.subscribe(EventType.ANY, proactive.observe)
   ```
4. **Hook into scenario loop** – when `propose_goal()` returns a hypothesis, prompt the user via the proxy, call `record_decision(goal, accepted)`, and only if `accepted` is `True` continue with `execute()` / `handoff()`.
5. **Pass user proxy to `AgentUserInterface`** – this is still the only object Meta-ARE touches.

### 5.1 Constructor example

```python
proxy = StatefulUserProxy(env, env.notification_system, summary_style="structured")
proactive = LLMBasedProactiveAgent()  # see docs/proactive_agent_guide.md for constructor details
aui = AgentUserInterface(user_proxy=proxy, ...)
```

### 5.2 Error handling

- If `UserActionFailed` propagates from the proxy, the scenario should decide whether to retry or end the turn gracefully.
- If `ProactiveInterventionError` is raised, log it and hand control back to the user.

## 6. Reply Format Guide

| Style       | Example                                                      |
|-------------|--------------------------------------------------------------|
| `plain`     | `"I added Eve and sent the confirmation email."`           |
| `structured`| ```
```pas
action: add_attendee
input: email="eve@example.com"
result: success
```
``` |

Rules:
- When structured, always wrap the block in triple backticks with language hint `pas`.
- Include one `action` block per tool call in chronological order.
- Add a `summary` line outside the fence if additional context is useful.

## 7. Minimal Working Example

```python
env = StateAwareEnvironmentWrapper()
env.register_apps([StatefulContactsApp(name="contacts"), StatefulEmailApp(name="email")])

proxy = StatefulUserProxy(env, env.notification_system)
llm_client = build_llm_client()  # your LLM factory
proactive = LLMBasedProactiveAgent(llm=llm_client, system_prompt="...")

def on_event(event: CompletedEvent) -> None:
    proactive.observe(event)

env.notification_system.subscribe(EventType.ANY, on_event)

aui = AgentUserInterface(user_proxy=proxy)
scenario = Scenario(scenario_id="demo", agent_user_interface=aui, ...)

if (goal := proactive.propose_goal()):
    user_reply = proxy.reply(f"I can take care of this: {goal}. Should I proceed?")
    accepted = user_reply.strip().lower() in {"yes", "y", "sure", "please do"}
    proactive.record_decision(goal, accepted)
    if accepted:
        proactive.execute(goal, env)
        proactive.handoff(env)
```

This example leaves the planning logic unspecified; teams fill it in using the interfaces above.

## 7. Extensibility Guidelines

- New summary styles must be added behind a feature flag and documented here before adoption.
- Additional proactive agent hooks (e.g. `reset`) require consensus from all teams – update the protocol and document the migration path.
- Scenario authors may provide richer metadata (e.g. JSON traces), but the user proxy and proactive agent APIs remain unchanged.

By adhering to this guide, each workstream can work in complete isolation: once the constructor signatures and reply formats are honoured, no further cross-team coordination is required.
