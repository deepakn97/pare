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
| `pas/user_proxy/agent.py`                    | Stateful proxy plus `UserActionFailed`/`TurnLimitReached` guards |
| `pas/proactive/agent.py`                        | Reference proactive agent + `ProactiveAgentProtocol`  |
| `pas/oracles.py`                                | Oracle matching and tracking helpers                  |
| `pas/scenarios/base.py`                         | Utilities to assemble PAS runtime stacks              |

Teams may add additional files, but the interfaces exposed here must remain unchanged.

## 3. User Agent Contract

```python
class StatefulUserAgent(BaseAgent):
    def __init__(
        self,
        llm_engine: LLMClientProtocol | LLMEngine | Callable[..., Any],
        tools: dict[str, Tool] | None = None,
        system_prompts: dict[str, str] | None = None,
        *,
        max_iterations: int = 10,
        max_turns: int = 40,
        wait_timeout: float = 2.0,
        **kwargs: Any,
    ) -> None: ...

class StatefulUserAgentRuntime(UserProxy):
    def __init__(
        self,
        *,
        agent: StatefulUserAgent,
        notification_system: BaseNotificationSystem,
        logger: logging.Logger,
        max_user_turns: int = 40,
        event_timeout: float = 2.0,
    ) -> None: ...

    def reply(self, message: str) -> str: ...
```

### 3.1 Constructor arguments

**StatefulUserAgent:**
- `llm_engine`: LLM engine or client compatible with Meta ARE
- `tools`: Dictionary mapping tool names to tool objects (includes user_tools from apps + final_answer)
- `system_prompts`: Dictionary of system prompts (default includes ReAct prompt)
- `max_iterations`: Maximum iterations per turn (default 10)
- `max_turns`: Maximum conversation turns before runtime raises TurnLimitReached (default 40)
- `wait_timeout`: Timeout for waiting on completed events (default 2.0 seconds)
- `**kwargs`: Additional arguments passed to Meta ARE's BaseAgent

**StatefulUserAgentRuntime:**
- `agent`: The StatefulUserAgent instance
- `notification_system`: Notification system for observing environment events
- `logger`: Logger for tracking runtime operations
- `max_user_turns`: Maximum number of conversation turns before raising TurnLimitReached (default 40)
- `event_timeout`: Timeout for waiting on completed events (default 2.0 seconds)

### 3.2 Behaviour of `reply(message)`

The runtime's `reply()` method:
1. Enforces turn budget (raises `TurnLimitReached` if exceeded)
2. Infers the active app from recent tool invocations
3. Updates the agent's system context with active app information
4. Delegates to the agent's native `reply()` method
5. The agent uses ReAct reasoning to decide which tools to call
6. PasJsonActionExecutor executes tools and waits for CompletedEvents
7. Returns the final answer when the agent calls final_answer
8. Raises `TurnLimitReached` if turn limit is exceeded

The agent automatically:
- Uses only tools marked as `@user_tool` (cannot call `@app_tool`s)
- Waits for CompletedEvents after each tool call (except final_answer)
- Records tool invocations with metadata for debugging
- Prefers tapping/clicking over typing per system prompt instructions

Tool updates are pushed from the Environment to the agent via `agent.update_tools_for_app()` when state transitions occur, not pulled by the runtime on every reply.

### 3.3 Tool execution flow

Each tool call follows this flow:
1. Agent outputs: `Action: {"action": "tool_name", "action_input": {...}}`
2. PasJsonActionExecutor parses and executes the tool
3. Executor waits for CompletedEvent from environment
4. Observation is returned to agent: `"Tool succeeded: {result}"` or `"Tool failed: {error}"`
5. Agent continues reasoning based on the observation

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
2. **Instantiate components** – create `StatefulUserAgentProxy` and a `ProactiveAgentProtocol` implementation.
3. **Wire event flow** – subscribe `proactive.observe` to all events:
   ```python
   env.notification_system.subscribe(EventType.ANY, proactive.observe)
   ```
4. **Hook into scenario loop** – when `propose_goal()` returns a hypothesis, prompt the user via the proxy, call `record_decision(goal, accepted)`, and only if `accepted` is `True` continue with `execute()` / `handoff()`.
5. **Pass user proxy to `AgentUserInterface`** – this is still the only object Meta-ARE touches.

### 5.1 Constructor example

```python
# Build user agent
llm_client = build_llm_client(model_name="gpt-4")
user_tools = {}  # Collect from apps
for app in env.apps.values():
    user_tools.update(app.get_user_tools())
user_tools["final_answer"] = FinalAnswerTool()

user_agent = StatefulUserAgent(
    llm_engine=llm_client,
    tools=user_tools,
    max_turns=40,
)

logger = logging.getLogger("pas.user_proxy")
runtime = StatefulUserAgentRuntime(
    agent=user_agent,
    notification_system=env.notification_system,
    logger=logger,
    max_user_turns=40,
)

# Build proactive agent
proactive = LLMBasedProactiveAgent()  # see docs/proactive_agent_guide.md for constructor details
```

### 5.2 Error handling

- If `TurnLimitReached` is raised from the runtime, the scenario should conclude the conversation gracefully.
- If `InvalidActionAgentError` is raised by Meta ARE, this indicates malformed LLM output; log it and potentially retry.
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
from pas.environment import StateAwareEnvironmentWrapper
from pas.user_proxy.agent import StatefulUserAgent, StatefulUserAgentRuntime
from pas.proactive.litellm_client import build_llm_client
from are.simulation.agents.default_agent.default_tools import FinalAnswerTool

# Setup environment
env = StateAwareEnvironmentWrapper()
env.register_apps([StatefulContactsApp(name="contacts"), StatefulEmailApp(name="email")])

# Build user agent
llm_client = build_llm_client(model_name="gpt-4")
user_tools = {}
for app in env.apps.values():
    user_tools.update(app.get_user_tools())
user_tools["final_answer"] = FinalAnswerTool()

user_agent = StatefulUserAgent(
    llm_engine=llm_client,
    tools=user_tools,
    max_turns=40,
)

logger = logging.getLogger("pas.user_proxy")
runtime = StatefulUserAgentRuntime(
    agent=user_agent,
    notification_system=env.notification_system,
    logger=logger,
    max_user_turns=40,
)

# Build proactive agent
proactive = LLMBasedProactiveAgent(llm=llm_client, system_prompt="...")

# Wire event observation
def on_event(event: CompletedEvent) -> None:
    proactive.observe(event)

env.notification_system.subscribe(EventType.ANY, on_event)

# Run conversation
response = runtime.reply("Add contact John Doe with email john@example.com")

# Proactive intervention flow
if (goal := proactive.propose_goal()):
    decision_response = runtime.reply(f"Proactive assistant proposal: {goal}")
    # Parse decision from response...
    accepted = parse_user_decision(decision_response)
    proactive.record_decision(goal, accepted)
    if accepted:
        proactive.execute(goal, env)
        proactive.handoff(env)
```

This example shows how the ReAct agent integrates with the proactive flow.

## 7. Extensibility Guidelines

- New summary styles must be added behind a feature flag and documented here before adoption.
- Additional proactive agent hooks (e.g. `reset`) require consensus from all teams – update the protocol and document the migration path.
- Scenario authors may provide richer metadata (e.g. JSON traces), but the user proxy and proactive agent APIs remain unchanged.

By adhering to this guide, each workstream can work in complete isolation: once the constructor signatures and reply formats are honoured, no further cross-team coordination is required.
