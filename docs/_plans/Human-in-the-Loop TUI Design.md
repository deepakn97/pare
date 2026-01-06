# Human-in-the-Loop TUI Design

**Status**: Planning
**Date**: 2026-01-05

## Overview

This design document describes a Human-in-the-Loop (HITL) Terminal User Interface (TUI) feature for PAS that allows a human researcher to directly control either the UserAgent or ProactiveAgent during scenario execution while observing the other LLM-controlled agent's activities in real-time.

### Why This Architecture (Correcting Previous Mistakes)

A previous attempt placed the TUI inside `HumanInputLLMEngine`. This was incorrect because:

1. **The LLMEngine is too low-level** - it only receives chat completion requests and cannot see the other agent's output
2. **The TUI needs visibility into BOTH agents** - to display what each agent is doing
3. **The human needs context** - they must see what the LLM-controlled agent did before deciding their action

### Correct Architecture

```
TwoAgentScenarioRunner
    |
    +-- TUIRenderer (owned by scenario runner)
    |       |
    |       +-- Displays full conversation from both agents
    |       +-- Shows which agent's turn it is
    |       +-- Renders available tools
    |       +-- Provides beautiful input prompt
    |
    +-- UserAgent
    |       +-- LLMEngine (if LLM mode)
    |       +-- HumanInputLLMEngine (if human mode) --+
    |                                                 |
    +-- ProactiveAgent                                | references
            +-- LLMEngine (if LLM mode)              |
            +-- HumanInputLLMEngine (if human mode) --+---> TUIRenderer
```

**Key Design Principles**:
1. `TUIRenderer` is owned by `TwoAgentScenarioRunner` because it needs visibility into both agents
2. `HumanInputLLMEngine` implements the `LLMEngine` interface (drop-in replacement)
3. `HumanInputLLMEngine` holds a reference to `TUIRenderer` for input collection
4. Configuration determines which agent (if any) is human-controlled

---

## Component Design

### 1. TUIRenderer

**Location**: `pas/tui/renderer.py`

**Responsibilities**:
- Render terminal display showing both agents' activities
- Display conversation history with color-coded agent identification
- Show available tools for the human-controlled agent
- Render environment notifications and state changes
- Provide input prompt for human interaction

**Interface**:
```python
class TUIRenderer:
    """Terminal User Interface renderer for Human-in-the-Loop scenarios."""

    def set_scenario_info(self, scenario_id: str, scenario_description: str) -> None:
        """Set scenario metadata for display."""

    def add_agent_message(
        self,
        agent_name: str,
        message_type: str,  # "thought", "action", "observation", "error"
        content: str,
        timestamp: float | None = None
    ) -> None:
        """Add a message from an agent to the conversation log."""

    def update_app_state(self, app_name: str, state_name: str | None) -> None:
        """Update the current app state display."""

    def set_available_tools(self, tools: list[dict[str, str]]) -> None:
        """Set the available tools for display."""

    def render(self) -> None:
        """Render the current TUI state to the terminal."""

    def get_human_input(self, prompt: str, agent_name: str) -> str:
        """Display input prompt and collect human input."""

    def show_turn_indicator(self, agent_name: str, is_human: bool) -> None:
        """Show whose turn it is with visual indicator."""
```

### 2. HumanInputLLMEngine

**Location**: `pas/tui/human_input_engine.py`

**Purpose**: Implements the `LLMEngine` interface to provide human input as a drop-in replacement for LLM backends.

**Interface**:
```python
class HumanInputLLMEngine(LLMEngine):
    """LLMEngine implementation that collects input from a human via TUI."""

    def __init__(
        self,
        tui_renderer: TUIRenderer,
        agent_name: str,  # "UserAgent" or "ProactiveAgent"
        model_name: str = "human",
    ) -> None:
        """Initialize the human input engine."""

    def chat_completion(
        self,
        messages: list[dict[str, Any]],
        stop_sequences: list[str] | None = None,
        **kwargs: Any,
    ) -> tuple[str, dict | None]:
        """Collect human input and return formatted response."""
```

**Human Input Flow**:
```
1. BaseAgent.step() calls llm_engine.chat_completion(messages)
2. HumanInputLLMEngine receives the call
3. It calls tui_renderer.render() to show current state
4. It calls tui_renderer.get_human_input() to collect input
5. It parses and validates the input
6. It returns formatted response matching LLM output format
7. BaseAgent continues with action execution
```

### 3. TUIConfig

**Location**: `pas/tui/config.py`

```python
class HumanControlledAgent(str, Enum):
    """Which agent the human controls."""
    NONE = "none"           # Both agents are LLM-controlled
    USER_AGENT = "user"     # Human controls UserAgent
    PROACTIVE_AGENT = "proactive"  # Human controls ProactiveAgent


class TUIConfig(BaseModel):
    """Configuration for TUI-enabled scenario runs."""

    human_controlled_agent: HumanControlledAgent
    show_llm_thoughts: bool = True
    show_tool_descriptions: bool = True
    input_timeout_seconds: float | None = None
    enable_help_commands: bool = True
```

---

## TUI Display Design

```
+------------------------------------------------------------------+
|  PAS Human-in-the-Loop Mode                    Turn: 3 / 10      |
|  Scenario: email_reply_assistance                                |
+------------------------------------------------------------------+
|  Environment Status                                              |
|  Active App: StatefulEmailApp | State: EmailInbox                |
+------------------------------------------------------------------+
|  Conversation History                                            |
|  ----------------------------------------------------------------|
|  [10:28:15] PROACTIVE (LLM) - Observe Mode                       |
|    Thought: I see the user received a new email from Alice...    |
|    Action: {"action": "wait", "action_input": {}}                |
|    Observation: Waiting for more context.                        |
|  ----------------------------------------------------------------|
|  [10:29:00] USER (HUMAN)                                         |
|    Thought: I want to check my emails                            |
|    Action: {"action": "StatefulEmailApp__list_emails", ...}      |
|    Observation: Found 5 emails...                                |
|  ----------------------------------------------------------------|
|  [10:29:30] PROACTIVE (LLM) - Observe Mode                       |
|    -> Proposal: "Would you like me to draft a reply to Alice?"   |
+------------------------------------------------------------------+
|  Available Tools (UserAgent)                                     |
|  - StatefulEmailApp__list_emails: List all emails                |
|  - StatefulEmailApp__open_email: Open and read an email          |
|  - PASAgentUserInterface__accept_proposal: Accept agent proposal |
+------------------------------------------------------------------+
|  >> YOUR TURN (UserAgent)                                        |
|  Enter your thought and action (or 'help' for commands):         |
|  > _                                                             |
+------------------------------------------------------------------+
```

### Input Format Options

1. **Full format**: `THOUGHT: I want to check emails ACTION: {"action": "...", "action_input": {}}`
2. **Simple action only**: `{"action": "...", "action_input": {}}` (auto-generates thought)
3. **Special commands**: `help`, `tools`, `history`, `state`, `quit`

---

## Implementation Phases

### Phase 1: Core TUI Infrastructure
**Files to Create**:
- `pas/tui/__init__.py`
- `pas/tui/renderer.py`
- `pas/tui/config.py`

### Phase 2: HumanInputLLMEngine
**Files to Create**:
- `pas/tui/human_input_engine.py`

### Phase 3: Scenario Runner Integration
**Files to Modify**:
- `pas/scenario_runner.py` - Add TUI initialization and log feeding

### Phase 4: CLI Integration
**Files to Create**:
- `pas/scripts/run_hitl.py`

### Phase 5: Testing
**Files to Create**:
- `tests/tui/test_renderer.py`
- `tests/tui/test_human_input_engine.py`

---

## File Changes Summary

### New Files

| File | Purpose |
|------|---------|
| `pas/tui/__init__.py` | Package exports |
| `pas/tui/renderer.py` | TUIRenderer class with Rich-based display |
| `pas/tui/human_input_engine.py` | HumanInputLLMEngine implementing LLMEngine |
| `pas/tui/config.py` | TUIConfig and HumanControlledAgent enum |
| `pas/scripts/run_hitl.py` | CLI script for HITL scenarios |

### Modified Files

| File | Changes |
|------|---------|
| `pas/scenario_runner.py` | Add TUI initialization, log feeding, tui_config parameter |
| `pyproject.toml` | Add `rich>=13.0.0` dependency |

---

## Critical Files for Implementation

- `pas/scenario_runner.py` - Core orchestration logic where TUIRenderer will be created
- `meta-are/are/simulation/agents/llm/llm_engine.py` - LLMEngine interface to implement
- `pas/agents/user/agent.py` - UserAgent implementation
- `pas/agents/proactive/agent.py` - ProactiveAgent implementation
- `meta-are/are/simulation/agents/default_agent/base_agent.py` - BaseAgent.step() flow
