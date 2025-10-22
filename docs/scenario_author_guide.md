# Scenario Authoring Guide

This guide describes how to assemble a full PAS scenario that combines
stateful apps, the LLM-backed user proxy, and the proactive agent stack. It
reflects the current implementation shipped in `pas/scenarios/contacts_followup.py`.

## 1. Architecture at a Glance

Every scenario wires the following layers together:

1. **Runtime + logging** – `pas.system.runtime.initialise_runtime` prepares the
   log files and notification system before any apps are registered.
2. **Stateful apps** – register `Stateful*App` instances with
   `StateAwareEnvironmentWrapper`. Apps surface tools that the user agent and
   proactive agent invoke.
3. **Notifications** – configure `pas.system.notification.PasNotificationSystem`
   (exposed through `create_notification_system`) so completed events become
   human readable system notifications.
4. **User agent** – `StatefulUserAgent` uses Meta ARE's ReAct reasoning to
   interact with stateful apps. The agent automatically receives state-appropriate
   tools and uses ReAct-style thought/action cycles to decide which tools to call.
5. **User agent runtime** – `StatefulUserAgentRuntime` wraps the agent and manages
   dynamic tool updates as the user navigates between apps and states.
6. **Proactive agent** – `pas.proactive.LLMBasedProactiveAgent` stores recent
   events, proposes a goal, executes the confirmed plan via
   `pas.system.proactive.build_plan_executor`, then hands control back.
7. **Session loop** – `pas.system.session.ProactiveSession` coordinates one
   “proactive cycle”: drain notifications, ask the agent to propose a goal,
   confirm with the user via the decision maker, execute, and surface a
   completion summary.

### Meta-ARE or PAS-native?

There are two equivalent ways to author a scenario:

1. **Reuse a Meta `Scenario`** – build the environment exactly as Meta does
   (events + oracles) and call
   `pas.meta_adapter.build_meta_scenario_components(...)`. The adapter converts
   the Meta apps into PAS stateful apps, registers the oracle actions, and wires
   them into the proactive session. This is the preferred approach when you can
   describe the flow with Meta’s primitives (see `ScenarioTutorial`).
2. **Author directly in PAS** – construct the apps and oracle actions yourself
   using helpers such as `build_contacts_followup_components`. This gives full
   control over initial state or bespoke PAS-only behaviour while still plugging
   into the same session/oracle machinery.

Unless a scenario needs PAS-specific seeding, start with option (1); it keeps
the code minimal and lets PAS inherit Meta’s validation tooling. Option (2) is
useful when you need extra state (e.g. our contacts follow-up demo) but should
still emit explicit `OracleAction` entries so that the proactive loop knows when
the task is truly complete.

## 2. Minimal Wiring Example

```python
from pathlib import Path

from are.simulation.notification_system import VerbosityLevel

from pas.apps.contacts.app import StatefulContactsApp
from pas.apps.email.app import StatefulEmailApp
from pas.apps.messaging.app import StatefulMessagingApp
from pas.logging_utils import get_pas_file_logger
from pas.proactive import LLMBasedProactiveAgent
from are.simulation.agents.default_agent.default_tools import FinalAnswerTool

from pas.proactive.litellm_client import build_llm_client
from pas.system import (
    ProactiveSession,
    attach_event_logging,
    build_plan_executor,
    create_environment,
    create_notification_system,
    initialise_runtime,
)
from pas.user_proxy.agent import StatefulUserAgent, StatefulUserAgentRuntime


def build_components(llm_client, user_llm_client):
    log_dir = Path("logs") / "pas"
    user_log = log_dir / "user_proxy.log"
    proactive_log = log_dir / "proactive_agent.log"
    events_log = log_dir / "events.log"

    initialise_runtime(log_paths=[user_log, proactive_log, events_log], clear_existing=True)

    notification_system = create_notification_system(verbosity=VerbosityLevel.MEDIUM)
    env = create_environment(notification_system)

    contacts = StatefulContactsApp(name="contacts")
    messaging = StatefulMessagingApp(name="messaging")
    email = StatefulEmailApp(name="email")
    env.register_apps([contacts, messaging, email])

    attach_event_logging(env, events_log)

    # Build user agent with tools from all apps
    user_tools = {}
    for app in env.apps.values():
        user_tools.update(app.get_user_tools())
    user_tools["final_answer"] = FinalAnswerTool()

    user_agent = StatefulUserAgent(
        llm_engine=user_llm_client,
        tools=user_tools,
        max_turns=25,
    )

    user_logger = get_pas_file_logger("pas.user_proxy", user_log)
    runtime = StatefulUserAgentRuntime(
        agent=user_agent,
        notification_system=notification_system,
        logger=user_logger,
        max_user_turns=25,
    )

    plan_executor_logger = get_pas_file_logger("pas.proactive.plan_executor", proactive_log)
    plan_executor = build_plan_executor(llm_client, logger=plan_executor_logger)

    agent_logger = get_pas_file_logger("pas.proactive.agent", proactive_log)
    proactive_agent = LLMBasedProactiveAgent(
        llm=llm_client,
        system_prompt="You are a proactive mobile assistant.",
        max_context_events=200,
        plan_executor=plan_executor,
        summary_builder=lambda result: result.notes,
        logger=agent_logger,
    )

    env.subscribe_to_completed_events(proactive_agent.observe)

    session_logger = get_pas_file_logger("pas.session.demo", proactive_log)
    session = ProactiveSession(
        env,
        runtime,
        proactive_agent,
        confirm_goal=lambda goal: True,
        logger=session_logger,
        oracle_actions=[],  # Add your OracleAction list here if needed
    )

    return env, runtime, proactive_agent, session
```

`build_plan_executor` currently delegates to the Meta-ARE ReAct agent. Supply
your own callable if you need tighter control over the execution flow.

The helper returns all building blocks so your scenario can initialise data,
launch an initial notification, and step through `session.run_cycle()`.

## 3. Logging & Notifications

- `initialise_runtime` clears and recreates `logs/pas/*.log` on every run when
  `clear_existing=True`. Provide absolute or relative paths depending on your
  sandbox.
- Use `get_pas_file_logger` to attach file handlers once; the helper prevents
  duplicate handlers when tests run repeatedly.
- `PasNotificationSystem` already formats Agent UI proposals and messaging
  events into human-readable notifications. Provide `extra_notifications`
  (see `build_proactive_stack`) to subscribe additional tools per app when a
  scenario needs more surface area. Notifications are posted on the "system"
  channel, matching the logs captured in `logs/pas/user_proxy.log`.

## 4. User Agent Behavior

`StatefulUserAgent` uses Meta ARE's ReAct reasoning to interact with stateful apps.
The agent automatically receives state-appropriate tools based on the current app
and navigation state.

**Key Characteristics**:
- Uses ReAct (Reasoning + Acting) cycles: Thought → Action → Observation
- Automatically waits for CompletedEvents after each tool call
- Dynamically updates available tools when navigating between apps/states
- Terminates conversations using the `final_answer` tool
- Enforces turn limits (runtime raises `TurnLimitReached` after `max_user_turns`)

The system prompt instructs the agent to:

- Think step-by-step about which tools to use
- Prefer tapping/clicking over typing when possible
- Use the `final_answer` tool when tasks are complete
- Keep messages brief when using `send_message_to_agent`

The runtime (`StatefulUserAgentRuntime`) wraps the agent and handles:
- Dynamic tool refresh when app/state changes
- Delegation to the underlying agent's `reply()` method
- State synchronization via CompletedEvent waiting

## 5. Proactive Session Loop

`ProactiveSession.run_cycle()` performs the end-to-end proactive flow:

1. Drain notification queue and let the user agent runtime respond using ReAct reasoning.
2. Call `agent.propose_goal()` once, using all events collected so far.
3. Prompt the user to accept or decline the proposed goal.
4. On approval, run `agent.execute(...)`, capture the `InterventionResult`, and
   deliver the summary back to the user.

Scenarios can run multiple cycles back-to-back if new notifications arrive.

## 6. Integrating with Meta-ARE Scenarios

After `build_components`, the canonical integration is:

```python
env, runtime, agent, session = build_components(agent_llm, user_llm)
session.run_cycle()
```

Key integration points:
- The `runtime` (StatefulUserAgentRuntime) wraps the user agent and handles ReAct reasoning
- Schedule additional cycles whenever external events enter the system
- The proactive agent observes all CompletedEvents automatically via the subscription setup

By following these steps you can port the reference contacts follow-up scenario
to new domains while reusing the user agent runtime, logging utilities, and proactive
session loop.
