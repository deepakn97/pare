# Scenario Review Guidelines

## Antipatterns to Check

### 1. Manual Data Setup Instead of App Methods
**Wrong:** Directly manipulating internal data structures
```python
# Don't do this for ANY app
self.app.internal_dict["id"] = SomeObject(id="id", ...)
self.messaging.id_to_name[user_id] = user_name
self.reminder.reminders["reminder_001"] = Reminder(...)
self.calendar.events["event_001"] = CalendarEvent(...)
```

**Correct:** Use the app's public methods
```python
# Use add/create methods - they return IDs you can store
self.messaging.add_users(["Sarah Chen"])
sarah_id = self.messaging.name_to_id["Sarah Chen"]

self.reminder.add_reminder(title="...", due_datetime="...", description="...")

self.calendar.add_calendar_event(title="...", start_datetime="...", end_datetime="...")

note_id = self.notes.create_note(folder="Work", title="...", content="...")
```

### 2. Oracle Event Dependencies
**Wrong:** Environment events or ConditionCheckEvents depending on oracle events
```python
# Oracle events don't execute in non-oracle mode!
oracle_event = app.some_action(...).oracle().depends_on(...)
env_event = app.send_to_user(...).depends_on(oracle_event)  # WRONG!
condition = ConditionCheckEvent.from_condition(fn).depends_on(oracle_event)  # WRONG!
```

**Correct:** Use ConditionCheckEvent with delay or depend on other ENV events
```python
def agent_did_action(env: AbstractEnvironment) -> bool:
    for event in env.event_log.list_view():
        if (event.event_type == EventType.AGENT
            and isinstance(event.action, Action)
            and event.action.function_name == "target_function"):
            return True
    return False

# Condition starts checking after delay from scenario start
condition = ConditionCheckEvent.from_condition(agent_did_action).delayed(100)
env_event = app.send_to_user(...).depends_on(condition)
```

### 3. Non-existent Methods
**Always verify method exists before using:**
```bash
uv run python -c "from pas.apps.note import StatefulNotesApp; print([m for m in dir(StatefulNotesApp) if not m.startswith('_')])"
```

**Common mistakes:**
- `get_note_by_title` does NOT exist - use `get_note_by_id` or `search_notes`
- `contacts_manager` does NOT exist in EmailApp
- Always check the actual app implementation in `pas/apps/<app_name>/`

### 4. IDs from Data Setup
**Wrong:** Hardcoding IDs in build_events_flow
```python
def init_and_populate_apps(self):
    self.notes.create_note(folder="Work", title="Meeting Notes", content="...")

def build_events_flow(self):
    # How do you know the ID?
    notes_app.get_note_by_id(note_id="???")  # WRONG!
```

**Correct:** Store IDs as instance variables
```python
def init_and_populate_apps(self):
    self.meeting_note_id = self.notes.create_note(folder="Work", title="Meeting Notes", content="...")

def build_events_flow(self):
    notes_app.get_note_by_id(note_id=self.meeting_note_id)  # Correct
```

### 5. Default Parameters
**Wrong:** Setting parameters that already have good defaults
```python
# Don't override defaults unnecessarily
self.email = StatefulEmailApp(name="Emails", user_email="user@example.com")  # user_email has default
self.messaging.current_user_id = "user_001"  # Already set by app
```

**Correct:** Only set when you need a specific value
```python
self.email = StatefulEmailApp(name="Emails")  # Uses default user_email
# current_user_id is already populated by StatefulMessagingApp
```

### 5a. Required Apps in All Scenarios
**Always include** `PASAgentUserInterface` and `HomeScreenSystemApp` in every scenario:
```python
def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
    self.agent_ui = PASAgentUserInterface()
    self.system_app = HomeScreenSystemApp(name="System")
    # ... other apps ...

    self.apps = [self.agent_ui, self.system_app, ...]  # Always include both
```
These apps are required infrastructure even if not directly used in the scenario's event flow.

### 6. Unrealistic User Interactions and Incoherent Story
**Check for:**
- User providing unrealistically detailed information in responses
- Scenario narrative that doesn't make logical sense
- Agent actions that wouldn't be reasonable given the context

**Story coherence example - WRONG:**
```
User orders a tripod for a photography workshop.
Workshop gets cancelled.
Agent proposes cancelling tripod order because "workshop included equipment rental."
```
This doesn't make sense - if the workshop is cancelled, user LOSES access to rental equipment, so they'd want to KEEP their purchased tripod.

**Story coherence example - CORRECT:**
```
User registers for workshop that INCLUDES a tripod in the package.
User also orders a separate tripod (not realizing it's included).
Agent recognizes the separate order is redundant → proposes cancellation.
```

**Wrong:** Expecting user to provide detailed information
```python
acceptance_event = aui.accept_proposal(
    content="Yes, for Sarah's meeting we approved Q1 budget, for Marcus..."  # Too detailed!
)
```

**Correct:** User gives simple approval, agent extracts details from data
```python
acceptance_event = aui.accept_proposal(content="Yes, please summarize the meeting outcomes.")
# Agent reads notes/calendar to get the actual details
```

### 7. Template Artifacts
**Remove before marking Valid:**
- `"""start of the template to build scenario for Proactive Agent."""`
- `# TODO: import all Apps that will be used in this scenario`
- `# WARNING: this part is responsible to and can be modified only by...`
- `"""end of the template to build scenario for Proactive Agent."""`

### 8. Calendar Availability Checking
**Valid methods for date filtering:**
- `get_calendar_events_from_to(start_datetime, end_datetime)` - time range query
- `list_events()` - all events

**Invalid for date filtering:**
- `search_events()` - only searches title, description, location, attendees (NOT dates)

### 9. Reminder vs Calendar
- Use **ReminderApp** for deadline tracking (due dates, follow-ups)
- Use **CalendarApp** for scheduled events with duration (meetings, appointments)

### 10. Incorrect Comments
**Check:** Verify claims about tools being "undecorated" or "not available"
- Always verify in `pas/apps/<app_name>/app.py` or via Python introspection
- Remove or correct misleading comments

### 11. Scenario Status Before Moving to Benchmark
**Required:**
```python
status = ScenarioStatus.Valid
is_benchmark_ready = True
```

### 12. Additional System Prompt for User Agent
Some scenarios have ambiguity where the user agent needs context to make appropriate accept/reject decisions. Use the `additional_system_prompt` class attribute to provide this context.

**When to use:**
- When there are multiple environment events that must all arrive before the agent should act (e.g., waiting for multiple people to respond)
- When timing matters (e.g., wait for all information before deciding)
- When the user's acceptance criteria isn't obvious from the scenario setup
- When there are multiple valid options and user should review them before accepting
- When budget, timing, or preference constraints affect acceptance decisions

**What to include:**
- Brief context about the user's situation
- Clear conditions for when to accept vs reject proposals
- Any constraints the user cares about (budget, timing, preferences)
- Instructions to wait for specific information if needed

If you are unsure whether to add an additional system prompt, use AskUserQuestion to clarify the additional prompt with the user.
**Example:**
```python
additional_system_prompt = """You are coordinating a group gift with Alice and Bob.
Wait for both contribution messages before accepting any proposal.
Only accept if the agent shows you gift options within the pooled budget."""
```

**Example (waiting for multiple events):**
```python
additional_system_prompt = """You are coordinating a study group with three classmates.
Wait for all three to respond with their availability before accepting any scheduling proposal.
Only accept if the proposed time works for everyone based on their stated availability."""
```

### 13. Validation Should Not Be Overly Strict
Validation should check that the agent achieved the **essential outcomes**, not that it followed a specific sequence of steps.

**Principle:** The agent might find different paths to the same goal. Validation should allow for this flexibility while ensuring critical actions were taken.

**What to check (essential outcomes):**
- Actions that directly fulfill the user's request (e.g., `checkout` for a purchase scenario)
- Actions that complete the scenario's core purpose (e.g., `send_message` to notify participants)
- User-facing actions that the scenario promises (e.g., proposal sent before taking action)

**What NOT to check (intermediate steps):**
- **Information gathering steps** like `search_product`, `list_all_products`, `get_due_reminders` - the agent might use different methods to find the same information
- **Cleanup steps** like `delete_reminder` - nice to have but not essential to success
- **Alternative paths** - if the agent can accomplish the goal via `list_all_products` instead of `search_product`, both should be valid

**Example reasoning:**
In a gift purchase scenario, the essential outcomes are: (1) purchase was completed, (2) contributors were notified. Whether the agent searched products, listed products, or already knew the product ID doesn't matter - only the outcome matters.

### 14. Attachment Handling for Apps with Internal Filesystem

For scenarios using apps that support `internal_fs` (e.g., `StatefulNotesApp`, `StatefulEmailApp`) and need to work with file attachments, there's a specific pattern to avoid bytes serialization errors.

**Why this matters:** The scenario's `_initial_apps` state is serialized (to JSON) AFTER `init_and_populate_apps()` but BEFORE `build_events_flow()`. If attachments (which contain bytes) are added during `init_and_populate_apps()`, the serialization will fail with `TypeError: Object of type bytes is not JSON serializable`.

**Wrong:** Adding attachments in `init_and_populate_apps()`
```python
def init_and_populate_apps(self):
    self.note = StatefulNotesApp(name="Notes")
    note_id = self.note.create_note(folder="Work", title="Report", content="...")
    # WRONG! This will cause bytes serialization error
    self.note.add_attachment_to_note(note_id=note_id, attachment_path="/file.pdf")
```

**Correct:** Initialize filesystem, write files in init, add attachments in `build_events_flow()` BEFORE `capture_mode()`
```python
def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
    self.agent_ui = PASAgentUserInterface()
    self.system_app = HomeScreenSystemApp(name="System")

    # 1. Initialize SandboxLocalFileSystem as an app
    self.files = SandboxLocalFileSystem(name="Files")

    # 2. Initialize apps that need filesystem access
    self.note = StatefulNotesApp(name="Notes")
    self.email = StatefulEmailApp(name="Emails")

    # 3. Set internal_fs on apps during init
    self.note.internal_fs = self.files
    self.email.internal_fs = self.files

    # 4. Write files to filesystem during init
    with self.files.open("/document.pdf", "wb") as f:
        f.write(b"[Simulated PDF content...]")

    # 5. Create note WITHOUT attachments - store ID for later
    self.note_id = self.note.create_note(folder="Work", title="Report", content="...")

    # 6. Register all apps INCLUDING the filesystem
    self.apps = [self.agent_ui, self.system_app, self.files, self.note, self.email]

def build_events_flow(self) -> None:
    note_app = self.get_typed_app(StatefulNotesApp, "Notes")

    # 7. Add attachments BEFORE capture_mode (after _initial_apps serialization)
    note_app.add_attachment_to_note(note_id=self.note_id, attachment_path="/document.pdf")

    with EventRegisterer.capture_mode():
        # ... define events here ...
```

**Key points:**
- Use `SandboxLocalFileSystem`, not `VirtualFileSystem`
- Include the filesystem in `self.apps` list
- Set `internal_fs` manually on apps during init (before protocol connection)
- Write file content to filesystem during init
- Add attachments in `build_events_flow()` BEFORE `EventRegisterer.capture_mode()`
- Never directly manipulate `note.attachments` or `email.attachments` - use the app methods

## Review Workflow

1. Run oracle mode
2. Independent review using these guidelines
3. Read previous review from `scenario_review_results.md`
4. Present unified findings to user (combining independent review + previous review findings)
5. Discussion with user
6. Once changes confirmed, make edits
7. Mark `status = ScenarioStatus.Valid` and `is_benchmark_ready = True`
8. Run oracle mode to verify
9. Move to benchmark folder (snake_case name)

## Oracle Mode Command

Run oracle mode for a scenario in the reviews folder:
```bash
PAS_SCENARIOS_DIR=reviews/deepak uv run python scripts/run_scenarios.py --scenarios <scenario_id> --oracle
```

Run oracle mode for a scenario in the benchmark folder:
```bash
PAS_SCENARIOS_DIR=benchmark uv run python scripts/run_scenarios.py --scenarios <scenario_id> --oracle
```

**Note:** The `<scenario_id>` is the snake_case name from the `@register_scenario()` decorator, not the class name.
