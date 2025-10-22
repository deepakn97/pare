# User Proxy Guide

This guide explains how the PAS user proxy is structured and how it integrates with Meta ARE's BaseAgent pattern.

## 1. Overview

`pas/user_proxy/agent.py` exports `StatefulUserAgent`, a Meta ARE BaseAgent that uses ReAct reasoning to interact with stateful apps. Its core responsibilities are:

1. Use ReAct-style reasoning to decide which tools to call based on agent messages and system notifications.
2. Execute tools against the current navigation state while tracking recent events.
3. Automatically wait for CompletedEvents after tool calls to keep state synchronized.
4. Enforce turn limits to keep conversations bounded.
5. Terminate conversations using the native Meta ARE final_answer tool.

The agent uses Meta ARE's native ReAct reasoning framework, eliminating the need for a separate planner layer.

## 2. Architecture

### StatefulUserAgent

The core agent that extends Meta ARE's BaseAgent:

```python
class StatefulUserAgent(BaseAgent):
    def __init__(
        self,
        llm_engine: LLMClientProtocol | LLMEngine | Callable[..., Any],
        tools: dict[str, Tool] | None = None,
        system_prompts: dict[str, str] | None = None,
        *,
        max_iterations: int = 10,
        max_turns: int = 40,
        wait_timeout: float = 2.0,
        **kwargs: Any,
    ) -> None:
        ...
```

- `llm_engine`: LLM engine or client for generating responses (compatible with Meta ARE)
- `tools`: Dictionary of available tools indexed by name (user_tools from apps + final_answer)
- `system_prompts`: Dictionary of system prompts (default includes ReAct prompt)
- `max_iterations`: Maximum iterations per turn (default 10)
- `max_turns`: Maximum conversation turns before termination (default 40)
- `wait_timeout`: Timeout for waiting on completed events (default 2.0 seconds)
- `**kwargs`: Additional arguments passed to Meta ARE's BaseAgent

The agent uses a custom PasJsonActionExecutor that:
1. Records PAS-specific metadata (app name, method name, raw arguments)
2. Waits for CompletedEvents after tool calls (except for final_answer)
3. Provides detailed error messages when tools fail

### StatefulUserAgentRuntime

Wraps the agent and coordinates with the environment and notification system:

```python
class StatefulUserAgentRuntime(UserProxy):
    def __init__(
        self,
        *,
        agent: StatefulUserAgent,
        notification_system: BaseNotificationSystem,
        logger: logging.Logger,
        max_user_turns: int = 40,
        event_timeout: float = 2.0,
    ) -> None:
        ...
```

- `agent`: The StatefulUserAgent instance
- `notification_system`: Notification system for observing environment events
- `logger`: Logger for tracking runtime operations
- `max_user_turns`: Maximum number of conversation turns (default 40)
- `event_timeout`: Timeout for waiting on completed events (default 2.0 seconds)

The runtime exposes the same `reply()` interface as Meta ARE's UserProxy and manages event synchronization.

## 3. Tool Execution and Event Synchronization

The PasJsonActionExecutor extends Meta ARE's JsonActionExecutor with PAS-specific requirements:

```python
class PasJsonActionExecutor(JsonActionExecutor):
    def execute_tool_call(
        self,
        parsed_action: ParsedAction,
        append_agent_log: Callable[[BaseAgentLog], None],
        make_timestamp: Callable[[], float],
    ) -> Any:
        ...
```

After each tool call (except final_answer), the executor:
1. Delegates to Meta ARE's base executor to execute the tool
2. Parses the tool name to extract app and method (e.g., "contacts__add_contact")
3. Waits for a CompletedEvent from the runtime to ensure state consistency
4. Records a ToolInvocation with metadata (app_name, method_name, args, result, event)
5. Returns the observation string for the agent's next reasoning step

This automatic event waiting ensures that the agent's view of app state stays synchronized with actual state transitions. The runtime manages the event queue and notifies the executor when new CompletedEvents arrive.

## 4. ReAct Reasoning

The agent uses Meta ARE's native ReAct (Reasoning + Acting) framework. Each turn follows the pattern:

```
Thought: [Agent's reasoning about what to do]
Action:
{"action": "tool_name", "action_input": {...}}<end_action>
```

The system prompt instructs the agent to:
- Think step-by-step about which tools to use
- Prefer tapping/clicking over typing when possible
- Use the final_answer tool when the task is complete
- Keep messages brief when using send_message_to_agent

Example ReAct trace:
```
Thought: The user wants to add a new contact. I should use the contacts app's add_contact tool.
Action:
{"action": "contacts__add_contact", "action_input": {"name": "John Doe", "email": "john@example.com"}}<end_action>
Observation: Contact added successfully

Thought: The task is complete. I'll summarize what was done.
Action:
{"action": "final_answer", "action_input": {"answer": "Added contact John Doe with email john@example.com"}}<end_action>
```

The agent automatically receives tool descriptions and available tools based on the current app state. Tool updates are pushed from the Environment when state transitions occur.

## 5. Reply Workflow

`StatefulUserAgentRuntime.reply(message: str)` orchestrates the interaction:

1. Enforce turn budget (raises `TurnLimitReached` if exceeded)
2. Infer the active app from recent tool invocations
3. Update the agent's system context with the active app information
4. Delegate to the underlying agent's `reply()` method
5. The agent uses ReAct reasoning to decide which tools to call
6. PasJsonActionExecutor executes each tool and waits for CompletedEvents
7. Continue until the agent calls final_answer or hits the turn limit
8. Return the final answer or error message

The runtime ensures that:
- State transitions are properly synchronized via CompletedEvents
- Turn limits are enforced (raises `TurnLimitReached` after `max_user_turns`)
- Termination is handled via native Meta ARE mechanisms

Tool updates are pushed from the Environment to the agent via `agent.update_tools_for_app()` when state transitions occur, rather than being pulled by the runtime on every turn.

## 6. Turn Limits and Errors

The runtime uses PAS-specific error handling with Meta ARE integration:

- `TurnLimitReached`: raised by the runtime when `max_user_turns` is exceeded. Scenarios should catch this and handle gracefully.
- `InvalidActionAgentError`: raised by Meta ARE when the LLM produces malformed action JSON. This indicates a prompt engineering issue or LLM confusion.
- Tool execution errors: captured by PasJsonActionExecutor and returned as observation strings, allowing the agent to retry or adjust its approach.

## 7. Logging

The agent uses standard Meta ARE logging plus PAS-specific extensions:

- Agent reasoning is logged via the LiteLLM client
- Tool execution details (app_name, method_name, args) are logged by PasJsonActionExecutor
- CompletedEvents are logged by the environment's event logging system
- Use `pas.logging_utils.get_pas_file_logger` to create dedicated loggers for PAS components

Running `pas/scripts/run_contacts_demo.py` prints log locations for monitoring agent behavior during development.

## 8. Integration with Scenarios

To use the agent in a scenario:

```python
import logging
from pas.user_proxy.agent import StatefulUserAgent, StatefulUserAgentRuntime
from pas.proactive.litellm_client import build_llm_client

# Build the agent
llm_client = build_llm_client(model_name="gpt-4")
user_agent = StatefulUserAgent(
    llm_engine=llm_client,
    tools=user_tools,  # From apps + final_answer
    max_turns=40,
)

# Wrap in runtime
logger = logging.getLogger("pas.user_proxy")
runtime = StatefulUserAgentRuntime(
    agent=user_agent,
    notification_system=env.notification_system,
    logger=logger,
    max_user_turns=40,
)

# Use in scenario
response = runtime.reply("Add a contact named John Doe")
```

The runtime is compatible with Meta ARE's UserProxy interface, allowing seamless integration with proactive agents and scenarios.
