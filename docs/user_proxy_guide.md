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
        llm_client: LiteLLMClient,
        tools: dict[str, object],
        *,
        max_turns: int = 40,
        logger: logging.Logger | None = None,
    ) -> None:
        ...
```

- `llm_client`: LiteLLM client for ReAct reasoning
- `tools`: Dictionary of available tools (user_tools from apps + final_answer)
- `max_turns`: Maximum conversation turns before termination (default 40)
- `logger`: Optional logger for tracking agent decisions

The agent uses a custom PasJsonActionExecutor that:
1. Records PAS-specific metadata (app name, method name, raw arguments)
2. Waits for CompletedEvents after tool calls (except for final_answer)
3. Provides detailed error messages when tools fail

### StatefulUserAgentRuntime

Wraps the agent and manages dynamic tool updates:

```python
class StatefulUserAgentRuntime:
    def __init__(
        self,
        agent: StatefulUserAgent,
        env: StateAwareEnvironmentWrapper,
    ) -> None:
        ...
```

- `agent`: The StatefulUserAgent instance
- `env`: StateAwareEnvironmentWrapper for accessing apps and managing state

The runtime exposes the same `reply()` interface as Meta ARE's Runtime but adds tool refresh logic when the current app/state changes.

## 3. Tool Execution and Event Synchronization

The PasJsonActionExecutor handles tool execution with PAS-specific requirements:

```python
class PasJsonActionExecutor(JsonActionExecutor):
    def execute_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tools: dict[str, Any],
    ) -> tuple[bool, str]:
        ...
```

After each tool call (except final_answer), the executor:
1. Parses the tool name to extract app and method (e.g., "contacts__add_contact")
2. Records metadata (app_name, method_name, raw_args) for PAS-specific logging
3. Waits for a CompletedEvent from the environment to ensure state consistency
4. Returns success/failure status with detailed error messages

This automatic event waiting ensures that the agent's view of app state stays synchronized with actual state transitions.

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

The agent automatically receives tool descriptions and available tools based on the current app state. When navigating between apps, the runtime refreshes the toolbox to show only relevant tools.

## 5. Reply Workflow

`StatefulUserAgentRuntime.reply(message: str)` orchestrates the interaction:

1. Check if the current app or state has changed since the last turn
2. If changed, refresh the agent's toolbox with tools for the new state
3. Delegate to the underlying agent's `reply()` method
4. The agent uses ReAct reasoning to decide which tools to call
5. PasJsonActionExecutor executes each tool and waits for CompletedEvents
6. Continue until the agent calls final_answer or hits the turn limit
7. Return the final answer or error message

The runtime ensures that:
- Tools are always up-to-date with the current navigation state
- State transitions are properly synchronized via CompletedEvents
- Turn limits are enforced (raises `MaxTurnsReached` after max_turns)
- Termination is handled via native Meta ARE mechanisms

## 6. Turn Limits and Errors

The agent uses Meta ARE's native error handling:

- `MaxTurnsReached`: raised when the agent has executed `max_turns` without calling final_answer. Scenarios should catch this and handle gracefully.
- `InvalidActionAgentError`: raised when the LLM produces malformed action JSON. This indicates a prompt engineering issue or LLM confusion.
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
from pas.user_proxy.agent import StatefulUserAgent, StatefulUserAgentRuntime
from pas.proactive.litellm_client import build_llm_client

# Build the agent
llm_client = build_llm_client(model_name="gpt-4")
user_agent = StatefulUserAgent(
    llm_client=llm_client,
    tools=user_tools,  # From apps + final_answer
    max_turns=40,
)

# Wrap in runtime
runtime = StatefulUserAgentRuntime(agent=user_agent, env=env)

# Use in scenario
response = runtime.reply("Add a contact named John Doe")
```

The runtime is compatible with Meta ARE's agent interface, allowing seamless integration with proactive agents and scenarios.
