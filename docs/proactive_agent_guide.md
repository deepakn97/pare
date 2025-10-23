# Proactive Agent Guide

This document explains how to implement a PAS proactive agent that works with
the current `LLMBasedProactiveAgent` + `ProactiveSession` pipeline.

## 1. Responsibilities

A proactive agent must:

1. Observe every `CompletedEvent` emitted by the environment.
2. Produce a concise, human-readable goal hypothesis when prompted.
3. Record whether the user accepted the goal.
4. Execute the confirmed plan strictly through app tools.
5. Generate a handoff summary and reset any transient state.

`pas.proactive.agent` contains the reference implementation and the
`ProactiveAgentProtocol` contract.

### Key Types

```python
from dataclasses import dataclass

@dataclass(slots=True)
class InterventionResult:
    success: bool
    notes: str
    metadata: dict[str, object] | None = None

class ProactiveAgentProtocol(Protocol):
    def observe(self, event: CompletedEvent) -> None: ...
    def propose_goal(self) -> str | None: ...
    def record_decision(self, task_guess: str, accepted: bool) -> None: ...
    def execute(self, task_guess: str, env: StateAwareEnvironmentWrapper) -> InterventionResult: ...
    def handoff(self, env: StateAwareEnvironmentWrapper) -> None: ...
    def pop_summary(self) -> str | None: ...
```

`ProactiveSession` orchestrates when these methods are invoked (see §4).

## 2. Event Collection (`observe`)

`observe` is called for every completed tool invocation, whether triggered by
the user proxy, proactive agent, or scripted environment events. The reference
agent keeps a bounded deque:

```python
def observe(self, event: CompletedEvent) -> None:
    if len(self._events) == self._events.maxlen:
        self._events.popleft()
    self._events.append(event)
    self._logger.info("Observed event: %s.%s (%s)", ...)
```

The agent never mutates the environment inside `observe`; it only records
context for later prompts.

## 3. Proposing a Goal (`propose_goal`)

`ProactiveSession.run_cycle()` invokes `propose_goal` *before* draining queued
notifications so the agent works off the freshest environment events (including
the user's most recent tool calls) from the previous turn. Build a prompt from
that history and return a short goal string or `None`. If new notifications are
still pending, the session will route them through the user proxy after the
proposal step.

The reference implementation:

```python
prompt = self._build_goal_prompt(self._events)
response = self._llm.complete(prompt)
goal = self._parse_goal(response)
```

Guidelines:

- Prompts should include direction (`USER`, `ENV`, etc.), function names, and
  resolved arguments so the LLM can reason about context.
- Return `None` if the LLM says “none” or the response is empty; the session
  will skip execution.
- Store the last hypothesis so you can log or use it when building incremental
  prompts.

## 4. Session Loop

`ProactiveSession` (see `docs/scenario_author_guide.md`) manages the flow:

1. Call `agent.propose_goal()` before draining queued notifications so the agent evaluates the freshest event history.
2. If a goal is produced, surface it through `ProactiveAgentUserInterface` and collect the user's decision.
3. Call `agent.record_decision(goal, accepted)`.
4. On acceptance, run `agent.execute(...)`, fetch `agent.pop_summary()`, and call
   `agent.handoff(...)`.
5. After each pass (including when the agent returns `None`), drain pending notifications via the user proxy so the environment advances.

Thus the agent does **not** decide when to run; it reacts inside the session's
`run_cycle()`.

## 5. Recording User Decisions

`record_decision` is invoked for every hypothesis, whether or not it was
executed. Use it to reset cached prompts and stash a default summary if the
user declined. `ProactiveSession` pulls the acceptance flag from the
`ProactiveAgentUserInterface`, but you should still log the raw string for
traceability. In the reference agent, a declined decision sets `_pending_summary`
to “User declined proactive assistance.” so the session can surface a clear message.

## 6. Execution (`execute`)

Execution defers to the callable produced by `build_plan_executor`. A
typical pattern is:

```python
result = self._plan_executor(task_guess, env)
summary = self._summary_builder(result)
self._pending_summary = summary
return result
```

- `_plan_executor` is the callable returned by
  `pas.system.proactive.build_plan_executor`, which by default invokes the
  Meta-ARE ReAct agent over the connected environment.
- The summary builder converts an `InterventionResult` into the text you want
  to show the user.
- Always log success/failure details for debugging.

## 7. Handoff & Summary

After `execute` returns, `ProactiveSession` calls:

```python
summary = agent.pop_summary()
agent.handoff(env)
```

Use `handoff` to clear transient state (e.g. reset `_last_task`) and undo any
navigation changes needed before the user resumes control. `pop_summary`
should return a one-shot string – once consumed it must reset the stored value
to `None`.

## 8. Logging Recommendations

The reference agent logs at two levels:

- `INFO` for high-level events (observed function, proposed goal, decision,
  execution outcome).
- `DEBUG` for the raw LLM prompt and response.

Use scenario-specific loggers via `pas.logging_utils.get_pas_file_logger` so the
output lands in `logs/pas/proactive_agent.log`. This makes it easy to replay
a session from the three role-specific logs (events, user proxy, proactive).

## 9. Extending the Reference Agent

To customise behaviour:

- Swap the `_summary_builder` function to emit richer explanations or
  structured JSON.
- Replace `_plan_executor` with your own callable if you need tighter
  guardrails than the default ReAct executor.
- Override `_build_goal_prompt` if you need additional metadata such as
  partial task progress or user profile attributes.

Keep the public protocol intact and keep logging consistent so scenarios and
tests can continue to introspect agent behaviour.
