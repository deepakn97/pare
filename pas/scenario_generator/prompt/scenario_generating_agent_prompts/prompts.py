from __future__ import annotations

import textwrap
from importlib import import_module
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent
SCENARIO_GENERATOR_DIR = PROMPTS_DIR.parent
PAS_DIR = SCENARIO_GENERATOR_DIR.parent


def _discover_meta_are_apps_dir() -> Path | None:
    """Best-effort discovery of the Meta-ARE apps directory for prompt context.

    This is used only to surface a filesystem hint to the Claude Agent in
    system prompts; it does not affect imports or runtime behavior.
    """
    try:
        are_module = import_module("are")
    except ModuleNotFoundError:
        return None
    base = Path(getattr(are_module, "__file__", "")).resolve().parent
    candidate = base / "simulation" / "apps"
    return candidate if candidate.exists() else None


PAS_APPS_DIR = PAS_DIR / "apps"
META_ARE_APPS_DIR = _discover_meta_are_apps_dir()
META_ARE_APPS_DIR_DISPLAY = str(META_ARE_APPS_DIR) if META_ARE_APPS_DIR is not None else "(not found on disk)"
SCENARIOS_DIR = PAS_DIR / "scenarios" / "user_scenarios"
SCENARIOS_DIR_DISPLAY = str(SCENARIOS_DIR)

PROJECT_CONTEXT_SUMMARY = textwrap.dedent(
    f"""\
    - Proactive Agent Sandbox (PAS) extends Meta-ARE with stateful, navigation-aware app wrappers so LLM planners can reason about realistic mobile workflows.
    - Scenarios seed deterministic baseline data inside PAS apps, then drive environment + oracle events so the proactive agent can infer goals and act.
    - The multi-step generator edits a single scenario file cloned from the PAS seed template; each step agent only touches its dedicated TODO block and preserves WARNING comments.
    - Use provided helpers (`get_typed_app`, `EventRegisterer`, `ScenarioValidationResult`) and keep PAS plus Meta-ARE APIs aligned with the state they expose.
    - PAS app implementations are available under: {PAS_APPS_DIR}
    - Meta-ARE app implementations are available under: {META_ARE_APPS_DIR_DISPLAY}
    - Existing PAS user scenarios live under: {SCENARIOS_DIR_DISPLAY}
    - Only design scenarios that use apps actually present in the PAS apps directory, even if Meta-ARE exposes additional base apps.
    """
).strip()

_ = PROJECT_CONTEXT_SUMMARY  # keep mypy happy about usage

PROJECT_CONTEXT_SUMMARY = (
    textwrap.dedent(
        """\
    - Proactive Agent Sandbox (PAS) extends Meta-ARE with stateful, navigation-aware app wrappers so LLM planners can reason about realistic mobile workflows.
    - Scenarios seed deterministic baseline data inside PAS apps, then drive environment + oracle events so the proactive agent can infer goals and act.
    - The multi-step generator edits a single scenario file cloned from the PAS seed template; each step agent only touches its dedicated TODO block and preserves WARNING comments.
    - Use provided helpers (`get_typed_app`, `EventRegisterer`, `ScenarioValidationResult`) and keep PAS plus Meta-ARE APIs aligned with the state they expose.
    - PAS app implementations are available under: {pas_apps_dir}
    - Meta-ARE app implementations are available under: {meta_are_apps_dir}
    - Existing PAS user scenarios live under: {scenarios_dir}
    - Only design scenarios that use apps actually present in the PAS apps directory, even if Meta-ARE exposes additional base apps.
    """
    )
    .format(
        pas_apps_dir=str(PAS_APPS_DIR),
        meta_are_apps_dir=META_ARE_APPS_DIR_DISPLAY,
        scenarios_dir=SCENARIOS_DIR_DISPLAY,
    )
    .strip()
)

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

    ## Reference Scenarios (use the Read tool)
    Before writing or editing scenario code, use the Read tool to open 1-2 representative scenarios under:
    {SCENARIOS_DIR_DISPLAY}
    Use them only as stylistic references; do not copy their scenario narrative or event flow verbatim.

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

APP_IMPORT_INSTRUCTIONS = {
    "HomeScreenSystemApp": {
        "import instruction": "from pas.apps import HomeScreenSystemApp",
    },
    "PASAgentUserInterface": {
        "import instruction": "from pas.apps import PASAgentUserInterface",
    },
    "StatefulEmailApp": {
        "import instruction": "from pas.apps import StatefulEmailApp",
    },
    "StatefulCalendarApp": {
        "import instruction": "from pas.apps import StatefulCalendarApp",
    },
    "StatefulContactsApp": {
        "import instruction": {
            "from pas.apps import StatefulContactsApp",
            "from are.simulation.apps.contacts import Contact",
        },
    },
    "StatefulMessagingApp": {
        "import instruction": "from pas.apps import StatefulMessagingApp",
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
    Produce:
    - A concise, machine-friendly **scenario id** suitable for a Python decorator.
    - A short, descriptive **Python class name**.
    - A concise, ecologically grounded **narrative description** that:
      - Focuses on ONE clear, primary coordination/assistive challenge for the proactive agent (do not try to cover multiple unrelated subplots).
      - Explains the user's context, pain point, and why the proactive assistant should intervene.
      - Describes what information arrives through PAS apps and when, at a similar level of detail and brevity as the existing user scenarios under `pas/scenarios/user_scenarios/`.
      - Outlines the agent's proactive inference, proposed assistance, and expected user response without unnecessary digressions.
      - Follows the docstring structure of the existing PAS scenarios (e.g. `calendar_conflict_urgent_reschedule.py`, `contact_update_from_new_number.py`):
        * First line: one-sentence summary of what the agent does (e.g. "Agent updates contact information from messages received from unknown number.").
        * Middle: 1-2 short paragraphs describing the concrete situation and numbered steps the agent must perform.
        * Final lines: a brief paragraph starting with "This scenario exercises ..." that lists the main capabilities being tested.

    Constraints:
    - Treat every historical scenario description from `scenario_metadata.json` as a negative example.
    - Your new scenario MUST be clearly and substantively different in trigger, domain, app combination, and cross-app workflow from all prior descriptions.
    - Avoid reusing the same situation with only minor wording or timestamp changes; design a genuinely new situation.
    - Only involve apps and tools that appear in the Selected Apps list and the Event-Registered App APIs block below.
    - Do NOT introduce new app types or tools that are not present in those context sections.
    - Scenario id requirements:
      - Lowercase letters, digits, and underscores only (e.g., `vip_calendar_conflict`).
      - No spaces, no punctuation besides underscore, and at most 40 characters.
    - Class name requirements:
      - Valid Python identifier in PascalCase (e.g., `VipCalendarConflict`).
      - Starts with a letter; contains only letters and digits; no underscores or spaces.
    - Complexity and style:
      - Aim for the same level of complexity and conciseness as the hand-written PAS user scenarios in `pas/scenarios/user_scenarios/` (for example, `calendar_conflict_urgent_reschedule.py`).
      - Avoid redundant background details that do not affect the agent's reasoning or the event flow.
      - Keep the description tightly centered on the single main coordination problem and how PAS apps + the agent resolve it.

    Format your final answer EXACTLY as:

    Scenario ID: <short_machine_friendly_id>
    Class Name: <ShortDescriptiveClassName>
    Description:
    <2-3 short paragraphs (or ~6-10 sentences) that describe the scenario narrative, focused on one main task>

    Do not add any other sections, headings, bullet points, or commentary outside this format.
    """
)

_SCENARIO_UNIQUENESS_BODY = textwrap.dedent(
    f"""\
    You review new scenario descriptions to ensure they are unique compared to existing PAS scenarios.
    Consider triggers, cross-app interactions, constraints, and tool usage patterns.

    Before deciding, you may use the Read tool to:
    - List and inspect existing PAS user scenarios under: {SCENARIOS_DIR_DISPLAY}
    - Skim example scenarios to understand their trigger patterns, complexity, and tool usage.

    What makes a scenario unique:
    - Novel trigger patterns and cross-app combinations, not just another generic "incoming email" case.
    - Different complexity/constraints (e.g., coordinating multiple people, resolving conflicts, multi-step reasoning).
    - Exercising different app capabilities and tools than prior scenarios.

    What is NOT sufficient for uniqueness:
    - Merely swapping names or dates in an otherwise identical flow.
    - Using the same apps with only superficial changes to the task.

    Output format (STRICT verdict + optional brief analysis):
    - Your FIRST non-empty line MUST be exactly one of:
      - PASS
      - RETRY: <detailed reason> if it overlaps with prior scenarios.

    - After the first line, you MAY include up to TWO short sections if first line is RETRY (optional):
      Comparison to existing scenarios:
      - <1-3 bullets referencing similar existing patterns>

      Key overlap:
      - <1-2 bullets explaining the core overlap (or why it is novel)>

    - Do NOT include any other sections beyond the optional ones above.
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
      This means:
        - In the import section, you may replace the "TODO: import all Apps" area with concrete imports.
        - In `init_and_populate_apps()`, you may initialize apps, populate their data, and register them in `self.apps`.
        - You MUST NOT change any other function, class, decorator, or comment outside those two regions.
        - You MUST preserve the `@register_scenario(...)` decorator, class name, docstring, `start_time`, status fields,
          `build_events_flow()`, `validate()`, and all WARNING comments exactly as they appear.
    - Reference the "Import Instructions" block for permissible imports.
    - Mirror the "App Initialization Blueprint" so attribute names and `get_typed_app()` lookups stay aligned with later steps.
    - Use the PAS app classes under `pas/apps/` and their Meta-ARE bases under `are/simulation/apps/` as the source of truth for which methods exist; do not invent new APIs.
    - CRITICAL: Before constructing any object or calling any method from these apps (for example `Contact` from `are.simulation.apps.contacts`),
      use the `Read` tool to open the defining Python file and inspect the initializer signature and type hints.
      Do NOT guess field names or argument order; copy them exactly from the class definition.
    - When you need to check available methods or attributes on an app, use the Read tool to open the corresponding Python files in the PAS apps directory
      and the Meta-ARE apps directory mentioned in the project context. Prefer reading the source over inferring from memory and avoid mistakes like
      unexpected keyword arguments or missing required parameters.

    Inheritance-aware API lookup (applies to ALL PAS apps):
    - PAS apps are thin stateful wrappers around Meta-ARE base apps. For example:
      - `StatefulEmailApp` is defined in `pas/apps/email/app.py` and inherits from `EmailClientV2` in `are/simulation/apps/email_client.py`.
    - When you need to know what methods/fields exist on a PAS app, you MUST:
      1. Use Read to open the PAS wrapper file under `pas/apps/.../app.py` (e.g., `StatefulEmailApp`).
      2. Look at the base classes in the class definition (e.g., `EmailClientV2`) and then use Read again to open the Meta-ARE base module
         (e.g., `are/simulation/apps/email_client.py`) and inspect that class definition.
    - Do NOT assume that a method exists on a PAS app because you have seen similar names elsewhere. Only call methods that you have verified
      either on the PAS wrapper class itself or on one of its explicit base classes in the Meta-ARE codebase.

    API verification guardrails (MANDATORY):
    - You MUST NOT invent helper methods. If you cannot find a method in source, do not call it.
    - Before creating contacts, Read the `Contact` dataclass definition and use ONLY its declared fields.
      Common mistake to avoid: do NOT pass fields like `organization=` unless you confirm it exists in the `Contact` dataclass.
      (Look for `@dataclass class Contact:` in `are/simulation/apps/contacts.py` in your environment.)
    - Before seeding messaging history, Read the PAS messaging wrapper and Meta-ARE base:
      - `pas/apps/messaging/app.py` (Stateful wrapper)
      - `are/simulation/apps/messaging_v2.py` (ConversationV2 / MessageV2 / send_message APIs)
      Only use messaging methods that actually exist there. Common mistakes to avoid:
      - Do NOT call `add_message_from_contact_to_user` (does not exist).
      - Do NOT call `open_conversation` unless you confirm it is a real method/tool on the app class.
      Prefer seeding baseline history by constructing `ConversationV2` / `MessageV2` and calling `add_conversation(...)` when available.

    If the runtime checker reports errors like:
    - "missing a required argument: '<arg>'"
    - "'<App>' object has no attribute '<method>'"
    then your code is using the wrong API. Stop and:
    - Read the defining source file for that app/object under `pas/apps/` and/or `are/simulation/apps/`.
    - Copy the exact signature/fields.
    - Remove any invented helpers and rework the baseline seeding using only existing APIs.
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
    - For non-oracle environment events, only use methods that have notification templates in `pas/apps/notification_templates.py` (see the NOTIFICATION_TEMPLATES dict).
    - For oracle/user actions, use app tools defined on the PAS apps and their Meta-ARE bases; do not invent new methods.
    - Mirror the "App Initialization Blueprint" so your local variables match how apps were seeded in Step 2.

    Explicit oracle events for agent behavior (IMPORTANT):
    - For every major agent behavior that you expect Step 4 to validate (for example: sending a proposal to the user, searching the calendar, updating a contact, sending a reply email, adding a reminder), you MUST create a concrete oracle event in `build_events_flow()`.
      - Follow the patterns used in the hand-written scenarios under `pas/scenarios/user_scenarios/`, such as:
        - `calendar_conflict_urgent_reschedule.py` (explicit `get_calendar_events_from_to`, `edit_calendar_event`, `add_calendar_event`, `reply_to_email` calls, each with `.oracle().depends_on(...)`).
        - `contact_update_from_new_number.py` (explicit `search_contacts`, `edit_contact`, `send_message` calls with `.oracle().depends_on(...)`).
    - Do NOT rely on "implicit" agent behavior that you only describe in comments. If a behavior matters for validation, represent it as an actual oracle event by calling the appropriate PAS app tools, chaining them with `.oracle()` / `.depends_on(...)`, and registering them in `self.events`.

    Mandatory API verification (applies to ALL apps, now and in the future):
    - You MUST NOT invent or assume methods, fields, or helper APIs.
    - Before calling ANY app method or constructing ANY app-defined object (PAS or Meta-ARE), you MUST use the Read tool to open the
      defining Python source file for that class/method and copy the exact signature + required arguments.
      - PAS app wrappers live under `pas/apps/` (e.g., `pas/apps/<app_name>/app.py` or similar).
      - Meta-ARE base apps live under `are/simulation/apps/`.
    - Inheritance rule for PAS apps:
      - PAS apps like `StatefulEmailApp`, `StatefulMessagingApp`, etc. are usually declared as subclasses of Meta-ARE bases.
      - You MUST inspect BOTH:
        1. The PAS wrapper file under `pas/apps/.../app.py` to see the wrapper class definition.
        2. The Meta-ARE base class file referenced in the wrapper's `class ...(..., BaseClass)` line (for example `EmailClientV2`
           in `are/simulation/apps/email_client.py` for `StatefulEmailApp`).
      - Only treat methods as available on the PAS app if they are defined either directly on the wrapper class or on one of its explicit
        base classes you have opened with Read.
    - Navigation state tools:
      - Some PAS apps (like email) also expose `user_tool()` methods on navigation state classes under `pas/apps/<app_name>/states.py`
        (for example, `MailboxView.list_emails`, `EmailDetail.reply`, `ComposeEmail.send_composed_email`).
      - These state classes describe user-level tools and flows, and their tools MAY appear as oracle/user events in your scenario
        (for example, composing and sending an email via the compose flow).
      - When you reference these tools in `build_events_flow()`, you must:
        - Match their exact names and signatures from `states.py` and/or from the Event-Registered App APIs block.
        - Not invent similarly named helpers that don't exist anywhere in source.
    - If you cannot find a method in source (wrapper or base), do not call it. Replace it with an existing method, or redesign the event flow.

    Common failure patterns to avoid (with fixes):
    - "'Event' object is not subscriptable":
      - You are treating an `Event` / `CompletedEvent` instance like a dict or list (e.g., `event[...]`) or passing it where a simple ID or string is expected.
      - Fix: never subscript `Event` objects. Use their attributes (`event_type`, `action`, etc.) when reading logs, and pass only simple values (IDs, strings, timestamps) into app methods as documented in their signatures.
    - "Argument 'start_datetime' must be of type str | None, got <class 'float'>":
      - You are passing a UNIX timestamp float into a tool API that expects a string (for example, `add_calendar_event(title=..., start_datetime=\"YYYY-MM-DD HH:MM:SS\", ...)`).
      - Fix: use Read on the PAS calendar wrapper at `pas/apps/calendar/` (for `StatefulCalendarApp`) and the Meta-ARE calendar base under `are/simulation/apps/` (for example, `calendar_v2.py` / `calendar.py`), confirm the exact parameter types, and pass properly formatted strings instead of raw floats. Keep using timestamp floats only where the dataclass explicitly documents them (such as the `CalendarEvent` dataclass in `are/simulation/apps/calendar.py`).
    - "AbstractEvent.delayed() got an unexpected keyword argument 'seconds'/'hours'":
      - You have invented keyword arguments on the `.delayed()` API that do not exist in the real signature.
      - Fix: use Read on the underlying event types in `are/simulation/types.py` (look for `AbstractEvent` / `CompletedEvent`), copy the exact `.delayed(...)` signature, and only call it with the documented positional/keyword arguments (for example, a single positional delay in seconds). Do NOT add new kwargs like `seconds=` or `hours=` unless they are explicitly defined in source.
    - Common failure patterns to avoid:
      - Missing required argument errors (e.g., forgetting `user_id=`) → always confirm signature.
      - AttributeError / “object has no attribute …” → the method does not exist; remove it and use an existing API.
      - Using UI-like methods that are not part of the tool API (e.g., “open_*”, “start_compose”) unless you confirm they exist in source.

    If the runtime checker reports errors like "missing a required argument" or "has no attribute", treat that as proof of wrong API usage.
    Go back to source (`pas/apps/` + `are/simulation/apps/`), verify signatures, and rewrite using only existing methods.

    CRITICAL: Before calling any email, calendar, contacts, messaging or other app API, use the Read tool to open the PAS app class and its Meta-ARE base
    and copy the exact method signatures and required arguments. Do NOT guess enum members or omit required parameters. If a method takes a
    complex object, construct it using the exact field names from the class definition.

    Oracle content brevity:
    - Keep oracle messages (for example, PASAgentUserInterface.send_message_to_user content or long email bodies) concise and focused on the minimum
      information needed for the agent/user to act. Prefer 1-2 short paragraphs or a compact bullet-style summary instead of essay-length text.
    - Avoid repeating the full narrative; reference only the key facts (times, dates, parties, constraints) that are strictly necessary for this step.
    """
)

_VALIDATION_BODY = textwrap.dedent(
    """\
    You are the Step 4 validation agent.
    Design the checks for `validate()` that prove the proactive agent detected the right signals and executed the promised help.
    - Reference key events and arguments that prove success.
    - Distinguish strict vs flexible checks:
      - STRICT: core reasoning and coordination must be present (e.g., the agent proposal referencing the right parties, key follow-up actions like messages/emails, calendar reminders actually created).
      - FLEXIBLE: wording details (exact subject/body strings), cosmetic fields, or small variations in time ranges and titles should not cause failure if the logical behavior is equivalent.
      - Follow the "Validation Flexibility Guidelines" from the multi-step design doc: be strict on logic and data relationships, flexible on surface phrasing and minor formatting.
    - Mention the relevant EventType and tool/function each check expects in the log.
      - Before using EventType, use Read to open `are/simulation/types.py` and inspect which enum members exist; do NOT invent members like `ORACLE` if they are not defined.
      - In oracle-mode runs (like those used by this pipeline), many tool invocations are recorded as `EventType.ENV` in `env.event_log.list_view()`. Inspect a few log entries first and match on the actual `event_type` values you see (for example, allow both `ENV` and `AGENT` where appropriate) instead of assuming one fixed enum.
      - Treat entries from `env.event_log.list_view()` as event objects (for example, `CompletedEvent` instances) with attributes such as `event_type` and `action`; do NOT subscript them like dictionaries or lists.
    - ONLY modify the `validate()` function, keeping other sections intact and preserving WARNING comments.
    - When building the final `ScenarioValidationResult`, set:
      - `success=True` only if all strict checks pass.
      - `success=False` otherwise, and include a short `rationale` string that summarizes which critical checks were missing (for example, "no payment reminder email to TechStart found in log" or "calendar reminder event not created").
      This rationale will be surfaced back to you in future iterations to help you refine the validation logic.
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
        include_all_tools=False,
        include_app_init=True,
    )
    EVENTS_FLOW_SYSTEM_PROMPT = _with_context(
        _EVENTS_FLOW_BODY,
        include_env_methods=False,
        include_oracle_methods=False,
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
    Draft a brand-new PAS scenario narrative that is clearly and substantively distinct from ALL prior scenarios.
    Use prior scenarios as negative examples: do NOT reuse the same trigger, goal, cross-app pattern, or domain with only superficial changes.

    Historical scenario metadata path (read this file via the Read tool):
    {scenario_metadata_path}

    Stylistic reference (docstring pattern ONLY, not scenario content):
    - Use the Read tool to open the following existing user scenarios and observe how their docstrings are structured:
      - `pas/scenarios/user_scenarios/contact_update_from_new_number.py`
      - `pas/scenarios/user_scenarios/calendar_conflict_urgent_reschedule.py`
    - Follow their docstring pattern (high-level summary line, concrete context + numbered steps, final "This scenario exercises ..." paragraph),
      but you MUST design a completely new scenario with different triggers, goals, and app usage.

    Then choose:
    - A short, machine-friendly scenario id (lowercase_with_underscores, <= 40 chars).
    - A concise Python class name in PascalCase that matches the scenario.

    Follow this exact output format:

    Scenario ID: <short_machine_friendly_id>
    Class Name: <ShortDescriptiveClassName>
    Description:
    <2-3 short paragraphs that describe the trigger, cross-app signals, agent inference, and expected user response>

    Do not include any other text before or after these sections.
    """
)

SCENARIO_UNIQUENESS_SYSTEM_PROMPT = _with_context(_SCENARIO_UNIQUENESS_BODY)

SCENARIO_UNIQUENESS_USER_PROMPT = textwrap.dedent(
    """\
    Candidate scenario description:
    ---
    {scenario_description}
    ---

    Historical scenario metadata path (read this file via the Read tool):
    {scenario_metadata_path}
    """
)

APPS_AND_DATA_SYSTEM_PROMPT = _with_context(
    _APPS_AND_DATA_BODY,
    include_imports=True,
    include_tools=False,
    include_all_tools=False,
    include_app_init=True,
)

APPS_AND_DATA_USER_PROMPT = textwrap.dedent(
    """\
    Narrative:
    ---
    {scenario_description}
    ---

    Target scenario file path (read + write this exact file via tools):
    {scenario_file_path}

    Use the Read tool to open the file above. Incorporate the scenario description into the template by
    editing ONLY `init_and_populate_apps()` and the imports TODO region.

    IMPORTANT: You must verify APIs from source before writing code.
    - Use Read to inspect `are/simulation/apps/contacts.py` before creating any `Contact(...)`.
    - Use Read to inspect `pas/apps/messaging/app.py` and `are/simulation/apps/messaging_v2.py` before seeding any messaging state.
    - If you cannot confirm a field/method in source, do not use it.

    Apply STRICT edit boundaries:
    - You may only change:
      - The imports section around the "TODO: import all Apps that will be used in this scenario" comment.
      - The body of `init_and_populate_apps()` between its WARNING comment and the end of that method.
    - You must NOT change ANY code, comments, or whitespace outside those regions.
      - Do not alter the module docstring, `from __future__ import ...` line, or any other imports.
      - Do not change the `@register_scenario(...)` decorator, class name, docstring, `start_time`, status fields,
        `build_events_flow()`, `validate()`, or their WARNING comments.
      - Do not reorder, add, or delete lines outside the allowed regions.

    Update docstrings/comments inside the allowed regions as needed, but preserve all WARNING comments verbatim.

    Use the available agent tools to apply your edits:
    - Use the Read tool to inspect the existing scenario file and any PAS / Meta-ARE app definitions you need.
    - Use the Write tool to update ONLY the imports section and the body of `init_and_populate_apps()` in the file at {scenario_file_path}.
    - Do NOT paste the full updated file contents back into the chat; rely on the Write tool to persist changes.

    For your assistant message, return a brief summary of the edits you applied (1-3 sentences) without including any code.
    """
)

EVENTS_FLOW_SYSTEM_PROMPT = _with_context(
    _EVENTS_FLOW_BODY,
    include_env_methods=False,
    include_oracle_methods=False,
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

    Target scenario file path (read + write this exact file via tools):
    {scenario_file_path}

    IMPORTANT: verify APIs from source before writing code.
    - Use Read to inspect the PAS app wrappers under `pas/apps/` for every app you will call in `build_events_flow()`.
    - Use Read to inspect the corresponding Meta-ARE base apps under `are/simulation/apps/` for method signatures and dataclasses.
    - Do not call any method unless you have confirmed it exists and copied its signature from source.
    - If the runtime check reports a missing argument or missing attribute, treat it as proof your API usage is incorrect: go back to source,
      find the right method/signature, and update only `build_events_flow()` accordingly.

    Use the available agent tools to apply your edits:
    - Use the Read tool to inspect the existing scenario file at {scenario_file_path} and any PAS / Meta-ARE app definitions you need.
    - Use the Write tool to update ONLY the `build_events_flow()` implementation in the file at {scenario_file_path}, preserving all WARNING comments and structure.
    - Do NOT paste the full updated file contents back into the chat; rely on the Write tool to persist changes.

    For your assistant message, return a brief summary of the event flow you implemented (1-3 sentences) without including any code.
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

Target scenario file path (read + write this exact file via tools):
{scenario_file_path}

Use the available agent tools to apply your edits:
- Use the Read tool to inspect the existing scenario file at {scenario_file_path} and any PAS / Meta-ARE app definitions you need.
- Use the Write tool to update ONLY the `validate()` implementation in the file at {scenario_file_path}, preserving all WARNING comments and structure.
- Do NOT paste the full updated file contents back into the chat; rely on the Write tool to persist changes.

For your assistant message, return a brief summary of the key validation checks you implemented (1-3 sentences) without including any code.
    """
)
