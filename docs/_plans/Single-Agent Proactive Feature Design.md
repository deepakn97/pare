# Enhanced Observe Agent with Read-Only Tools

**GitHub Issue**: #37 - Enhanced observe agent capabilities
**Status**: Phases 1-4 Complete

## Summary

Enhance the existing `ProactiveAgent` class to give the observe agent access to all read-only tools (in addition to `wait` and `send_message_to_user`). This allows the observe agent to explore the environment before making proposals. Also implement turn termination logic where turns end only when specific tools are called.

**Architecture Decision**: Keep the two-agent architecture (observe + execute agents) rather than creating a single unified agent. Future work will add history sharing between agents.

---

## Implementation Summary (Completed)

### Phase 1: Read-Only Tools for Observe Agent ✅
Updated `init_tools()` in `pas/agents/proactive/agent.py` to give the observe agent access to all `OperationType.READ` tools in addition to `wait` and `send_message_to_user`. Tools are filtered using the `__operation_type__` attribute on tool functions.

### Phase 2: Turn Termination Logic ✅
- Increased `observe_max_iterations` default from 1 to 10 to allow exploration
- Implemented `get_proactive_agent_termination_step()` in `pas/agents/proactive/agent.py` that terminates the observe agent's turn only when `wait` or `send_message_to_user` is called
- The termination step checks the agent's logs for `ToolCallLog` entries matching turn-ending tool names

### Phase 3: Updated Observe Prompt ✅
Updated `pas/agents/proactive/prompts/observe_prompt.py` to inform the agent about its expanded tool access and the turn termination behavior.

### Phase 4: Testing ✅
Tested the observe agent with expanded tools and verified turn termination works correctly. Also resolved a logging configuration issue where DEBUG logs from ARE's `base_agent.py` were appearing despite log level being set to INFO.

**Logging Fix**: Updated `suppress_noisy_are_loggers()` in `pas/logging_config.py` to also remove any handlers that might have been added by ARE's `get_default_logger()` function, which could bypass the log level settings.

---

## Key Design Decisions

1. **Tool Access in OBSERVE mode**: Observe agent gets `wait`, `send_message`, AND all **read-only tools** (`OperationType.READ`) from apps for exploration
2. **Turn Termination**:
   - OBSERVE mode: Turn ends ONLY when `wait` or `send_message_to_user` is called (agent can take multiple read-only actions)
   - EXECUTE mode: Turn ends when `send_message_to_user` is called
3. **Keep Two Agents**: Maintain separate observe and execute `BaseAgent` instances
4. **Future: History Transfer**: Add mechanism to feed observe agent history to execute agent
5. **Future: History Summarizer**: Implement LLM-based summarizer for agent history

## Files to Modify

| File | Changes |
|------|---------|
| `pas/agents/proactive/agent.py` | Update `init_tools()`, add turn termination logic |
| `pas/agents/proactive/prompts/observe_prompt.py` | Update prompt to reflect new tool capabilities |

---

## Implementation Phases

### Phase 1: Update `init_tools()` for Observe Agent

**File**: `pas/agents/proactive/agent.py`

Current implementation only gives observe agent `wait` and `send_message_to_user`:

```python
# Current (lines 150-156)
observe_tool_names = ["PASAgentUserInterface__wait", "PASAgentUserInterface__send_message_to_user"]
observe_tools = [tool for tool in app_tools if tool.name in observe_tool_names]
```

**New implementation** - give observe agent read-only tools as well:

```python
def init_tools(self, scenario: Scenario) -> None:
    """Initialize the tools.

    Args:
        scenario: Scenario to initialize the tools for.
    """
    app_tools = self.remove_aui_irrelevant_tools(scenario.get_tools())
    logger.info(f"Found {len(app_tools)} tools: {[tool.name for tool in app_tools]}")
    are_simulation_tools = [AppToolAdapter(tool) for tool in app_tools]
    self.tools += are_simulation_tools

    # Core observe tools (always included)
    core_observe_tool_names = ["PASAgentUserInterface__wait", "PASAgentUserInterface__send_message_to_user"]

    # Build observe tools: core tools + all READ-only tools
    observe_tools: list[AppTool] = []
    for tool in app_tools:
        if tool.name in core_observe_tool_names:
            observe_tools.append(tool)
        elif getattr(tool.function, "__operation_type__", OperationType.READ) == OperationType.READ:
            observe_tools.append(tool)

    if len(observe_tools) == 0:
        raise ValueError("No observe tools found. The observe agent must have the send_message_to_user tool.")

    self.observe_agent.tools = {tool.name: tool for tool in observe_tools}
    self.execute_agent.tools = {tool.name: tool for tool in self.tools}

    logger.info(f"Observe agent has {len(observe_tools)} tools (core + read-only)")
    logger.info(f"Execute agent has {len(self.tools)} tools (all)")
```

**Tool Distribution Summary**:

| Tool | Observe Agent | Execute Agent |
|------|---------------|---------------|
| `wait` | ✅ | ✅ |
| `send_message_to_user` | ✅ | ✅ |
| READ tools (`OperationType.READ`) | ✅ | ✅ |
| WRITE tools (`OperationType.WRITE`) | ❌ | ✅ |

**Required Import**:
```python
from are.simulation.tool_utils import OperationType
```

### Phase 2: Turn Termination Logic

Implement turn termination where turns end only when specific tools are called, not based on iteration count alone.

**For Observe Agent**: Turn ends when `wait` or `send_message_to_user` is called.

```python
def _check_for_turn_ending_tool(self, agent: BaseAgent, turn_ending_tools: list[str]) -> bool:
    """Check if a turn-ending tool was called in the last iteration.

    Args:
        agent: The agent to check logs for.
        turn_ending_tools: List of tool names that end the turn.

    Returns:
        True if a turn-ending tool was called, False otherwise.
    """
    logs = agent.get_agent_logs()
    for log in reversed(logs):
        if isinstance(log, ToolCallLog):
            if any(tool_name in log.tool_name.lower() for tool_name in turn_ending_tools):
                return True
            # If we hit a non-turn-ending tool call, keep checking previous logs
            # until we find a turn-ending one or exhaust recent logs
        if isinstance(log, TaskLog):
            # Stop searching at the task boundary
            break
    return False

def _run_observe_mode(
    self,
    user_messages: list[Message],
    env_notifications: list[Message],
    reset: bool = True,
) -> str | MMObservation | None:
    """Run the observe agent - turn ends when wait or send_message is called."""
    logger.info("Running in OBSERVE mode")
    self.observe_agent.iterations = 0

    task = self.build_task_from_notifications(user_messages)
    attachments: list[Attachment] = [attachment for message in user_messages for attachment in message.attachments]

    # Run agent - it will continue until max_iterations or turn-ending tool
    result = self.observe_agent.run(
        task=task, hint=None, reset=reset, attachments=attachments if attachments else None
    )

    # Check for proposal
    proposal_made, proposal_content = self.check_for_proposal()
    if proposal_made:
        logger.info(f"Proactive Agent sent a proposal: {proposal_content}")
        self.mode = ProactiveAgentMode.AWAITING_CONFIRMATION
        self.pending_goal = proposal_content

    return result
```

**For Execute Agent**: Turn ends when `send_message_to_user` is called (to notify completion).

**Constructor Change** - increase `observe_max_iterations`:
```python
def __init__(
    self,
    ...
    observe_max_iterations: int = 10,  # Increased from 1 to allow exploration
    execute_max_iterations: int = 20,
    ...
) -> None:
```

### Phase 3: Update Observe Prompt

**File**: `pas/agents/proactive/prompts/observe_prompt.py`

Update the prompt to inform the agent about its expanded tool access:

```python
# Add to OBSERVE_TOOLS_USAGE section
OBSERVE_TOOLS_USAGE = """
## Available Tools
You have access to:
1. `wait` - Wait and observe without taking action (ends your turn)
2. `send_message_to_user` - Propose a task to the user (ends your turn)
3. **Read-only tools** - Use these to explore the environment and gather information before making proposals

## Guidelines
- Use read-only tools to understand the current state before proposing
- Only `wait` or `send_message_to_user` will end your observe turn
- You can make multiple read-only tool calls to gather context
- Gather relevant context to make informed, specific proposals
"""
```

---

## Learnings & Notes for Future Work

1. **ARE Logging Architecture**: ARE's `get_default_logger()` creates isolated loggers with DEBUG level and custom handlers. When `use_custom_logger=False` is passed to `BaseAgent`, it uses `get_parent_logger()` which respects the parent logging configuration. Ensure all `BaseAgent` instances in PAS use `use_custom_logger=False` to respect PAS's logging setup.

2. **History Access**: The observe agent's history can be accessed via `self.observe_agent.get_agent_logs()` which returns a list of `BaseAgentLog` objects including `ToolCallLog`, `ObservationLog`, `TaskLog`, etc. This will be useful for Phase 5's history transfer.

3. **Termination Step Pattern**: The termination step receives the agent and the last log entry. It can inspect `agent.get_agent_logs()` to check for specific tool calls. This pattern could be reused for execute agent termination.

---

## Future Work

### Phase 5 (Future): History Transfer to Execute Agent

Feed observe agent's history to execute agent when transitioning to execute mode. This provides context about what was observed before the proposal.

**Approach Options**:
1. **Direct history injection**: Copy relevant logs from observe_agent to execute_agent
2. **Summary injection**: Generate a summary and inject as initial context
3. **Replay mechanism**: Use `base_agent.replay()` with filtered logs

```python
def _transfer_history_to_execute_agent(self) -> None:
    """Transfer relevant observe history to execute agent."""
    observe_logs = self.observe_agent.get_agent_logs()
    # Filter for relevant logs (observations, tool calls, etc.)
    relevant_logs = [log for log in observe_logs if self._is_relevant_for_execute(log)]
    # Inject into execute agent
    # TBD: exact mechanism
```

### Phase 6 (Future): History Summarizer

Implement an LLM-based summarizer that takes agent history and generates a concise summary.

**Use Cases**:
- Compress long observe sessions before feeding to execute agent
- Generate session summaries for logging/debugging
- Reduce context length for long-running scenarios

```python
class HistorySummarizer:
    """Summarizes agent history using an LLM call."""

    def __init__(self, llm_engine: LLMEngine):
        self.llm_engine = llm_engine

    def summarize(self, logs: list[BaseAgentLog]) -> str:
        """Generate a summary of the agent's history.

        Args:
            logs: List of agent logs to summarize.

        Returns:
            A concise summary of what the agent observed and did.
        """
        # Build prompt from logs
        history_text = self._format_logs_for_summary(logs)

        prompt = f"""Summarize the following agent session history concisely:

{history_text}

Focus on:
- Key observations made
- Important information discovered
- Actions taken and their results
- Current state/context relevant for next steps
"""

        summary = self.llm_engine(prompt)
        return summary
```

---

## Implementation Order

1. ~~Update `init_tools()` in `agent.py` to give observe agent read-only tools~~ ✅
2. ~~Update `observe_max_iterations` default to 10~~ ✅
3. ~~Implement turn termination logic (turn ends on `wait`/`send_message_to_user`)~~ ✅
4. ~~Update observe prompt to reflect new capabilities~~ ✅
5. ~~Test observe agent with expanded tool access and turn termination~~ ✅
6. (Future) Implement history transfer mechanism
7. (Future) Implement history summarizer

## Critical Files Reference

- **Main file to modify**: `pas/agents/proactive/agent.py`
- **Observe prompt**: `pas/agents/proactive/prompts/observe_prompt.py`
- **Tool decorator**: `pas/apps/tool_decorators.py` (defines `OperationType`)
- **Tool utils**: `are/simulation/tool_utils.py` (defines `OperationType` enum)

## Cleanup

- Remove `pas/agents/proactive/single_agent.py` (if created during earlier development)
