# Stackelberg POMDP Formulation for PARE

## 1. Overview

The Proactive Agent Research Environment (PARE) models a two-agent system where a **User** interacts with mobile applications while a **Proactive Agent** observes user behavior and proposes helpful interventions. We formalize this as a **Stackelberg POMDP** with asymmetric information, state-dependent action spaces, and leader-follower turn structure.

### Key Characteristics

- **Asymmetric agents**: User (leader) has state-constrained actions; agent (follower) has privileged access
- **Partial observability**: Agents receive different observations of the same state
- **Stackelberg turns**: Within each turn, user acts first, agent observes user action, then agent acts
- **Dual rewards**: Task success (terminal) + proposal acceptance (per-step)

---

## 2. Formal Definition

A PARE Stackelberg POMDP is defined by the tuple:

$$\mathcal{M} = \langle \mathcal{N}, \mathcal{S}, \{\mathcal{A}_i\}_{i \in \mathcal{N}}, T, R, \{\mathcal{O}_i\}_{i \in \mathcal{N}}, \mathcal{I} \rangle$$

where $\mathcal{N} = \{\mathbf{U}, \mathbf{A}\}$ denotes the user (leader) and the proactive agent (follower).

| Symbol | Name | Description |
|--------|------|-------------|
| $\mathcal{N}$ | Agent set | $\{\mathbf{U}, \mathbf{A}\}$ -- user and proactive agent |
| $\mathcal{S}$ | State space | Global environment state |
| $\mathcal{A}_i$ | Action space | Actions available to agent $i$ |
| $T$ | Transition function | State dynamics |
| $R$ | Reward function | Reward signal |
| $\mathcal{O}_i$ | Observation space | What agent $i$ can observe |
| $\mathcal{I}$ | Instruction space | Task specifications for agents |

---

## 3. Component Definitions

### 3.1 Agent Set $\mathcal{N}$

$$\mathcal{N} = \{\mathbf{U}, \mathbf{A}\}$$

**Definition**: The set of decision-making entities in the environment. $\mathbf{U}$ is the leader (acts first), $\mathbf{A}$ is the follower (observes user action before acting).

**PARE Mapping**:

- $\mathbf{U}$: Simulated by `UserAgent` - interacts with apps to accomplish tasks
- $\mathbf{A}$: Implemented by `ProactiveAgent` - observes user and proposes interventions

**Example**: In a "schedule meeting" scenario:

- User navigates Email app to find meeting request
- Agent observes user reading email, proposes creating calendar event

---

### 3.2 State Space $\mathcal{S}$

$$\mathcal{S} = \mathcal{S}_{\text{app}} \times \mathcal{S}_{\text{global}} \times \mathcal{S}_{\text{db}} \times \mathcal{S}_{\text{history}}$$

#### 3.2.1 App State $\mathcal{S}_{\text{app}}$

$$\mathcal{S}_{\text{app}} = \bigcup_{a \in \text{Apps}} \text{States}(a)$$

**Definition**: The current screen/view within the active application.

**PARE Mapping**: `StatefulApp.current_state: AppState`

**Example (Contacts App)**:

$$\mathcal{S}_{\text{app}}^{\text{contacts}} = \{\texttt{ContactsList}, \texttt{ContactDetail}(c), \texttt{ContactEdit}(c) \mid c \in \text{ContactIDs}\}$$

Concrete instance: $s_{\text{app}} = \texttt{ContactDetail}(\text{"C001"})$ - viewing contact with ID "C001"

#### 3.2.2 Global State $\mathcal{S}_{\text{global}}$

$$\mathcal{S}_{\text{global}} = \{\texttt{Home}, \texttt{Contacts}, \texttt{Email}, \texttt{Calendar}, \texttt{Notes}, \texttt{Reminder}, \texttt{Messaging}\}$$

**Definition**: Which application is currently active (foreground).

**PARE Mapping**: `StateAwareEnvironmentWrapper.active_app: App`

**Example**: $s_{\text{global}} = \texttt{Email}$ means the Email app is in foreground.

#### 3.2.3 Database State $\mathcal{S}_{\text{db}}$

$$\mathcal{S}_{\text{db}} = \prod_{a \in \text{Apps}} \text{Data}(a)$$

**Definition**: The persistent data across all applications.

**PARE Mapping**: App backend data stores (e.g., `contacts_app._backend.contacts`)

**Example**:

```
s_db = {
    contacts: {
        "C001": Contact(first_name="Alice", email="alice@example.com"),
        "C002": Contact(first_name="Bob", email="bob@example.com")
    },
    emails: {
        "E001": Email(subject="Meeting Request", from="alice@example.com", folder="INBOX")
    },
    calendar: {...},
    notes: {...}
}
```

#### 3.2.4 History State $\mathcal{S}_{\text{history}}$

$$\mathcal{S}_{\text{history}} = \mathcal{H}_\mathbf{U} \times \mathcal{H}_\mathbf{A}$$

**Definition**: Truncated, bounded view of past events relevant to each agent's decision-making. Since history is truncated (finite window), $|\mathcal{S}_{\text{history}}|$ is bounded, preserving the Markov property.

**Components**:

$\mathcal{H}_\mathbf{U}$: User-relevant history

- Navigation stack for `go_back()` functionality
- Most recent agent proposal (if any)
- Recent environment notifications

$\mathcal{H}_\mathbf{A}$: Agent-relevant history

- Recent user actions (truncated window)
- Agent's own previous proposals
- Recent environment notifications

**PARE Mapping**:

- Navigation: `StatefulApp.navigation_stack`
- User actions: `UserActionLog` entries
- Proposals: `AgentMessageLog` (latest only)
- Notifications: `EnvironmentNotificationLog`

**Example**:

```
s_history = (
    h_U: {
        nav_stack: [ContactsList],
        pending_proposal: "Create calendar event for meeting?",
        env_notifs: ["New email from alice@example.com"]
    },
    h_A: {
        user_actions: ["open_app(email)", "search_emails('meeting')", "open_email('E001')"],
        last_proposal: "Create calendar event for meeting?",
        env_notifs: ["Reminder: Meeting at 2pm"]
    }
)
```

---

### 3.3 Action Spaces $\mathcal{A}_i$

#### 3.3.1 User Action Space $\mathcal{A}_\mathbf{U}$

$$\mathcal{A}_\mathbf{U}: \mathcal{S}_{\text{app}} \times \mathcal{S}_{\text{global}} \rightarrow 2^{\mathcal{A}_\mathbf{U}^{\text{all}}}$$

**Definition**: The user's available actions depend on the current app state. This is a **state-dependent action space**.

**Constraint**: At state $s$, user must select from valid actions:

$$a_\mathbf{U}^t \in \mathcal{A}_\mathbf{U}(s_{\text{app}}^t, s_{\text{global}}^t)$$

When a proposal from the agent is pending, the user's action space is augmented with $\texttt{accept\_proposal}$ and $\texttt{reject\_proposal}$.

**PARE Mapping**: `environment.get_user_tools()`

**Example**:

| State | Available Actions $\mathcal{A}_\mathbf{U}(s)$ |
|-------|--------------------------------------------------|
| $s_{\text{app}} = \texttt{Home}$ | `{open_app(contacts), open_app(email), open_app(calendar), ...}` |
| $s_{\text{app}} = \texttt{ContactsList}$ | `{list_contacts(), search_contacts(), open_contact(), create_contact(), go_home(), switch_app()}` |
| $s_{\text{app}} = \texttt{ContactDetail(C001)}$ | `{view_contact(), start_edit(), delete_contact(), go_back(), go_home()}` |
| Any state + pending proposal | Above $\cup$ `{accept_proposal, reject_proposal}` |

#### 3.3.2 Proactive Agent Action Space $\mathcal{A}_\mathbf{A}$

$$\mathcal{A}_\mathbf{A} = \mathcal{A}_{\text{read}} \cup \mathcal{A}_{\text{propose}} \cup \{\texttt{wait}\}$$

**Definition**: The agent's action space is **state-independent** (privileged access).

**Components**:

- $\mathcal{A}_{\text{read}}$: Read-only queries across all apps for information gathering
- $\mathcal{A}_{\text{propose}} = \{\texttt{propose}(a) \mid a \in \mathcal{A}_{\text{privileged}}\}$: Propose a task to the user
- $\texttt{wait}$: Continue observation without intervention

**PARE Mapping**: `environment.get_tools()`

**Example**:

- $\texttt{list\_emails}(\text{folder="INBOX"})$ (read action)
- $\texttt{propose}(\texttt{create\_calendar\_event}(\text{title="Meeting", time="2pm"}))$
- $\texttt{wait}$

---

### 3.4 Transition Function $T$

$$T: \mathcal{S} \times \mathcal{A}_\mathbf{U} \times \mathcal{A}_\mathbf{A} \rightarrow \mathcal{S}$$

**Definition**: Given current state and joint action, produces next state. Base model is deterministic; stochastic extension supports tool failure probability.

**PARE Mapping**: State transitions handled by `handle_state_transition()` in `StatefulApp`

**Example**:

Initial: $s = (\texttt{ContactsList}, \texttt{Contacts}, \{...\}, ([], \emptyset, []))$

Action: $a_\mathbf{U} = \texttt{open\_contact}(\text{"C001"})$, $a_\mathbf{A} = \texttt{wait}$

Result: $s' = (\texttt{ContactDetail("C001")}, \texttt{Contacts}, \{...\}, ([\texttt{ContactsList}], \emptyset, [...]))$

---

### 3.5 Observation Spaces $\mathcal{O}_i$

#### 3.5.1 User Observation $\mathcal{O}_\mathbf{U}$

$$\mathcal{O}_\mathbf{U}(s) = (\mathcal{O}_{\text{screen}}, \mathcal{O}_{\text{tools}}, \mathcal{O}_{\text{proposals}}, \mathcal{O}_{\text{env}})$$

The user's observation is a function of the current state only.

**Components**:

- $\mathcal{O}_{\text{screen}}$: Current app and state information
- $\mathcal{O}_{\text{tools}}$: Available actions with descriptions
- $\mathcal{O}_{\text{proposals}}$: Pending proposal from agent (if any)
- $\mathcal{O}_{\text{env}}$: Environment notifications (truncated -- e.g., new email shows sender and subject, not full content)

**PARE Mapping**: `CurrentAppStateLog`, `AvailableToolsLog`, `AgentMessageLog`, `EnvironmentNotificationLog`

**Example**:

```
O_U(s) = (
    screen: "Email -> MailboxView(INBOX)",
    tools: ["list_emails()", "search_emails()", "open_email()", ...],
    proposal: "Agent suggests: Create calendar event for meeting?",
    env: ["[10:00] New email received"]
)
```

#### 3.5.2 Agent Observation $\mathcal{O}_\mathbf{A}$

$$\mathcal{O}_\mathbf{A}(s, a_\mathbf{U}) = (\mathcal{O}_{\text{user\_actions}}, \mathcal{O}_{\text{env}}, \mathcal{O}_{\text{proposal\_response}})$$

The agent's observation is a function of both the state **and** the user's action, reflecting the Stackelberg structure.

**Components**:

- $\mathcal{O}_{\text{user\_actions}}$: User's executed actions (not user's observations)
- $\mathcal{O}_{\text{env}}$: Environment notifications
- $\mathcal{O}_{\text{proposal\_response}}$: User's response to last proposal (if any)

**PARE Mapping**: `UserActionLog`, `EnvironmentNotificationLog`

**Example**:

```
O_A(s, a_U) = (
    user_action: "open_email(id='E001')",
    user_action_history: ["open_app(email)", "search_emails('meeting')"],
    env: ["[09:55] Reminder: Meeting at 2pm"],
    proposal_response: None
)
```

---

### 3.6 Instruction Space $\mathcal{I}$

$$\mathcal{I} = \mathcal{I}_\mathbf{U} \times \mathcal{I}_\mathbf{A}$$

**Definition**: Task specifications provided to each agent at episode start. Instructions are part of policy conditioning.

**Components**:

- $\mathcal{I}_\mathbf{U}$: User's goal in natural language
- $\mathcal{I}_\mathbf{A}$: Agent's objective (observe and assist)

**PARE Mapping**: Scenario definitions in `PAREScenario`

**Example**:

```
I_U = "You received an email about a meeting with Alice. Schedule it on your calendar."
I_A = "Observe user actions and propose helpful interventions when appropriate."
```

---

### 3.7 Reward Function $R$

$$R: \mathcal{S} \times \mathcal{A}_\mathbf{U} \times \mathcal{A}_\mathbf{A} \rightarrow \mathbb{R}^2$$

**Definition**: PARE uses a dual reward structure:

$$R(s, a_\mathbf{U}, a_\mathbf{A}) = (R_\textrm{Succeed}(s), R_\textrm{Accept}(a_\mathbf{U}, a_\mathbf{A}))$$

#### 3.7.1 Success Reward $R_\textrm{Succeed}$

$$R_\textrm{Succeed}: \mathcal{S} \rightarrow \{0, 1\}$$

Terminal reward indicating whether the user's goals $\mathcal{G}_\mathbf{U}$ are fulfilled in the final environment state, as verified by the scenario oracle:

$$R_\textrm{Succeed}(s) = \begin{cases} 1 & \text{if } s_{\text{db}} \models \phi_{\text{goal}} \\ 0 & \text{otherwise} \end{cases}$$

where $\phi_{\text{goal}}$ is the goal predicate from the scenario oracle.

**PARE Mapping**: `scenario.validate(env)`

**Example**: For "create calendar event" task:

$$\phi_{\text{goal}} = \exists e \in \text{CalendarEvents}: e.\text{title} = \text{"Meeting"} \land e.\text{time} = \text{"2pm"}$$

#### 3.7.2 Acceptance Reward $R_\textrm{Accept}$

$$R_\textrm{Accept}: \mathcal{A}_\mathbf{U} \times \mathcal{A}_\mathbf{A} \rightarrow \{-1, 0, 1\}$$

Per-step reward for proposal quality:

$$R_\textrm{Accept}(a_\mathbf{U}, a_\mathbf{A}) = \begin{cases}
+1 & \text{if } a_\mathbf{A} = \texttt{propose}(\cdot) \land a_\mathbf{U} = \texttt{accept} \\
-1 & \text{if } a_\mathbf{A} = \texttt{propose}(\cdot) \land a_\mathbf{U} = \texttt{reject} \\
0 & \text{otherwise}
\end{cases}$$

**PARE Mapping**: Computed from `proposal_count` and `acceptance_count`

**Example**:

- Agent proposes calendar event, user accepts: $R_\textrm{Accept} = +1$
- Agent proposes irrelevant action, user rejects: $R_\textrm{Accept} = -1$
- Agent waits (no proposal): $R_\textrm{Accept} = 0$

---

## 4. Episode Dynamics

### 4.1 Initialization

1. Sample initial state $s^0 \sim P_0(\mathcal{S})$ from scenario definition
2. Provide instructions $I = (I_\mathbf{U}, I_\mathbf{A}) \in \mathcal{I}$

### 4.2 Turn Structure (Stackelberg)

Each turn $t$ follows the Stackelberg structure: the user acts first, the agent observes the user's action, then the agent acts:

```
Turn t:
+---------------------------------------------------------------------------+
|  USER PHASE (Leader)                                                      |
|  1. o_U^t = O_U(s^t)                                                     |
|  2. a_U^t ~ pi_U(. | o_U^t, h_U^t, I_U)                                 |
|         subject to: a_U^t in A_U(s_app^t, s_global^t)                    |
+---------------------------------------------------------------------------+
|  AGENT PHASE (Follower)                                                   |
|  3. o_A^t = O_A(s^t, a_U^t)            <- agent sees user's action       |
|  4. a_A^t ~ pi_A(. | o_A^t, h_A^t, I_A)                                 |
+---------------------------------------------------------------------------+
|  ENVIRONMENT UPDATE                                                       |
|  5. s^{t+1} = T(s^t, a_U^t, a_A^t)                                      |
|  6. r^t = R(s^t, a_U^t, a_A^t)                                           |
|  7. Update histories: h_i^{t+1} = update(h_i^t, o_i^t, a_i^t)           |
+---------------------------------------------------------------------------+
```

### 4.3 Termination

Episode ends when:

- $t = T_{\max}$ (maximum turns reached), or
- Environment signals completion

### 4.4 Cumulative Return

$$G = \sum_{t=0}^{T} R_\textrm{Accept}(a_\mathbf{U}^t, a_\mathbf{A}^t) + R_\textrm{Succeed}(s^T)$$

---

## 5. Summary

| Component | Symbol | Type | PARE Implementation |
|-----------|--------|------|-------------------|
| Agents | $\mathcal{N} = \{\mathbf{U}, \mathbf{A}\}$ | Set | `{UserAgent, ProactiveAgent}` |
| App State | $\mathcal{S}_{\text{app}}$ | Finite | `StatefulApp.current_state` |
| Global State | $\mathcal{S}_{\text{global}}$ | Finite | `env.active_app` |
| Database | $\mathcal{S}_{\text{db}}$ | Structured | App backends |
| History | $\mathcal{S}_{\text{history}}$ | Bounded | Logs, nav stack |
| User Actions | $\mathcal{A}_\mathbf{U}(s)$ | State-dependent | `env.get_user_tools()` |
| Agent Actions | $\mathcal{A}_\mathbf{A}$ | Fixed | `{read(...), propose(...), wait}` |
| Transition | $T$ | Deterministic | `handle_state_transition()` |
| User Obs | $\mathcal{O}_\mathbf{U}(s)$ | Function of $s$ | Agent logs |
| Agent Obs | $\mathcal{O}_\mathbf{A}(s, a_\mathbf{U})$ | Function of $s$, $a_\mathbf{U}$ | Agent logs |
| Instructions | $\mathcal{I}$ | Natural language | `PAREScenario` |
| Success Reward | $R_\textrm{Succeed}$ | $\{0, 1\}$ | `scenario.validate()` |
| Acceptance Reward | $R_\textrm{Accept}$ | $\{-1, 0, 1\}$ | acceptance tracking |
