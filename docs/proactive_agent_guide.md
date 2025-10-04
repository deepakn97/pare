# Proactive Agent Implementation Guide

This document is self-contained. Implement everything described here and your
proactive agent will plug into PAS scenarios without additional knowledge.

> **Backend optionality**
>
> The protocol below does not constrain the implementation strategy. An agent
> may be purely rule-based, call into a hosted LLM, use a distilled model, or a
> mix of all three. As long as the public methods honour their contracts, the
> surrounding systems remain oblivious to the underlying AI.

## 1. Role Recap

A proactive agent observes Meta-ARE events, infers user goals, seeks explicit
permission from the user proxy, performs interventions via `@app_tool`s, and
returns control to the user. It never calls user tools and never interacts with
`AgentUserInterface` directly.

## 2. Module & Class Layout

Create `pas/proactive/agent.py` with the following protocol and base class:

```python
# pas/proactive/agent.py

from dataclasses import dataclass

@dataclass(slots=True)
class InterventionResult:
    success: bool
    notes: str

class ProactiveInterventionError(RuntimeError):
    """Raised when an autonomous intervention fails."""

class ProactiveAgentProtocol(Protocol):
    def observe(self, event: CompletedEvent) -> None: ...
    def propose_goal(self) -> str | None: ...
    def record_decision(self, task_guess: str, accepted: bool) -> None: ...
    def execute(self, task_guess: str, env: StateAwareEnvironmentWrapper) -> InterventionResult: ...
    def handoff(self, env: StateAwareEnvironmentWrapper) -> None: ...
```

Your concrete implementation (e.g. `LLMBasedProactiveAgent`) must satisfy this
protocol.

## 3. Event Ingestion (`observe`)

- Called for **every** `CompletedEvent` that the environment emits. Scenario
  authors will register the callback for you.
- Implementation should filter events by relevance. Recommended approach:

  ```python
  def observe(self, event: CompletedEvent) -> None:
      if event.event_type is EventType.USER:
          self._user_events.append(event)
      elif event.event_type is EventType.AGENT:
          self._agent_events.append(event)
  ```

- Never mutate the environment inside `observe` – it should be side-effect free
  except for updating internal state.

## 4. Goal Hypothesis (`propose_goal`)

- Analyse accumulated events and return a short task guess (string), or `None` if the agent is unsure.
- The string should be human-readable and suitable for sending to the user proxy (for example: "Send a welcome email to the new contact").

Any inference backend is acceptable (rules, LLMs, compact policies). The contract ends once a string is returned; the surrounding system never inspects internal state. Minimal rule-based implementation can look for simple triggers (e.g. "user added attendee manually" → propose sending a follow-up email).

## 5. Recording the user decision (`record_decision`)

- Called exactly once for every task guess returned by `propose_goal()` after the scenario has asked the user.
- `accepted=True` means the user wants the proactive agent to proceed; `False` means the user declined.
- Use this hook to log statistics, update learning signals, or drop any temporary state tied to the guess.
- When `accepted` is `False`, the scenario will *not* call `execute()`. This marks the terminal event for that guess.

## 6. Execution (`execute`)

- Called with the confirmed task guess string.
- Perform intervention strictly via `@app_tool`s. Example:

  ```python
  def execute(self, task_guess: str, env: StateAwareEnvironmentWrapper) -> InterventionResult:
      email_app = cast(StatefulEmailApp, env.get_app("email"))
      try:
          email_app.send_email_to_user(subject="Agenda", content="...")
      except Exception as exc:
          raise ProactiveInterventionError("send_email failed") from exc
      return InterventionResult(success=True, notes="Email sent")
  ```

- Wrap failures in `ProactiveInterventionError`. Scenarios catch it and log the
  failure.
- Always return `InterventionResult` with `success`/`notes` even on partial
  success so the user proxy can craft a proper message.

## 7. Handoff (`handoff`)

- Ensure the environment is in a neutral state when giving control back.
  Typical actions:
  - Navigate back to the app’s listing screen (call `app.go_back()` if needed).
  - Record a summary message for the user proxy to surface (“I’ve sent the
    follow-up email.”). Recommended approach: store it on the agent instance and
    let the scenario fetch it.
- Do not send messages directly to the agent; rely on the user proxy to do so.

## 8. Minimal Implementation Template

```python
class LLMBasedProactiveAgent(ProactiveAgentProtocol):
    def __init__(self, llm: LLMClient, *, system_prompt: str, max_context_events: int = 200) -> None:
        self._events: deque[CompletedEvent] = deque()
        self._pending_summary: str | None = None
        self._llm = llm
        self._system_prompt = system_prompt
        self._max_context_events = max_context_events

    def observe(self, event: CompletedEvent) -> None:
        if len(self._events) >= self._max_context_events:
            self._events.popleft()
        self._events.append(event)

    def propose_goal(self) -> str | None:
        history = list(self._events)
        prompt = self._build_goal_prompt(history)
        response = self._llm.complete(prompt)
        return self._parse_goal(response)

    def record_decision(self, task_guess: str, accepted: bool) -> None:
        if not accepted:
            self._pending_summary = "User declined proactive help."

    def execute(self, task_guess: str, env: StateAwareEnvironmentWrapper) -> InterventionResult:
        intervention_plan = plan_intervention(task_guess, env)
        notes = run_plan(intervention_plan, env)
        self._pending_summary = notes.summary
        return notes

    def handoff(self, env: StateAwareEnvironmentWrapper) -> None:
        email_app = cast(StatefulEmailApp, env.get_app("email"))
        while email_app.navigation_stack:
            email_app.go_back()

    def pop_summary(self) -> str | None:
        summary = self._pending_summary
        self._pending_summary = None
        return summary
```

Always expose a documented accessor like `pop_summary()` (above) instead of
touching underscored attributes directly. Scenario authors can call this method
and pass the returned text to the user proxy for final messaging.

`LLMClient`, `_build_goal_prompt`, `_parse_goal`, `plan_intervention`, and
`run_plan` are placeholders – implement them however your stack requires
(synchronous calls, queued jobs, hybrid orchestration, etc.).

## 9. Testing Checklist

1. Feed a sequence of `CompletedEvent`s into `observe` and confirm `propose_goal()` returns the expected task string.
2. Call `record_decision(task, accepted)` with both `True` and `False` and ensure state is updated correctly (no execution should occur on `False`).
3. Verify `execute()` calls only app tools and raises `ProactiveInterventionError` on failure.
4. After `handoff()`, the app navigation stack is empty (or in a known safe state).
5. Structured logging (e.g. notes in `InterventionResult`) includes the tools used.

Adhering to this guide ensures your proactive agent integrates cleanly with the
user proxy and scenario pipeline.
