# Two-Agent Proactive System Design

**Status**: Draft
**Date**: 2025-10-26 (Updated with codebase audit)
**Authors**: Design discussion with Claude

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    TwoAgentScenarioRunner                       │
│  ─────────────────────────────────────────────────────────────  │
│  Orchestrates: Environment + User Agent + Proactive Agent       │
│  Main Loop: env.tick() → user.step() → proactive.step()        │
└─────────────────────────────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐
│StateAware    │ │UserAgent     │ │ProactiveAgent        │
│Environment   │ │              │ │                      │
│Wrapper       │ │              │ │                      │
│──────────────│ │──────────────│ │──────────────────────│
│- StatefulApps│ │- base_agent  │ │- observe_agent       │
│- Events      │ │  (BaseAgent) │ │  (BaseAgent)         │
│- Notif System│ │              │ │- execute_agent       │
│              │ │              │ │  (BaseAgent)         │
│get_user_tools│ │step()        │ │                      │
│get_tools()   │ │              │ │step()                │
└──────────────┘ └──────────────┘ └──────────────────────┘
```

## Codebase Audit and Migration Strategy

### Current State Analysis

The existing PAS codebase contains **~12,000 lines** of code, but analysis reveals that **~70% is unnecessary complexity** that should be removed or replaced for the new two-agent design.

#### ✅ **KEEP - Core Components (~2,500 lines, 30%)**

**1. Apps Module** (`pas/apps/`) - **ESSENTIAL**
- ✅ `core.py` (236 lines) - `AppState` and `StatefulApp` base classes
- ✅ `tool_decorators.py` - `@user_tool`, `@app_tool`, `@pas_event_registered`
- ✅ All stateful app implementations:
  - `contacts/app.py` + `states.py` (~300 lines)
  - `email/app.py` + `states.py` (~530 lines)
  - `calendar/app.py` + `states.py` (~600 lines)
  - `messaging/app.py` + `states.py` (~400 lines)
- ✅ `system.py` - `HomeScreenSystemApp` for go_back navigation
- ❌ `proactive_agent_ui.py` - REMOVE (replaced by Meta-ARE's AgentUserInterface)
- 🟡 `agent_ui/states.py` - DEFER (may be useful for stateful agent UI later)

**Why keep**: This is PAS's core innovation - state-based navigation FSM for realistic mobile simulation. All apps properly implement `get_user_tools()` and `get_tools()` methods.

**2. Environment** (`pas/environment.py`) - **ESSENTIAL**
- ✅ `StateAwareEnvironmentWrapper` class (95 lines)
- **TODO**: Add `get_user_tools()` and `get_tools()` method implementations

**Why keep**: Critical for state transitions and tool discovery. Properly extends Meta-ARE's Environment.

**3. Oracles** (`pas/oracles.py`) - **ESSENTIAL**
- ✅ Entire file (114 lines) - `OracleTracker`, `event_matches()`

**Why keep**: Needed for scenario validation. Well-designed, no changes needed.

**4. Utilities** - **ESSENTIAL**
- ✅ `logging_utils.py` - PAS logging setup
- ✅ `llm_adapter.py` - `LLMClientProtocol` and `PasLLMEngine`

**Why keep**: Small, focused utilities that work well.

**5. Scenario Types** (`pas/scenarios/types.py`) - **PARTIAL**
- ✅ `OracleAction` dataclass - Keep
- ❌ `ScenarioSetup` dataclass - Remove (will be redefined for new design)

#### ❌ **REMOVE - Bloated/Unnecessary (~1,300 lines, ~15%)**

**1. Old Agent Implementations** - **DELETE/REPLACE**
- ❌ `pas/proactive/agent.py` (~100 lines) - `LLMBasedProactiveAgent`
- ❌ `pas/proactive/react_adapter.py` - Custom ReAct implementation
- ❌ `pas/proactive/litellm_client.py` - LiteLLM wrapper
- ❌ `pas/user_proxy/agent.py` (517 lines!) - `StatefulUserAgent`, `StatefulUserAgentRuntime`

**Why remove**: Replaced by Meta-ARE `BaseAgent` directly. New design uses three `BaseAgent` instances (user, observe, execute) with different configs and tool sets.

**Impact**: ~700 lines removed

**2. Old Orchestration System** - **DELETE/REPLACE**
- ❌ `pas/system/session.py` (205 lines) - `ProactiveSession`
- ❌ `pas/system/runtime.py` - Helper functions
- ❌ `pas/system/proactive.py` - `build_plan_executor`
- ❌ `pas/system/notification.py` - Custom notification wrapper

**Why remove**: Replaced by new `TwoAgentScenarioRunner` and orchestrators. Current design has custom notification handling and turn management that's redundant with Meta-ARE.

**Impact**: ~400 lines removed

**3. Old Scenario Builders** - **DELETE/REPLACE**
- ❌ `pas/scenarios/base.py` (145 lines) - `build_proactive_stack()`
- ✅ **Keep for reference**: Hand-written scenarios:
  - `contacts_followup.py`
  - `calendar_create_scenario.py`
  - `calendar_meeting_plan_scenario.py`

**Why remove**: `build_proactive_stack()` is tied to old architecture. Will be replaced by new builder in `TwoAgentScenarioRunner`.

**Impact**: ~145 lines of builder code removed

#### 🟡 **DEFER - Not Needed Now (~5,500+ lines, ~55%)**

**1. Scenario Generator** (`pas/scenario_generator/`) - **ARCHIVE**
- 🟡 Status: Keep as-is but ignore for now
- Size: ~156KB, ~2,000+ lines
- Contains: Agent for generating test scenarios, prompts, utils

**Why defer**: Useful for generating test scenarios but not needed for core two-agent system implementation. Can be updated later once two-agent system works.

**2. Generated Scenarios** (`pas/scenarios/generated_scenarios/`) - **KEEP**
- 🟡 Status: Leave in place, ignore for now
- Size: 19 files, ~140KB
- Contains: Example proactive scenarios

**Why defer**: Test data that doesn't hurt to keep. May be useful later for benchmarking.

**3. Meta Adapter** (`pas/meta_adapter.py`) - **REVISIT LATER**
- 🟡 Status: Keep but may need updates
- Size: 362 lines
- Purpose: Convert Meta-ARE scenarios to PAS format

**Why defer**: May need updates for new two-agent design, but not urgent.

**4. Scripts** (`pas/scripts/`) - **REWRITE**
- 🟡 Status: Keep structure, update to use new orchestration
- Files: `run_contacts_demo.py`, `run_demo.py`, `run_meta_tutorial_demo.py`

**Why defer**: Useful for demos but need to be updated to use new `TwoAgentScenarioRunner`.

### Summary Statistics

| Category | Lines | Status | Notes |
|----------|-------|--------|-------|
| **Apps (core + 4 stateful)** | ~2,100 | ✅ KEEP | Core innovation |
| **Environment wrapper** | 95 | ✅ KEEP | Add 2 methods |
| **Oracles** | 114 | ✅ KEEP | Perfect as-is |
| **Utilities** | ~100 | ✅ KEEP | Small & focused |
| **Scenario types** | ~50 | ✅ KEEP | Just OracleAction |
| | | | |
| **Old proactive agent** | ~700 | ❌ REMOVE | → BaseAgent |
| **Old orchestration** | ~400 | ❌ REMOVE | → New design |
| **Old scenario builders** | ~145 | ❌ REMOVE | → New runners |
| | | | |
| **Scenario generator** | ~2,000 | 🟡 DEFER | Update later |
| **Generated scenarios** | ~3,000 | 🟡 DEFER | Test data |
| **Meta adapter** | 362 | 🟡 DEFER | May need updates |
| **Scripts** | ~200 | 🔄 UPDATE | Use new design |

**Net Result**:
- **Keep/Use**: ~2,500 lines (apps + env + oracles + utils)
- **Remove**: ~1,300 lines (old agents + orchestration)
- **Write New**: ~1,000 lines (new orchestrators + runner + configs)
- **Defer**: ~5,500 lines (generators + test data)

**Final Codebase**: ~3,500 lines of core functionality (down from 12,000)

---

## Core Components

### 1. StateAwareEnvironmentWrapper (Existing - Minor Extensions)

**File**: `pas/environment.py`

**Additions needed**:
```python
class StateAwareEnvironmentWrapper(Environment):
    # ... existing code ...

    def get_user_tools(self) -> list[Tool]:
        """Get tools available to user agent from all apps."""
        # Call each app's get_user_tools() method
        # Implementation deferred
        pass

    def get_tools(self) -> list[Tool]:
        """Get all privileged tools for proactive agent from all apps."""
        # Call each app's get_tools() method
        # Implementation deferred
        pass
```

**Responsibilities**:
- Manage stateful apps
- Trigger state transitions on CompletedEvents
- Provide current available tools to orchestrators via get_user_tools()/get_tools()
- Subscribe to completed events
- Integration with Meta-ARE notification system

---

### 2. UserAgent (New)

**File**: `pas/agents/user/user_agent.py`

**Class Definition**:
```python
class UserAgent:
    """User agent for single-action turns (wraps Meta-ARE BaseAgent)."""

    def __init__(
        self,
        base_agent: BaseAgent,
        notification_system: BaseNotificationSystem,
        get_user_tools: Callable[[], list[Tool]],
    ):
        """
        Args:
            base_agent: Meta-ARE BaseAgent with max_iterations=1
            notification_system: Shared notification system
            get_user_tools: Callback to get current user tools (from environment)
        """
        self.base_agent = base_agent
        self.notification_system = notification_system
        self.get_user_tools = get_user_tools
        self.last_read_timestamp = None

    def step(self) -> str | None:
        """Execute one user agent turn.

        1. Get new notifications from notification_system
        2. Build task from notifications
        3. Refresh base_agent.tools from get_user_tools()
        4. Run base_agent.run(task, max_iterations=1)
        5. Return result
        """
        pass

    def build_task_from_notifications(
        self,
        user_messages: list[Message],
        env_notifications: list[Message]
    ) -> str:
        """Build user task from accumulated notifications."""
        pass
```

**Responsibilities**:
- Poll notification system for new messages
- Build task string from notifications (user messages + environment notifications)
- Refresh tools before each turn using `get_user_tools()` callback
- Execute base agent (1 action per turn)
- Track last read timestamp to avoid re-processing notifications

---

### 3. ProactiveAgent (New)

**File**: `pas/agents/proactive/proactive_agent.py`

**Class Definition**:
```python
class ProactiveAgent:
    """Orchestrates the proactive agent's observe/execute modes."""

    def __init__(
        self,
        observe_agent: BaseAgent,
        execute_agent: BaseAgent,
        notification_system: BaseNotificationSystem,
        get_tools: Callable[[], list[Tool]],
        inject_user_tools: Callable[[list[Tool]], None],
    ):
        """
        Args:
            observe_agent: Meta-ARE BaseAgent for observation (max_iterations=1)
            execute_agent: Meta-ARE BaseAgent for execution (max_iterations=20)
            notification_system: Shared notification system
            get_tools: Callback to get all app tools (from environment)
            inject_user_tools: Callback to inject accept/reject tools dynamically
        """
        self.observe_agent = observe_agent
        self.execute_agent = execute_agent
        self.notification_system = notification_system
        self.get_tools = get_tools
        self.inject_user_tools = inject_user_tools

        self.mode = "observe"  # "observe" | "awaiting_confirmation" | "execute"
        self.pending_goal = None
        self.last_read_timestamp = None

    def step(self) -> dict[str, Any]:
        """Execute one proactive agent turn.

        Mode: observe
            - Get notifications
            - Build observation task
            - Run observe_agent
            - Check if send_message_to_user was called
            - If yes: inject accept/reject tools, switch to awaiting_confirmation

        Mode: awaiting_confirmation
            - Check notifications for accept/reject
            - If accept: switch to execute mode
            - If reject: switch back to observe mode

        Mode: execute
            - Build execution task with confirmed goal
            - Run execute_agent
            - Switch back to observe mode

        Returns:
            Result dict with mode, goal, and outcome
        """
        pass

    def build_observation_task(
        self,
        user_actions: list[Message],
        env_notifications: list[Message],
    ) -> str:
        """Build observation task from notifications."""
        pass

    def build_execution_task(self, goal: str) -> str:
        """Build execution task with confirmed goal."""
        pass

    def check_for_proposal(self) -> str | None:
        """Check if observe_agent called send_message_to_user."""
        # Check agent logs for send_message_to_user call
        pass

    def check_for_confirmation(self) -> tuple[bool, bool]:
        """Check if user accepted or rejected.

        Returns:
            (has_decision, accepted)
        """
        # Check notifications for accept_proposal/reject_proposal
        pass
```

**Responsibilities**:
- Manage proactive agent state (observe/awaiting_confirmation/execute)
- Execute observe agent (1 action to decide wait vs propose)
- Execute execute agent (multi-step ReAct for task execution)
- Detect send_message_to_user calls and inject accept/reject tools
- Detect user confirmation and transition modes
- Build appropriate task prompts for each mode

---

### 4. TwoAgentScenarioRunner (New)

**File**: `pas/scenario_runner.py`

**Class Definition**:
```python
class TwoAgentScenarioRunner:
    """Main scenario runner for two-agent proactive system."""

    def __init__(
        self,
        user_agent_config: ARESimulationReactBaseAgentConfig,
        proactive_observe_config: ARESimulationReactBaseAgentConfig,
        proactive_execute_config: ARESimulationReactBaseAgentConfig,
    ):
        """
        Args:
            user_agent_config: Config with system_prompt for user behavior
            proactive_observe_config: Config for observation agent
            proactive_execute_config: Config for execution agent
        """
        self.user_agent_config = user_agent_config
        self.proactive_observe_config = proactive_observe_config
        self.proactive_execute_config = proactive_execute_config

    def run(
        self,
        apps: list[StatefulApp],
        initial_events: list[Event],
        oracles: list[OracleAction] | None = None,
        max_turns: int = 100,
    ) -> ScenarioValidationResult:
        """Run two-agent scenario.

        1. Setup environment with apps and initial events
        2. Create notification system
        3. Build three BaseAgent instances (user, observe, execute)
        4. Create orchestrators
        5. Start environment (non-blocking)
        6. Main loop:
            - user_orchestrator.step()
            - proactive_orchestrator.step()
            - Check termination (max_turns or oracles satisfied)
        7. Stop environment
        8. Return validation result
        """
        pass

    def _build_user_agent(
        self,
        llm_engine: LLMEngine,
        notification_system: BaseNotificationSystem,
    ) -> BaseAgent:
        """Build user BaseAgent from config."""
        pass

    def _build_observe_agent(
        self,
        llm_engine: LLMEngine,
        notification_system: BaseNotificationSystem,
    ) -> BaseAgent:
        """Build observation BaseAgent from config."""
        pass

    def _build_execute_agent(
        self,
        llm_engine: LLMEngine,
        notification_system: BaseNotificationSystem,
    ) -> BaseAgent:
        """Build execution BaseAgent from config."""
        pass

    def _inject_accept_reject_tools(self, env: StateAwareEnvironmentWrapper) -> None:
        """Dynamically inject accept_proposal/reject_proposal into AgentUserInterface."""
        pass

    def _check_termination(
        self,
        turn: int,
        max_turns: int,
        oracle_tracker: OracleTracker | None,
    ) -> bool:
        """Check if scenario should terminate."""
        pass
```

**Responsibilities**:
- Main entry point for running two-agent scenarios
- Setup environment, notification system, agents, orchestrators
- Run main turn-based loop
- Handle termination conditions (max_turns or oracle satisfaction)
- Validate scenario outcomes

---

### 5. Agent Configurations (New)

**File**: `pas/configs/agent_configs.py`

**System Prompts**:
```python
USER_AGENT_SYSTEM_PROMPT = """
You are simulating a mobile phone user navigating apps.

Your role:
- Respond naturally to notifications and messages
- You can only use tools available on the current screen
- Act realistically like a human user would
- Make decisions based on notifications you receive

Constraints:
- You are limited to what a real user could tap/type on the screen
- Your available tools change based on which screen you're on
- You cannot access backend/system functions
"""

PROACTIVE_OBSERVE_SYSTEM_PROMPT = """
You are a proactive assistant observing user's mobile activity.

Your role:
- Observe user actions and environment notifications
- Identify opportunities to help the user proactively
- Decide whether to propose a helpful goal or wait

Guidelines:
- Only propose goals that are genuinely helpful
- Consider recent user activity and context
- Be conservative - don't over-intervene
- Use send_message_to_user(content) to propose a goal
- Simply wait if no good opportunity exists

You have access to all app functions for analysis.
"""

PROACTIVE_EXECUTE_SYSTEM_PROMPT = """
You are executing an approved proactive task.

Your role:
- Complete the confirmed goal using available app functions
- Work efficiently and accurately
- Handle errors gracefully

You have privileged access to all app functions.
"""

def build_user_agent_config(
    model_name: str = "gpt-4",
    max_iterations: int = 1,
) -> ARESimulationReactBaseAgentConfig:
    """Build config for user agent."""
    return ARESimulationReactBaseAgentConfig(
        system_prompt=USER_AGENT_SYSTEM_PROMPT,
        max_iterations=max_iterations,
        llm_engine_config=LLMEngineConfig(model_name=model_name),
    )

def build_proactive_observe_config(
    model_name: str = "gpt-4",
    max_iterations: int = 1,
) -> ARESimulationReactBaseAgentConfig:
    """Build config for observation agent."""
    return ARESimulationReactBaseAgentConfig(
        system_prompt=PROACTIVE_OBSERVE_SYSTEM_PROMPT,
        max_iterations=max_iterations,
        llm_engine_config=LLMEngineConfig(model_name=model_name),
    )

def build_proactive_execute_config(
    model_name: str = "gpt-4o",
    max_iterations: int = 20,
) -> ARESimulationReactBaseAgentConfig:
    """Build config for execution agent."""
    return ARESimulationReactBaseAgentConfig(
        system_prompt=PROACTIVE_EXECUTE_SYSTEM_PROMPT,
        max_iterations=max_iterations,
        llm_engine_config=LLMEngineConfig(model_name=model_name),
    )
```

---

### 6. AgentUserInterface Extensions (Modification to Meta-ARE Usage)

**Approach**: Dynamically inject accept/reject tools into AgentUserInterface app instance

**File**: `pas/apps/system_tools.py`

```python
def create_accept_proposal_tool(
    on_accept: Callable[[str], None]
) -> Tool:
    """Create accept_proposal tool dynamically."""
    pass

def create_reject_proposal_tool(
    on_reject: Callable[[str], None]
) -> Tool:
    """Create reject_proposal tool dynamically."""
    pass

def inject_confirmation_tools(
    aui_app: AgentUserInterface,
    on_accept: Callable[[str], None],
    on_reject: Callable[[str], None],
) -> None:
    """Inject accept/reject tools into AgentUserInterface instance."""
    pass
```

---

## Data Flow

### Single Turn Execution Flow

```
Turn N:

1. Environment.tick()
   └─ Process events at time T
   └─ Emit notifications via notification_system

2. UserAgent.step()
   ├─ Get notifications (env + agent messages)
   ├─ Build task: "New email from Alice. Proactive agent says: Shall I reply?"
   ├─ Refresh tools: base_agent.tools = env.get_user_tools()
   ├─ Run: base_agent.run(task, max_iterations=1)
   │   └─ BaseAgent executes: Think → Act (e.g., accept_proposal)
   └─ Return result

3. ProactiveAgent.step()
   ├─ Check mode (observe | awaiting_confirmation | execute)
   │
   ├─ If mode == "observe":
   │   ├─ Get notifications (user actions + env)
   │   ├─ Build task: "User accepted proposal. What should you do?"
   │   ├─ Refresh tools: observe_agent.tools = env.get_tools()
   │   ├─ Run: observe_agent.run(task, max_iterations=1)
   │   ├─ Check logs: did agent call send_message_to_user?
   │   └─ If yes: mode = "awaiting_confirmation", inject accept/reject tools
   │
   ├─ If mode == "awaiting_confirmation":
   │   ├─ Check notifications for accept/reject
   │   └─ If accept: mode = "execute", pending_goal = confirmed_goal
   │   └─ If reject: mode = "observe"
   │
   └─ If mode == "execute":
       ├─ Build task: "Complete this goal: {pending_goal}"
       ├─ Refresh tools: execute_agent.tools = env.get_tools()
       ├─ Run: execute_agent.run(task, max_iterations=20)
       └─ mode = "observe", pending_goal = None
```

---

## File Structure

```
pas/
├── environment.py                   # StateAwareEnvironmentWrapper (extend)
├── scenario_runner.py               # TwoAgentScenarioRunner (new, root level)
├── agents/                          # Agent implementations (Meta-ARE style)
│   ├── __init__.py
│   ├── user/
│   │   ├── __init__.py
│   │   └── user_agent.py           # UserAgent (new)
│   └── proactive/
│       ├── __init__.py
│       └── proactive_agent.py      # ProactiveAgent (new)
├── configs/
│   ├── __init__.py
│   └── agent_configs.py             # System prompts + config builders (new)
├── apps/
│   ├── core.py                      # StatefulApp (existing)
│   ├── contacts/                    # Existing apps
│   ├── email/
│   └── system_tools.py              # Accept/reject tool creation (new)
└── scripts/
    └── run_two_agent_demo.py        # Demo script (new)
```

---

## Key Design Principles

1. **Reuse Meta-ARE BaseAgent**: Both user and proactive agents are standard Meta-ARE BaseAgents with different configs
2. **Tool Filtering via Callbacks**: Orchestrators refresh tools using callbacks (get_user_tools, get_tools) - they don't hold environment reference
3. **State in Orchestrators**: Mode tracking (observe/execute) lives in ProactiveAgentOrchestrator
4. **Notification-Driven**: All inter-agent communication via shared notification system
5. **Dynamic Tool Injection**: Accept/reject tools injected when send_message_to_user is called
6. **Turn-Based Synchronization**: User agent → Proactive agent → repeat
7. **Config-Based Prompts**: System prompts defined in ARESimulationReactBaseAgentConfig following Meta-ARE patterns

---

## Implementation Phases

### Phase 0: Codebase Cleanup (Optional but Recommended)
**Goal**: Remove bloat before starting new implementation

**Actions**:
1. Archive old code for reference:
   ```bash
   mkdir -p pas/_archive/
   mv pas/proactive/ pas/_archive/proactive_old/
   mv pas/user_proxy/ pas/_archive/user_proxy_old/
   mv pas/system/ pas/_archive/system_old/
   mv pas/scenarios/base.py pas/_archive/scenario_base_old.py
   mv pas/apps/proactive_agent_ui.py pas/_archive/
   ```

2. Create new directory structure:
   ```bash
   mkdir -p pas/agents/user/
   mkdir -p pas/agents/proactive/
   mkdir -p pas/configs/
   ```

3. Keep scenario generator as-is (ignore for now):
   - Don't touch `pas/scenario_generator/`
   - Don't touch `pas/scenarios/generated_scenarios/`

**Outcome**: Clean slate with ~2,500 lines of essential code (apps + env + oracles + utils)

---

### Phase 1: Environment Extensions
**Goal**: Add tool discovery methods to environment

**Actions**:
1. Implement `StateAwareEnvironmentWrapper.get_user_tools()`:
   - Iterate over registered apps
   - Call `app.get_user_tools()` if method exists
   - Return aggregated list of user tools

2. Implement `StateAwareEnvironmentWrapper.get_tools()`:
   - Iterate over registered apps
   - Call `app.get_tools()` if method exists
   - Return aggregated list of all tools

3. Test tool discovery:
   - Create simple test with StatefulContactsApp
   - Verify user tools change with state
   - Verify all tools are available

**Outcome**: Environment can provide current tools to orchestrators

---

### Phase 2: Agent Configurations
**Goal**: Define system prompts and config builders

**Actions**:
1. Create `pas/configs/agent_configs.py`
2. Define three system prompts (user, observe, execute)
3. Implement config builder functions:
   - `build_user_agent_config()`
   - `build_proactive_observe_config()`
   - `build_proactive_execute_config()`
4. Test config creation

**Outcome**: Reusable agent configurations ready for use

---

### Phase 3: User Agent Orchestrator
**Goal**: Implement single-action user agent orchestration

**Actions**:
1. Create `pas/orchestrators/user_agent_orchestrator.py`
2. Implement `UserAgentOrchestrator.__init__()`:
   - Accept BaseAgent, notification system, get_user_tools callback
   - Initialize state tracking

3. Implement `UserAgentOrchestrator.step()`:
   - Poll notifications from notification system
   - Build task from notifications
   - Refresh tools via `get_user_tools()` callback
   - Run `user_agent.run(task)`
   - Return result

4. Implement `build_task_from_notifications()`:
   - Format notifications into task string
   - Follow Meta-ARE's task building pattern

5. Test with standalone BaseAgent:
   - Create simple test scenario
   - Verify tool refresh works
   - Verify notification polling works

**Outcome**: Working user agent orchestrator

---

### Phase 4: Proactive Agent Orchestrator
**Goal**: Implement observe/execute mode switching

**Actions**:
1. Create `pas/orchestrators/proactive_agent_orchestrator.py`
2. Implement `ProactiveAgentOrchestrator.__init__()`:
   - Accept two BaseAgent instances (observe, execute)
   - Accept notification system and callbacks
   - Initialize mode state

3. Implement `ProactiveAgentOrchestrator.step()`:
   - Mode branching logic (observe/awaiting_confirmation/execute)
   - Call appropriate agent based on mode
   - Handle mode transitions

4. Implement helper methods:
   - `build_observation_task()`
   - `build_execution_task()`
   - `check_for_proposal()` - inspect agent logs
   - `check_for_confirmation()` - inspect notifications

5. Test mode transitions:
   - Mock send_message_to_user call
   - Mock accept/reject notifications
   - Verify mode switches correctly

**Outcome**: Working proactive agent orchestrator with mode management

---

### Phase 5: Tool Injection System
**Goal**: Dynamic accept/reject tool injection

**Actions**:
1. Create `pas/apps/system_tools.py`
2. Implement `create_accept_proposal_tool()`:
   - Create Tool instance with callback
   - Decorated with @user_tool and @event_registered

3. Implement `create_reject_proposal_tool()`:
   - Similar to accept tool

4. Implement `inject_confirmation_tools()`:
   - Add tools to AgentUserInterface instance
   - Register in environment

5. Test injection:
   - Create AgentUserInterface instance
   - Inject tools dynamically
   - Verify tools appear in user agent's tool list

**Outcome**: Dynamic tool injection working

---

### Phase 6: Scenario Runner
**Goal**: Main orchestrator tying everything together

**Actions**:
1. Create `pas/scenario_runner/two_agent_runner.py`
2. Implement `TwoAgentScenarioRunner.__init__()`:
   - Accept three agent configs

3. Implement `TwoAgentScenarioRunner.run()`:
   - Setup environment with apps and events
   - Create notification system
   - Build three BaseAgent instances
   - Create orchestrators
   - Main loop: user.step() → proactive.step()
   - Termination logic

4. Implement agent builders:
   - `_build_user_agent()`
   - `_build_observe_agent()`
   - `_build_execute_agent()`

5. Implement helpers:
   - `_inject_accept_reject_tools()`
   - `_check_termination()`

6. Test full scenario:
   - Use simple contacts scenario
   - Verify both agents run
   - Verify oracle tracking works

**Outcome**: Complete two-agent system working end-to-end

---

### Phase 7: Demo Script & Testing
**Goal**: Demonstrate system with realistic scenario

**Actions**:
1. Create `pas/scripts/run_two_agent_demo.py`
2. Port contacts_followup scenario to new system
3. Add comprehensive logging
4. Test with different LLM models
5. Validate oracle satisfaction
6. Debug any notification flow issues

**Outcome**: Polished demo ready for presentation

---

### Phase 8: Documentation & Cleanup
**Goal**: Document new system and remove old code permanently

**Actions**:
1. Update README with new architecture
2. Update API documentation
3. Add usage examples
4. Permanently delete archived old code (if confident)
5. Update scenario generator to use new system (optional)

**Outcome**: Clean, documented codebase

---

## Integration with Meta-ARE

### Key Meta-ARE Components Used

1. **BaseAgent** (`are.simulation.agents.default_agent.base_agent`)
   - Core ReAct loop implementation
   - Tool execution and logging
   - Used for all three agent instances (user, observe, execute)

2. **BaseNotificationSystem** (`are.simulation.notification_system`)
   - Shared message queue for inter-agent communication
   - Converts CompletedEvents to Messages
   - Configured with notified_tools for event broadcasting

3. **Environment** (`are.simulation.environment`)
   - Time management and event processing
   - Event queue and tick-based simulation
   - Extended by StateAwareEnvironmentWrapper

4. **ARESimulationReactBaseAgentConfig** (`are.simulation.agents.are_simulation_agent_config`)
   - Agent configuration with system_prompt
   - LLM engine config
   - Max iterations per agent

5. **Tool** (`are.simulation.tools`)
   - Standard tool interface
   - Decorator support (@user_tool, @app_tool, @event_registered)

6. **CompletedEvent** (`are.simulation.types`)
   - Event tracking for tool execution
   - Used by StateAwareEnvironmentWrapper for state transitions
   - Converted to notifications by notification system

### Notification Flow with @event_registered

```python
# In app code (e.g., ContactsApp)
@user_tool()
@event_registered(operation_type=OperationType.WRITE)
def open_contact(self, contact_id: str) -> str:
    # Implementation
    pass

# When called:
1. Tool executed
2. @event_registered decorator creates CompletedEvent
3. Event added to environment log
4. Environment calls notification_system.handle_event(event)
5. Notification system converts to Message based on config
6. Message added to MessageQueue
7. Both orchestrators can read from queue
```

### Tool Availability Pattern

```python
# In StatefulApp (existing PAS pattern)
class StatefulContactsApp(ContactsApp):
    def get_user_tools(self) -> list[Tool]:
        """Get tools available to user based on current state."""
        return self.current_state.get_available_user_tools()

    def get_tools(self) -> list[Tool]:
        """Get all privileged tools for proactive agent."""
        return extract_all_app_tools(self)

# In StateAwareEnvironmentWrapper
def get_user_tools(self) -> list[Tool]:
    """Aggregate user tools from all apps."""
    tools = []
    for app in self.apps:
        if hasattr(app, 'get_user_tools'):
            tools.extend(app.get_user_tools())
    return tools

def get_tools(self) -> list[Tool]:
    """Aggregate all tools from all apps."""
    tools = []
    for app in self.apps:
        if hasattr(app, 'get_tools'):
            tools.extend(app.get_tools())
    return tools
```

---

## Questions and Decisions Log

### Q1: Should both agents be Meta-ARE BaseAgents?
**Decision**: Yes, with different tool sets and configs. User agent gets @user_tool functions, proactive agent gets @app_tool functions.

### Q2: How should proactive agent observe user actions?
**Decision**: Via shared BaseNotificationSystem. Configure notification system to broadcast all tool calls as events using @event_registered decorator.

### Q3: What orchestration pattern?
**Decision**: Turn-based. Each time step: env.tick() → user_agent.step() → proactive_agent.step()

### Q4: How to limit user agent to one action per turn?
**Decision**: Use BaseAgent with max_iterations=1. Full ReAct cycle (think→act→observe) but terminates after one action.

### Q5: How to switch proactive agent between observe and execute modes?
**Decision**: Two separate BaseAgent instances (observe_agent with max_iterations=1, execute_agent with max_iterations=20). ProactiveAgentOrchestrator manages mode state and selects which agent to run.

### Q6: How to inject accept/reject tools dynamically?
**Decision**: When observe_agent calls send_message_to_user, ProactiveAgentOrchestrator detects this (by checking agent logs), creates accept_proposal/reject_proposal tools, and injects them into AgentUserInterface app instance.

### Q7: Where should orchestrator state live?
**Decision**: In the orchestrators themselves. ProactiveAgentOrchestrator tracks mode (observe/awaiting_confirmation/execute) and pending_goal internally.

### Q8: Should orchestrators have environment reference?
**Decision**: No. Use callbacks (get_user_tools, get_tools, inject_user_tools) to avoid tight coupling.

### Q9: How to define system prompts?
**Decision**: Follow Meta-ARE pattern: define prompts as strings in config module, pass via ARESimulationReactBaseAgentConfig.system_prompt field.

### Q10: Scenario termination conditions?
**Decision**: Two conditions: (1) max_turns reached, OR (2) oracles satisfied. Check both after each turn.

---

## Open Questions

1. **Notification filtering**: Should each orchestrator maintain its own last_read_timestamp, or use a different mechanism to avoid re-processing notifications?

2. **Tool refresh timing**: Should tools be refreshed before every agent turn, or only when state changes are detected?

3. **Error handling**: How should the system handle errors during agent execution (LLM failures, tool execution errors, etc.)?

4. **Logging and debugging**: What additional logging is needed beyond Meta-ARE's BaseAgentLog system?

5. **Performance**: With two separate LLM calls per turn (user + proactive), should we add batching or parallelization?

6. **State transition notifications**: Should state transitions (e.g., ContactsList → ContactDetail) emit notifications, or is tool-call notification sufficient?

---

## Next Steps

1. Review this design document with team
2. Create GitHub issues for each implementation phase
3. Set up development branch for two-agent system
4. Begin Phase 1 implementation (orchestrators)
5. Create unit tests for orchestrator logic
6. Develop simple test scenario for validation

---

## References

- Meta-ARE BaseAgent: `/Users/dnathani/Projects/goalInference/meta-are/are/simulation/agents/default_agent/base_agent.py`
- Meta-ARE ScenarioRunner: `/Users/dnathani/Projects/goalInference/meta-are/are/simulation/scenario_runner.py`
- Meta-ARE NotificationSystem: `/Users/dnathani/Projects/goalInference/meta-are/are/simulation/notification_system.py`
- PAS StateAwareEnvironmentWrapper: `/Users/dnathani/Projects/goalInference/pas/pas/environment.py`
- PAS StatefulApp: `/Users/dnathani/Projects/goalInference/pas/pas/apps/core.py`
