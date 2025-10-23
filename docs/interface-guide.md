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
| `pas/user_proxy/agent.py`                    | Stateful proxy plus turn-limit (`TurnLimitReached`) guards |
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
  - Set `success=False` in the returned result to indicate failure; the session will surface this as an error. Implementations may raise `ProactiveInterventionError` if execution cannot produce an `InterventionResult`.
- `handoff`: restore a safe state (e.g. return to a neutral screen) and optionally enqueue a summary message for the user proxy to send later.

The proactive agent never calls user tools and never interacts with `AgentUserInterface` directly.

For full constructor options and exception semantics of
`LLMBasedProactiveAgent`/`ProactiveInterventionError`, refer to
`docs/proactive_agent_guide.md`.

## 5. Scenario Authoring Responsibilities

1. **Environment setup** – instantiate `StateAwareEnvironmentWrapper`, register stateful apps.
2. **Instantiate user components** – create `StatefulUserAgent` and `StatefulUserAgentRuntime`, register the agent with the environment, and subscribe `runtime._on_event` so tool updates stay in sync.
3. **Expose proactive UI** – create `ProactiveAgentUserInterface(user_proxy=runtime)` and register it with the environment, ensuring the notification system subscribes to `send_proposal_to_user` so proposals surface as notifications.
4. **Build the proactive agent** – construct a `ProactiveAgentProtocol` implementation and subscribe it to completed events:
   ```python
   env.subscribe_to_completed_events(proactive.observe)
   ```
5. **Hook into the session loop** – instantiate `ProactiveSession(env, runtime, proactive, agent_ui, ...)`. The session automatically sends proposals through the Agent UI, reads the acceptance flag from `proposal_history`, and calls `record_decision` / `execute` / `handoff` accordingly.

### 5.1 Constructor example

```python
import logging

from are.simulation.agents.default_agent.default_tools import FinalAnswerTool
from pas.apps.proactive_agent_ui import ProactiveAgentUserInterface
from pas.proactive import LLMBasedProactiveAgent
from pas.proactive.litellm_client import build_llm_client
from pas.system import ProactiveSession, build_plan_executor
from pas.user_proxy.agent import StatefulUserAgent, StatefulUserAgentRuntime

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

env.register_user_agent(user_agent)
env.subscribe_to_completed_events(runtime._on_event)

agent_ui = ProactiveAgentUserInterface(user_proxy=runtime)
env.register_apps([agent_ui])

# Build proactive agent
plan_executor = build_plan_executor(llm_client, logger=logging.getLogger("pas.proactive.executor"))
proactive = LLMBasedProactiveAgent(
    llm=llm_client,
    system_prompt="You are a proactive assistant.",
    max_context_events=200,
    plan_executor=plan_executor,
    summary_builder=lambda result: result.notes,
    logger=logging.getLogger("pas.proactive.agent"),
)

env.subscribe_to_completed_events(proactive.observe)

session = ProactiveSession(
    env,
    runtime,
    proactive,
    agent_ui,
    confirm_goal=lambda goal: True,
    logger=logging.getLogger("pas.session"),
    oracle_actions=[],
)
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
import logging

from pas.apps.contacts.app import StatefulContactsApp
from pas.apps.email.app import StatefulEmailApp
from pas.apps.proactive_agent_ui import ProactiveAgentUserInterface
from pas.environment import StateAwareEnvironmentWrapper
from pas.proactive import LLMBasedProactiveAgent
from pas.proactive.litellm_client import build_llm_client
from pas.system import ProactiveSession, build_plan_executor
from pas.system.notification import PasNotificationSystem
from pas.user_proxy.agent import StatefulUserAgent, StatefulUserAgentRuntime
from are.simulation.agents.default_agent.default_tools import FinalAnswerTool
from are.simulation.types import CompletedEvent

# Setup environment
notification_system = PasNotificationSystem(
    extra_notifications={"ProactiveAgentUserInterface": ["send_proposal_to_user"]}
)
env = StateAwareEnvironmentWrapper(notification_system=notification_system)
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
    notification_system=notification_system,
    logger=logger,
    max_user_turns=40,
)

# Build proactive agent
plan_executor = build_plan_executor(llm_client, logger=logging.getLogger("pas.proactive.executor"))
proactive = LLMBasedProactiveAgent(
    llm=llm_client,
    system_prompt="You are a proactive assistant.",
    max_context_events=200,
    plan_executor=plan_executor,
    summary_builder=lambda result: result.notes,
    logger=logging.getLogger("pas.proactive.agent"),
)

# Wire event observation
def on_event(event: CompletedEvent) -> None:
    proactive.observe(event)

env.register_user_agent(user_agent)
env.subscribe_to_completed_events(runtime._on_event)
env.subscribe_to_completed_events(on_event)

agent_ui = ProactiveAgentUserInterface(user_proxy=runtime)
env.register_apps([agent_ui])

runtime.init_conversation()
# Run conversation
response = runtime.reply("Add contact John Doe with email john@example.com")

session = ProactiveSession(
    env,
    runtime,
    proactive,
    agent_ui,
    confirm_goal=lambda goal: True,
    logger=logging.getLogger("pas.session"),
    oracle_actions=[],
)

# Trigger notifications or scripted events before running a proactive cycle.
cycle = session.run_cycle()
print(cycle.goal, cycle.accepted, cycle.summary)
```

This example shows how the ReAct agent integrates with the proactive flow.

## 7. Extensibility Guidelines

- New summary styles must be added behind a feature flag and documented here before adoption.
- Additional proactive agent hooks (e.g. `reset`) require consensus from all teams – update the protocol and document the migration path.
- Scenario authors may provide richer metadata (e.g. JSON traces), but the user proxy and proactive agent APIs remain unchanged.

By adhering to this guide, each workstream can work in complete isolation: once the constructor signatures and reply formats are honoured, no further cross-team coordination is required.
