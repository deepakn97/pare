# User Proxy Guide

This guide explains how the PAS user proxy is structured today and how to plug
in alternative planners while keeping the public contract stable.

## 1. Overview

`pas/user_proxy/stateful.py` exports `StatefulUserAgentProxy`, a drop-in replacement
for Meta-ARE’s default proxy. Its core responsibilities are:

1. Translate free-form messages (from the agent or system notifications) into concrete
   tool invocations.
2. Execute those tools against the current navigation state while tracking
   recent events.
3. Surface structured replies and maintain a transcript for logging/debugging.
4. Enforce turn limits to keep conversations bounded.

The proxy is planner-agnostic. Today we ship `pas/user_proxy/llm_planner.py`
which generates tool calls via the OpenAI Responses API, but you can swap in a
rule-based or human planner as long as it matches the callable signature.

## 2. Constructor

```python
class StatefulUserAgentProxy(UserProxy):
    def __init__(
        self,
        env: StateAwareEnvironmentWrapper,
        notification_system: BaseNotificationSystem,
        *,
        max_user_turns: int = 40,
        logger: logging.Logger,
        planner: PlannerCallable | None = None,
        event_timeout: float = 2.0,
    ) -> None:
        ...
```

- `env`: shared environment wrapper. Access apps via `env.get_app(...)`.
- `notification_system`: provides notifications triggered by
  `pas.system.notification` for the scenario.
- `max_user_turns`: after this many replies, `TurnLimitReached` is raised.
- `logger`: required logger instance for tracking proxy actions and decisions.
- `planner`: callable that accepts the incoming message and the proxy instance,
  then returns a list of `(app_name, method_name, args)` tuples.
- `event_timeout`: how long to wait for a matching `CompletedEvent` when a tool
  is marked as a write operation (default 2.0 seconds).

Upon construction, the proxy subscribes to the environment’s completed events
and records user-originating events in `_recent_events` for later lookups.

## 3. Notification Handling

Scenarios convert tool completions into notifications through
`pas.system.notification.PasNotificationSystem` (instantiated via
`pas.system.runtime.create_notification_system`). The proxy consumes them with:

```python
notifications = proxy.consume_notifications()
for text in notifications:
    proxy.react_to_event(text)
```

The default implementation filters out noisy meta-events (e.g. raw
conversation IDs) and logs a friendly summary (`Notification (app: messaging)`
...). These notifications feed back into the planner so the user LLM receives
the same context a human would see on a phone lock screen.

## 4. Planner Contract

`PlannerCallable` is defined as:

```python
PlannerCallable = Callable[[str, StatefulUserAgentProxy], Sequence[tuple[str, str, dict[str, object]]]]
```

The built-in `LLMUserPlanner` prepares a prompt that includes:

- Instructions + current app/view (e.g. `messaging` / `ConversationOpened`).
- The latest system notification.
- A catalog of available tools, identified as `option_1`, `option_2`, ... with
  parameter metadata.

The system instructions explicitly tell the planner to prioritise
`accept_proposal` or `decline_proposal` whenever a notification starts with
`"Proactive assistant proposal:"`. These tools are only exposed while the Agent
UI has a pending proposal, ensuring proactive prompts are resolved without
cluttering other notifications. Navigation-only actions such as
`ProactiveAgentUserInterface.go_back` are intentionally hidden so the interface
behaves like a persistent overlay. The instructions also remind the planner
that the user would rather tap than type, so `ProactiveAgentUserInterface.send_message_to_agent`
should be used sparingly and any manual reply kept brief.

It expects the LLM to return JSON of the form:

```json
{"actions": [{"tool": "option_1", "args": {"conversation_id": "..."}}]}
```

`StatefulUserAgentProxy` executes each action in order, collecting `ToolInvocation`
dataclasses that capture the name, arguments, return value, and corresponding
event (if any).

### System-level confirmations

Scenarios now ask the user to confirm proactive assistance through a dedicated
decision maker (`pas.user_proxy.decision_maker.LLMDecisionMaker`). This keeps
YES/NO prompts out of Messaging threads. The decision maker talks directly to
the user LLM and returns `True`/`False`/`None`; `ProactiveSession` records the
raw text for auditing. The user proxy itself does not send confirmation
messages anymore—it continues to focus on app navigation and tool execution.

## 5. Reply Workflow

`reply(message: str)` handles both agent prompts and direct user LLM outputs:

1. Guard the turn limit.
2. Append the incoming message to the transcript (`role="agent"` or
   `role="system"` for notifications).
3. Call the planner to produce tool invocations. Empty plans raise
   `UserActionFailed`.
4. Execute tools, waiting for write events when required. `UserActionFailed`
   propagates immediately and does not increment the turn counter.
5. Format a short reply summarising the completed tool calls
   (`Completed: app.tool -> {...}`) and log it.
6. Append the reply to the transcript with `role="user"` and increment
   `_turns_taken`.

`react_to_event` simply marks the source as `system` but otherwise shares the
same path as `reply`.

## 6. Turn Limits and Errors

- `TurnLimitReached`: raised when the proxy has already produced
  `max_user_turns` successful replies. Scenarios should catch it and hand control
  back to the main agent.
- `UserActionFailed`: indicates the planner or execution path could not fulfil
  the request (missing tool, invalid arguments, event timeout, etc.). The caller
  decides how to recover.

## 7. Logging

Use `pas.logging_utils.get_pas_file_logger` to create dedicated loggers:

- `pas.user_proxy` – high-level transcripts (`Agent message received ...`,
  `User reply ...`).
- `pas.user_proxy.planner` – full planner prompts and LLM responses.
- `pas.events` (from `attach_event_logging`) – canonical view of all completed
  events for audit.

Running `pas/scripts/run_contacts_demo.py` prints the log locations so you can
tail them while developing new planners or scenarios.

## 8. Extending the Proxy

- Swap in an alternative planner by passing a different callable to the
  constructor. Keep the same return structure so execution stays intact.
- Override `_format_reply` if you prefer structured JSON or richer
  explanations.
- Adjust `consume_notifications` if your notification format differs from the default
  `Notification (app: ...)` style.

With these pieces in place, the user proxy will interoperate with the proactive
session loop, logging utilities, and Meta-ARE agent interface without further
changes.
