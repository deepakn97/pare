from __future__ import annotations

import textwrap
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent
SCENARIO_GENERATOR_DIR = PROMPTS_DIR.parent
PAS_DIR = SCENARIO_GENERATOR_DIR.parent


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


EXAMPLE_SCENARIO_PATH = PAS_DIR / "example_proactive_scenarios" / "email_notification.py"
# EXAMPLE_SCENARIO_SOURCE = _safe_read_text(EXAMPLE_SCENARIO_PATH).strip()
# if not EXAMPLE_SCENARIO_SOURCE:
EXAMPLE_SCENARIO_SOURCE = "# Example PAS scenario file is missing."

PROJECT_CONTEXT_SUMMARY = textwrap.dedent(
    """\
    - Proactive Agent Sandbox (PAS) extends Meta-ARE with stateful, navigation-aware app wrappers so LLM planners can reason about realistic mobile workflows.
    - Scenarios seed deterministic baseline data inside PAS apps, then drive environment + oracle events so the proactive agent can infer goals and act.
    - The multi-step generator edits a single scenario file cloned from the PAS seed template; each step agent only touches its dedicated TODO block and preserves WARNING comments.
    - Use provided helpers (`get_typed_app`, `EventRegisterer`, `ScenarioValidationResult`) and keep PAS plus Meta-ARE APIs aligned with the state they expose.
    """
).strip()

GLOBAL_CONTEXT_PROMPT = textwrap.dedent(
    f"""\
    # Generate Proactive Scenario: $ARGUMENTS

    You operate as the coordinated prompt stack that powers PAS's multi-step scenario authoring pipeline. Keep outputs concise, deterministic, and aligned with the available PAS tooling.

    ## Project Overview
    {PROJECT_CONTEXT_SUMMARY}

    ## Workflow Contract
    1. **Step 0 - Uniqueness**: compare against historical descriptions before proposing anything new.
    2. **Step 1 - Narrative**: produce 2-3 paragraphs summarizing the trigger, agent inference, and expected acceptance.
    3. **Step 2 - Apps & Data**: seed `init_and_populate_apps()` without touching other sections; only pre-existing state belongs here.
    4. **Step 3 - Events Flow**: fully implement `build_events_flow()` with environment + oracle events, using `EventRegisterer.capture_mode()`.
    5. **Step 4 - Validation**: finish `validate()` with log checks that prove the agent offered help and completed the task.

    ## Temporal & Data Alignment
    - Always set `start_time` to a realistic UTC timestamp that matches emails, messages, and calendar entries.
    - Keep all timestamps coherent (e.g., "tomorrow" in the narrative means +1 day from `start_time`).
    - Baseline data must exist before events replay; runtime arrivals belong to `build_events_flow()`.

    ## Event Authoring Guardrails
    - Non-oracle environment events MUST map to functions declared in `pas/apps/notification_templates.py` for both user and agent streams.
    - Register every event you create; missing entries in `self.events` will never execute.
    - Use `send_email_to_user_with_id()` when later oracle actions need the same `email_id`.
    - Chain events with `.delayed()` or `.depends_on()` to model realistic timing and user acceptances.

    ## Example PAS Scenario
    ```python
    {EXAMPLE_SCENARIO_SOURCE}
    ```

    ## Dynamic Context Blocks
    Each prompt below automatically appends the Selected Apps list, import instructions, tool descriptions, app-initialization blueprint, and the allowed environment/oracle APIs derived from the current CLI arguments. Rely on those sections instead of trying to inspect the repository at runtime.
    """
)

APP_INITIALIZATION_SNIPPETS = {
    "HomeScreenSystemApp": {
        "init": 'self.system_app = HomeScreenSystemApp(name="System")',
        "flow": 'system_app = self.get_typed_app(HomeScreenSystemApp, "System")',
        "intent": "Navigation shell and notification surface that lets the agent notice environment cues.",
    },
    "PASAgentUserInterface": {
        "init": "self.agent_ui = PASAgentUserInterface()",
        "flow": "aui = self.get_typed_app(PASAgentUserInterface)",
        "intent": "Channel for proposals, acceptances, and summaries shared with the simulated user.",
    },
    "StatefulEmailApp": {
        "init": 'self.email = StatefulEmailApp(name="Emails")',
        "flow": 'email_app = self.get_typed_app(StatefulEmailApp, "Emails")',
        "intent": "Stateful email client for reading threads, replying, and drafting proactive responses.",
    },
    "StatefulCalendarApp": {
        "init": 'self.calendar = StatefulCalendarApp(name="Calendar")',
        "flow": 'calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")',
        "intent": "Holds meetings and availability windows the agent must query or update.",
    },
    "StatefulContactsApp": {
        "init": 'self.contacts = StatefulContactsApp(name="Contacts")',
        "flow": 'contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")',
        "intent": "Provides structured contact info that other apps reference (emails, phones, org roles).",
    },
    "StatefulMessagingApp": {
        "init": 'self.messaging = StatefulMessagingApp(name="Messages")',
        "flow": 'messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")',
        "intent": "Two-way text threads where the agent can notice unread items or send follow ups.",
    },
}


def build_app_initialization_block(app_names: list[str]) -> str:
    """Return a formatted cheat-sheet describing how each selected app is initialized."""
    ordered: list[str] = []
    for name in app_names:
        if name not in ordered:
            ordered.append(name)
    entries: list[str] = []
    for name in ordered:
        spec = APP_INITIALIZATION_SNIPPETS.get(name)
        if spec is None:
            continue
        entry = textwrap.dedent(
            f"""\
            {name}:
              init_and_populate_apps():
                {spec["init"]}
              build_events_flow():
                {spec["flow"]}
              intent: {spec["intent"]}
            """
        ).strip()
        entries.append(entry)
    if not entries:
        return "(none)"
    intro = (
        "Reuse these attribute names (or keep them consistent) so `init_and_populate_apps()` "
        "and `build_events_flow()` stay aligned. Adjust only if your scenario already reserves the suggested attribute."
    )
    return "\n\n".join([intro, *entries])


_SELECTED_BLOCK = ""
_IMPORT_BLOCK = ""
_TOOLS_BLOCK = ""
_NON_ORACLE_BLOCK = ""
_ORACLE_BLOCK = ""
_ALL_TOOLS_BLOCK = ""
_SELECTED_TOOLS_BLOCK = ""
_APP_INIT_BLOCK = ""

# Base bodies for system prompts (used to rebuild prompts when dynamic context changes)
_SCENARIO_DESCRIPTION_BODY = textwrap.dedent(
    """\
    You are the Step 1 description agent for the PAS multi-step generator.
    Produce a concise, ecologically grounded narrative that:
    - Explains the user's context, pain points, and why the proactive assistant should intervene.
    - Describes what information arrives through PAS apps and when.
    - Outlines the agent's proactive inference, proposed assistance, and expected user response.

    Constraints:
    - Treat every historical scenario description from `valid_descriptions.json` as a negative example.
    - Your new scenario MUST be clearly and substantively different in trigger, domain, app combination, and cross-app workflow from all prior descriptions.
    - Avoid reusing the same situation with only minor wording or timestamp changes; design a genuinely new situation.
    - Only involve apps and tools that appear in the Selected Apps list and the Event-Registered App APIs block below.
    - Do NOT introduce new app types or tools that are not present in those context sections.

    Output exactly 2-3 short sentences in plain text. Avoid implementation details.
    """
)

_SCENARIO_UNIQUENESS_BODY = textwrap.dedent(
    """\
    You review new scenario descriptions to ensure they are unique compared to existing PAS scenarios.
    Consider triggers, cross-app interactions, constraints, and tool usage patterns.
    Reply with:
      - "PASS" if the scenario is substantively different.
      - "RETRY: <short reason>" if it overlaps with prior scenarios.
    Keep responses under 50 words.
    """
)

_APPS_AND_DATA_BODY = textwrap.dedent(
    """\
    You are the Step 2 Apps & Data Setup Agent.
    Using the approved narrative, list the baseline data to seed each PAS app inside `init_and_populate_apps()`.
    - Only include pre-existing data (contacts, calendar events, message history, etc.).
    - Structure the output per app with clear subsections.
    - Do NOT invent runtime events; those belong to Step 3.
    - Only modify the import section and `init_and_populate_apps()` body. Keep WARNING comments and other TODO blocks untouched.
    - Reference the "Import Instructions" block for permissible imports.
    - Mirror the "App Initialization Blueprint" so attribute names and `get_typed_app()` lookups stay aligned with later steps.
    - The "Event-Registered App APIs" block lists every method you may call (including those without `@app_tool`); stay within that set when seeding state.
    """
)

_EVENTS_FLOW_BODY = textwrap.dedent(
    """\
    You are the Step 3 events-flow agent.
    Generate the ordered sequence for `build_events_flow()` using the approved narrative and data plan.
    Requirements:
    - Start with non-oracle environment events to set context.
    - Include oracle/user interactions (agent proposal → user response → agent follow-up).
    - Specify event source, method, arguments, delays, and purpose.
    - Reference IDs and data from Step 2 exactly; do not fabricate new ones.
    - ONLY modify the `build_events_flow()` section of the template while keeping WARNING comments and other sections
      unchanged, except for inserting the concrete implementation in the TODO area.
    Output should be the full updated python file with only the build_events_flow section changed.
    - Use only the environment methods listed in the "Allowed Non-Oracle Environment Methods" block below for context events.
    - Use only the functions listed in "Allowed Oracle Methods" for oracle/user actions; do not call other app APIs here.
    - Mirror the "App Initialization Blueprint" so your local variables match how apps were seeded in Step 2.
    """
)

_VALIDATION_BODY = textwrap.dedent(
    """\
    You are the Step 4 validation agent.
    Design the checks for `validate()` that prove the proactive agent detected the right signals and executed the promised help.
    - Reference key events and arguments that prove success.
    - Distinguish strict vs flexible checks.
    - Mention the relevant EventType and tool/function each check expects in the log.
    - ONLY modify the `validate()` function, keeping other sections intact and preserving WARNING comments.
    Output must be the full python file with only the validate TODO replaced by executable code.
    """
)


def configure_dynamic_context(
    *,
    selected_apps: str,
    import_instructions: str,
    tool_descriptions: str,
    allowed_non_oracle_block: str,
    allowed_oracle_block: str,
    allowed_all_tools_block: str,
    app_initialization_block: str,
    selected_tools_description: str,
) -> None:
    """Inject run-time app/tool instructions into the global prompt."""
    global \
        _SELECTED_BLOCK, \
        _IMPORT_BLOCK, \
        _TOOLS_BLOCK, \
        _NON_ORACLE_BLOCK, \
        _ORACLE_BLOCK, \
        _ALL_TOOLS_BLOCK, \
        _SELECTED_TOOLS_BLOCK, \
        _APP_INIT_BLOCK
    global \
        SCENARIO_DESCRIPTION_SYSTEM_PROMPT, \
        SCENARIO_UNIQUENESS_SYSTEM_PROMPT, \
        APPS_AND_DATA_SYSTEM_PROMPT, \
        EVENTS_FLOW_SYSTEM_PROMPT, \
        VALIDATION_SYSTEM_PROMPT

    def _make_block(title: str, content: str) -> str:
        content = content.strip()
        if not content:
            content = "(none)"
        return f"## {title}\n{content}"

    _SELECTED_BLOCK = _make_block("Selected Apps", selected_apps)
    _IMPORT_BLOCK = _make_block("Import Instructions", import_instructions)
    _TOOLS_BLOCK = _make_block("Available Tools", tool_descriptions)
    _NON_ORACLE_BLOCK = _make_block("Allowed Non-Oracle Environment Methods", allowed_non_oracle_block)
    _ORACLE_BLOCK = _make_block("Allowed Oracle Methods", allowed_oracle_block)
    _ALL_TOOLS_BLOCK = _make_block("Event-Registered App APIs", allowed_all_tools_block)
    _SELECTED_TOOLS_BLOCK = _make_block("Event-Registered App APIs", selected_tools_description)
    _APP_INIT_BLOCK = _make_block("App Initialization Blueprint", app_initialization_block)

    # Rebuild system prompts so they include the latest dynamic context blocks.
    SCENARIO_DESCRIPTION_SYSTEM_PROMPT = _with_context(
        _SCENARIO_DESCRIPTION_BODY,
        include_selected_tools=True,
    )
    SCENARIO_UNIQUENESS_SYSTEM_PROMPT = _with_context(_SCENARIO_UNIQUENESS_BODY)
    APPS_AND_DATA_SYSTEM_PROMPT = _with_context(
        _APPS_AND_DATA_BODY,
        include_imports=True,
        include_tools=False,
        include_all_tools=True,
        include_app_init=True,
    )
    EVENTS_FLOW_SYSTEM_PROMPT = _with_context(
        _EVENTS_FLOW_BODY,
        include_env_methods=True,
        include_oracle_methods=True,
        include_app_init=True,
    )
    VALIDATION_SYSTEM_PROMPT = _with_context(
        _VALIDATION_BODY,
        include_selected=False,
    )


def _with_context(
    body: str,
    *,
    include_selected: bool = False,
    include_app_init: bool = False,
    include_imports: bool = False,
    include_tools: bool = False,
    include_all_tools: bool = False,
    include_selected_tools: bool = False,
    include_env_methods: bool = False,
    include_oracle_methods: bool = False,
) -> str:
    sections = [body]
    if include_selected and _SELECTED_BLOCK:
        sections.append(_SELECTED_BLOCK)
    if include_app_init and _APP_INIT_BLOCK:
        sections.append(_APP_INIT_BLOCK)
    if include_imports and _IMPORT_BLOCK:
        sections.append(_IMPORT_BLOCK)
    if include_tools and _TOOLS_BLOCK:
        sections.append(_TOOLS_BLOCK)
    if include_selected_tools and _SELECTED_TOOLS_BLOCK:
        sections.append(_SELECTED_TOOLS_BLOCK)
    elif include_all_tools and _ALL_TOOLS_BLOCK:
        sections.append(_ALL_TOOLS_BLOCK)
    if include_env_methods and _NON_ORACLE_BLOCK:
        sections.append(_NON_ORACLE_BLOCK)
    if include_oracle_methods and _ORACLE_BLOCK:
        sections.append(_ORACLE_BLOCK)
    context = "\n\n".join(sections).strip()
    return f"{GLOBAL_CONTEXT_PROMPT}\n\n{context}"


SCENARIO_DESCRIPTION_SYSTEM_PROMPT = _with_context(
    _SCENARIO_DESCRIPTION_BODY,
    include_selected_tools=True,
    include_app_init=True,
)

SCENARIO_DESCRIPTION_USER_PROMPT = textwrap.dedent(
    """\
    Draft a brand-new PAS scenario narrative that is clearly and substantively distinct from ALL recent descriptions listed below.
    Use the prior descriptions as negative examples: do NOT reuse the same trigger, goal, cross-app pattern, or domain with only superficial changes.

    Recent approved descriptions (from `valid_descriptions.json`):
    ---
    {historical_descriptions}
    ---

    Write 2-3 paragraphs that describe the trigger, cross-app signals, agent inference, and expected user response.
    Keep timestamps realistic and ensure each beat is achievable with the currently selected PAS apps.
    """
)

SCENARIO_UNIQUENESS_SYSTEM_PROMPT = _with_context(_SCENARIO_UNIQUENESS_BODY)

SCENARIO_UNIQUENESS_USER_PROMPT = textwrap.dedent(
    """\
    Candidate scenario description:
    ---
    {scenario_description}
    ---
    Recent approved descriptions (from `valid_descriptions.json`):
    {historical_descriptions}
    """
)

APPS_AND_DATA_SYSTEM_PROMPT = _with_context(
    _APPS_AND_DATA_BODY,
    include_imports=True,
    include_tools=False,
    include_all_tools=True,
    include_app_init=True,
)

APPS_AND_DATA_USER_PROMPT = textwrap.dedent(
    """\
    Narrative:
    ---
    {scenario_description}
    ---

    Current scenario file path: {scenario_file_path}
    Current scenario file contents (initially cloned from seed template):
    ```python
    {scenario_file_contents}
    ```

    Incorporate the scenario description into the template above by returning a COMPLETE python file that
focuses on `init_and_populate_apps()` and the TODO in the import part. Update docstrings/comments as needed, but do NOT change any other function
except to keep their TODO placeholders. Maintain the register_scenario metadata, WARNING comments, and class structure.
    """
)

EVENTS_FLOW_SYSTEM_PROMPT = _with_context(
    _EVENTS_FLOW_BODY,
    include_env_methods=True,
    include_oracle_methods=True,
    include_app_init=True,
)

EVENTS_FLOW_USER_PROMPT = textwrap.dedent(
    """\
    Narrative:
    ---
    {scenario_description}
    ---
    Baseline data plan:
    ---
    {apps_and_data}
    ---

Current scenario file (after Step 2):
```python
{scenario_file_contents}
```

Produce the updated python file with a fully implemented `build_events_flow()` following the TODO guidance.
    """
)

VALIDATION_SYSTEM_PROMPT = _with_context(
    _VALIDATION_BODY,
    include_selected=False,
)

VALIDATION_USER_PROMPT = textwrap.dedent(
    """\
    Narrative:
    ---
    {scenario_description}
    ---
    Event flow outline:
    ---
    {events_flow}
    ---

Current scenario file (after Step 3):
```python
{scenario_file_contents}
```

Return the updated python file with the `validate()` function fully implemented per the warning comments.
    """
)
