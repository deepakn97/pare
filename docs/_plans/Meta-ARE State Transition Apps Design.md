**ARCHITECTURE UPDATE**: This plan uses `StatefulApp` approach with well-established design patterns:
- **State Pattern (GoF)**: Apps inherit from both `StatefulApp` and their meta-are parent (e.g., `StatefulMessagingApp(StatefulApp, MessagingAppV2)`)
- **Late Binding**: States created independently, app injects itself via `bind_to_app()` for clear ownership (App HAS-A AppState)
- **Pushdown Automaton**: Navigation stack for `go_back()` functionality
- **Entry/Exit Actions**: Hook methods `on_enter()`/`on_exit()` for state initialization/cleanup and RL logging
- **Instantiated vs Static States**: States with context (e.g., `ConversationState(conv_id)`) vs stateless (e.g., `ConversationListState`)

This eliminates separate manager classes and follows proven patterns from Gang of Four and Game Programming Patterns.

## Table of Contents
1. [Meta-ARE Architecture Analysis](#meta-are-architecture-analysis)
2. [Proposed iOS Navigation System](#proposed-ios-navigation-system)
3. [Implementation Plan](#implementation-plan)
4. [Key Benefits](#key-benefits)
5. [Technical Specifications](#technical-specifications)

## Meta-ARE Architecture Analysis

### Core Components

#### 1. Event System (`are/simulation/types.py`)

**Key Finding**: Every `@app_tool()` method decorated with `@event_registered()` automatically generates a `CompletedEvent` when called.

```python
# EventRegisterer.event_registered decorator (line 1400)
def wrapper(self, *args, **kwargs):
    event = CompletedEvent(
        event_id=f"{event_type.value}-{action_id}",
        event_type=event_type,
        action=action,  # Contains function, args, app
        metadata=event_metadata,
        event_time=event_time,
    )
    self.add_event(event)  # Flows to Environment/NotificationSystem
```

**Critical Integration Point**: Events flow through `Environment.handle_completed_event()` - perfect interception point for view management.

#### 2. Tool Registration System (`are/simulation/tool_utils.py`)

**Existing Decorators**:
- `@app_tool()` - Tools available to main/proactive agent (unrestricted)
- `@user_tool()` - Tools available to user simulation agent (view-restricted)
- `@env_tool()` - Environment tools
- `@data_tool()` - Data tools

**Tool Types** (`are/simulation/apps/app.py`):
```python
class ToolType(Enum):
    APP = auto()    # Main agent tools
    USER = auto()   # User simulation tools
    ENV = auto()    # Environment tools
    DATA = auto()   # Data tools
```

#### 3. User Simulation (`are/simulation/agents/user_proxy.py`)

**Critical Discovery**: Meta-ARE has built-in LLM-based user simulation!

```python
class UserProxyLLM(UserProxy):
    def __init__(self, llm: LLMEngine, system_message: str):
        # LLM-based user simulation agent

    def reply(self, message: str) -> str:
        # Simulated user responses
```

**User Tools Example** (`are/simulation/apps/agent_user_interface.py`):
```python
@user_tool()
@event_registered(operation_type=OperationType.WRITE, event_type=EventType.USER)
def send_message_to_agent(self, content: str):
    # Creates EventType.USER events (not EventType.AGENT)
```

#### 4. Notification System (`are/simulation/notification_system.py`)

**Observation Generation**: Converts `CompletedEvent`s into `Message`s for agents automatically.

```python
def convert_to_message(self, event: AbstractEvent) -> Message | None:
    # Line 301 - converts events to observations
    # Perfect extension point for view-based observations
```

**Filtering System**: `NotificationSystemConfig.notified_tools` controls which events generate notifications.

#### 5. System App (`are/simulation/apps/system.py`)

**Existing SystemApp**: Already handles system-level operations like `wait()`, `get_current_time()`, `wait_for_notification()`.

**Extension Point**: Perfect place for our `open_app()`, `switch_app()`, `get_open_apps()` tools.

## Proposed iOS Navigation System

### Architecture Overview

Our system creates a **mobile UI simulation layer** on top of meta-are's backend functionality, mimicking real iPhone app behavior patterns for proactive goal inference research.

#### Two Agent Types:
1. **User Simulation Agent**: View-restricted, uses only `@user_tool` methods, mimics real phone usage
2. **Proactive Agent**: Unrestricted observer, can call any `@app_tool` when intervening

### Core Components

#### 1. AppState Base Class

**Terminology Note**: "Navigation State" (our AppState classes) vs "Data State" (meta-are's JSON app data). Navigation states represent which screen/view the user is on, while data states represent the actual application data.

**Design Pattern**: Uses **late binding** pattern where states are created independently and then bound to the app when set. This makes ownership clear: App HAS-A AppState, and injects itself when needed. Based on the classic State pattern from Gang of Four and Game Programming Patterns.

```python
class AppState(ABC):
    """Base navigation state class for implementing the State pattern.

    States are created independently and bound to an app via late binding.
    This follows the classic State pattern where context (App) owns states,
    and states maintain a back-reference to context for delegation.

    Each state represents a specific screen/view in the app's navigation hierarchy.
    States expose only the actions (tools) that are valid from that navigation context.

    // RL NOTE: Navigation states form an MDP where each state has specific available actions.
    // Future: Add metadata like reward_on_enter, is_terminal for RL training.
    """
    def __init__(self):
        """Initialize state without app reference (late binding pattern)."""
        self._app: App | None = None
        self._cached_tools: list[AppTool] | None = None

    def bind_to_app(self, app: App) -> None:
        """Bind this state to an app (late binding).

        Called automatically by StatefulApp.set_current_state().
        Makes ownership clear: App creates state, then injects itself.

        Args:
            app: The app this state belongs to
        """
        self._app = app

    @property
    def app(self) -> App:
        """Get the app this state is bound to.

        Raises:
            RuntimeError: If state not bound to app yet
        """
        if self._app is None:
            raise RuntimeError(
                f"{self.__class__.__name__} not bound to app. "
                "States must be set via app.set_current_state()"
            )
        return self._app

    def get_available_actions(self) -> list[AppTool]:
        """Get user tools (actions) available from this navigation state.

        Tools are cached to avoid rebuilding on every call.

        // RL NOTE: These are the valid actions A(s) in the MDP from this state s.

        Returns:
            list[AppTool]: Available user tools in this state
        """
        if self._cached_tools is None:
            tools = []
            for method_name, method in inspect.getmembers(self, predicate=inspect.ismethod):
                if hasattr(method, '_is_user_tool'):  # Check for @user_tool decorator
                    tools.append(build_tool(self.app, method))  # Use bound app as context
            self._cached_tools = tools
        return self._cached_tools

    @abstractmethod
    def on_enter(self) -> None:
        """Called when transitioning INTO this state.

        Use for state initialization: load data, log transition, etc.
        Inspired by Game Programming Patterns' entry actions.

        // RL NOTE: Use for logging state transitions for RL dataset.
        // Log: (previous_state, action, this_state) for trajectory data.
        """
        pass

    @abstractmethod
    def on_exit(self) -> None:
        """Called when transitioning OUT OF this state.

        Use for state cleanup: save data, log transition, etc.
        Inspired by Game Programming Patterns' exit actions.

        // RL NOTE: Use for logging state exits for RL dataset.
        """
        pass

    @abstractmethod
    def get_data(self) -> dict:
        """Get the data state for this navigation state.

        Returns:
            dict: Data state (different from navigation state)
        """
        pass

    @abstractmethod
    def load_data(self, state: dict) -> None:
        """Load data state into this navigation state.

        Args:
            state: Data state to load
        """
        pass
```

#### 2. Specific State Implementations

**ConversationState** (Instantiated State - has context):
```python
class ConversationState(AppState):
    """Navigation state representing an open conversation view.

    This is an instantiated state (new instance per conversation) because
    it holds context (conversation_id). Different from static states.

    // RL NOTE: This is a conversation-specific state in the navigation MDP.
    // Context (conversation_id) is part of the state representation.
    // Different conversation_id = different state in the MDP.
    """
    def __init__(self, conversation_id: str):
        """Create conversation state with context.

        Note: No app parameter - uses late binding pattern.

        Args:
            conversation_id: The conversation context
        """
        super().__init__()
        self.conversation_id = conversation_id

    def on_enter(self) -> None:
        """Load conversation messages when entering this state."""
        # Example: Load messages from app
        # messages = self.app.get_messages(self.conversation_id)
        # // RL NOTE: Log state entry: (prev_state, action, ConversationState(conv_id))
        pass

    def on_exit(self) -> None:
        """Cleanup when leaving conversation."""
        # Example: Clear cached messages
        # // RL NOTE: Log state exit
        pass

    def get_data(self) -> dict:
        """Get data state for this conversation."""
        return {"conversation_id": self.conversation_id}

    def load_data(self, state: dict) -> None:
        """Load data state."""
        self.conversation_id = state.get("conversation_id", "")

    @user_tool()
    def send_message(self, content: str, attachment_path: str = None) -> str:
        """Send message in current conversation (context-aware)."""
        # Context injection - conversation_id is implicit from navigation state
        return self.app.send_message_to_group_conversation(
            conversation_id=self.conversation_id,
            content=content,
            attachment_path=attachment_path
        )

    # Note: go_back() is implemented in StatefulApp, not here
```

**ConversationListState** (Static State - no context):
```python
class ConversationListState(AppState):
    """Navigation state representing the conversations list view.

    This could be a static state (single instance reused) because it has
    no instance-specific data. For MVP, we create new instances each time.

    // RL NOTE: This is typically an initial/hub state in the messaging app navigation graph.
    // Often the initial state s₀ for messaging episodes.
    """
    def __init__(self):
        """Create conversation list state.

        Note: No app parameter - uses late binding pattern.
        """
        super().__init__()

    def on_enter(self) -> None:
        """Load conversations list when entering this state."""
        # Example: Refresh conversations list
        # // RL NOTE: Log state entry
        pass

    def on_exit(self) -> None:
        """Cleanup when leaving conversations list."""
        # // RL NOTE: Log state exit
        pass

    def get_data(self) -> dict:
        """Get data state for conversation list."""
        return {}  # No instance-specific data

    def load_data(self, state: dict) -> None:
        """Load data state."""
        pass  # No instance-specific data to load

    @user_tool()
    def get_conversations(self) -> str:
        """View all conversations."""
        return self.app.get_conversations()

    @user_tool()
    def search_conversations(self, query: str) -> str:
        """Search conversations."""
        return self.app.search_conversations(query)

    @user_tool()
    def open_conversation(self, conversation_id: str) -> str:
        """Open specific conversation (triggers state transition)."""
        # This will trigger state transition to ConversationState
        return f"Opening conversation {conversation_id}"

    # Note: go_back() is implemented in StatefulApp, not here
```

**Design Note**: `go_back()` is implemented in `StatefulApp` as a universal navigation action, not duplicated in each state. It's conditionally available based on `navigation_stack` contents.

#### 3. StatefulApp Base Class

**Design Pattern**: Implements **Pushdown Automaton** (state stack) from Game Programming Patterns for `go_back()` functionality. Uses late binding to inject app reference into states.

```python
class StatefulApp(App):
    """Base class for apps with navigation state management.

    Apps inherit from both StatefulApp and their meta-are parent class.
    Example: StatefulMessagingApp(StatefulApp, MessagingAppV2)

    Implements Pushdown Automaton pattern with navigation_stack for go_back().

    // RL NOTE: This implements the state transition function T(s,a) -> s' via handle_state_transition.
    // Tracks state history for trajectory analysis and logs transitions for RL training.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_state: AppState | None = None
        self.navigation_stack: list[AppState] = []  # Pushdown automaton stack
        # // RL NOTE: Future - add self.state_history: list[AppState] for full trajectory tracking

    def set_current_state(self, state: AppState) -> None:
        """Set current state with late binding and entry/exit actions.

        This is the main state transition method. It:
        1. Binds state to app (late binding - app injects itself)
        2. Calls on_exit() on old state (cleanup)
        3. Pushes old state to navigation stack (for go_back())
        4. Calls on_enter() on new state (initialization)
        5. Sets current_state

        // RL NOTE: This is where state transitions occur. Entry/exit actions
        // are perfect for logging (prev_state, action, new_state) tuples.

        Args:
            state: The new state to transition to
        """
        state.bind_to_app(self)  # Late binding: app injects itself into state

        if self.current_state is not None:
            self.current_state.on_exit()  # Exit old state
            self.navigation_stack.append(self.current_state)  # Push for go_back()

        state.on_enter()  # Enter new state (before setting for exception safety)
        self.current_state = state  # Transition complete

    @user_tool()
    def go_back(self) -> str:
        """Navigate back to previous state using navigation stack.

        Implements Pushdown Automaton pattern - pops state from stack.
        Only available when navigation_stack is not empty (see get_user_tools).

        // RL NOTE: This is a universal navigation action, not state-specific.

        Returns:
            str: Message indicating navigation back
        """
        if not self.navigation_stack:
            return "Already at the initial state"

        self.current_state = self.navigation_stack.pop()
        return f"Navigated back to {self.current_state.__class__.__name__}"

    def get_user_tools(self) -> list[AppTool]:
        """Get tools from current navigation state for user agents.

        Includes state-specific tools PLUS go_back() if navigation stack not empty.

        // RL NOTE: Returns A(s) - available actions in current state s.
        // Action space is state-dependent for user agent.

        Returns:
            list[AppTool]: Available user tools in current state
        """
        tools = []

        # Get state-specific tools
        if self.current_state is not None:
            tools.extend(self.current_state.get_available_actions())

        # Add go_back() if stack not empty (conditional availability)
        if self.navigation_stack:
            tools.append(build_tool(self, self.go_back))

        return tools

    def get_tools(self) -> list[AppTool]:
        """Proactive agents get ALL @app_tool methods (unrestricted).

        // RL NOTE: Proactive agent has full action space regardless of user's state.
        """
        return super().get_tools()

    def get_state(self) -> dict:
        """Get data state from current navigation state.

        Delegates to current_state.get_data() to get data state.

        Returns:
            dict: Data state of current navigation state
        """
        if self.current_state is None:
            return {}
        return self.current_state.get_data()

    def load_state(self, state: dict) -> None:
        """Load data state into current navigation state.

        Delegates to current_state.load_data().

        Args:
            state: Data state to load
        """
        if self.current_state is not None:
            self.current_state.load_data(state)

    @abstractmethod
    def handle_state_transition(self, event: CompletedEvent) -> None:
        """Update current navigation state based on tool events (state transitions).

        Subclasses must implement this to define app-specific state transition logic.
        Note: go_back() transitions are handled automatically, don't handle here.

        // RL NOTE: This is where state transitions T(s,a) -> s' occur.
        // Log (state, action, next_state) tuples for RL training dataset generation.

        Args:
            event: Completed event from tool execution

        Example implementation:
            function_name = event.function_name()
            if function_name == "open_conversation":
                conv_id = event.action.args.get("conversation_id")
                self.set_current_state(ConversationState(conv_id))
        """
        raise NotImplementedError("Subclasses must implement state transition logic")

    def get_state_graph(self) -> dict[str, list[str]]:
        """Get navigation state graph as adjacency list.

        // RL NOTE: This defines the MDP structure. Can be used for graph-based RL algorithms.
        // TODO: Implement after MVP - will analyze reachable states from each state.

        Returns:
            dict[str, list[str]]: State graph as adjacency list
        """
        raise NotImplementedError("To be implemented based on MVP learnings")

    def get_reachable_states(self, from_state: AppState) -> list[type[AppState]]:
        """Get states reachable from given state.

        // RL NOTE: Useful for planning algorithms and policy verification.
        // TODO: Implement after MVP

        Args:
            from_state: The state to analyze

        Returns:
            list[type[AppState]]: List of reachable state types
        """
        raise NotImplementedError("To be implemented based on MVP learnings")
```

#### 4. StateAware Environment

```python
class StateAwareEnvironmentWrapper(Environment):
    """Environment wrapper that triggers state transitions in StatefulApps.

    Much simpler than original design - apps manage their own state directly.

    // RL NOTE: This is the environment in the RL sense - manages state transitions and
    // provides observations (available actions) to agents based on current navigation state.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # // RL NOTE: Future - add episode tracking, trajectory logging

    def handle_completed_event(self, event: CompletedEvent):
        """Intercept events to trigger navigation state transitions in StatefulApps

        // RL NOTE: This is where the environment processes actions and transitions to next state.
        // Log (s, a, r, s') tuples here for RL dataset generation.
        """
        super().handle_completed_event(event)  # Normal processing first

        # Handle state transitions for StatefulApps
        app_name = event.app_name()
        app = self.get_app_by_name(app_name)

        if isinstance(app, StatefulApp):
            app.handle_state_transition(event)

    # Note: get_available_user_tools() is handled automatically!
    # Each StatefulApp overrides get_user_tools() to return state-specific tools.
    # The Environment just calls app.get_user_tools() which delegates to current_state.

    # Note: get_available_agent_tools() also handled automatically!
    # Each StatefulApp's get_tools() returns super().get_tools() which gets all @app_tool methods.
```

#### 5. Extended System Tools

**Extended SystemApp** (Original: `are/simulation/apps/system.py`):
```python
class SystemApp(App):  # Extend existing SystemApp
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.open_apps: dict[str, AppController] = {}
        self.active_app: str | None = None

    @user_tool()
    @event_registered(operation_type=OperationType.WRITE, event_type=EventType.USER)
    def open_app(self, app_name: str) -> str:
        """Open an application"""
        # Will be handled by StateAwareEnvironment
        return f"Opening {app_name}"

    @user_tool()
    @event_registered(operation_type=OperationType.WRITE, event_type=EventType.USER)
    def switch_app(self, app_name: str) -> str:
        """Switch to a different open app"""
        return f"Switched to {app_name}"

    @user_tool()
    def get_open_apps(self) -> list[str]:
        """Get list of currently open apps"""
        return list(self.open_apps.keys())
```

## Implementation Plan

See **[Detailed Implementation Todo](#detailed-implementation-todo)** section below for complete step-by-step instructions.

**Quick Summary:**
- **Phase 1**: Core infrastructure (`AppState` + `StatefulApp` base classes, environment wrapper)
- **Phase 2**: Messaging app implementation (states + StatefulMessagingApp)
- **Phase 3**: Integration testing and validation
- **Phase 4**: Additional apps (Contacts, Calendar) following same pattern

## Technical Specifications

### Event Flow Architecture

```
User Agent Action → @user_tool method → Context Injection → @app_tool call →
@event_registered → CompletedEvent → Environment.handle_completed_event() →
State Transition → Observation Update → User Agent sees updated available actions
```

**// RL NOTE**: This flow represents one timestep in the MDP: agent takes action a in state s, environment transitions to s', agent receives new observation (available actions in s').

### Design Patterns

Our architecture combines several well-established design patterns:

#### 1. State Pattern (Gang of Four)
- **Context**: `StatefulApp` (owns states, delegates behavior)
- **State**: `AppState` subclasses (encapsulate state-specific behavior)
- **Bidirectional Reference**: States maintain back-reference to context for delegation
- **Pattern**: Context owns states, states delegate back to context

From GoF: "State objects may store a backreference to the context object" - this is standard and expected.

#### 2. Late Binding Pattern
- **Problem**: Avoid circular dependency (state needs app, app creates state)
- **Solution**: States created independently, app injects itself via `bind_to_app()`
- **Ownership**: Makes clear that App HAS-A AppState (composition)
- **Usage**:
  ```python
  # Create state without app reference
  state = ConversationState(conversation_id="123")
  # App takes ownership and injects itself
  app.set_current_state(state)  # Calls state.bind_to_app(app) internally
  ```

#### 3. Pushdown Automaton (Game Programming Patterns)
- **Feature**: Navigation stack for `go_back()` functionality
- **Implementation**: `navigation_stack: list[AppState]` stores state history
- **Pattern**: Push state on transition, pop on back navigation
- **Benefit**: Enables realistic mobile navigation patterns

#### 4. Entry/Exit Actions (Game Programming Patterns)
- **Hook Methods**: `on_enter()` and `on_exit()` called during state transitions
- **Purpose**: Initialization, cleanup, logging
- **RL Use**: Perfect for logging (prev_state, action, new_state) tuples
- **Sequence**:
  ```python
  old_state.on_exit()     # Cleanup
  new_state.on_enter()    # Initialize
  current_state = new_state  # Transition
  ```

#### 5. Static vs Instantiated States (Game Programming Patterns)
- **Static States**: No instance-specific data (e.g., `ConversationListState`)
  - Could use singleton pattern (future optimization)
  - For MVP: Create new instances each time
- **Instantiated States**: Has instance-specific data (e.g., `ConversationState(conv_id)`)
  - Must create new instance for each context
  - Different context = different state in MDP

**References**:
- Gang of Four: "Design Patterns: Elements of Reusable Object-Oriented Software"
- Game Programming Patterns: https://gameprogrammingpatterns.com/state.html

### Tool Context Injection Pattern

```python
# User sees simple interface
@user_tool()
def send_message(self, content: str):
    # Behind the scenes: inject conversation_id from navigation state context
    return self.app.send_message_to_group_conversation(
        conversation_id=self.conversation_id,  # Implicit from navigation state
        content=content
    )
```

**// RL NOTE**: Context injection makes state representation compact for agents while maintaining full state information internally.

### Dynamic Action Filtering

```python
# In StatefulApp
def get_user_tools(self) -> list[AppTool]:
    """Only actions available from current navigation state

    // RL NOTE: Action space A(s) is state-dependent for user agent
    """
    if self.current_state:
        return self.current_state.get_available_actions()
    return []

def get_tools(self) -> list[AppTool]:
    """ALL @app_tool methods - unrestricted for proactive agent

    // RL NOTE: Proactive agent has full action space regardless of user's state
    """
    return super().get_tools()  # Delegates to App.get_tools()
```

**Note**: The Environment doesn't need special methods! It just calls `app.get_user_tools()` or `app.get_tools()` which handle the filtering automatically via StatefulApp's overrides.

### State Management

- **Navigation State**: Lightweight, in-memory, based on dataclasses (which screen user is on)
- **Data State**: Managed by underlying meta-are apps (actual app data - JSON)
- **Synchronization**: Event-driven via `handle_completed_event()`

**// RL NOTE**: Navigation state is part of the MDP state representation. Data state changes can be incorporated into reward function or state features for RL training.

### Observation System Integration

**Leveraging Existing NotificationSystem** (`are/simulation/notification_system.py`):
- Extend `convert_to_message()` to generate state-specific observations
- Use existing `notified_tools` filtering system
- Automatic timestamping and message queuing

**// RL NOTE**: Observations o(s) include available actions, which change with navigation state. Can extend to include state features for richer observation space.

## Key Benefits

### 1. Minimal Meta-ARE Changes
- **Wrapper Pattern**: `StateAwareEnvironment` wraps existing `Environment`
- **Extension Pattern**: Extend `SystemApp`, don't modify core apps
- **Leverage Existing**: Use built-in `@user_tool`, event system, notification system

### 2. Real Mobile UI Simulation
- **State Restrictions**: User agent actions depend on current navigation state (implicit state machine)
- **Context Injection**: Actions automatically inject implicit context from navigation state
- **Natural Workflows**: Mimics actual iPhone usage patterns

**// RL NOTE**: State-based action filtering creates realistic user behavior constraints, essential for learning from human trajectories.

### 3. Proactive Agent Research
- **Rich Behavioral Data**: Multi-step state-dependent workflows generate rich trajectories
- **Realistic User Patterns**: Natural mobile interaction sequences
- **Clear Intervention Points**: Proactive agent observes and intervenes when appropriate

**// RL NOTE**: State-action trajectories τ = (s₀, a₀, s₁, a₁, ...) from user simulations provide training data for goal inference models and proactive intervention policies.

### 4. Architectural Soundness
- **Event-Driven**: Leverages meta-are's sophisticated event system
- **Clean Separation**: User tools vs Agent tools clearly separated
- **Automatic Observations**: View updates handled by existing notification system
- **No Circular Dependencies**: Views don't inherit from App class

## Example User Flow (MDP Trajectory)

### Scenario: User sends message in existing conversation

```python
# **// RL NOTE**: This demonstrates a complete state-action trajectory τ with entry/exit actions

# 0. App Initialization
#    app = StatefulMessagingApp()
#    initial_state = ConversationListState()  # Created without app reference (late binding)
#    app.set_current_state(initial_state)
#    - Late binding: initial_state.bind_to_app(app) is called
#    - Entry action: initial_state.on_enter() is called
#    - Current state is set: app.current_state = initial_state

# 1. Initial State s₀: User is in ConversationListState
#    Available Actions A(s₀): get_conversations(), search_conversations(), open_conversation()
#    **// RL NOTE**: This is the initial state of an episode

# 2. User takes Action a₀: open_conversation(conversation_id="123")
#    - Event: EventType.USER, function: "open_conversation"
#    - Environment calls: app.handle_state_transition(event)
#    - App creates new state: new_state = ConversationState("123")  # No app reference yet
#    - App transitions: app.set_current_state(new_state)
#      a) Late binding: new_state.bind_to_app(app)
#      b) Exit action: ConversationListState.on_exit()  # Log exit, cleanup
#      c) Push to stack: navigation_stack.append(old_state)
#      d) Entry action: ConversationState("123").on_enter()  # Log entry, load messages
#      e) Set current: app.current_state = new_state
#    - State Transition: T(s₀, a₀) → s₁
#    - New State s₁: ConversationState("123")
#    **// RL NOTE**: Navigation state changes, context (conversation_id) is now part of state
#    **// RL NOTE**: Entry/exit actions perfect for logging (s₀, a₀, s₁) tuple

# 3. State s₁: User now in ConversationState("123")
#    Available Actions A(s₁): send_message(), go_back()
#    **// RL NOTE**: Action space has changed based on current state
#    **// RL NOTE**: go_back() is available because navigation_stack is not empty

# 4. User takes Action a₁: send_message(content="Hello!")
#    - Context Injection: send_message_to_group_conversation(conversation_id="123", content="Hello!")
#      (conversation_id injected from navigation state s₁)
#    - Event: EventType.USER, function: "send_message_to_group_conversation"
#    - State Transition: T(s₁, a₁) → s₁ (remains in same state)
#    - Observation O(s₁): User sees updated conversation with their new message
#    **// RL NOTE**: Some actions don't change navigation state but do change data state

# 5. User takes Action a₂: go_back()
#    - go_back() pops state from navigation_stack
#    - current_state = navigation_stack.pop()  # Returns to ConversationListState
#    - State Transition: T(s₁, a₂) → s₀
#    - Back to initial state with empty navigation_stack
#    **// RL NOTE**: Pushdown automaton pattern enables natural mobile navigation

# 6. Proactive Agent observes trajectory τ = (s₀, a₀, s₁, a₁, s₁, a₂, s₀)
#    - Agent has full action space regardless of user's state
#    - Can infer user goal from state-action sequence
#    - Can intervene with proactive actions when appropriate
#    **// RL NOTE**: This trajectory provides training data for goal inference models
#    **// RL NOTE**: Entry/exit logging provides (state, action, next_state) tuples automatically
```

This architecture creates realistic mobile interaction patterns perfect for proactive goal inference research while leveraging meta-are's robust infrastructure.

## Detailed Implementation Todo

**Terminology Note**: Throughout this implementation, "Navigation State" refers to which screen/view the user is on, while "Data State" refers to meta-are's JSON app data. This distinction is crucial.

### Phase 1: Core Infrastructure (src/proactivegoalinference/)

#### Task 1.1: Create Base Navigation State System Classes
**File**: `src/proactivegoalinference/apps/core.py`

**// RL NOTE**: This file defines the core MDP structure - states and available actions per state.

- [ ] Create `AppState` base class
  - [ ] `__init__(self, app: App)` - store reference to underlying meta-are app
  - [ ] `_cached_tools: list[AppTool] | None = None` - cache tools to avoid rebuilding
  - [ ] `get_available_actions(self) -> list[AppTool]` - extract @user_tool decorated methods
  - [ ] Implementation:
    - Check if `_cached_tools` is None
    - If None, iterate through `inspect.getmembers(self, predicate=inspect.ismethod)`
    - For each method, check `hasattr(method, '_is_user_tool')`
    - Use `build_tool(self.app, method)` to create AppTool
    - Cache and return the tools
  - [ ] Add docstring: "Base class for navigation states. Each state represents a screen/view with specific available actions."
  - [ ] **// RL NOTE**: Add comment about future state features: `# TODO: Add state_id, state_features for RL`

- [ ] Create `StatefulApp(App)` base class
  - [ ] `__init__(self, *args, **kwargs)` - call `super().__init__()` and initialize state tracking
  - [ ] `current_state: AppState | None = None` - track current navigation state
  - [ ] `get_user_tools(self) -> list[AppTool]` - override to delegate to current_state.get_available_actions()
    - If `current_state` exists, return `self.current_state.get_available_actions()`
    - Otherwise return empty list
  - [ ] `get_tools(self) -> list[AppTool]` - keep unrestricted for proactive agent
    - Return `super().get_tools()` to get all @app_tool methods
  - [ ] `handle_state_transition(self, event: CompletedEvent)` - abstract method for state transitions
    - Raise NotImplementedError with message "Subclasses must implement state transition logic"
  - [ ] **// RL NOTE**: Add comment: `# This implements the state transition function T(s,a) -> s'`
  - [ ] Add stub methods (not implemented):
    - [ ] `get_state_graph(self) -> dict[str, list[str]]` - raises NotImplementedError with "TODO: Implement after MVP"
    - [ ] `get_reachable_states(self, from_state: AppState) -> list[type[AppState]]` - raises NotImplementedError
    - [ ] **// RL NOTE**: Add comment: `# State graph analysis methods for MDP structure understanding`

**Dependencies to import**:
```python
import inspect
from abc import ABC
from are.simulation.apps.app import App, AppTool
from are.simulation.tool_utils import build_tool
from are.simulation.types import CompletedEvent
```

**Testing considerations**:
- Mock an App instance
- Mock methods with `_is_user_tool` attribute
- Verify `get_available_actions()` correctly identifies user tools
- Verify tools are built with correct app context
- Verify tools are cached after first call
- Verify `StatefulApp.get_user_tools()` delegates to current_state
- Verify `StatefulApp.get_tools()` returns parent class @app_tool methods
- Verify stub methods raise NotImplementedError

---

#### Task 1.2: Create StateAware Environment Wrapper
**File**: `src/proactivegoalinference/environment.py`

**// RL NOTE**: This is the RL environment - manages state transitions and provides state-dependent action spaces.

- [ ] Create `StateAwareEnvironment` class inheriting from `Environment`
  - [ ] `__init__(self, *args, **kwargs)` - call super, initialize navigation state tracking
  - [ ] **// RL NOTE**: Add comment: `# TODO: Add trajectory logging: self.state_action_history = []`

- [ ] Override `handle_completed_event(self, event: CompletedEvent)`
  - [ ] Call `super().handle_completed_event(event)` first for normal processing
  - [ ] Extract `app_name` from event using `event.app_name()`
  - [ ] Get the app instance using `self.get_app_by_name(app_name)` (meta-are Environment method)
  - [ ] Check if app is instance of `StatefulApp` using `isinstance(app, StatefulApp)`
  - [ ] If yes, call `app.handle_state_transition(event)` to trigger state transition
  - [ ] **// RL NOTE**: Add comment: `# TODO: Log (state, action, next_state) transitions here for RL dataset`

**Dependencies to import**:
```python
from are.simulation.environment import Environment
from are.simulation.types import CompletedEvent
from proactivegoalinference.apps.state_lib import StatefulApp
```

**Testing considerations**:
- Verify event interception doesn't break normal meta-are flow
- Test that state transitions are triggered for StatefulApp instances
- Test that non-StatefulApp instances are not affected
- Verify `get_app_by_name()` is called correctly
- Verify state transition logging hooks are in place (even if not implemented)

**Notes**:
- No need for separate registration of managers - apps manage their own state
- Tool filtering happens automatically through `App.get_user_tools()` override in StatefulApp
- Much simpler than original design!

---

#### Task 1.3: Extend SystemApp for Navigation
**File**: `src/proactivegoalinference/apps/system/app.py`

Note: We'll create a subclass rather than modifying meta-are's SystemApp directly.

- [ ] Create `ExtendedSystemApp(SystemApp)` class
  - [ ] `__init__(self, *args, **kwargs)` - call super, initialize app state
  - [ ] `open_apps: set[str]` - track which apps are "open"
  - [ ] `active_app: str | None` - track active app name

- [ ] Add `@user_tool()` methods:
  - [ ] `open_app(self, app_name: str) -> str`
    - Add `@event_registered(operation_type=OperationType.WRITE, event_type=EventType.USER)`
    - Validate app_name exists in environment
    - Add to `open_apps` set
    - Set as `active_app`
    - Return success message

  - [ ] `switch_app(self, app_name: str) -> str`
    - Add `@event_registered(operation_type=OperationType.WRITE, event_type=EventType.USER)`
    - Verify app is in `open_apps`
    - Set as `active_app`
    - Return success message

  - [ ] `get_open_apps(self) -> list[str]`
    - Return list of currently open apps
    - No event registration needed (read-only)

  - [ ] `close_app(self, app_name: str) -> str`
    - Add `@event_registered(operation_type=OperationType.WRITE, event_type=EventType.USER)`
    - Remove from `open_apps`
    - If active, clear `active_app`
    - Return success message

**Dependencies to import**:
```python
from are.simulation.apps.system import SystemApp
from are.simulation.tool_utils import user_tool, event_registered
from are.simulation.types import OperationType, EventType
```

**Testing considerations**:
- Test app state transitions (closed → open → active)
- Verify events are generated correctly
- Test error cases (opening non-existent app, switching to closed app)

---

### Phase 2: Messaging App Implementation (src/proactivegoalinference/apps/messaging/)

**File Structure**:
```
src/proactivegoalinference/apps/
├── __init__.py
├── core.py     # AppState, StatefulApp base classes
└── messaging/
    ├── __init__.py
    ├── app.py       # StatefulMessagingApp
    └── states.py    # ConversationListState, ConversationState
```

#### Task 2.1: Create Messaging Navigation State Classes
**File**: `src/proactivegoalinference/apps/messaging/states.py`

**// RL NOTE**: These are concrete states in the messaging app MDP. Each state has specific available actions.

- [ ] Create `ConversationList(AppState)` class
  - [ ] `__init__(self, messaging_app: MessagingAppV2)` - pass to AppState parent
  - [ ] `@user_tool() get_conversations(self) -> str` - delegate to `self.app.get_conversations()`
  - [ ] `@user_tool() search_conversations(self, query: str) -> str` - delegate to `self.app.search_conversations(query)`
  - [ ] `@user_tool() open_conversation(self, conversation_id: str) -> str` - return message (triggers state transition)
  - [ ] Add docstring: "Initial/hub state showing list of conversations"
  - [ ] **// RL NOTE**: Add comment: `# This is often the initial state s₀ for messaging episodes`

- [ ] Create `Conversation(AppState)` class
  - [ ] `__init__(self, conversation_id: str, messaging_app: MessagingAppV2)` - store conversation_id and pass app to parent
  - [ ] `conversation_id: str` - store context (part of state representation)
  - [ ] `@user_tool() send_message(self, content: str, attachment_path: str = None) -> str`
    - Inject `conversation_id` automatically from state
    - Call `self.app.send_message_to_group_conversation(conversation_id=self.conversation_id, content=content, attachment_path=attachment_path)`
  - [ ] `@user_tool() get_messages(self, limit: int = 20) -> str`
    - Inject `conversation_id` from state
    - Call appropriate app method with context
  - [ ] `@user_tool() go_back(self) -> str` - return message (triggers state transition back to list)
  - [ ] Add docstring: "State representing active conversation view with specific conversation_id"
  - [ ] **// RL NOTE**: Add comment: `# State includes conversation_id context. Different conversations = different states.`

**Dependencies to import**:
```python
from are.simulation.apps.messaging_v2 import MessagingAppV2
from are.simulation.tool_utils import user_tool
from proactivegoalinference.apps.state_lib import AppState
```

**Testing considerations**:
- Verify context injection works correctly
- Test action extraction from state classes
- Verify state transition messages are appropriate
- Test that different conversation_ids create functionally different states

---

#### Task 2.2: Create StatefulMessagingApp
**File**: `src/proactivegoalinference/apps/messaging/app.py`

**// RL NOTE**: This implements the state transition function T(s, a) -> s' for the messaging app MDP.

- [ ] Create `StatefulMessagingApp(StatefulApp, MessagingAppV2)` class (multiple inheritance)
  - [ ] `__init__(self, *args, **kwargs)`
    - Call `super().__init__(*args, **kwargs)` to initialize both parents
    - Set `self.current_state = ConversationListState(self)` as initial state
    - **// RL NOTE**: Add comment: `# Initial state s₀ for messaging episodes`

  - [ ] Override `handle_state_transition(self, event: CompletedEvent)`
    - Extract `function_name` using `event.function_name()`
    - Extract `args` using `event.action.args`
    - Implement state transition logic T(s, a) -> s':
      - `"open_conversation"` → `self.current_state = ConversationState(args.get("conversation_id"), self)`
      - `"go_back"` → `self.current_state = ConversationListState(self)`
    - **// RL NOTE**: Add comment: `# State transition function T(s,a) -> s'. TODO: Log transitions for RL dataset.`

  - [ ] Override stub methods from StatefulApp base (still not implemented):
    - [ ] `get_state_graph()` - NotImplementedError("Messaging state graph analysis not yet implemented")
    - [ ] `get_reachable_states()` - NotImplementedError("Reachable states analysis not yet implemented")

**Dependencies to import**:
```python
from are.simulation.apps.messaging_v2 import MessagingAppV2
from are.simulation.types import CompletedEvent
from proactivegoalinference.apps.state_lib import StatefulApp
from .states import ConversationListState, ConversationState
```

**Testing considerations**:
- Test all state transitions
- Verify event parsing works correctly
- Test edge cases (invalid conversation_id, etc.)
- Verify initial state is set correctly
- Test that state transitions create correct state objects with proper context
- Verify MRO is correct (StatefulApp before MessagingAppV2)
- Test that `get_user_tools()` returns state-specific tools
- Test that `get_tools()` returns all @app_tool methods

---

### Phase 3: Integration and Testing

#### Task 3.1: Create Integration Test Suite
**File**: `tests/test_navigation_state_integration.py`

**// RL NOTE**: These tests verify the MDP implementation - state transitions, action spaces, and observations.

- [ ] Setup fixtures
  - [ ] Create StateAwareEnvironmentWrapper
  - [ ] Create StatefulMessagingApp instance
  - [ ] Register StatefulMessagingApp with environment
  - [ ] Setup test user simulation agent
  - [ ] Setup test proactive agent

- [ ] Test: Action filtering based on current navigation state
  - [ ] Start in ConversationListState
  - [ ] Verify user sees only list state actions
  - [ ] Transition to ConversationState
  - [ ] Verify user sees only conversation state actions
  - [ ] Verify proactive agent still sees all actions regardless of state
  - [ ] **// RL NOTE**: Validates state-dependent action space A(s)

- [ ] Test: Event-driven state transitions
  - [ ] Trigger `open_conversation` action
  - [ ] Verify state transition occurs (T(s, a) -> s')
  - [ ] Verify new actions are available in new state
  - [ ] Trigger `go_back` action
  - [ ] Verify return to previous state
  - [ ] **// RL NOTE**: Validates state transition function T

- [ ] Test: Context injection from navigation state
  - [ ] Transition to ConversationState with "conv-123"
  - [ ] Call `send_message(content="test")` action
  - [ ] Verify underlying app receives `conversation_id="conv-123"` from state context
  - [ ] Verify message is sent to correct conversation
  - [ ] **// RL NOTE**: Validates state representation includes necessary context

- [ ] Test: Observation updates after actions
  - [ ] Send message (take action)
  - [ ] Verify CompletedEvent is generated
  - [ ] Verify user receives observation with updated available actions
  - [ ] **// RL NOTE**: Validates observation function O(s)

---

#### Task 3.2: Create User Flow Validation Tests
**File**: `tests/test_messaging_user_flows.py`

**// RL NOTE**: These tests validate complete state-action trajectories representing realistic user behavior.

- [ ] Test: Complete messaging workflow (episode trajectory)
  - [ ] User starts in conversation list state (s₀)
  - [ ] User searches for conversation (action a₀)
  - [ ] User opens specific conversation (action a₁, transition to s₂)
  - [ ] User sends multiple messages (actions in s₂)
  - [ ] User navigates back (action leading to s₀)
  - [ ] Verify all state transitions work correctly
  - [ ] Verify all context injections work correctly
  - [ ] **// RL NOTE**: This represents a complete episode trajectory τ = (s₀, a₀, s₁, a₁, ...)

- [ ] Test: Proactive agent intervention
  - [ ] User navigates through states (generating trajectory)
  - [ ] Proactive agent observes user state-action sequence
  - [ ] Proactive agent calls unrestricted action to assist
  - [ ] Verify proactive agent has access to all actions regardless of user's current state
  - [ ] Verify intervention doesn't break user's navigation state
  - [ ] **// RL NOTE**: Tests proactive agent's ability to intervene while observing user trajectory

- [ ] Test: Multi-app scenario (cross-app state management)
  - [ ] User opens messaging app (initial state)
  - [ ] User switches to contacts app (once implemented)
  - [ ] User returns to messaging app
  - [ ] Verify navigation state persists correctly per app
  - [ ] Verify action filtering works across app switches
  - [ ] **// RL NOTE**: Tests state space partitioning across multiple apps

---

#### Task 3.3: Create Unit Tests
**File**: `tests/test_navigation_state_unit.py`

- [ ] Test `AppState.get_available_actions()`
  - Mock methods with/without `@user_tool` decorator
  - Verify only decorated methods are returned as actions
  - Verify action building uses correct app context
  - **// RL NOTE**: Validates action extraction for A(s)

- [ ] Test `StateAwareEnvironmentWrapper.handle_completed_event()`
  - Mock event
  - Verify super is called (normal meta-are flow preserved)
  - Verify manager's handle_tool_event is called (state transition)
  - Verify active_app_name updates correctly
  - **// RL NOTE**: Validates state transition mechanism

- [ ] Test `ExtendedSystemApp` navigation tools
  - Test open_app, switch_app, close_app actions
  - Verify navigation state management
  - Verify event generation

- [ ] Test `StatefulApp` stub methods
  - Verify `get_state_graph()` raises NotImplementedError
  - Verify `get_reachable_states()` raises NotImplementedError
  - Verify `handle_state_transition()` raises NotImplementedError in base class
  - Ensure error messages are helpful

---

### Phase 4: Additional Apps (Future)

#### Task 4.1: Contacts App Navigation States
**Files**: `src/proactivegoalinference/apps/contacts/states.py`, `app.py`

- [ ] `ContactsListState` - view all contacts (initial state)
- [ ] `ContactDetailState` - view specific contact
- [ ] `ContactEditState` - edit contact details
- [ ] `StatefulContactsApp(StatefulApp, ContactsApp)` - manage state transitions
- [ ] **// RL NOTE**: Contacts app adds another sub-MDP to the overall state space

#### Task 4.2: Calendar App Navigation States
**Files**: `src/proactivegoalinference/apps/calendar/states.py`, `app.py`

- [ ] `CalendarViewState` - month/week/day views
- [ ] `EventDetailState` - view event details
- [ ] `EventEditState` - create/edit events
- [ ] `StatefulCalendarApp(StatefulApp, CalendarApp)` - manage state transitions
- [ ] **// RL NOTE**: Calendar app MDP, interacts with messaging/contacts for cross-app workflows

---

## Implementation Order Summary

**Architecture**: StatefulApp approach with multiple inheritance (StatefulApp + meta-are App classes)

**Start here**: Phase 1.1 - Base Navigation State System Classes (foundational MDP structure)

**Critical path**:
1. Task 1.1: `apps/state_lib.py` - Core MDP abstractions (`AppState` + `StatefulApp` base classes)
2. Task 1.2: `state_aware_environment.py` - RL environment integration layer (much simpler with StatefulApp)
3. Task 1.3: `extended_system_app.py` - System-level navigation actions (optional)
4. Task 2.1: `apps/messaging/states.py` - First concrete state implementations
5. Task 2.2: `apps/messaging/app.py` - StatefulMessagingApp with state transition logic
6. Task 3.1-3.3: Testing to validate the MDP architecture

**Key decision points**:
- After Task 1.1: Verify StatefulApp and AppState base classes work correctly
- After Task 2.2: Ensure messaging state machine works with StatefulMessagingApp
- After Phase 3: Decide if architecture needs adjustments before expanding to more apps

**Estimated complexity**:
- Phase 1: 1-2 days (simpler with StatefulApp approach)
- Phase 2: 1 day (straightforward once base classes work)
- Phase 3: 1-2 days (validates MDP implementation and trajectory generation)
- Phase 4: 0.5 day per app (pattern is very clear with StatefulApp)

**Architecture Benefits**:
- ✅ No separate manager classes needed
- ✅ Simpler registration (just register StatefulMessagingApp)
- ✅ Clear inheritance chain (StatefulMessagingApp IS-A MessagingAppV2)
- ✅ State transition logic colocated with app
- ✅ Automatic tool filtering via `get_user_tools()` override

**// RL NOTE**: The critical path establishes the MDP framework first (states, actions, transitions), then validates with concrete messaging app implementation, then extends to more apps for richer state-action spaces.

---

## Stretch Goals (Post-MVP)

### Meta-ARE Terminology Clarification
**Goal**: Rename meta-are's "state" to "data_state" for clearer distinction from navigation states.

**Rationale**: Currently meta-are uses "state" to refer to JSON app data. Our navigation states represent screen/view position. To avoid confusion, we should update meta-are terminology.

**Scope**:
- Search meta-are codebase for uses of "state" referring to data
- Rename to "data_state" throughout meta-are
- Update tests and documentation
- This is non-blocking for our MVP - we can work with current terminology
- Estimate: 1-2 days of careful refactoring

**Priority**: Low (post-MVP cleanup for better code clarity)

**// RL NOTE**: This clarification helps distinguish MDP state (navigation) from application data state in documentation and discussions.
