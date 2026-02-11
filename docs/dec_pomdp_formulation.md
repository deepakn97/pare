# Dec-POMDP Formulation for PAS

## 1. Overview

The Proactive Agent Sandbox (PAS) models a two-agent system where a **User** interacts with mobile applications while a **Proactive Agent** observes user behavior and proposes helpful interventions. We formalize this as a **Decentralized Partially Observable Markov Decision Process (Dec-POMDP)** with asymmetric information, state-dependent action spaces, and Stackelberg turn structure.

### Key Characteristics

- **Asymmetric agents**: User has state-constrained actions; agent has privileged access
- **Partial observability**: Agents receive different observations of the same state
- **Stackelberg turns**: Within each turn, user acts first, agent observes user action, then agent acts
- **Dual rewards**: Task success (terminal) + proposal acceptance (per-step)

---

## 2. Formal Definition

A PAS Dec-POMDP is defined by the tuple:

$$\mathcal{M} = \langle \mathcal{N}, \mathcal{S}, \{\mathcal{A}_i\}_{i \in \mathcal{N}}, T, R, \{\Omega_i\}_{i \in \mathcal{N}}, \{O_i\}_{i \in \mathcal{N}}, \mathcal{I}, \gamma \rangle$$

| Symbol | Name | Description |
|--------|------|-------------|
| $\mathcal{N}$ | Agent set | Set of agents |
| $\mathcal{S}$ | State space | Global environment state |
| $\mathcal{A}_i$ | Action space | Actions available to agent $i$ |
| $T$ | Transition function | State dynamics |
| $R$ | Reward function | Reward signal |
| $\Omega_i$ | Observation space | What agent $i$ can observe |
| $O_i$ | Observation function | How observations are generated for agent $i$ |
| $\mathcal{I}$ | Instruction space | Task specifications for agents |
| $\gamma$ | Discount factor | Future reward discounting |

---

## 3. Component Definitions

### 3.1 Agent Set $\mathcal{N}$

$$\mathcal{N} = \{\text{user}, \text{agent}\}$$

**Definition**: The set of decision-making entities in the environment.

**PAS Mapping**:

- `user`: Simulated by `UserAgent` - interacts with apps to accomplish tasks
- `agent`: Implemented by `ProactiveAgent` - observes user and proposes interventions

**Example**: In a "schedule meeting" scenario:

- User navigates Email app to find meeting request
- Agent observes user reading email, proposes creating calendar event

---

### 3.2 State Space $\mathcal{S}$

$$\mathcal{S} = \mathcal{S}_{\text{app}} \times \mathcal{S}_{\text{global}} \times \mathcal{S}_{\text{db}} \times \mathcal{S}_{\text{history}}$$

#### 3.2.1 App State $\mathcal{S}_{\text{app}}$

$$\mathcal{S}_{\text{app}} = \bigcup_{a \in \text{Apps}} \text{States}(a)$$

**Definition**: The current screen/view within the active application.

**PAS Mapping**: `StatefulApp.current_state: AppState`

**Example (Contacts App)**:

$$\mathcal{S}_{\text{app}}^{\text{contacts}} = \{\texttt{ContactsList}, \texttt{ContactDetail}(c), \texttt{ContactEdit}(c) \mid c \in \text{ContactIDs}\}$$

Concrete instance: $s_{\text{app}} = \texttt{ContactDetail}(\text{"C001"})$ - viewing contact with ID "C001"

#### 3.2.2 Global State $\mathcal{S}_{\text{global}}$

$$\mathcal{S}_{\text{global}} = \{\texttt{Home}, \texttt{Contacts}, \texttt{Email}, \texttt{Calendar}, \texttt{Notes}, \texttt{Reminder}, \texttt{Messaging}\}$$

**Definition**: Which application is currently active (foreground).

**PAS Mapping**: `StateAwareEnvironmentWrapper.active_app: App`

**Example**: $s_{\text{global}} = \texttt{Email}$ means the Email app is in foreground.

#### 3.2.3 Database State $\mathcal{S}_{\text{db}}$

$$\mathcal{S}_{\text{db}} = \prod_{a \in \text{Apps}} \text{Data}(a)$$

**Definition**: The persistent data across all applications.

**PAS Mapping**: App backend data stores (e.g., `contacts_app._backend.contacts`)

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

$$\mathcal{S}_{\text{history}} = \mathcal{H}_{\text{user}} \times \mathcal{H}_{\text{agent}}$$

**Definition**: Truncated, bounded view of past events relevant to each agent's decision-making. Since history is truncated (finite window), $|\mathcal{S}_{\text{history}}|$ is bounded, preserving the Markov property.

**Components**:

$\mathcal{H}_{\text{user}}$: User-relevant history

- Navigation stack for `go_back()` functionality
- Most recent agent proposal (if any)
- Recent environment notifications

$\mathcal{H}_{\text{agent}}$: Agent-relevant history

- Recent user actions (truncated window)
- Agent's own previous proposals
- Recent environment notifications

**PAS Mapping**:

- Navigation: `StatefulApp.navigation_stack`
- User actions: `UserActionLog` entries
- Proposals: `AgentMessageLog` (latest only)
- Notifications: `EnvironmentNotificationLog`

**Example**:

```
s_history = (
    h_user: {
        nav_stack: [ContactsList],
        pending_proposal: "Create calendar event for meeting?",
        env_notifs: ["New email from alice@example.com"]
    },
    h_agent: {
        user_actions: ["open_app(email)", "search_emails('meeting')", "open_email('E001')"],
        last_proposal: "Create calendar event for meeting?",
        env_notifs: ["Reminder: Meeting at 2pm"]
    }
)
```

---

### 3.3 Action Spaces $\mathcal{A}_i$

#### 3.3.1 User Action Space $\mathcal{A}_{\text{user}}$

$$\mathcal{A}_{\text{user}}: \mathcal{S}_{\text{app}} \times \mathcal{S}_{\text{global}} \rightarrow 2^{\mathcal{A}_{\text{user}}^{\text{all}}}$$

**Definition**: The user's available actions depend on the current app state. This is a **state-dependent action space**.

**Constraint**: At state $s$, user must select from valid actions:

$$a_{\text{user}}^t \in \mathcal{A}_{\text{user}}(s_{\text{app}}^t, s_{\text{global}}^t)$$

**PAS Mapping**: `environment.get_user_tools()`

**Example**:

| State | Available Actions $\mathcal{A}_{\text{user}}(s)$ |
|-------|--------------------------------------------------|
| $s_{\text{app}} = \texttt{Home}$ | `{open_app(contacts), open_app(email), open_app(calendar), ...}` |
| $s_{\text{app}} = \texttt{ContactsList}$ | `{list_contacts(), search_contacts(), open_contact(), create_contact(), go_home(), switch_app()}` |
| $s_{\text{app}} = \texttt{ContactDetail(C001)}$ | `{view_contact(), start_edit(), delete_contact(), go_back(), go_home()}` |
| Any state + pending proposal | Above $\cup$ `{accept, reject}` |

#### 3.3.2 Proactive Agent Action Space $\mathcal{A}_{\text{agent}}$

$$\mathcal{A}_{\text{agent}} = \mathcal{A}_{\text{propose}} \cup \{\texttt{wait}\}$$

**Definition**: The agent's action space is **state-independent** (privileged access).

**Components**:

- $\mathcal{A}_{\text{propose}} = \{\texttt{propose}(a) \mid a \in \mathcal{A}_{\text{privileged}}\}$: Propose executing a tool
- $\texttt{wait}$: Take no action this turn

where $\mathcal{A}_{\text{privileged}}$ includes all app tools without state constraints.

**PAS Mapping**: `environment.get_tools()`

**Example**:

- $\texttt{propose}(\texttt{create\_calendar\_event}(\text{title="Meeting", time="2pm"}))$
- $\texttt{wait}$

---

### 3.4 Transition Function $T$

$$T: \mathcal{S} \times \mathcal{A}_{\text{user}} \times \mathcal{A}_{\text{agent}} \rightarrow \mathcal{S}$$

**Definition**: Given current state and joint action, produces next state. Base model is deterministic; stochastic extension supports tool failure probability.

**PAS Mapping**: State transitions handled by `handle_state_transition()` in `StatefulApp`

**Example**:

Initial: $s = (\texttt{ContactsList}, \texttt{Contacts}, \{...\}, ([], \emptyset, []))$

Action: $a_{\text{user}} = \texttt{open\_contact}(\text{"C001"})$, $a_{\text{agent}} = \texttt{wait}$

Result: $s' = (\texttt{ContactDetail("C001")}, \texttt{Contacts}, \{...\}, ([\texttt{ContactsList}], \emptyset, [...]))$

---

### 3.5 Observation Spaces $\Omega_i$ and Functions $O_i$

#### 3.5.1 User Observation Space $\Omega_{\text{user}}$

$$\Omega_{\text{user}} = \mathcal{O}_{\text{screen}} \times \mathcal{O}_{\text{tools}} \times \mathcal{O}_{\text{proposals}} \times \mathcal{O}_{\text{env}}$$

**Components**:

- $\mathcal{O}_{\text{screen}}$: Current app and state information
- $\mathcal{O}_{\text{tools}}$: Available actions with descriptions
- $\mathcal{O}_{\text{proposals}}$: Pending proposal from agent (if any)
- $\mathcal{O}_{\text{env}}$: Environment notifications

**User Observation Function**:

$$O_{\text{user}}: \mathcal{S} \rightarrow \Omega_{\text{user}}$$

User observation depends only on current state.

**PAS Mapping**: `CurrentAppStateLog`, `AvailableToolsLog`, `AgentMessageLog`, `EnvironmentNotificationLog`

**Example**:

```
o_user = O_user(s) = (
    screen: "Email -> MailboxView(INBOX)",
    tools: ["list_emails()", "search_emails()", "open_email()", ...],
    proposal: "Agent suggests: Create calendar event for meeting?",
    env: ["[10:00] New email received"]
)
```

#### 3.5.2 Agent Observation Space $\Omega_{\text{agent}}$

$$\Omega_{\text{agent}} = \mathcal{O}_{\text{user\_actions}} \times \mathcal{O}_{\text{env}} \times \mathcal{O}_{\text{proposal\_response}}$$

**Components**:

- $\mathcal{O}_{\text{user\_actions}}$: User's executed actions (not user's observations)
- $\mathcal{O}_{\text{env}}$: Environment notifications
- $\mathcal{O}_{\text{proposal\_response}}$: User's response to last proposal (if any)

**Agent Observation Function**:

$$O_{\text{agent}}: \mathcal{S} \times \mathcal{A}_{\text{user}} \rightarrow \Omega_{\text{agent}}$$

Agent observation depends on state **and** user's action (agent sees what user did).

**PAS Mapping**: `UserActionLog`, `EnvironmentNotificationLog`

**Example**:

```
o_agent = O_agent(s, a_user) = (
    user_action: "open_email(id='E001')",
    user_action_history: ["open_app(email)", "search_emails('meeting')"],
    env: ["[09:55] Reminder: Meeting at 2pm"],
    proposal_response: None
)
```

---

### 3.6 Instruction Space $\mathcal{I}$

$$\mathcal{I} = \mathcal{I}_{\text{user}} \times \mathcal{I}_{\text{agent}}$$

**Definition**: Task specifications provided to each agent at episode start. Instructions are part of policy conditioning.

**Components**:

- $\mathcal{I}_{\text{user}}$: User's goal in natural language
- $\mathcal{I}_{\text{agent}}$: Agent's objective (observe and assist)

**PAS Mapping**: Scenario definitions in `PASScenario`

**Example**:

```
I_user = "You received an email about a meeting with Alice. Schedule it on your calendar."
I_agent = "Observe user actions and propose helpful interventions when appropriate."
```

---

### 3.7 Reward Function $R$

$$R: \mathcal{S} \times \mathcal{A}_{\text{user}} \times \mathcal{A}_{\text{agent}} \rightarrow \mathbb{R}^2$$

**Definition**: PAS uses a dual reward structure:

$$R(s, a_{\text{user}}, a_{\text{agent}}) = (R_{\text{success}}(s), R_{\text{proposal}}(a_{\text{user}}, a_{\text{agent}}))$$

#### 3.7.1 Success Reward $R_{\text{success}}$

$$R_{\text{success}}: \mathcal{S} \rightarrow \{0, 1\}$$

Terminal reward indicating task goal achievement:

$$R_{\text{success}}(s) = \begin{cases} 1 & \text{if } s_{\text{db}} \models \phi_{\text{goal}} \\ 0 & \text{otherwise} \end{cases}$$

where $\phi_{\text{goal}}$ is the goal predicate from the scenario oracle.

**PAS Mapping**: `scenario.validate(env)`

**Example**: For "create calendar event" task:

$$\phi_{\text{goal}} = \exists e \in \text{CalendarEvents}: e.\text{title} = \text{"Meeting"} \land e.\text{time} = \text{"2pm"}$$

#### 3.7.2 Proposal Reward $R_{\text{proposal}}$

$$R_{\text{proposal}}: \mathcal{A}_{\text{user}} \times \mathcal{A}_{\text{agent}} \rightarrow \{-1, 0, 1\}$$

Per-step reward for proposal quality:

$$R_{\text{proposal}}(a_{\text{user}}, a_{\text{agent}}) = \begin{cases}
+1 & \text{if } a_{\text{agent}} = \texttt{propose}(\cdot) \land a_{\text{user}} = \texttt{accept} \\
-1 & \text{if } a_{\text{agent}} = \texttt{propose}(\cdot) \land a_{\text{user}} = \texttt{reject} \\
0 & \text{otherwise}
\end{cases}$$

**PAS Mapping**: Computed from `proposal_count` and `acceptance_count`

**Example**:

- Agent proposes calendar event, user accepts: $R_{\text{proposal}} = +1$
- Agent proposes irrelevant action, user rejects: $R_{\text{proposal}} = -1$
- Agent waits (no proposal): $R_{\text{proposal}} = 0$

---

### 3.8 Discount Factor $\gamma$

$$\gamma \in [0, 1]$$

**PAS Setting**: $\gamma = 1$ (undiscounted) since episodes have bounded length via `max_turns`.

---

## 4. Episode Dynamics

### 4.1 Initialization

1. Sample initial state $s^0 \sim P_0(\mathcal{S})$ from scenario definition
2. Provide instructions $I = (I_{\text{user}}, I_{\text{agent}}) \in \mathcal{I}$

### 4.2 Turn Structure (Stackelberg)

Each turn $t$ follows a **sequential structure** where the agent observes the user's action before acting:

```
Turn t:
+---------------------------------------------------------------------------+
|  USER PHASE                                                               |
|  1. o_user^t = O_user(s^t)                                                |
|  2. a_user^t ~ pi_user(. | o_user^t, h_user^t, I_user)                    |
|         subject to: a_user^t in A_user(s_app^t, s_global^t)               |
+---------------------------------------------------------------------------+
|  AGENT PHASE                                                              |
|  3. o_agent^t = O_agent(s^t, a_user^t)     <- agent sees user's action    |
|  4. a_agent^t ~ pi_agent(. | o_agent^t, h_agent^t, I_agent)               |
+---------------------------------------------------------------------------+
|  ENVIRONMENT UPDATE                                                       |
|  5. s^{t+1} = T(s^t, a_user^t, a_agent^t)                                 |
|  6. r^t = R(s^t, a_user^t, a_agent^t)                                     |
|  7. Update histories: h_i^{t+1} = update(h_i^t, o_i^t, a_i^t)             |
+---------------------------------------------------------------------------+
```

### 4.3 Termination

Episode ends when:

- $t = T_{\max}$ (maximum turns reached), or
- Environment signals completion

### 4.4 Cumulative Return

$$G = \sum_{t=0}^{T} \gamma^t R_{\text{proposal}}(a_{\text{user}}^t, a_{\text{agent}}^t) + R_{\text{success}}(s^T)$$

---

## 5. Summary

| Component | Symbol | Type | PAS Implementation |
|-----------|--------|------|-------------------|
| Agents | $\mathcal{N}$ | Set | `{UserAgent, ProactiveAgent}` |
| App State | $\mathcal{S}_{\text{app}}$ | Finite | `StatefulApp.current_state` |
| Global State | $\mathcal{S}_{\text{global}}$ | Finite | `env.active_app` |
| Database | $\mathcal{S}_{\text{db}}$ | Structured | App backends |
| History | $\mathcal{S}_{\text{history}}$ | Bounded | Logs, nav stack |
| User Actions | $\mathcal{A}_{\text{user}}(s)$ | State-dependent | `env.get_user_tools()` |
| Agent Actions | $\mathcal{A}_{\text{agent}}$ | Fixed | `{propose(...), wait}` |
| Transition | $T$ | Deterministic | `handle_state_transition()` |
| User Obs | $O_{\text{user}}(s)$ | Function of $s$ | Agent logs |
| Agent Obs | $O_{\text{agent}}(s, a_{\text{user}})$ | Function of $s$, $a_{\text{user}}$ | Agent logs |
| Instructions | $\mathcal{I}$ | Natural language | `PASScenario` |
| Success Reward | $R_{\text{success}}$ | $\{0, 1\}$ | `scenario.validate()` |
| Proposal Reward | $R_{\text{proposal}}$ | $\{-1, 0, 1\}$ | acceptance tracking |
