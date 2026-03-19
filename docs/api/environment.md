# Environment API

State-aware environment wrapper that drives PARE runtime execution.

Key responsibilities:

- active-app and background-app tracking
- user-tool exposure based on current app state
- full proactive-tool exposure across registered apps
- navigation callback wiring through `HomeScreenSystemApp`
- completed-event processing and PARE metadata injection

For the end-to-end execution path, see the Architecture page [Runtime Execution Flow](../runtime_execution_flow.md).

## StateAwareEnvironmentWrapper

::: pare.environment
