# Scenario Authoring Guide

This document contains everything a scenario author needs to wire the PAS user
proxy, proactive agent, and stateful apps into Meta-ARE. No other documentation
is required.

## 1. Goal

Create scenarios that:

- Use `StateAwareEnvironmentWrapper` and PAS stateful apps to simulate realistic
  mobile navigation.
- Route every `CompletedEvent` to the proactive agent for goal detection.
- Inject the custom `StatefulUserProxy` into Meta-ARE’s
  `AgentUserInterface` so that the agent receives conversational replies.
- Define initial data, success criteria, and failure handling.

## 2. Required dependencies

Ensure your scenario module imports:

```python
from collections.abc import Callable
from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.notification_system import NotificationSystem
from are.simulation.types import CompletedEvent, EventType
from pas.apps.calendar import StatefulCalendarApp
from pas.apps.contacts import StatefulContactsApp
from pas.environment import StateAwareEnvironmentWrapper
from pas.proactive.agent import GoalHypothesis, ProactiveAgentProtocol
from pas.user_proxy.stateful import StatefulUserProxy, TurnLimitReached
```

Add other stateful apps as needed.

## 3. Scenario structure template

Create a helper that builds the environment + components:

```python
def build_env() -> tuple[StateAwareEnvironmentWrapper, StatefulUserProxy, ProactiveAgentProtocol]:
    env = StateAwareEnvironmentWrapper()
    env.register_apps([
        StatefulContactsApp(name="contacts"),
        StatefulCalendarApp(name="calendar"),
        # add more apps here
    ])

    notification_system = env.notification_system
    user_proxy = StatefulUserProxy(env, notification_system, summary_style="structured")
    proactive_agent = RuleBasedProactiveAgent()  # your implementation

    notification_system.subscribe(EventType.ANY, proactive_agent.observe)
    return env, user_proxy, proactive_agent
```

## 4. Wiring into a Scenario

Example using Meta-ARE’s `Scenario` API:

```python
def create_scenario() -> Scenario:
    env, user_proxy, proactive = build_env()

    def on_goal() -> None:
        goal = proactive.propose_goal()
        if goal is None:
            return
        if proactive.confirm_goal(user_proxy):
            try:
                result = proactive.execute(goal, env)
            except ProactiveInterventionError as exc:
                env.logger.error("intervention failed: %s", exc)
            else:
                user_proxy.reply(result.notes)  # optional follow-up
            finally:
                proactive.handoff(env)

    # schedule periodic goal checks (e.g. after each event)
    env.notification_system.subscribe(EventType.ANY, lambda _: on_goal())

    agent_ui = AgentUserInterface(user_proxy=user_proxy)
    scenario = Scenario(
        scenario_id="contacts_followup",
        agent_user_interface=agent_ui,
        environment=env,
        description="User wants to follow up with newly added contact.",
    )
    return scenario
```

The above pattern ensures the proactive agent is considered after each event.
Real scenarios may wish to debounce `on_goal()` (e.g. only after user turns).

## 5. Passing contextual data

If the scenario needs to pass configuration to the proxy or proactive agent,
provide them via the constructors inside `build_env()`. Examples:

```python
user_proxy = StatefulUserProxy(env, notification_system, max_user_turns=20, greeting="Hey there!")
proactive = RuleBasedProactiveAgent(max_hypotheses=3)
```

Avoid global variables; keep everything encapsulated so tests can instantiate
multiple environments in parallel.

## 6. Success / failure criteria

Leverage Meta-ARE’s existing validation hooks (`Scenario.validate`). Ensure you
store sufficient metadata to judge success:

- Use the proactive agent’s `InterventionResult.notes` and the proxy’s
  structured replies as evidence.
- Record important `CompletedEvent`s for post-run inspection (you can reuse the
  `StateAwareEnvironmentWrapper.event_log`).

## 7. Error handling conventions

- Catch `TurnLimitReached` from the user proxy and end the scenario gracefully
  (e.g. mark as incomplete, prompt user to retry).
- Catch `UserActionFailed` or `ProactiveInterventionError` and log them; do not
  crash the environment.
- Always call `proactive.handoff(env)` in a `finally` block when an intervention
  was attempted, so the UI state is restored.

## 8. Scenario data seeding

Scenario authors are responsible for providing initial data in PAS apps:

```python
contacts = env.get_app("contacts")
contacts.add_contacts([...])
calendar = env.get_app("calendar")
calendar.populate_events([...])
```

Perform seeding **before** the scenario starts running. Avoid modifying data
mid-scenario outside of tool calls; it breaks the navigation mirrors.

## 9. Testing checklist

1. Instantiate the scenario and run through a scripted conversation using the
   user proxy alone to ensure all planned user flows succeed.
2. Trigger the proactive agent by emitting mock `CompletedEvent`s and verify
   it proposes/executes goals as expected.
3. Confirm `AgentUserInterface` receives readable replies (inspect console
   output or scenario logs).
4. Verify turn limits and error handling behave according to §7.

With this wiring, the scenario can evolve independently of the user proxy and
proactive agent implementations. Any future extensions should append to this
contract and keep backwards compatibility.
