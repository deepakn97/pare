# Scenario Authoring Guide

This guide describes how to assemble a full PAS scenario that combines
stateful apps, the LLM-backed user proxy, and the proactive agent stack. It
reflects the current implementation shipped in `pas/scenarios/contacts_followup.py`.

## 1. Architecture at a Glance

Every scenario wires the following layers together:

1. **Runtime + logging** – `pas.system.runtime.initialise_runtime` prepares the
   log files and notification system before any apps are registered.
2. **Stateful apps** – register `Stateful*App` instances with
   `StateAwareEnvironmentWrapper`. Apps surface tools that the user proxy and
   proactive agent invoke.
3. **Notification pop-ups** – use `pas.notifications.register_popup_for_event`
   (or the decorator helper) so that completed events turn into human readable
   system pop-ups. The user proxy consumes these via
   `StatefulUserProxy.consume_notifications()`.
4. **User planner** – `pas.system.user.build_stateful_user_planner` builds an
   LLM-backed planner that enumerates per-app tools and system navigation tools
   depending on the current state.
5. **Decision maker** – `pas.user_proxy.decision_maker.LLMDecisionMaker` (or a
   custom implementation) turns system-level prompts into ACCEPT/DECLINE style
   decisions without touching app tools.
6. **Proactive agent** – `pas.proactive.LLMBasedProactiveAgent` stores recent
   events, proposes a goal, executes the confirmed plan via
   `pas.system.proactive.build_plan_executor`, then hands control back.
7. **Session loop** – `pas.system.session.ProactiveSession` coordinates one
   “proactive cycle”: drain pop-up notifications, ask the agent to propose a
   goal, confirm with the user via the decision maker, execute, and surface a
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
from typing import Sequence

from are.simulation.notification_system import VerbosityLevel
from are.simulation.validation.constants import APP_ALIAS

from pas.apps.contacts.app import StatefulContactsApp
from pas.apps.email.app import StatefulEmailApp
from pas.apps.messaging.app import StatefulMessagingApp
from pas.logging_utils import get_pas_file_logger, initialise_pas_logs
from pas.notifications import register_popup_for_event, format_incoming_message
from pas.proactive import LLMBasedProactiveAgent
from pas.system import (
    ProactiveSession,
    attach_event_logging,
    build_plan_executor,
    build_stateful_user_planner,
    create_environment,
    create_notification_system,
    initialise_runtime,
)
from pas.user_proxy import StatefulUserProxy
from pas.user_proxy.decision_maker import LLMDecisionMaker


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

    # Ensure Messaging pop-ups show human text
    register_popup_for_event(
        "StatefulMessagingApp",
        "create_and_add_message",
        builder=format_incoming_message,
    )

    # Contacts is the default app when the conversation begins
    planner_logger = get_pas_file_logger("pas.user_proxy.planner", user_log)
    planner = build_stateful_user_planner(
        user_llm_client,
        apps=[contacts, messaging],
        initial_app_name="messaging",
        include_system_tools=True,
        logger=planner_logger,
    )

    decision_logger = get_pas_file_logger("pas.user_proxy.decisions", user_log)
    decision_maker = LLMDecisionMaker(user_llm_client, logger=decision_logger)

    user_logger = get_pas_file_logger("pas.user_proxy", user_log)
    user_proxy = StatefulUserProxy(
        env,
        notification_system,
        max_user_turns=25,
        logger=user_logger,
        planner=planner,
    )

    orchestrator_logger = get_pas_file_logger("pas.proactive.orchestrator", proactive_log)
    plan_executor = build_plan_executor(
        llm_client,
        (),
        system_prompt=(
            "Choose the single best tool to satisfy the confirmed goal. Every email-related argument must be a "
            "valid email address. If you cannot provide a proper address, leave optional fields empty instead of "
            "guessing."
        ),
        logger=orchestrator_logger,
    )

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
        user_proxy,
        proactive_agent,
        decision_maker=decision_maker,
        confirm_goal=lambda goal: True,
        logger=session_logger,
        oracle_actions=setup.oracle_actions,
    )

    return env, user_proxy, proactive_agent, decision_maker, session
```

The helper returns all building blocks so your scenario can initialise data,
launch an initial notification, and step through `session.run_cycle()`.

## 3. Logging & Notifications

- `initialise_runtime` clears and recreates `logs/pas/*.log` on every run when
  `clear_existing=True`. Provide absolute or relative paths depending on your
  sandbox.
- Use `get_pas_file_logger` to attach file handlers once; the helper prevents
  duplicate handlers when tests run repeatedly.
- Convert app events into pop-ups with `register_popup_for_event` or
  `register_popup`. Builders receive a `CompletedEvent` and return the text that
  the user LLM sees (for example, `format_incoming_message`). By default pop-ups
  are posted on the "system" channel, matching the logs produced in
  `logs/pas/user_proxy.log`.

## 4. User Planner Expectations

`build_stateful_user_planner` dynamically inspects the current app state and
exposes only the tools that are presently valid. The planner prompt contains:

- Current app + view (derived from the active state's class name).
- Most recent pop-up text (system notification).
- Option IDs (`option_1`, `option_2`, …) mapped to concrete
  `app_name.method_name` pairs plus parameter descriptions.

The planner must be called for every agent/user message as well as for pop-up
reactions (`StatefulUserProxy.react_to_event`). Planner outputs are JSON-encoded
tool invocations that the proxy executes in order.

## 5. Proactive Session Loop

`ProactiveSession.run_cycle()` performs the end-to-end proactive flow:

1. Drain notification queue (`StatefulUserProxy.consume_notifications()`)
   and let the user proxy respond.
2. Call `agent.propose_goal()` once, using all events collected so far.
3. Prompt the user via the messaging app to accept or decline.
4. On approval, run `agent.execute(...)`, capture the `InterventionResult`, and
   deliver the summary back to the user.

Scenarios can run multiple cycles back-to-back if new notifications arrive.

## 6. Integrating with Meta-ARE Scenarios

- After `build_components`, the canonical integration is:

  ```python
  env, user_proxy, agent, session = build_components(agent_llm, user_llm)
  user_proxy.init_conversation()
  session.run_cycle()
  ```

- Hook the `user_proxy` into `AgentUserInterface` (see `docs/user_proxy_guide.md`).
- Schedule additional cycles whenever external events enter the system (for
  example, after Meta-ARE delivers a new message).

By following these steps you can port the reference contacts follow-up scenario
to new domains while reusing the LLM planner, logging utilities, and proactive
session loop.
