---
description: Generate a new proactive scenario for PAS following a step-by-step workflow
argument-hint: [scenario-focus (e.g., "email-calendar", "contact-messaging")]
---

# Generate Proactive Scenario: $ARGUMENTS

You are helping create a proactive scenario for PAS (Proactive Agent Sandbox).

## Context
First, read these files to understand the system:
- `README.md` - Project overview
- `pas/scenarios/benchmark/email_notification.py` - Example scenario
- `pas/apps/` - Available apps with user tools

**CRITICAL**: Do not create scenarios which require apps that are not present in `pas/apps/`. Meta-ARE has more apps, but we can't use them if we don't have the corresponding PAS wrappers in this repo.

## Understanding Tool Architecture

**CRITICAL**: To understand the full capabilities of each app:
1. **User tools** (`@user_tool`) are defined in `pas/apps/<app_name>/`
2. **App tools** (`@app_tool`) and **environment tools** (`@env_tool`) are defined in the base Meta-ARE classes under `are/simulation/apps/` (installed package)

**Before creating scenarios**:
- Read the PAS app class in `pas/apps/<app_name>/app.py` to see the stateful navigation
- Read the corresponding Meta-ARE base class to understand all available tools (env_tool, app_tool)
- Example: `StatefulEmailApp` extends `EmailClientV2` from `meta-are/are/simulation/apps/email_client.py`

## Available Apps
- **StatefulContactsApp** - Contacts management (extends `ContactsApp` from Meta-ARE)
- **StatefulEmailApp** - Email client with folders (extends `EmailClientV2` from Meta-ARE)
- **StatefulCalendarApp** - Calendar events (extends `CalendarV2` from Meta-ARE)
- **StatefulMessagingApp** - Text messaging (extends `MessagingAppV2` from Meta-ARE)
- **PASAgentUserInterface** - Agent-user communication (extends `AgentUserInterface` from Meta-ARE)

## CRITICAL: Temporal Coherence and Ecological Validity

**Problem**: The simulation uses a time manager that provides timestamps to agents via notifications. If `start_time = 0` (Unix epoch = Jan 1, 1970), agents receive notifications timestamped "1970-01-01 00:00:05" while calendar events reference "2025-11-19 14:00:00". This temporal mismatch breaks ecological validity.

**Solution**: Use ecologically valid timestamps that align simulation time with scenario data.

### Setting start_time

**ALWAYS** set `start_time` to a realistic date aligned with your scenario data:

```python
from datetime import datetime, timezone

# Example: Scenario about meeting next week
# Today: 2025-11-11, Meeting: 2025-11-19 at 2 PM
start_time: float | None = datetime(2025, 11, 11, 9, 0, 0, tzinfo=timezone.utc).timestamp()
```

**Guidelines**:
1. **Default to current date**: Use today's date (ask user if unsure) as the scenario start
2. **Add explanatory comment**: Document the date and reasoning
3. **Align with data**: Ensure calendar events, email timestamps, etc. are coherent with start_time
4. **Use UTC timezone**: Always use `timezone.utc` for consistency

**Example temporal alignment**:
- Scenario starts: `2025-11-11 09:00:00` (start_time)
- Email received: `+2 seconds` → Agent sees "2025-11-11 09:00:02" ✓
- Meeting proposed: `2025-11-19 14:00:00` → 8 days in future ✓
- Agent reasoning: "Meeting is next Tuesday" ✓

**Do NOT use**:
- ❌ `start_time = 0` (causes 1970 timestamps)
- ❌ `start_time = None` (unpredictable default behavior)
- ❌ Misaligned dates (email says "tomorrow" but calendar shows next month)

## Workflow - FOLLOW STEP BY STEP

**IMPORTANT**: Each step has TWO phases:
1. **Discussion phase**: Present details and get user approval
2. **Implementation phase**: Write code to scenario file, wait for user to verify and explicitly say "let's move on to next step"

### Step 0: Ensure Scenario Uniqueness

**CRITICAL - Do this FIRST**:
Before proposing any scenario idea, you MUST:
1. List all existing scenarios in `pas/scenarios/user_scenarios/` for yourself. Don't show this to user and don't be verbose about it.
2. Read each existing scenario to understand:
   - What trigger patterns/contexts they use
   - What complexity/constraints they involve
   - What agent tools (`@app_tool` decorated methods) are used in oracle events
3. Ensure your proposed scenario is **substantively unique**

**What makes a scenario unique:**
- **Novel trigger patterns**: Not just "incoming email" but specific contexts:
  - New email chain vs. new message in existing chain
  - Single sender vs. multiple participants in a thread
  - Temporal patterns (e.g., waiting for last person to respond)
  - Cross-app triggers (e.g., email + calendar conflict detection)
- **Different complexity/constraints**: Even if high-level goal is similar, add novel challenges:
  - Coordinating multiple people (e.g., waiting for 4/5 recipients to reply before acting)
  - Handling conflicts or exceptions
  - Multi-step reasoning or conditional logic
- **Exercising different agent capabilities**: Check which `@app_tool` methods have been used in existing scenarios' oracle events, then design scenarios that require *different* tools the agent hasn't used yet

**What is NOT sufficient for uniqueness:**
- Just using different apps (e.g., "email+calendar" vs "email+contacts" alone isn't enough)
- Generic trigger descriptions (e.g., "email arrives" - be specific about the context!)
- Same complexity level with slightly different data (e.g., "schedule meeting with Alice" vs "schedule meeting with Bob")

**Format**: Understand the existing scenarios with their trigger patterns, complexity, and tools used. Then propose your unique scenario idea explaining what makes it different.

**WAIT for user approval** of your unique scenario idea before proceeding to Step 1.

---

### Step 1: Scenario Description

**Phase 1a - Discussion**:
Create a narrative description that includes:
- What user actions occur in which apps
- What context/pattern triggers the proactive agent to act
- What the agent should infer and propose to the user
- Expected user response (accept/reject)

**Format**: Write 2-3 paragraphs describing the complete scenario flow.

**WAIT for user approval** (e.g., "approved", "looks good", "proceed with code")

**Phase 1b - Implementation**:
After approval, create the scenario file in `pas/scenarios/user_scenarios/<scenario_name>.py`:
- Create the scenario class skeleton with `@register_scenario` decorator
- Add the approved description as the class docstring
- Add scenario metadata (start_time, duration, status, is_benchmark_ready)

**WAIT for user verification and explicit "let's move on to next step" before proceeding to Step 2.**

---

### Step 2: Apps & Data Setup

**Phase 2a - Discussion**:
Specify the following for `init_and_populate_apps()`:

For each app involved:
- **App name** (e.g., StatefulEmailApp, StatefulContactsApp)
- **Initial/baseline data** to populate (pre-existing data BEFORE scenario starts):
  - Contacts: Existing contacts (first_name, last_name, contact_id, phone, email)
  - Calendar events: Past/existing events (event_id, title, start_datetime, end_datetime, attendees, location)
  - Messages: Old message history (conversation_id, participants, messages)

**IMPORTANT**: Do NOT pre-populate NEW data that should arrive during the scenario (incoming emails, new messages, etc.). Those belong in `build_events_flow()` as events.

**Format**: List each app and its test data in structured format.

**WAIT for user approval** (e.g., "approved", "looks good", "proceed with code")
_Note_: In the automated multi-step generator used in this repo, this approval is implicit and the agent
automatically proceeds to the code implementation phase without waiting for human confirmation.

**Phase 2b - Implementation**:
After approval (or implicit approval in the automated pipeline), implement the `init_and_populate_apps()` method in the scenario file:
- Initialize each app instance
- Populate with approved test data
- Add all apps to `self.apps` list

**WAIT for user verification and explicit "let's move on to next step" before proceeding to Step 3.**

---

### Step 3: Events Flow

**Phase 3a - Discussion**:
Define the event sequence for `build_events_flow()`:

List each event with:
1. **Event source**: Which app triggers it
2. **Function call**: Exact method name and arguments
3. **Event type**: Oracle (`.oracle()`) or regular
4. **Timing**: Use `.delayed(seconds)` or `.depends_on(other_event, delay_seconds=N)`
5. **Purpose**: Brief explanation

**CRITICAL REQUIREMENT for environment events**:
- **Any non-oracle environment event** used in `build_events_flow()` MUST have a notification template in `pas/apps/notification_templates.py`
  - Templates must exist for BOTH "user" and "agent" views
  - Check `NOTIFICATION_TEMPLATES` dict before using any environment event
  - Examples: `send_email_to_user_only`, `send_email_to_user_with_id`, `create_and_add_message`
  - Oracle events (`.oracle()`) do NOT need templates
  - If event not in templates, you must add it first (see email_notification scenario example)

**Email ID Referencing Problem and Solution**:
- **Problem**: Meta-ARE's `send_email_to_user_only()` auto-generates email_id, making it impossible to reference in subsequent events (e.g., `reply_to_email()`)
- **Solution**: Use PAS's custom `send_email_to_user_with_id()` when you need to reply to emails:
  ```python
  # In build_events_flow():
  email_event = email.send_email_to_user_with_id(
      email_id="email-from-alice",  # Known ID for later reference
      sender="alice@example.com",
      subject="Meeting Request",
      content="Can we meet tomorrow?",
  ).delayed(2)

  # Later, agent can reply using the known ID:
  reply_event = email.reply_to_email(
      email_id="email-from-alice",
      content="Yes, I'm available!",
  ).oracle().depends_on(acceptance_event, delay_seconds=2)
  ```
- **Note**: If scenario doesn't need to reply to emails, use `send_email_to_user_only()` as normal

**Event Registration Requirement**:
- **CRITICAL**: ALL events defined in `build_events_flow()` MUST be added to `self.events` list
- Missing events will not execute, causing validation to fail
- Example:
  ```python
  # Define events
  event1 = app.action1().delayed(2)
  event2 = app.action2().depends_on(event1, delay_seconds=2)
  event3 = app.action3().depends_on(event2, delay_seconds=1)

  # Register ALL events
  self.events = [event1, event2, event3]  # Don't forget any!
  ```

**Key patterns**:
- Oracle events: Background/automated actions (incoming emails, agent proposals)
- User actions: Typically follow agent proposals with `.depends_on()`
- Timing: Use realistic delays (2-5 seconds between related events)

**Format**: Numbered list of events with all details.

**WAIT for user approval** (e.g., "approved", "looks good", "proceed with code")

**Phase 3b - Implementation**:
After approval, implement the `build_events_flow()` method in the scenario file:
- Use `EventRegisterer.capture_mode()` context
- Create each event with proper chaining (`.delayed()`, `.depends_on()`, `.oracle()`)
- Store events in `self.events` list

**WAIT for user verification and explicit "let's move on to next step" before proceeding to Step 4.**

---

### Step 4: Validation Conditions

**Phase 4a - Discussion**:
Define success criteria for `validate()`:

Specify what to check in `env.event_log.list_view()`:
- **Agent proposal verification**: Check for EventType.AGENT with specific function_name and content
- **Task completion verification**: Check for EventType.AGENT actions on other apps
- **Expected arguments**: Verify args contain correct data (emails, contact IDs, etc.)

**Validation Flexibility Guidelines**:
- **Be flexible on wording/format, strict on logic**: Validate essential requirements without over-constraining implementation
- **Examples of what to validate strictly vs flexibly**:
  - ✅ STRICT: Agent checked calendar for time range that overlaps with proposed meeting (e.g., if meeting is 2-3 PM, agent must check a range containing that time)
  - ✅ STRICT: Event created with correct date, start/end times for the meeting
  - ✅ STRICT: Key attendees included (e.g., "Sarah Johnson" must be in attendees list)
  - ✅ FLEXIBLE: Exact event title (e.g., "Meeting with Sarah" vs "Project Planning Meeting with Sarah Johnson")
  - ✅ FLEXIBLE: Location string format (e.g., check for "Conference Room A" OR "Downtown Office", not exact match)
  - ❌ BAD: Don't validate exact wording of agent messages to user
  - ❌ BAD: Don't require agent to check only the exact meeting time range (2:00-3:00 PM) - wider ranges (1:00-4:00 PM) are also valid
- **Rationale**: Agents may use different phrasings/approaches while achieving the core goal correctly

**Format**: List each validation check with:
- What event type to look for
- Which app/function should be called
- What arguments/content should be present (distinguish strict vs flexible requirements)

**WAIT for user approval** (e.g., "approved", "looks good", "proceed with code")

**Phase 4b - Implementation**:
After approval, implement the `validate()` method in the scenario file:
- Iterate through `env.event_log.list_view()`
- Check for each approved validation condition
- Return `ScenarioValidationResult(success=True/False)`
- Handle exceptions with try/except

**WAIT for user verification. Scenario is now complete!**

---

## Important Rules
- **NEVER skip steps** - Each requires explicit approval
- **NEVER proceed to next step** without user saying "let's move on to next step"
- **Write code only after approval** in each phase 'b'
- **Always wait for code verification** before moving to next step
- **Be concise** - Provide enough detail for approval, but avoid verbose explanations
- Follow existing patterns from email_notification.py example
- Focus on realistic proactive scenarios where agent adds clear value
- Verify all non-oracle environment events have notification templates in `pas/apps/notification_templates.py`
