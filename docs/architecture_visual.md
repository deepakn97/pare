# PAS Architecture - Visual Overview

## High-Level Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      PROACTIVE SESSION                                   │
│                    (Orchestrator/Controller)                             │
│                                                                           │
│  Methods: run_cycle() → ProactiveCycleResult                            │
│  - Drains notifications                                                  │
│  - Gets goal proposal from agent                                         │
│  - Confirms with user via DecisionMaker                                  │
│  - Executes intervention                                                 │
│  - Validates with OracleTracker                                          │
└────┬─────────┬──────────┬───────────┬─────────────┬─────────────────────┘
     │         │          │           │             │
     │         │          │           │             │
     ▼         ▼          ▼           ▼             ▼
┌─────────┐ ┌──────┐ ┌─────────┐ ┌────────┐ ┌──────────────┐
│   ENV   │ │ USER │ │PROACTIVE│ │DECISION│ │    ORACLE    │
│ WRAPPER │ │PROXY │ │  AGENT  │ │ MAKER  │ │   TRACKER    │
└─────────┘ └──────┘ └─────────┘ └────────┘ └──────────────┘
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
   │  Stateful   │      │  Proactive  │     │Notification│
   │ UserProxy   │      │    Agent    │     │   System   │
   └─────────────┘      └─────────────┘     └────────────┘
```

---

## User Proxy Architecture

```
                           StatefulUserProxy
                                  │
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
        ▼                         ▼                         ▼
  ┌──────────┐            ┌──────────────┐         ┌──────────────┐
  │   ENV    │            │  LLMPlanner  │         │LLMDecision   │
  │ WRAPPER  │            │              │         │    Maker     │
  └──────────┘            └──────────────┘         └──────────────┘
        │                         │                         │
        │                         │                         │
        │                         │                         │
    calls                   builds tool                confirms
  @user_tool                list from                  proposals
   functions              current AppState           yes/no only
        │                         │                         │
        ▼                         ▼                         ▼
   ┌────────────────────────────────────────────────────────────┐
   │                    Flow:                                    │
   │                                                              │
   │  1. receive message/notification                            │
   │  2. LLMPlanner → inspect current AppState                   │
   │  3. build list of available tools (only current screen)     │
   │  4. LLM selects tools to call                               │
   │  5. execute @user_tool calls                                │
   │  6. CompletedEvent emitted                                  │
   │  7. update transcript                                       │
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
    ├─► [1] Handle Notifications
    │       │
    │       ├─► proxy.consume_notifications()
    │       │       → returns list of notification strings
    │       │
    │       └─► For each notification:
    │               proxy.react_to_event(notification)
    │                   → calls LLMPlanner
    │                   → executes @user_tool
    │                   → returns reply string
    │
    ├─► [2] Propose Goal
    │       │
    │       └─► agent.propose_goal()
    │               → LLM analyzes _events history
    │               → returns hypothesis string or None
    │               → Example: "Follow up with Alice about meeting"
    │
    ├─► [3] Confirm with User
    │       │
    │       ├─► Build prompt with latest notification + goal
    │       │
    │       └─► decision_maker.decide(prompt)
    │               → LLM decides: accept/decline
    │               → returns (bool, raw_response)
    │
    ├─► [4] Execute (if accepted)
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
    │       └─► prompt user to acknowledge completion
    │               → decision_maker.decide(summary)
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
│  2. STATEFUL USER PROXY                                                  │
│     • LLMPlanner inspects current AppState                              │
│     • Builds list of available @user_tool functions                     │
│     • LLM selects tool(s) to call                                       │
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
            │  StatefulUser   │
            │     Proxy       │
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
│ Used by: StatefulUserProxy      │ Used by: ProactiveAgent         │
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
│  DecisionMakerProtocol                                                  │
├────────────────────────────────────────────────────────────────────────┤
│  • decide(message: str,                                                │
│           accept_tokens: set[str],                                     │
│           decline_tokens: set[str]) → tuple[bool, str]                 │
│                                                                         │
│      System-level confirmations (yes/no)                               │
│      Returns: (decision: bool, raw_response: str)                      │
└────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│  PlannerCallable                                                        │
├────────────────────────────────────────────────────────────────────────┤
│  • __call__(message: str, context: dict) → list[ToolInvocation]       │
│                                                                         │
│      Inspects current AppState                                         │
│      Builds available tool list                                        │
│      Returns list of tools to execute                                  │
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
[2] StatefulUserProxy.consume_notifications()
    • Receives notification from PasNotificationSystem
    • LLMPlanner builds tool list from messaging app current state
    • Opens messaging app, views conversation
        ↓
[3] CompletedEvent emitted → ProactiveAgent.observe()
    • Agent stores: "User opened conversation with Alice"
        ↓
[4] ProactiveSession calls agent.propose_goal()
    • LLM analyzes: "User likely needs to follow up about rescheduling"
    • Returns: "Send calendar invite for alternative meeting time"
        ↓
[5] DecisionMaker prompts user
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
│ • LLMPlanner       │  │ • observe()        │  │ • Environment      │
│ • LLMDecision      │  │ • propose_goal()   │  │   setup            │
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
