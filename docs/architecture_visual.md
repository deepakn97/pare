# PAS Architecture - Visual Overview

## High-Level Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      PROACTIVE SESSION                                   │
│                    (Orchestrator/Controller)                             │
│                                                                           │
│  Methods: run_cycle() → ProactiveCycleResult                            │
│  - Requests a goal proposal from the agent                               │
│  - Surfaces proposal via runtime + Agent UI                              │
│  - Executes accepted interventions                                       │
│  - Drains remaining notifications                                        │
│  - Validates completion with OracleTracker                               │
└────┬─────────┬──────────┬───────────┬─────────────┬─────────────────────┘
     │         │          │           │             │
     │         │          │           │             │
     ▼         ▼          ▼           ▼             ▼
┌─────────┐ ┌──────┐ ┌─────────┐ ┌──────────────┐
│   ENV   │ │ USER │ │PROACTIVE│ │    ORACLE    │
│ WRAPPER │ │AGENT │ │  AGENT  │ │   TRACKER    │
└─────────┘ └──────┘ └─────────┘ └──────────────┘
```

---

## Complete System Architecture

```
┌───────────────────────────────────────────────────────────────────────────┐
│                    StateAwareEnvironmentWrapper                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │              PasNotificationSystem                                   │  │
│  │  • Converts CompletedEvent → human-readable notifications           │  │
│  │  • Posts to "system" channel                                        │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │
│  │  Stateful    │  │  Stateful    │  │  Stateful    │  │   System    │  │
│  │ ContactsApp  │  │   EmailApp   │  │ CalendarApp  │  │     App     │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────┘  │
│         │                  │                  │                │          │
│         │                  │                  │                │          │
│  ┌──────▼──────────────────▼──────────────────▼────────────────▼──────┐  │
│  │                     current_state: AppState                        │  │
│  │                     navigation_stack: [AppState, ...]              │  │
│  │                                                                     │  │
│  │  Each AppState defines available @user_tool functions              │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────┘
                               │
                               │ CompletedEvent stream
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
   ┌─────────────┐      ┌─────────────┐     ┌────────────┐
   │   User      │      │  Proactive  │     │Notification│
   │   Agent     │      │    Agent    │     │   System   │
   │  Runtime    │      │             │     │            │
   └─────────────┘      └─────────────┘     └────────────┘
```

---

## User Agent Architecture

```
                    StatefulUserAgentRuntime
                                  │
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
        ▼                         ▼                         ▼
  ┌──────────┐            ┌─────────────────┐      ┌──────────────┐
  │   ENV    │            │StatefulUserAgent│      │ Notification │
  │ WRAPPER  │            │  (ReAct-based)  │      │    System    │
  └──────────┘            └─────────────────┘      └──────────────┘
        │                         │                         │
        │                         │                         │
        │                         │                         │
    pushes                  reasons with              provides
 tool updates               ReAct cycles            notifications
to agent via               (Thought→Action)
update_tools_for_app
        │                         │                         │
        ▼                         ▼                         ▼
   ┌────────────────────────────────────────────────────────────┐
   │                    Flow:                                    │
   │                                                              │
   │  1. receive message/notification                            │
   │  2. Runtime infers active app from recent tools             │
   │  3. Agent uses ReAct reasoning to select tools              │
   │  4. PasJsonActionExecutor calls @user_tool                  │
   │  5. Wait for CompletedEvent                                 │
   │  6. Record ToolInvocation metadata                          │
   │  7. Return observation to agent for next step               │
   └────────────────────────────────────────────────────────────┘
```

---

## Proactive Agent Architecture

```
                    LLMBasedProactiveAgent
                    (implements ProactiveAgentProtocol)
                              │
                              │
        ┌─────────────────────┼──────────────────────┐
        │                     │                      │
        ▼                     ▼                      ▼
  ┌───────────┐      ┌────────────────┐     ┌──────────────┐
  │  _events  │      │ _plan_executor │     │_summary      │
  │  (deque)  │      │  (ReAct agent) │     │  _builder    │
  └───────────┘      └────────────────┘     └──────────────┘
        │                     │                      │
        │                     │                      │
   stores all            executes with           formats
   CompletedEvents       @app_tool access        human text


                    Protocol Methods Flow:
                    ─────────────────────────

      observe(event)           Every tool call → store in _events
            ↓
      propose_goal()           LLM analyzes _events → hypothesis
            ↓
      record_decision()        Log user's accept/decline
            ↓
      execute(goal, env)       _plan_executor runs autonomous plan
            ↓                  Uses @app_tool (privileged access)
      pop_summary()            Return human-readable summary
            ↓
      handoff(env)             Cleanup, return control to user
```

---

## App State Navigation (Example: Email App)

```
                         StatefulEmailApp
                                │
                                │ current_state
                                ▼
                    ┌───────────────────────┐
                    │   EmailInboxState     │
                    │                       │
                    │  Available Tools:     │
                    │  • open_email(id)     │
                    │  • compose_email()    │
                    │  • search_emails()    │
                    └───────────────────────┘
                         │              │
                    open_email()   compose_email()
                         │              │
          ┌──────────────┘              └────────────────┐
          ▼                                              ▼
┌─────────────────────┐                    ┌───────────────────────┐
│ EmailDetailState    │                    │ EmailComposeState     │
│                     │                    │                       │
│  Available Tools:   │                    │  Available Tools:     │
│  • reply()          │                    │  • send_email()       │
│  • forward(to)      │                    │  • cancel_compose()   │
│  • delete()         │                    │  • add_attachment()   │
│  • go_back() ──┐    │                    │  • go_back() ──┐      │
└─────────────────┘  │                    └─────────────────┘  │
                     │                                         │
                     └──────────┬──────────────────────────────┘
                                │
                                ▼
                      (pops navigation_stack)
                      returns to previous state

Navigation Pattern: Pushdown Automaton
• Actions push new states onto stack
• go_back() pops stack
• Universal navigation across all apps
```

---

## ProactiveSession.run_cycle() Flow

```
START run_cycle()
    │
├─► [1] Propose Goal
│       │
│       └─► agent.propose_goal()
│               → LLM analyzes _events history
│               → returns hypothesis string or None
│               → Example: "Follow up with Alice about meeting"
│
│       └─► if goal is None:
│               ├─► pending notifications handled via runtime.react_to_event(...)
│               └─► loop exits early
│
├─► [2] Confirm with User
│       │
│       ├─► Agent UI surfaces proposal notification to user proxy
│       │
│       └─► User proxy accepts/declines via `accept_proposal` / `decline_proposal`
│               → decision recorded in `proposal_history`
│
├─► [3] Execute (if accepted)
│       │
│       ├─► agent.execute(goal, env)
│       │       → _plan_executor runs with @app_tool access
│       │       → returns InterventionResult(success, notes, metadata)
│       │
│       ├─► summary = agent.pop_summary()
│       │       → human-readable explanation of what was done
│       │
│       ├─► agent.handoff(env)
│       │       → cleanup, reset state
│       │
│       └─► Completion summary logged (no additional user acknowledgement)
│
├─► [4] Drain Notifications
│       │
│       ├─► proxy.consume_notifications()
│       │       → fetches queued notifications after each decision/execution step
│       │
│       └─► runtime.react_to_event(notification)
│               → uses ReAct reasoning
│               → executes @user_tool
│               → returns reply string
│
├─► [5] Validate
    │       │
    │       └─► oracle_tracker.is_satisfied()
    │               → checks if required OracleActions matched
    │               → returns True if all oracles satisfied
    │
    └─► RETURN ProactiveCycleResult
            ├─ notifications: [(notification, reply), ...]
            ├─ goal: str
            ├─ accepted: bool
            ├─ result: InterventionResult
            └─ summary: str
```

---

## Event Flow (Complete Cycle)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  1. USER ACTION                                                          │
│     User message or notification arrives                                 │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  2. USER AGENT RUNTIME                                                   │
│     • Agent uses ReAct reasoning (Thought → Action → Observation)       │
│     • Infers active app from recent tool invocations                    │
│     • Selects tool(s) to call based on current state                    │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  3. TOOL EXECUTION                                                       │
│     @user_tool function executes                                        │
│     Example: email.open_email(id="msg_123")                             │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  4. COMPLETEDEVENT EMITTED                                               │
│     Event contains: app_name, function_name, args, result               │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌──────────────────┐
│ StateAwareEnv   │    │ Notification    │    │ ProactiveAgent   │
│ • Updates nav   │    │   System        │    │ • observe()      │
│   state         │    │ • Formats to    │    │ • Stores in      │
│ • Notifies      │    │   human text    │    │   _events deque  │
│   subscribers   │    │ • Posts to      │    │                  │
│                 │    │   "system"      │    │                  │
└─────────────────┘    └─────────────────┘    └──────────────────┘
         │                       │
         │                       │
         └───────────┬───────────┘
                     │
                     ▼
            ┌─────────────────┐
            │  User Agent     │
            │    Runtime      │
            │ • Receives      │
            │   notification  │
            │ • May react     │
            └─────────────────┘
```

---

## Tool Types Comparison

```
┌─────────────────────────────────┬─────────────────────────────────┐
│         @user_tool              │         @app_tool               │
├─────────────────────────────────┼─────────────────────────────────┤
│ Simulated user actions          │ Privileged operations           │
│                                 │                                 │
│ Limited by current AppState     │ Full access to all functions    │
│ (only tools on current screen)  │ (any app, any function)         │
│                                 │                                 │
│ Used by: User Agent Runtime     │ Used by: ProactiveAgent         │
│                                 │                                 │
│ Examples:                       │ Examples:                       │
│ • open_email(id)                │ • forward_email(id, to)         │
│ • tap_contact(name)             │ • create_event(title, time)     │
│ • type_message(text)            │ • send_message(to, content)     │
│ • click_button()                │ • update_contact(name, phone)   │
│                                 │                                 │
│ Constrained to UI capabilities  │ Direct backend access           │
└─────────────────────────────────┴─────────────────────────────────┘
```

---

## Key Interfaces (Protocols)

```
┌────────────────────────────────────────────────────────────────────────┐
│  ProactiveAgentProtocol                                                 │
├────────────────────────────────────────────────────────────────────────┤
│  • observe(event: CompletedEvent) → None                               │
│      Called for every tool execution in the system                     │
│                                                                         │
│  • propose_goal() → str | None                                         │
│      Analyze _events history, return goal hypothesis                   │
│                                                                         │
│  • record_decision(task: str, accepted: bool) → None                   │
│      Log whether user accepted/declined the proposal                   │
│                                                                         │
│  • execute(task: str, env: Environment) → InterventionResult           │
│      Run autonomous intervention with @app_tool access                 │
│                                                                         │
│  • handoff(env: Environment) → None                                    │
│      Cleanup, reset state, return control to user                      │
│                                                                         │
│  • pop_summary() → str | None                                          │
│      Return one-time human-readable summary message                    │
└────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│  UserAgentProtocol                                                      │
├────────────────────────────────────────────────────────────────────────┤
│  • init_conversation() → str                                           │
│      Initialize conversation state                                     │
│                                                                         │
│  • reply(message: str) → str                                           │
│      Process message using ReAct reasoning                             │
│                                                                         │
│  • react_to_event(message: str) → str                                  │
│      React to system notification                                      │
│                                                                         │
│  • consume_notifications() → list[str]                                 │
│      Get pending notifications from system                             │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Oracle Validation System

```
                         OracleTracker
                              │
                              │
                    ┌─────────┴─────────┐
                    │                   │
                    ▼                   ▼
          oracle_actions: list    matched: set
                    │                   │
                    │                   │
        ┌───────────┴───────────┐       │
        ▼           ▼           ▼       │
  OracleAction OracleAction OracleAction│
  ────────────────────────────────────  │
  app_name: "email"                     │
  function_name: "forward_email"        │
  args: {                               │
    "email_id": "msg_123",              │
    "to": "alice@example.com"           │
  }                                     │
                                        │
                                        │
  When CompletedEvent arrives: ─────────┘
      ↓
  check_event(event):
      • Compare app_name
      • Compare function_name
      • Match arguments
      • If all match → add to matched set

  is_satisfied():
      • return len(matched) == len(oracle_actions)


Purpose: Ensures proactive interventions ACTUALLY complete required tasks
         Prevents demos from silently accepting partial/incorrect results
```

---

## Complete Integration Example

```
┌─────────────────────────────────────────────────────────────────────────┐
│  SCENARIO: Contact Follow-up                                            │
└─────────────────────────────────────────────────────────────────────────┘

[1] System sends notification:
    "New message from Alice: Can we reschedule our meeting?"
        ↓
[2] User Agent Runtime.consume_notifications()
    • Receives notification from PasNotificationSystem
    • Agent uses ReAct reasoning to decide actions
    • Opens messaging app, views conversation
        ↓
[3] CompletedEvent emitted → ProactiveAgent.observe()
    • Agent stores: "User opened conversation with Alice"
        ↓
[4] ProactiveSession calls agent.propose_goal()
    • LLM analyzes: "User likely needs to follow up about rescheduling"
    • Returns: "Send calendar invite for alternative meeting time"
        ↓
[5] Session prompts user for confirmation
    • "Proposed action: Send calendar invite... Proceed?"
    • User confirms: "accept"
        ↓
[6] agent.execute(goal, env)
    • _plan_executor (ReAct agent) runs with @app_tool access:
        1. calendar.view_availability()
        2. calendar.create_event(title="Meeting with Alice",
                                  time="tomorrow 2pm")
        3. calendar.send_invite(event_id, to="alice@example.com")
    • Returns: InterventionResult(success=True, notes="Created event...")
        ↓
[7] agent.pop_summary()
    • Returns: "I've created a meeting for tomorrow at 2pm and sent
                the invite to Alice."
        ↓
[8] OracleTracker.is_satisfied()
    • Checks that calendar.create_event was called with correct args
    • Checks that calendar.send_invite was called with Alice's email
    • Returns: True (all oracles matched)
        ↓
[9] ProactiveSession returns ProactiveCycleResult
    • goal: "Send calendar invite..."
    • accepted: True
    • result.success: True
    • summary: "I've created a meeting..."
```

---

## Summary: Three Workstreams

```
┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐
│   USER PROXY       │  │  PROACTIVE AGENT   │  │ SCENARIO AUTHOR    │
│   WORKSTREAM       │  │    WORKSTREAM      │  │   WORKSTREAM       │
├────────────────────┤  ├────────────────────┤  ├────────────────────┤
│                    │  │                    │  │                    │
│ Implements:        │  │ Implements:        │  │ Implements:        │
│ • StatefulUser     │  │ • LLMBased         │  │ • Scenario         │
│   Proxy            │  │   ProactiveAgent   │  │   builders         │
│ • ReAct reasoning  │  │ • observe()        │  │ • Environment      │
│ • Tool execution   │  │ • propose_goal()   │  │   setup            │
│   Maker            │  │ • execute()        │  │ • App wiring       │
│                    │  │                    │  │ • Oracle           │
│ Uses:              │  │ Uses:              │  │   definition       │
│ • @user_tool only  │  │ • @app_tool only   │  │                    │
│ • Current screen   │  │ • Full access      │  │ Uses:              │
│   tools            │  │ • ReAct executor   │  │ • All components   │
│                    │  │                    │  │ • ProactiveSession │
└────────────────────┘  └────────────────────┘  └────────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │   ProactiveSession     │
                    │   (Orchestrator)       │
                    │                        │
                    │ Coordinates all three  │
                    │ workstreams through    │
                    │ defined protocols      │
                    └────────────────────────┘
```

This architecture enables **independent development**: each workstream can work in isolation as long as they follow the protocol contracts defined in `docs/interface-guide.md`.
