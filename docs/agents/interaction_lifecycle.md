# Agent Interaction Lifecycle

This page explains how the user and proactive agents interact during a PARE scenario run.

## The Two Roles

### User Agent

`pare.agents.user.agent.UserAgent` simulates user-side phone interaction.

It:

- receives proposal messages and user-facing environment notifications
- gets only the tools available on the current active app state plus system/AUI tools
- executes one synchronous user turn at a time

### Proactive Agent

`pare.agents.proactive.agent.ProactiveAgent` manages two internal modes of work:

- **observe agent**: decides whether to propose something
- **execute agent**: carries out an accepted proposal

## User Agent Turn Lifecycle

One user turn in `UserAgent.agent_loop(...)` roughly does this:

1. inject current app and current state into agent custom state
2. refresh currently available tools from the environment
3. read current notification messages
4. build a task from agent-facing messages
5. run the wrapped ReAct agent once for that turn
6. return the result or raise on failure

The user agent therefore reacts to the current phone state and proposal messages rather than operating with global unrestricted tool access.

## Proactive Agent Mode Lifecycle

`ProactiveAgent` cycles through three modes:

1. `OBSERVE`
2. `AWAITING_CONFIRMATION`
3. `EXECUTE`

### Observe

In observe mode:

- the observe agent consumes environment notifications and recent user messages
- it can either:
  - call `wait`, or
  - call `send_message_to_user`

If it sends a message to the user, PARE treats that as a proposal and stores it as `pending_goal`, then switches to `AWAITING_CONFIRMATION`.

### Awaiting Confirmation

In awaiting-confirmation mode:

- PARE inspects new user messages
- `[ACCEPT]` moves the proactive agent to `EXECUTE`
- `[REJECT]` clears the proposal and returns to `OBSERVE`

### Execute

In execute mode:

- the execute agent receives a task built from:
  - the pending goal
  - the user reply
- it runs with broader tool access than the observe agent
- after completion, the proactive agent resets to `OBSERVE`

## Tool Partitioning

The proactive agent intentionally splits tools:

- observe agent gets read-oriented tools plus proposal/wait tools
- execute agent gets the actionable tool set for carrying out accepted work

This keeps proposing and acting as separate phases in the runtime.

## How the Runner Orchestrates Both

`TwoAgentScenarioRunner` alternates:

1. one user-agent turn
2. one proactive-agent turn
3. repeat until:
   - max turns reached, or
   - environment stops

After the loop, PARE validates the scenario and extracts metrics such as:

- proposal count
- acceptance count
- read-only actions
- write actions
- number of turns

## Message Surfaces

`PARENotificationSystem` is what lets both sides see the same world differently:

- user-facing environment notifications
- agent-facing environment notifications
- proposal/accept/reject traffic through `PAREAgentUserInterface`

That message split is a core reason PARE can model proactive interaction rather than just plain autonomous execution.
