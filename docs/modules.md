# Key PAS Modules

- `pas.apps` – Stateful wrappers around Meta-ARE mobile apps (contacts,
  messaging, email, calendar) and their navigation states.
- `pas.environment.StateAwareEnvironmentWrapper` – monitors completed events
  and triggers navigation transitions while broadcasting notifications.
- `pas.user_proxy` – user proxy implementation plus planners and decision
  maker utilities.
- `pas.proactive` – proactive agent, OpenAI client wrapper, and plan executor
  bridge to Meta-ARE ReAct agents.
- `pas.scenarios` – factories that assemble environments, agents, and oracle
  expectations for demos or imported Meta scenarios.
- `pas.system` – runtime helpers to initialise logging, build planners, and run
  `ProactiveSession` cycles end-to-end.
