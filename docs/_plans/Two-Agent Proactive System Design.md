# Two-Agent Proactive System Design

**Status**: Active Implementation
**Date**: 2025-10-28 (Reconciled - Single Source of Truth)
**Previous Updates**:
- 2025-10-28: Added MessageType extension design, reconciled documents
- 2025-10-27: Updated with Meta-ARE integration approach
- 2025-10-26: Codebase audit

**Authors**: Design discussion with Claude

**Key Design**: UserAgent and ProactiveAgent are wrapper classes around Meta-ARE BaseAgent(s), similar to ARESimulationAgent pattern. They manage their own notification polling, tool refresh, and mode state. TwoAgentScenarioRunner extends Meta-ARE's ScenarioRunner to orchestrate the turn-based loop.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│              TwoAgentScenarioRunner                             │
│              extends Meta-ARE ScenarioRunner                    │
│  ─────────────────────────────────────────────────────────────  │
│  • Inherits: Scenario parsing, oracle validation, trace export │
│  • Implements: _run_with_two_agents() custom turn-based loop   │
│  • Handles: Dynamic tool injection (accept/reject proposals)   │
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
│              │ │Manages:      │ │  (BaseAgent)         │
│get_user_tools│ │- Notif poll  │ │                      │
│get_tools()   │ │- Tool refresh│ │Manages:              │
│              │ │              │ │- Mode state          │
│              │ │agent_loop()  │ │- Mode transitions    │
└──────────────┘ └──────────────┘ └──────────────────────┘
                        │
                        ▼
        ┌───────────────────────────────┐
        │   Meta-ARE Scenario           │
        │───────────────────────────────│
        │ • apps: list[App]             │
        │ • events: list[AbstractEvent] │
        │   (includes OracleEvent)      │
        │ • validate(env) → Result      │
        └───────────────────────────────┘
```

## Core Components

### 1. StateAwareEnvironmentWrapper (Existing - Completed)

**File**: `pas/environment.py`

**Status**: ✅ COMPLETED (Phases 1 and 1.5)

**Implementation**:
```python
class StateAwareEnvironmentWrapper(Environment):
    def __init__(self, ...):
        self.active_app: StatefulApp | None = None  # Currently open app
        self.background_apps: list[StatefulApp] = []  # App stack for go_back

    def get_user_tools(self) -> list[AppTool]:
        """Get tools available to user agent based on current app state."""
        tools = []
        # System tools always available
        if self.system_app:
            tools.extend(self.system_app.get_user_tools())
        # Active app tools (state-dependent)
        if self.active_app:
            tools.extend(self.active_app.get_user_tools())
        return tools

    def get_tools(self) -> list[AppTool]:
        """Get all privileged tools for proactive agent from all apps."""
        tools = []
        for app in self.apps.values():
            if hasattr(app, 'get_tools'):
                tools.extend(app.get_tools())
        return tools

    def add_to_log(self, event: CompletedEvent):
        """Intercept events for active app tracking and state transitions."""
        # Handle open_app events
        if event.function_name() == "open_app":
            app_name = event.action.resolved_args["app_name"]
            self._switch_active_app(app_name)

        # Trigger state transitions in active app
        if self.active_app:
            self.active_app.handle_state_transition(event)

        # Call parent
        super().add_to_log(event)
```

**Responsibilities**:
- Manage stateful apps and track currently active app
- Trigger state transitions on CompletedEvents
- Provide state-dependent user tools via get_user_tools()
- Provide all privileged tools via get_tools()
- Integration with Meta-ARE notification system

---

### 2. UserAgent ✅ COMPLETED (Phase 3)

**File**: `pas/agents/user/agent.py`

**Design Pattern**: Follows Meta-ARE's `ARESimulationAgent` pattern - receives pre-created BaseAgent plus separate parameters (llm_engine, time_manager, callbacks), then sets properties on the base_agent.

**Constructor Signature**:
```python
def __init__(
    self,
    log_callback: Callable[[BaseAgentLog], None],
    pause_env: Callable[[], None] | None,
    resume_env: Callable[[float], None] | None,
    llm_engine: LLMEngine,
    base_agent: BaseAgent,
    time_manager: TimeManager,
    max_iterations: int = 1,
    max_turns: int | None = None,
    simulated_generation_time_config: SimulatedGenerationTimeConfig | None = None,
)
```

**Key Methods**:
- `prepare_user_agent_run()` - One-time initialization (tools, system prompt, notification system)
- `init_tools(tools)` - Initialize base_agent with filtered user tools
- `init_system_prompt(scenario)` - Replace placeholders in system prompt
- `init_notification_system(ns)` - Set notification system on base_agent
- `get_notifications()` - ✅ COMPLETED - Poll notification system and filter by type
- `build_task_from_notifications()` - ✅ COMPLETED - Build task from agent messages
- `agent_loop()` - Execute agent loop with notification polling (PENDING)

**Notification Handling**:
UserAgent receives three types of notifications:
1. **AGENT_MESSAGE** (from ProactiveAgent proposals via send_message_to_user)
2. **ENVIRONMENT_NOTIFICATION** (from environment events like emails)
3. **ENVIRONMENT_STOP** (termination signals)

**Message Formatting** (Custom role_dict and message_dict):
```python
DEFAULT_USER_STEP_2_ROLE = {
    # ... all default keys from Meta-ARE except "agent_user_interface" ...
    "agent_message": MessageRole.USER,  # New: ProactiveAgent proposals
    "environment_notifications": MessageRole.USER,  # Keep: Environment events
}

DEFAULT_USER_STEP_2_MESSAGE = {
    # ... all default keys from Meta-ARE except "agent_user_interface" ...
    "agent_message": "Proactive agent messages:\n***\n{content}\n***\n",
    "environment_notifications": "Environment notifications updates:\n***\n{content}\n***\n",
}
```

**Important Notes**:
- Tools are **dynamic** - refreshed every turn based on active app
- Uses custom preprocessing step to pull AGENT_MESSAGE notifications → AgentMessageLog
- No need for `remove_aui_irrelevant_tools()` - message tools are `@app_tool`, not `@user_tool`

---

### 3. ProactiveAgent ✅ COMPLETED (Phase 4)

**File**: `pas/agents/proactive/agent.py`

**Design Pattern**: Follows Meta-ARE's `ARESimulationAgent` pattern - receives TWO pre-created BaseAgent instances (observe + execute) plus separate parameters, then sets properties on both agents.

**Constructor Signature**:
```python
def __init__(
    self,
    log_callback: Callable[[BaseAgentLog], None],
    pause_env: Callable[[], None] | None,
    resume_env: Callable[[float], None] | None,
    observe_llm_engine: LLMEngine,
    observe_agent: BaseAgent,
    execute_llm_engine: LLMEngine,
    execute_agent: BaseAgent,
    time_manager: TimeManager,
    tools: list[Tool] | None = None,
    observe_max_iterations: int = 1,
    execute_max_iterations: int = 20,
    max_turns: int | None = None,
    simulated_generation_time_config: SimulatedGenerationTimeConfig | None = None,
)
```

**Internal State**:
- `mode`: ProactiveAgentMode enum ("observe" | "awaiting_confirmation" | "execute")
- `pending_goal`: Stored goal when awaiting confirmation

**Key Methods**:
- `prepare_proactive_agent_run()` - One-time initialization (tools, system prompts, notification system)
- `init_tools(scenario)` - Initialize tools for both agents (observe gets send_message_to_user only, execute gets all)
- `init_observe_system_prompt(scenario)` - Replace placeholders in observe system prompt
- `init_execute_system_prompt(scenario)` - Replace placeholders in execute system prompt
- `init_notification_system(ns)` - Set notification system on both agents
- `remove_aui_irrelevant_tools()` - Configure AgentUserInterface (set wait_for_user_response=False, remove redundant message tools)
- `get_notifications()` - Poll notification system and filter by type (USER_MESSAGE, ENVIRONMENT_NOTIFICATION, ENVIRONMENT_STOP)
- `build_task_from_notifications()` - Build task string from user messages
- `agent_loop()` - Execute one proactive agent turn with mode branching (returns `str | MMObservation | None`)
- `check_for_proposal()` - Check if observe_agent called send_message_to_user
- `_check_confirmation()` - Private helper: Check notifications for accept/reject
- `_run_observe_mode()` - Private helper: Run observe agent and check for proposals
- `_run_execute_mode()` - Private helper: Run execute agent with pending goal

**Responsibilities**:
- Manage proactive agent state (observe/awaiting_confirmation/execute)
- Execute observe agent (BaseAgent.run() with max_iterations=1)
- Execute execute agent (BaseAgent.run() with max_iterations=20)
- Detect send_message_to_user calls in agent logs
- Detect user confirmation (accept/reject) and transition modes
- Build appropriate task prompts for each mode

**Important Notes**:
- **Tools are static** - ProactiveAgent gets ALL privileged tools from all apps (via `env.get_tools()`) regardless of state. Unlike UserAgent, no tool refresh is needed because the tool set doesn't change.
- **Mode state is accessible** - TwoAgentScenarioRunner can check `proactive_agent.mode` to detect when proposals are made and when execution completes
- **Return type** - `agent_loop()` returns `str | MMObservation | None` (BaseAgent.run() result), not status dict
- **Tool injection** - ProactiveAgent does NOT inject accept/reject tools; that's handled by TwoAgentScenarioRunner by checking `proactive_agent.mode`

---

### 4. TwoAgentScenarioRunner ✅ COMPLETED (Phase 6)

**File**: `pas/scenario_runner.py`

**Class Definition**:
```python
class TwoAgentScenarioRunner(ScenarioRunner):
    """Extends Meta-ARE's ScenarioRunner for two-agent proactive system.

    Inherits:
        - Scenario parsing (JSON → Scenario object)
        - Oracle validation (OracleEvent checking via scenario.validate())
        - Trace export
        - Environment setup and teardown
        - Agent configuration infrastructure

    Implements:
        - Custom two-agent turn-based loop (_run_with_two_agents)
        - UserAgent and ProactiveAgent orchestration
        - Dynamic tool injection for accept/reject
    """

    def _run_with_two_agents(
        self,
        scenario_id: str,
        scenario: Scenario,
        env: StateAwareEnvironmentWrapper,
        user_config: ARESimulationReactBaseAgentConfig,
        proactive_observe_config: ARESimulationReactBaseAgentConfig,
        proactive_execute_config: ARESimulationReactBaseAgentConfig,
        max_turns: int | None = None,
    ) -> ScenarioValidationResult:
        """Run scenario with two-agent turn-based loop.

        Flow:
        1. Build three BaseAgent instances (user, observe, execute)
        2. Wrap in UserAgent and ProactiveAgent
        3. Turn-based loop:
            - user_agent.agent_loop()
            - proactive_agent.agent_loop()
            - If proactive made proposal: inject accept/reject tools
            - Check termination (max_turns or env stopped)
        4. Validate using scenario.validate(env) (handles OracleEvent checking)
        5. Return ScenarioValidationResult
        """
        pass
```

**Responsibilities**:
- Implement `_run_with_two_agents()` method with custom turn-based logic
- Build BaseAgent instances with system prompts
- Create UserAgent and ProactiveAgent with raw parameters
- **Handle dynamic tool injection** (accept_proposal/reject_proposal into AgentUserInterface)
- Orchestrate turn-based loop: user_agent.agent_loop() → proactive_agent.agent_loop()
- Detect when ProactiveAgent makes proposal → inject accept/reject tools via environment
- Leverage parent class for everything else

---

### 5. Agent System Prompts (Completed - Phase 2)

**Status**: ✅ COMPLETED

**User Agent Prompts**: `pas/agents/user/prompts/`
- `system_prompt.py`: Main system prompt with modular components
- `notification_system.py`: Notification policy prompt

**Proactive Agent Prompts**: `pas/agents/proactive/prompts/`
- `observe_prompt.py`: Observation mode system prompt
- `execute_prompt.py`: Execution mode system prompt
- `notification_system.py`: Notification policy prompts for both modes

---

### 6. PAS AgentUserInterface and MessageType Extension

**Approach**:
1. Extend Meta-ARE's MessageType enum with new AGENT_MESSAGE type for ProactiveAgent proposals
2. Extend Meta-ARE's AgentUserInterface with accept_proposal/reject_proposal tools
3. Extend Meta-ARE's BaseNotificationSystem to handle send_message_to_user → AGENT_MESSAGE

**Files**:
- `pas/notification_system.py` - PASMessageType enum (Phase 3.1 ✅) and PASNotificationSystem (Phase 6.5)
- `pas/apps/agent_ui/app.py` - PASAgentUserInterface (Phase 5)
- `pas/agents/agent_log.py` - AgentMessageLog class (Phase 6.5)
- `pas/agents/user/preprocessing.py` - User agent preprocessing function (Phase 7 - manual in demo)
- `pas/agents/agent_factory.py` - Agent factory functions (Phase 8 - optional polish)

**Notification Flow Architecture**:

1. **ProactiveAgent → UserAgent** (proposal):
   - ProactiveAgent calls `send_message_to_user(content)` from AgentUserInterface
   - With `wait_for_user_response = False` → non-blocking, terminates turn
   - PASNotificationSystem converts event → **`MessageType.AGENT_MESSAGE`** (new custom type)
   - UserAgent preprocessing pulls AGENT_MESSAGE → creates `AgentMessageLog`
   - UserAgent receives formatted via custom message_dict template: "Proactive agent messages:\n***\n{content}\n***\n"

2. **UserAgent → ProactiveAgent** (response):
   - UserAgent calls `accept_proposal()` or `reject_proposal()` (methods on PASAgentUserInterface)
   - **These methods internally call `send_message_to_agent()`**
   - `send_message_to_agent` has special case in notification system → creates `MessageType.USER_MESSAGE`
   - ProactiveAgent receives via `get_notifications()` in `new_user_messages`

3. **Environment → UserAgent** (environment events):
   - Environment events (emails, messages, etc.) configured in `notified_tools`
   - Creates **`MessageType.ENVIRONMENT_NOTIFICATION`** (existing Meta-ARE type)
   - UserAgent preprocessing pulls ENVIRONMENT_NOTIFICATION → creates `EnvironmentNotificationLog`
   - UserAgent receives formatted via existing template: "Environment notifications updates:\n***\n{content}\n***\n"

**Configuration needed**:
```python
# In notification system config
notified_tools = {
    "AgentUserInterface": ["send_message_to_user"]  # Triggers AGENT_MESSAGE conversion
    # send_message_to_agent automatically creates USER_MESSAGE (special case in Meta-ARE)
    "Email": ["receive_email"],  # Example env notification
}
```

**Implementation Timeline**:
- **Phase 3.1 ✅ COMPLETED**: Created PASMessageType enum in pas/notification_system.py, fixed role_dict/message_dict in UserAgent
- **Phase 6.5 (Before running code)**: Implement PASNotificationSystem and AgentMessageLog
- **Phase 7 (Demo script)**: Manual preprocessing function for UserAgent BaseAgent
- **Phase 8 (Polish)**: Agent factory for automated BaseAgent creation

**PASAgentUserInterface Implementation**:
```python
class PASAgentUserInterface(AgentUserInterface):
    """PAS extension of Meta-ARE's AgentUserInterface.

    Adds accept_proposal and reject_proposal tools for responding to ProactiveAgent.
    """

    @user_tool()
    @event_registered(operation_type=OperationType.WRITE, event_type=EventType.USER)
    def accept_proposal(self, reason: str = "") -> str:
        """Accept the proactive assistant's proposal."""
        content = f"[ACCEPT]: {reason}" if reason else "[ACCEPT]"
        return self.send_message_to_agent(content=content)

    @user_tool()
    @event_registered(operation_type=OperationType.WRITE, event_type=EventType.USER)
    def reject_proposal(self, reason: str = "") -> str:
        """Reject the proactive assistant's proposal."""
        content = f"[REJECT]: {reason}" if reason else "[REJECT]"
        return self.send_message_to_agent(content=content)
```

---

### 7. UserAgent Context Injection via Pre-steps

**Motivation**: UserAgent needs real-time awareness of (1) what actions it can currently take, and (2) where it is in the app navigation hierarchy. This context must update dynamically as the user navigates between apps and app states.

**Why Not Use Task or System Prompt?**
- **Task**: Reserved for agent messages and notifications (what the agent should *do*)
- **System Prompt**: Static, set once at initialization (cannot reflect dynamic state changes)
- **Solution**: Use Meta-ARE's `conditional_pre_steps` mechanism to inject context as log entries before each agent iteration

**Architecture Pattern**:
```
ScenarioRunner (has env)
    → passes context as parameters
    → UserAgent.agent_loop(current_tools, current_app, current_state)
    → stores in BaseAgent.custom_state
    → Pre-step reads from custom_state
    → appends logs before BaseAgent.run()
```

**Implementation Components**:

1. **Custom Log Types** (`pas/agents/agent_log.py`):
   - `AvailableToolsLog`: Lists all currently available tools with descriptions
   - `CurrentAppStateLog`: Shows active app and current navigation state

2. **Message Formatting** (`pas/agents/user/agent.py:50-53`):
   ```python
   DEFAULT_USER_STEP_2_ROLE["available_tools"] = MessageRole.USER
   DEFAULT_USER_STEP_2_ROLE["current_app_state"] = MessageRole.USER
   DEFAULT_USER_STEP_2_MESSAGE["available_tools"] = "Available tools:\n***\n{content}\n***\n"
   DEFAULT_USER_STEP_2_MESSAGE["current_app_state"] = "Current app state:\n***\n{content}\n***\n"
   ```

3. **Pre-step Function** (`pas/agents/user/steps.py:23-83`):
   ```python
   def pull_notifications_and_tools(agent: BaseAgent) -> None:
       # Pull notifications (AGENT_MESSAGE, ENVIRONMENT_NOTIFICATION)
       # ... notification handling code ...

       # Inject available tools context
       current_tools = list(agent.tools.values())
       if current_tools:
           toolbox = Toolbox(tools=current_tools)
           tool_descriptions = toolbox.show_tool_descriptions(DEFAULT_TOOL_DESCRIPTION_TEMPLATE)
           agent.append_agent_log(AvailableToolsLog(content=tool_descriptions, ...))

       # Inject app state context
       current_app = agent.custom_state.get("current_app")
       current_state = agent.custom_state.get("current_state")
       if current_app:
           app_info = f"Current active app: {current_app.name}\n"
           if current_state:
               app_info += f"Current active state: {current_state.name}\n"
           agent.append_agent_log(CurrentAppStateLog(content=app_info, ...))
   ```

4. **Context Passing** (`pas/scenario_runner.py:231-235`):
   ```python
   user_tools = env.get_user_tools()
   current_app = env.active_app
   current_state = current_app.current_state if current_app else None

   user_result = user_agent.agent_loop(
       user_tools,
       current_app=current_app,
       current_state=current_state
   )
   ```

5. **Context Storage** (`pas/agents/user/agent.py:agent_loop()`):
   ```python
   def agent_loop(self, current_tools, current_app=None, current_state=None):
       # Store in custom_state for pre-step access
       self.react_agent.custom_state["current_app"] = current_app
       self.react_agent.custom_state["current_state"] = current_state
       # ... rest of method
   ```

**Agent's View** (formatted by message_dict):
```
Available tools:
***
- StatefulContactsApp__list_contacts: Lists all contacts...
    Takes inputs: {}
    Returns an output of type: string

- StatefulContactsApp__open_contact: Opens a specific contact...
    Takes inputs: {'contact_id': {'type': 'string'}}
    Returns an output of type: string
***

Current app state:
***
Current active app: StatefulContactsApp
Current active state: ContactsList
***

Proactive agent messages:
***
Would you like me to send a message to Alice?
***
```

**Key Design Decisions**:

1. **Why use `Toolbox.show_tool_descriptions()`?**
   - Provides complete tool information (name, description, inputs, output types)
   - Uses Meta-ARE's standard Jinja2 template system
   - Consistent with how system prompts describe tools

2. **Why store app/state in `custom_state`?**
   - Pre-steps only receive `agent: BaseAgent` parameter
   - `custom_state` is Meta-ARE's dict for agent-specific data
   - Alternative would require environment reference (breaks encapsulation)

3. **Why pass context through scenario_runner?**
   - Scenario_runner has environment reference
   - Maintains separation: UserAgent doesn't depend on environment
   - Follows existing pattern (current_tools already passed this way)

4. **When does context update?**
   - Every turn before `UserAgent.agent_loop()` call
   - Tools refresh: After state transitions (via `env.get_user_tools()`)
   - App/state refresh: After navigation actions (env tracks `active_app`)

**Benefits**:
- Agent always sees current tool capabilities (crucial for state-based navigation)
- Agent knows location in app hierarchy (improves decision-making)
- Context updates automatically with every turn (no manual refresh needed)
- Clean separation: context passing vs context formatting

---

## Data Flow

### Single Turn Execution Flow

```
Turn N:

1. Environment.tick()
   └─ Process events at time T
   └─ Emit notifications via notification_system

2. UserAgent.agent_loop()
   ├─ Get notifications (AGENT_MESSAGE + ENVIRONMENT_NOTIFICATION + ENVIRONMENT_STOP)
   ├─ Build task: "Proactive agent: 'Shall I reply to Alice?' Environment: New email from Bob"
   ├─ Refresh tools: base_agent.tools = env.get_user_tools()
   ├─ Run: base_agent.run(task, max_iterations=1)
   │   └─ BaseAgent executes: Think → Act (e.g., accept_proposal)
   └─ Return result

3. ProactiveAgent.agent_loop()
   ├─ Get notifications (USER_MESSAGE + ENVIRONMENT_NOTIFICATION + ENVIRONMENT_STOP)
   ├─ Check mode (observe | awaiting_confirmation | execute)
   │
   ├─ If mode == "observe":
   │   ├─ Build task from user messages (env notifications handled by BaseAgent preprocessing)
   │   ├─ Run: observe_agent.run(task, max_iterations=1)
   │   ├─ Check logs: did agent call send_message_to_user?
   │   ├─ If yes: mode = "awaiting_confirmation", pending_goal = proposal content
   │   └─ Return BaseAgent result (str | MMObservation | None)
   │
   ├─ If mode == "awaiting_confirmation":
   │   ├─ Check notifications for accept/reject
   │   ├─ If accept: mode = "execute", run execute_agent immediately in same turn
   │   ├─ If reject: mode = "observe"
   │   └─ Return BaseAgent result or None
   │
   └─ If mode == "execute":
       ├─ Build task: "Proposed Goal: {pending_goal}\nUser reply: {user_message}"
       ├─ Run: execute_agent.run(task, max_iterations=20)
       ├─ mode = "observe", pending_goal = None
       └─ Return BaseAgent result

4. TwoAgentScenarioRunner (orchestration logic):
   ├─ After proactive_agent.agent_loop(), check proactive_agent.mode:
   │   └─ If mode == "awaiting_confirmation": inject accept_proposal/reject_proposal tools
   ├─ Check termination (max_turns or env stopped)
   └─ Loop back to step 1
```

---

## Implementation Phases

### Phase 0: Codebase Cleanup ✅ COMPLETED
**Status**: Old code archived to `pas/_archives/`

### Phase 1: Environment Extensions - Tool Discovery ✅ COMPLETED
**Status**: get_user_tools() and get_tools() implemented

### Phase 1.5: Active App Tracking ✅ COMPLETED
**Status**: active_app tracking, open_app logic moved to environment

### Phase 2: Agent System Prompts ✅ COMPLETED
**Status**: All prompts implemented in pas/agents/*/prompts/

### Phase 3: UserAgent ✅ COMPLETED
**Status**:
- ✅ Phase 3.1: Created PASMessageType enum in notification_system.py, fixed role_dict/message_dict
- ✅ Phase 3.2: get_notifications() completed
- ✅ Phase 3.3: build_task_from_notifications() completed
- ✅ Phase 3.4: agent_loop() completed
- ✅ Phase 3.5: Comprehensive tests (28 tests)

### Phase 4: ProactiveAgent ✅ COMPLETED
**Status**: All methods implemented in pas/agents/proactive/agent.py
- ✅ `__init__()` - Initialize with two BaseAgent instances
- ✅ `init_tools()` - Filter tools for observe/execute agents
- ✅ `init_observe_system_prompt()` - Replace placeholders
- ✅ `init_execute_system_prompt()` - Replace placeholders
- ✅ `prepare_proactive_agent_run()` - One-time initialization
- ✅ `remove_aui_irrelevant_tools()` - Configure AgentUserInterface
- ✅ `get_notifications()` - Poll and filter notifications
- ✅ `build_task_from_notifications()` - Build task from user messages
- ✅ `check_for_proposal()` - Detect send_message_to_user calls
- ✅ `agent_loop()` - Mode-based execution with branching
- ✅ `_check_confirmation()` - Private helper for accept/reject
- ✅ `_run_observe_mode()` - Private helper for observe mode
- ✅ `_run_execute_mode()` - Private helper for execute mode

### Phase 5: PASAgentUserInterface ✅ COMPLETED
**Status**: accept_proposal/reject_proposal tools implemented
- ✅ Removed StatefulApp inheritance and state management
- ✅ Implemented `accept_proposal(reason: str = "")` with `[ACCEPT]` format
- ✅ Implemented `reject_proposal(reason: str = "")` with `[REJECT]` format
- ✅ Both methods call `send_message_to_agent()` with tag prefixes
- ✅ Clean 64-line implementation with proper decorators

### Phase 6: TwoAgentScenarioRunner
**Status**: Pending - main orchestration loop

### Phase 6.5: Notification System Extensions ✅ COMPLETED
**Status**: PASNotificationSystem, AgentMessageLog implemented

### Phase 7: Demo Script
**Status**: Pending - manual BaseAgent creation, preprocessing function

### Phase 8: Agent Factory (Optional Polish)
**Status**: Pending - automated BaseAgent creation

---

## North Star Phase: Natural User Behavior Simulation

**Status**: Future Enhancement (post-Phase 8)

**Vision**: Transform UserAgent from a purely **reactive** agent (only acts when receiving notifications) to a **proactive** agent that exhibits spontaneous, realistic user behavior even without external triggers.

**Motivation**:
- Real users don't sit idle waiting for ProactiveAgent proposals - they browse feeds, check apps, send messages, scroll through photos, etc.
- Spontaneous behavior adds realistic noise to the system and tests ProactiveAgent's ability to observe and infer goals amid distractions
- Makes simulation more ecologically valid for goal inference research

**Current Behavior** (Phase 3 implementation):
```python
# In agent_loop(), line 326-328
else:
    logger.debug("No new messages from proactive agent or environment")
    time.sleep(1)  # Avoid busy looping
```

When no notifications exist, UserAgent sleeps and waits passively.

**Target Behavior**:
UserAgent spontaneously performs random actions even when no notifications arrive:
- Browse contact list
- Check calendar
- Read old messages
- Scroll through apps
- Open and close apps
- View notifications
- etc.

**Implementation Approach**:

1. **Add spontaneous action probability parameter** (`spontaneous_action_probability: float`):
   - Range: [0.0, 1.0]
   - 0.0 = current behavior (sleep when idle)
   - 1.0 = always take spontaneous action when idle
   - Controlled via CLI parameter or config

2. **Define spontaneous action policy**:
   - **Option A**: Uniform random sampling from available user tools
   - **Option B**: Context-aware weighted sampling (e.g., favor browsing over destructive actions)
   - **Option C**: LLM-driven spontaneous behavior (ask UserAgent "what would you naturally do now?")

3. **Safety constraints**:
   - Blacklist destructive tools (delete_contact, delete_event, etc.) from spontaneous actions
   - Whitelist "safe browsing" actions (list_contacts, view_calendar, check_notifications)
   - Add validation to prevent data corruption in scenarios with oracle expectations

4. **Modified agent_loop() logic**:
```python
else:
    logger.debug("No new messages from proactive agent or environment")
    if random.random() < self.spontaneous_action_probability:
        # Perform spontaneous action
        spontaneous_tool = self._select_spontaneous_action()
        logger.debug(f"UserAgent performing spontaneous action: {spontaneous_tool}")
        result = self.react_agent.run(
            task=f"Perform spontaneous exploration: {spontaneous_tool}",
            hint=None,
            reset=False
        )
    else:
        time.sleep(1)  # Original behavior
```

5. **Evaluation considerations**:
   - Track spontaneous actions separately in logs for analysis
   - Compare goal inference accuracy with/without spontaneous behavior
   - Measure scenario completion rates with noisy user behavior
   - Analyze how ProactiveAgent adapts to distractions

**Design Questions to Resolve**:
- Should spontaneous actions increment turn_count?
- Should spontaneous actions trigger ProactiveAgent observations?
- How to balance realism vs. scenario completion time?
- Should spontaneous behavior be scenario-specific or global?

**Reference**: Original observation in UserAgent.agent_loop() comment (agent.py:326)

---

## Questions and Decisions Log

### Q1: Should both agents be Meta-ARE BaseAgents?
**Decision**: Yes, with different tool sets and configs. User agent gets @user_tool functions, proactive agent gets @app_tool functions.

### Q2: How should proactive agent observe user actions?
**Decision**: Via shared BaseNotificationSystem. Configure notification system to broadcast all tool calls as events using @event_registered decorator.

### Q3: What orchestration pattern?
**Decision**: Turn-based. Each time step: user_agent.agent_loop() → proactive_agent.agent_loop()

### Q4: How to limit user agent to one action per turn?
**Decision**: Use BaseAgent with max_iterations=1. Full ReAct cycle (think→act→observe) but terminates after one action.

### Q5: How to switch proactive agent between observe and execute modes?
**Decision**: Two separate BaseAgent instances (observe_agent with max_iterations=1, execute_agent with max_iterations=20). ProactiveAgent manages mode state and selects which agent to run.

### Q6: How to inject accept/reject tools dynamically?
**Decision**: When observe_agent calls send_message_to_user, ProactiveAgent detects this (by checking agent logs) and returns status to TwoAgentScenarioRunner. ScenarioRunner injects accept_proposal/reject_proposal tools into AgentUserInterface app instance.

### Q7: Where should mode state live?
**Decision**: In ProactiveAgent class itself. ProactiveAgent tracks mode (observe/awaiting_confirmation/execute) and pending_goal internally.

### Q8: Should agents have environment reference?
**Decision**: No direct reference. UserAgent and ProactiveAgent receive pre-built BaseAgent instances. TwoAgentScenarioRunner handles tool injection via environment.

### Q9: How to define system prompts?
**Decision**: Follow Meta-ARE pattern: define prompts in agent-specific prompt files, use as system_prompt when building BaseAgent.

### Q10: Scenario termination conditions?
**Decision**: Two conditions: (1) max_turns reached, OR (2) environment stopped. Oracle validation happens after completion via scenario.validate().

### Q11: Should UserAgent's notification prompt list specific notified tools?
**Decision**: No. Always use generic notification prompt that doesn't list specific tool names because:
- Tool availability is state-dependent and communicated via BaseAgent's `tools` parameter (passed to LLM)
- Listing specific tool names would leak information about unreached app states
- The notification policy describes event delivery behavior (what you'll be notified about), not tool availability (what you can call)
- The generic prompt maintains realistic user simulation by not revealing unnavigated features

**Implementation**: `pas/agents/user/prompts/notification_system.py` - `get_notification_system_prompt()` always returns generic `USER_AGENT_NOTIFICATION_PROMPT`, ignoring the `notification_system.config.notified_tools` configuration.

### Q12: How does scenario.get_user_tools() work with StatefulApps?
**Answer**: `scenario.get_user_tools()` returns **state-dependent tools only**, not all possible tools. Here's the call chain:
1. `Scenario.get_user_tools()` calls `app.get_user_tools()` for each app
2. `StatefulApp.get_user_tools()` delegates to `self.current_state.get_available_actions()`
3. Result: Only tools from the current state of each app

**Key insight**: Whether called via `scenario.get_user_tools()` or `environment.get_user_tools()`, the result is always state-aware because StatefulApps internally delegate to their current state.

### Q13: What is the difference between iterations and turns in Meta-ARE?
**Answer**:
- **Iteration**: One ReAct cycle (think→act→observe) within a single BaseAgent.run() call. Controlled by `max_iterations` parameter on BaseAgent.
- **Turn**: One complete BaseAgent.run() execution (which may contain multiple iterations). In Meta-ARE agent_loop, "turns" tracks how many times BaseAgent.run() has been called.

**Key insight**: UserAgent uses max_iterations=1 (one action per turn). ProactiveAgent uses max_iterations=1 for observe mode, max_iterations=20 for execute mode.

**Terminology**: We renamed UserAgent.step() to UserAgent.agent_loop() because it executes a full turn (BaseAgent.run()), not just one iteration.

### Q14: How do MessageTypes map to log types in UserAgent?
**Answer**: UserAgent receives three MessageType notifications, which preprocessing converts to log entries:
1. **MessageType.AGENT_MESSAGE** → `AgentMessageLog` → log type "agent_message" → template: "Proactive agent messages:\n***\n{content}\n***\n"
2. **MessageType.ENVIRONMENT_NOTIFICATION** → `EnvironmentNotificationLog` → log type "environment_notifications" → template: "Environment notifications updates:\n***\n{content}\n***\n"
3. **MessageType.ENVIRONMENT_STOP** → (handled separately, causes termination)

**Key insight**: UserAgent does NOT receive `MessageType.USER_MESSAGE` (that's for ProactiveAgent receiving accept/reject responses). Therefore, UserAgent's custom role_dict/message_dict removes "agent_user_interface" and adds "agent_message".

**Implementation**:
- `pas/notification_system.py` extends `MessageType` with `AGENT_MESSAGE` and implements`PASNotificationSystem.convert_to_message()` with special case for send_message_to_user → AGENT_MESSAGE
- `pas/agents/agent_log.py` defines `AgentMessageLog` class
- UserAgent preprocessing function (in demo script for Phase 7) pulls AGENT_MESSAGE notifications and creates AgentMessageLog entries

---

## Implementation Learnings

### Test Writing Strategy (Phase 4.1)
**Key insight**: Don't over-mock when writing unit tests.

**Wrong approach**:
- Mock everything including internal methods
- Test Meta-ARE components
- Check prompt initialization details

**Correct approach**:
- Mock only external dependencies (BaseAgent.run(), notification_system.message_queue)
- Let internal methods execute naturally (check_for_proposal, _check_confirmation, etc.)
- Test OUR logic, not Meta-ARE's logic
- Focus on high-probability-of-failure scenarios
- Example: Don't test prompt initialization, don't test Meta-ARE's BaseAgent behavior

**Reference**: ProactiveAgent tests (tests/agents/proactive/test_agent.py) - 17 focused tests

### ProactiveAgent Bug Fix (Phase 4.1)
**Issue**: Tuple unpacking bug in `_check_confirmation()` handling.

**Bug** (agent.py:404):
```python
accepted = self._check_confirmation(new_user_messages)  # Gets entire tuple
if accepted:  # Tuple (False, None) is still truthy!
```

**Fix**:
```python
accepted, _ = self._check_confirmation(new_user_messages)  # Properly unpack
if accepted:  # Now checks the actual boolean value
```

**Root cause**: Method returns `tuple[bool, str | None]`, but code wasn't unpacking. Non-empty tuples are always truthy in Python, so `(False, None)` evaluated to True.

### PASAgentUserInterface Simplified Design (Phase 5)
**Key decision**: Remove all state management - keep it simple.

**Removed**:
- `ProactiveProposal` dataclass
- `pending_proposal` and `proposal_history` instance variables
- `send_proposal_to_user()` method (ProactiveAgent uses parent's `send_message_to_user()`)
- `get_pending_proposal()` method
- StatefulApp inheritance (not needed)

**Final implementation**:
- Two simple methods: `accept_proposal(reason)` and `reject_proposal(reason)`
- Both just call `self.send_message_to_agent(content=formatted_message)`
- Use `with disable_events():` wrapper to prevent double event registration
- Use `@type_check` decorator for parameter validation
- Format: `"[ACCEPT]: {reason}"` or `"[ACCEPT]"` (tags as PREFIXES, not inline)

**Reference**: pas/apps/agent_ui/app.py (64 lines total, very clean)

### Message Format Clarification
**Critical**: Tags are PREFIXES at the start of messages, not inline.

**Correct format**:
- `"[ACCEPT] yes, please go ahead with that"`
- `"[REJECT] no, I don't want that"`

**Wrong format** (tags inline):
- `"yes, I [ACCEPT] this proposal"` ❌

**Why**: Tags are injected by `accept_proposal()` and `reject_proposal()` tools, not typed by user. User's actual message (in any language) comes after the tag.

### Phase 6 Implementation Discoveries (TwoAgentScenarioRunner)
**Status**: Implementation in progress (pas/scenario_runner.py)

**Critical Discoveries**:

1. **UserAgent.agent_loop() requires `current_tools` parameter**
   - NOT optional! Signature: `agent_loop(current_tools: list[AppTool], max_turns, initial_agent_logs)`
   - Must refresh tools BEFORE each user turn: `user_tools = env.get_user_tools()`
   - Pass to agent: `user_agent.agent_loop(current_tools=user_tools, max_turns=1)`
   - Tool refresh is CRITICAL for state-dependent navigation

2. **_run_with_two_agents() returns tuple for export**
   - Return: `(validation_result, user_agent, proactive_agent)`
   - Enables accessing agent properties for trace export:
     - UserAgent: `.model`, `.agent_framework`
     - ProactiveAgent: `.observe_model`, `.execute_model`, `.agent_framework`

3. **Two-agent trace export format**
   - model_id: `"user:{model}|observe:{model}|execute:{model}"`
   - agent_id: `"user:{framework}|proactive:{framework}"`
   - Uses Meta-ARE's JsonScenarioExporter

4. **max_turns semantics**
   - Outer loop `max_turns`: Number of full cycles (user turn + proactive turn)
   - UserAgent.agent_loop() `max_turns=1`: Execute exactly one turn (one task execution)

5. **Exception handling requires None checks**
   - If exception during agent creation, agents are None
   - Must check `if user_agent is not None and proactive_agent is not None` before export

6. **Environment setup details**
   - Use `PasNotificationSystem(verbosity=VerbosityLevel.HIGH)` not `VerboseNotificationSystem()`
   - Set `exit_when_no_events=False` - don't exit when event queue empty
   - Start with `env.run(scenario, wait_for_end=False)` - non-blocking
   - Always call `env.stop()` in finally/cleanup

**Implemented Methods**:
- `run_pas_scenario()` - Public API with logging setup, timing, result formatting
- `_run_pas_scenario()` - Environment setup, orchestration, trace export
- `_run_with_two_agents()` - Core turn-based loop
- `_export_pas_trace()` - Two-agent trace export

**Still TODO for Phase 6**:
- Implement PAS-specific config class (currently using self.config which doesn't exist)
- Add scenario loading from string (currently raises NotImplementedError)
- Add judge-only mode support
- Testing

### Phase 6.5 Implementation Discoveries (Notification System & Logs)
**Status**: ✅ COMPLETED

**Critical Discoveries**:

1. **PASNotificationSystem architecture**
   - Inherits from `BaseNotificationSystem` (not `VerboseNotificationSystem` as initially planned)
   - Only overrides `convert_to_message()` for PAS-specific cases
   - Falls back to parent for all standard cases (send_message_to_agent, environment notifications)
   - Uses `AUIMessage` wrapper with proper `Sender.AGENT` / `Sender.USER` enum
   - Attachment support for both AGENT_MESSAGE and USER_MESSAGE

2. **Prefix logic moved to notification system (eliminates duplication)**
   - Originally: Tools added `[ACCEPT]:`/`[REJECT]:` prefix → Notification system reconstructed it
   - Now: Tools pass raw content → Notification system adds prefix based on function_name
   - Single source of truth for message formatting
   - PASAgentUserInterface tools:
     - `accept_proposal(content)` - just passes through
     - `reject_proposal(content)` - just passes through
   - PASNotificationSystem adds prefixes:
     - `accept_proposal` → `"[ACCEPT]: {content}"`
     - `reject_proposal` → `"[REJECT]: {content}"`

3. **AgentMessageLog and PASAgentLog design**
   - PASAgentLog subclass approach (avoids monkey-patching)
   - Extends `BaseAgentLog.from_dict()` with extended log_type_map
   - Meta-ARE uses `"log_type"` key in serialization (not `"type"`)
   - Uses `pop()` not `get()` - metadata keys must be removed before passing to constructor
   - Type hints remain `BaseAgentLog` - no changes needed to existing code
   - File: `pas/agents/agent_log.py`

4. **ProactiveAgent doesn't need custom log preprocessing**
   - TaskLog already handles USER_MESSAGE from UserAgent (accept/reject responses)
   - BaseAgent.run() automatically creates TaskLog from task parameter
   - No preprocessing step needed for ProactiveAgent

**Implemented Components**:
- `PASNotificationSystem` (pas/notification_system.py)
  - `convert_to_message()` override with AGENT_MESSAGE and USER_MESSAGE handling
- `AgentMessageLog` (pas/agents/agent_log.py)
  - Log type for ProactiveAgent proposals to UserAgent
- `AvailableToolsLog` (pas/agents/agent_log.py)
  - Log type for current tool descriptions (injected by pre-step)
- `CurrentAppStateLog` (pas/agents/agent_log.py)
  - Log type for current app and state context (injected by pre-step)
- `PASAgentLog` (pas/agents/agent_log.py)
  - Extended log type map with `from_dict()` override for all PAS log types
- Updated `PASAgentUserInterface` (pas/apps/proactive_aui.py)
  - Simplified tools by removing prefix duplication

---

## Phase 8: Notification Formatting System (In Progress)

**Status**: IN PROGRESS (2025-11-04)
**Context**: Testing demo script revealed need for formatted notifications and user action observation

### Background: The Problem

During demo testing, we discovered two critical issues:

1. **User actions poorly formatted**: ProactiveAgent received ugly notification like:
   ```
   HomeScreenSystemApp: CompletedEvent(event_type=<EventType.AGENT: 'AGENT'>, ...)
   ```
   Instead of readable format like:
   ```
   [2024-01-01 00:00:12] User: HomeScreenSystemApp__open_app(app_name='StatefulMessagingApp')
   ```

2. **Message queue consumption bug**: Both UserAgent and ProactiveAgent should see environment notifications, but `message_queue.get_by_timestamp()` **removes** messages from queue. Current flow:
   - Turn starts → UserAgent pre-step calls `get_by_timestamp()` → consumes all `ENVIRONMENT_NOTIFICATION`
   - ProactiveAgent pre-step runs → queue is empty → misses notifications!

### Solution Architecture

#### Part 1: User Action Formatting (Delta Approach)

**Design**: Format user actions (EventType.USER) separately from environment notifications:

1. **Add `USER_ACTION` to PASMessageType enum** ✅ COMPLETED
   - New message type distinct from `ENVIRONMENT_NOTIFICATION`
   - Allows different formatting for user actions vs environment events

2. **PASNotificationSystem.convert_to_message()** ✅ COMPLETED
   - Detect `event.event_type == EventType.USER`
   - Format as: `"{AppName}__{function}(arg1=val1, arg2=val2)"`
   - Return `Message(message_type=USER_ACTION)`

3. **UserActionLog class** ✅ COMPLETED
   - New log type with `get_type() = "user_action"`
   - ProactiveAgent pre-step creates these from `USER_ACTION` messages

4. **Pre-step delta handling** (PENDING - Phase 8.5)
   - `message_queue.get_by_timestamp()` automatically provides delta (only new messages)
   - No manual index tracking needed!

**Data Flow**:
```
User calls tool
  → @pas_event_registered creates CompletedEvent(event_type=EventType.USER)
  → PASNotificationSystem.convert_to_message()
  → Returns Message(message_type=USER_ACTION, message="AppName__func(args)")
  → Added to notification_system.message_queue
  → ProactiveAgent pre-step pulls USER_ACTION → creates UserActionLog
  → format_notification() adds timestamp: "[2024-01-01 12:00:00] AppName__func(args)"
  → message_dict wraps: "New user action:\n***\n[timestamp] AppName__func(args)\n***\n"
```

#### Part 2: Message Queue Sharing Bug - Scenario Runner Solution

**Problem Analysis**: Cannot modify BaseNotificationSystem easily because:
- `self.message_queue.put()` called in 3 places (lines 236, 258, 299)
- `self.message_queue.messages.peek()` used in `get_next_notification_time()` (line 220)
- `self.message_queue.has_new_messages()` used in `handle_timeout_after_events()` (line 248)
- Any custom MessageQueue affects ALL these methods

**Rejected Solutions**:
- ❌ **Two queues in notification system**: Would require overriding `handle_time_based_notifications()`, `handle_timeout_after_events()`, `handle_event()` - too much duplication
- ❌ **Custom MessageQueue with per-agent tracking**: Would break `get_next_notification_time()` and `has_new_messages()` - complex to maintain
- ❌ **Subscriber pattern**: User explicitly ruled out

**CHOSEN SOLUTION: Scenario Runner Distribution** ✅

**Architecture**: TwoAgentScenarioRunner gets messages once per turn, stores in each agent's `custom_state`:

```python
# In TwoAgentScenarioRunner._run_with_two_agents()
while turn_count < max_turns:
    # Get ALL notifications ONCE per turn
    all_notifications = env.notification_system.message_queue.get_by_timestamp(
        timestamp=datetime.fromtimestamp(env.time_manager.time(), tz=UTC)
    )

    # Distribute to both agents via custom_state
    # Note: execute_agent doesn't need notifications (only observe_agent does)
    user_agent.react_agent.custom_state["notifications"] = all_notifications
    proactive_agent.observe_agent.custom_state["notifications"] = all_notifications

    # Continue with existing code...
    user_tools = env.get_user_tools()
    current_app = env.active_app
    current_state = current_app.current_state if current_app and isinstance(current_app, StatefulApp) else None

    user_result = user_agent.agent_loop(
        user_tools, current_app, current_state, reset=user_reset or not user_agent.react_agent.is_initialized
    )

    proactive_result = proactive_agent.agent_loop(
        reset=proactive_reset or not proactive_agent.observe_agent.is_initialized
    )
```

**Detailed Implementation Steps for Phase 8.7**:

1. **TwoAgentScenarioRunner._run_with_two_agents()** (scenario_runner.py:234)
   - Add `get_by_timestamp()` call at start of while loop
   - Store result in both agents' `custom_state["notifications"]`

2. **UserAgent.get_notifications()** (agents/user/agent.py:252-267)
   - Change from: `notification_system.message_queue.get_by_timestamp(...)`
   - To: `self.react_agent.custom_state.get("notifications", [])`
   - Remove re-insertion logic (lines 264-265)

3. **ProactiveAgent.get_notifications()** (agents/proactive/agent.py:306-325)
   - Change from: `notification_system.message_queue.get_by_timestamp(...)`
   - To: `self.observe_agent.custom_state.get("notifications", [])`
   - Remove re-insertion logic (lines 318-319)

4. **User pre-step** (agents/user/steps.py:25-27)
   - Change from: `agent.notification_system.message_queue.get_by_timestamp(...)`
   - To: `agent.custom_state.get("notifications", [])`

5. **Proactive pre-step** (agents/proactive/steps.py:23-25)
   - Change from: `agent.notification_system.message_queue.get_by_timestamp(...)`
   - To: `agent.custom_state.get("notifications", [])`

**Execution Flow After Phase 8.7**:
```
Turn starts
├─ Scenario runner: get_by_timestamp() ONCE → store in custom_state
├─ UserAgent.agent_loop()
│  ├─ get_notifications() → reads from custom_state, filters by type
│  ├─ build_task_from_notifications() → uses filtered AGENT_MESSAGE
│  └─ react_agent.run() → pre-step reads from same custom_state
│     └─ Pre-step creates: AgentMessageLog, EnvironmentNotificationLog, AvailableToolsLog, CurrentAppStateLog
│
└─ ProactiveAgent.agent_loop()
   ├─ get_notifications() → reads from custom_state, filters by type
   ├─ build_task_from_notifications() → uses filtered USER_MESSAGE
   └─ observe_agent.run() → pre-step reads from same custom_state
      └─ Pre-step creates: EnvironmentNotificationLog, UserActionLog (after Phase 8.5)
```

**Key Insight**: `get_notifications()` is NOT removed because it:
- Filters notifications by type (AGENT_MESSAGE, USER_MESSAGE, etc.)
- Detects ENVIRONMENT_STOP for termination
- Builds task strings via `build_task_from_notifications()`
- Pre-steps handle log creation, `get_notifications()` handles task building

**Advantages**:
- ✅ ZERO modifications to BaseNotificationSystem
- ✅ Both agents see identical raw notifications
- ✅ Single source of truth (one `get_by_timestamp()` call per turn)
- ✅ Clean separation of concerns (runner distributes, agents filter/consume)
- ✅ Eliminates message queue consumption race condition

#### Part 3: Two-Template Notification System

**Requirement**: UserAgent and ProactiveAgent should see DIFFERENT views of the same notification:
- **UserAgent**: Truncated view (e.g., "Email from Alice: Meeting tomor...")
- **ProactiveAgent**: Full view (e.g., "Email from Alice: Meeting tomorrow\n\n[full body]")

**Design**: App-specific Jinja2 templates with user/agent distinction

**Template Location**: `pas/apps/notification_templates.py` (single file for all apps)
**Rationale**:
- When developer adds new app, they add templates for BOTH views in ONE place
- Easy to review/compare formatting across apps
- Follows pattern: templates describe app behavior, not agent behavior

**Template Structure**:
```python
NOTIFICATION_TEMPLATES = {
    "user": {  # Templates for UserAgent (truncated)
        "StatefulEmailApp": {
            "create_and_add_email": "Email from {{sender}}: {{subject[:20]}}..."
        },
        "StatefulMessagingApp": {
            "create_and_add_message": "New message in {{conversation_id}}"
        },
        "StatefulCalendarApp": {
            "create_and_add_email_by_attendee": "Calendar: Event by {{who_add}}"
        }
    },
    "agent": {  # Templates for ProactiveAgent (full)
        "StatefulEmailApp": {
            "create_and_add_email": "Email from {{sender}}: {{subject}}\n{{body}}"
        },
        "StatefulMessagingApp": {
            "create_and_add_message": "Message in {{conversation_id}}: {{content}}"
        },
        "StatefulCalendarApp": {
            "create_and_add_email_by_attendee": "Calendar: {{title}} by {{who_add}}"
        }
    }
}
```

**Usage** (in scenario runner when distributing notifications):
```python
# Format notifications differently for each agent
user_notifications = format_notifications(all_notifications, view="user")
agent_notifications = format_notifications(all_notifications, view="agent")

user_agent.custom_state["notifications"] = user_notifications
proactive_agent.custom_state["notifications"] = agent_notifications
```

### Implementation Status

**✅ Completed**:
- Phase 8.1: Add USER_ACTION to PASMessageType enum
- Phase 8.2: Implement UserActionLog class
- Phase 8.3: Format user actions in PASNotificationSystem.convert_to_message()
- Phase 8.4: Create pas/apps/notification_templates.py with two-template system
- Phase 8.5: Update proactive pre-step to handle USER_ACTION messages
- Phase 8.6: Add user_action to ProactiveAgent role_dict and message_dict
- Phase 8.7: Implement scenario runner notification distribution (message queue fix)

**⏳ Pending**:
- Phase 8.8: Fix notification view parameter usage (see "Notification View Problem" below)
- Phase 8.9: Test notification formatting with demo script

### Key Design Decisions

1. **Why delta approach?**
   - BaseAgent's `build_history_from_logs()` iterates through ALL logs from beginning
   - Each `UserActionLog` entry appears exactly once in chronological order
   - No redundancy - LLM sees full action history naturally

2. **Why scenario runner distribution?**
   - Avoids modifying BaseNotificationSystem (complex, many dependencies)
   - Clean separation: notification system creates messages, scenario runner distributes them
   - Only 5 lines changed vs 50+ lines for other approaches

3. **Why two templates?**
   - Research requirement: user should have limited information, agent should have full context
   - Simulates realistic information asymmetry
   - Single template file makes it easy for developers to maintain consistency

4. **Why `AppName__function` format for user actions?**
   - Shows agent the exact tool name that was called
   - Matches tool naming convention (what agent would use to call same tool)
   - Clear and unambiguous

### Notification View Problem (Phase 8.8)

**Status**: ⚠️ DISCOVERED (2025-11-05)

**Problem**: Created two-template system but `view` parameter isn't being used correctly.

**Current Flow**:
```python
# In PASNotificationSystem.convert_to_message() (line 52)
def convert_to_message(self, event: CompletedEvent, view: Literal["user", "agent"] = "user") -> Message | None:
    # ...
    message = get_content_for_environment_message(event, view)  # Calls with view parameter
    # ...

# But ALL notifications are created with default view="user"!
# Both agents get Message objects with truncated "user" view content
```

**Current Implementation**:
- `PASNotificationSystem.convert_to_message()` defaults to `view="user"` (line 52)
- `Message` objects are created ONCE when event completes
- Scenario runner distributes SAME Message objects to both agents:
  ```python
  all_notifications = env.notification_system.message_queue.get_by_timestamp(...)
  user_agent.react_agent.custom_state["notifications"] = all_notifications  # user view
  proactive_agent.observe_agent.custom_state["notifications"] = all_notifications  # also user view!
  ```

**Result**: ProactiveAgent currently sees truncated "user" view instead of full "agent" view.

**Design Doc Mismatch**: Lines 1146-1154 suggested reformatting approach:
```python
user_notifications = format_notifications(all_notifications, view="user")
agent_notifications = format_notifications(all_notifications, view="agent")
```

**Two Solution Options**:

1. **Re-format approach**: Scenario runner reformats Message.message content using templates
   - Pro: `Message` objects already created, just update `.message` field
   - Con: Need to track event metadata to know which template to use
   - Con: Might lose information if event data wasn't preserved in Message

2. **Dual-creation approach**: Notification system creates two versions per event
   - Con: Requires overriding `handle_event()` in PASNotificationSystem
   - Con: More complex - need two separate message queues or message routing

3. **On-demand formatting** (RECOMMENDED): Don't pre-format messages, format during pre-step
   - Change `Message.message` to store raw event data (dict with args)
   - Pre-step calls `render_template(message.raw_data, view="user"|"agent")`
   - Pro: Clean separation - notification system stores data, pre-step formats it
   - Pro: Single message queue, format once per agent
   - Con: Requires changing Message structure or using message.metadata

**Question for User**: Which approach should we take?

### Related Bugs Discovered

1. **EventType bug** ✅ FIXED (Phase 7.8)
   - `@pas_event_registered` defaulted to `EventType.AGENT`
   - User actions incorrectly labeled as AGENT events
   - **Fix**: Changed default to `EventType.USER`

2. **time_read bug** (Pending - Phase 9)
   - `pas/notification_system.py:126` sets `time_read=timestamp`
   - Messages immediately marked as read
   - **Fix**: Remove or set to `None`

---

## Project Status Reference

**Current Phase**: Phase 8 (Notification Formatting System) - see "Phase 8: Notification Formatting System" section above for detailed status

**For TODO tracking**: See "Implementation Phases" section above (lines 567-624) for canonical phase breakdown and current status

**Active work**: Phase 8.8 - Fix notification view parameter usage (see "Notification View Problem" in Phase 8 section)

**IMPORTANT FOR NEXT SESSION**: When starting a new conversation, use the TodoWrite tool to restore working context. Reference the Implementation Phases section and Phase 8 detailed section to build the todo list

---

## Open Questions

1. **Notification filtering**: Should agents maintain last_read_timestamp, or use a different mechanism to avoid re-processing notifications?

2. **Tool refresh timing**: Should tools be refreshed before every agent turn, or only when state changes are detected?

3. **Error handling**: How should the system handle errors during agent execution (LLM failures, tool execution errors, etc.)?

4. **Logging and debugging**: What additional logging is needed beyond Meta-ARE's BaseAgentLog system?

5. **Performance**: With two separate LLM calls per turn (user + proactive), should we add batching or parallelization?

6. **State transition notifications**: Should state transitions (e.g., ContactsList → ContactDetail) emit notifications, or is tool-call notification sufficient?

---

## References

- Meta-ARE BaseAgent: `/Users/dnathani/Projects/goalInference/meta-are/are/simulation/agents/default_agent/base_agent.py`
- Meta-ARE ScenarioRunner: `/Users/dnathani/Projects/goalInference/meta-are/are/simulation/scenario_runner.py`
- Meta-ARE NotificationSystem: `/Users/dnathani/Projects/goalInference/meta-are/are/simulation/notification_system.py`
- PAS StateAwareEnvironmentWrapper: `/Users/dnathani/Projects/goalInference/pas/pas/environment.py`
- PAS StatefulApp: `/Users/dnathani/Projects/goalInference/pas/pas/apps/core.py`
- PAS UserAgent: `/Users/dnathani/Projects/goalInference/pas/pas/agents/user/agent.py`

---
