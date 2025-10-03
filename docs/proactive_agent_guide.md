# Proactive Agent Implementation Guide

This document is self-contained. Implement everything described here and your
proactive agent will plug into PAS scenarios without additional knowledge.

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
class GoalHypothesis:
    summary: str
    confidence: float
    supporting_events: list[CompletedEvent]
    required_tools: list[str]

@dataclass(slots=True)
class InterventionResult:
    success: bool
    notes: str

class ProactiveInterventionError(RuntimeError):
    """Raised when an autonomous intervention fails."""

class ProactiveAgentProtocol(Protocol):
    def observe(self, event: CompletedEvent) -> None: ...
    def propose_goal(self) -> GoalHypothesis | None: ...
    def confirm_goal(self, proxy: UserProxy) -> bool: ...
    def execute(self, goal: GoalHypothesis, env: StateAwareEnvironmentWrapper) -> InterventionResult: ...
    def handoff(self, env: StateAwareEnvironmentWrapper) -> None: ...
```

Your concrete implementation (e.g. `RuleBasedProactiveAgent`) must satisfy this
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

- Analyse accumulated events and return the next actionable `GoalHypothesis`, or
  `None` if no confident goal exists.
- `summary`: plain-language description (“Add Eve to tomorrow’s sync”).
- `confidence`: float 0.0–1.0. Scenarios may filter based on threshold.
- `supporting_events`: subset of observed events that justify the hypothesis.
- `required_tools`: list of `@app_tool` names you expect to use during
  execution. This allows logging and future capability checks.

Minimal rule-based implementation can look for simple triggers (e.g. “user added
attendee manually” → propose follow-up email).

## 5. Confirmation (`confirm_goal`)

- Invoked only after the scenario receives explicit user consent (e.g. the user
  replied “yes”). The method gives your agent a final chance to decline.
- You receive the `UserProxy` instance; you may send clarification messages via
  `proxy.reply(...)` using a canned string (“Just to confirm…”). Avoid calling
  user tools; keep the interaction minimal.
- Return `True` to proceed, `False` to abort.

## 6. Execution (`execute`)

- Called with the confirmed `GoalHypothesis`.
- Perform intervention strictly via `@app_tool`s. Example:

  ```python
  def execute(self, goal: GoalHypothesis, env: StateAwareEnvironmentWrapper) -> InterventionResult:
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
class RuleBasedProactiveAgent(ProactiveAgentProtocol):
    def __init__(self) -> None:
        self._events: deque[CompletedEvent] = deque()
        self._pending_summary: str | None = None

    def observe(self, event: CompletedEvent) -> None:
        if len(self._events) > 200:
            self._events.popleft()
        self._events.append(event)

    def propose_goal(self) -> GoalHypothesis | None:
        # naive example: if user recently added a contact, propose sending an email
        for event in reversed(self._events):
            if event.function_name() == "create_contact":
                return GoalHypothesis(
                    summary="Send a welcome email to the new contact",
                    confidence=0.7,
                    supporting_events=[event],
                    required_tools=["compose_email"],
                )
        return None

    def confirm_goal(self, proxy: UserProxy) -> bool:
        proxy.reply("I can send a welcome email now. Shall I proceed?")
        return True

    def execute(self, goal: GoalHypothesis, env: StateAwareEnvironmentWrapper) -> InterventionResult:
        email_app = cast(StatefulEmailApp, env.get_app("email"))
        try:
            email_app.compose_and_send(subject="Welcome", content="Hi!", recipients=["new@contact"])
        except Exception as exc:  # replace with concrete call
            raise ProactiveInterventionError("Email send failed") from exc
        self._pending_summary = "Sent the welcome email."
        return InterventionResult(success=True, notes="Sent welcome email")

    def handoff(self, env: StateAwareEnvironmentWrapper) -> None:
        # ensure we're back on inbox
        email_app = cast(StatefulEmailApp, env.get_app("email"))
        while email_app.navigation_stack:
            email_app.go_back()
```

Scenario authors can retrieve `agent._pending_summary` (or better, expose a
`get_summary()` method) and pass it to the user proxy for final messaging.

## 9. Testing Checklist

1. Feed a sequence of `CompletedEvent`s into `observe` and confirm
   `propose_goal()` returns the expected hypothesis.
2. Ensure `confirm_goal()` does not call user tools and always returns a bool.
3. Verify `execute()` calls only app tools and raises `ProactiveInterventionError` on failure.
4. After `handoff()`, the app navigation stack is empty (or in a known safe state).
5. Structured logging (e.g. notes in `InterventionResult`) includes the tools used.

Adhering to this guide ensures your proactive agent integrates cleanly with the
user proxy and scenario pipeline.
