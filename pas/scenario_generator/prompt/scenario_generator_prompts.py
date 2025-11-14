from __future__ import annotations

import textwrap

from .system_prompt import SYSTEM_PROMPT_TEMPLATE

# ===== Repair Prompt Templates =====

REPAIR_SYSTEM_PROMPT_BASE = textwrap.dedent(
    """You are fixing issues in a generated scenario file. \
Your goal is to correct the problems while maintaining the scenario's intended logic and behavior.
Return a single COMPLETE fenced python code block that includes the corrected file."""
)

REPAIR_SYSTEM_PROMPT_WITH_INSTRUCTIONS_BASE = textwrap.dedent(
    """You are fixing issues in a generated scenario file. \
Your goal is to correct the problems while maintaining the scenario's intended logic and behavior.
Return a single COMPLETE fenced python code block that includes the corrected file.

Use ONLY the following allowed imports list. If something is missing, prefer equivalents from this list or keep existing working imports.
INSTRUCTIONS TO IMPORT AVAILABLE TOOLS:
{import_instructions}"""
)

# ===== Seed Task Templates =====

SEED_TASK_BASE = textwrap.dedent(
    """Reference scenario(s) (generate a new .py scenario file inspired by these, \
but with DIFFERENT content and themes while using tools from the selected apps; \
if no apps are explicitly selected, use all available apps). \
The difficulty of the generated scenario should be similar to the reference scenarios.

    CRITICAL REQUIREMENT: Initialize all selected apps \
using the standard PAS initialization pattern (see `scenario_with_all_pas_apps` and `very_basic_demo_pas_app`). \
Prefer to use tools from each initialized app when it meaningfully contributes to the workflow; it is acceptable \
if some apps are only initialized and not used.

    PROACTIVE INTERACTION REQUIREMENT (MANDATORY): The scenario MUST include a proactive interaction pattern where:
    1. The agent proposes a specific action to the user (using AgentUserInterface__send_message_to_user)
    2. The user responds with detailed approval (using AgentUserInterface__send_message_to_agent with meaningful, contextual response like "Yes, please share it with Jordan" or "Yes, go ahead and schedule that meeting")
    3. The agent then executes the proposed action based on user approval
    4. This pattern should be central to the scenario's workflow, not just a minor interaction
    5. Each proactive proposal MUST be grounded in prior context: only propose actions that clearly follow from
       earlier environment events or tool outputs (e.g., forwarding a specific image that was actually received in
       a previous message, not an invented one).

NOVELTY AND ANTI-DUPLICATION REQUIREMENTS (critical):
- Choose a DIFFERENT primary objective than any provided example (do not replicate scheduling if example schedules; pick another realistic task).
- Use a RICH mix of the selected apps so that multiple apps play meaningful roles where appropriate.
- Vary the event flow: different number of events (±2 or more), different ordering, different delays, and different combination of event types.
- Use DIFFERENT local identifiers: variable names, temporary IDs, email subjects, message contents, event titles, and registry IDs MUST differ from examples. \
  Do not reuse example identifiers except API-required class/method names.
- Change validation signals: assert success via different cues (e.g., different function args checked, counts, or presence of reminders/updates rather than creation of the same item).
- Avoid long token reuse: aside from API symbols, avoid reusing any 5+ consecutive identifier/keyword token sequences seen in examples.
- Ensure the generated class name and @register_scenario key are unique and not present in the references.
- IMPORTANT: Novelty is primarily about new COMBINATIONS and SEQUENCES of tools across apps (mix of ENV/non-ENV/oracle usage),
  not just different storyline content. Choose different tool flows and cross-app interactions than the examples.
- STRONG DIVERGENCE: Avoid repeating common example themes (e.g., calendar rescheduling conflicts, summarizing or forwarding messages/photos,
  simple “check my calendar” proposals). Prefer new objectives (e.g., fetch a code or order number from messages and notify a teammate;
  auto-create a contact from a message signature and then send a follow-up; tag and filter conversations; block focus time on the calendar
  based on a chat instruction). Prefer different app pairings and ENV methods than examples.

CONTEXT-GROUNDED BEHAVIOR (critical):
- Do NOT invent new concrete facts (emails, messages, users, file paths, IDs, URLs, event contents, etc.) that do not come from:
  (a) explicit initialization in init_and_populate_apps, or
  (b) the return values or state changes of previous tool calls in this scenario.
- Any action you take (forwarding, sharing, scheduling, attaching files, etc.) MUST be grounded in prior
  environment events or tool outputs in this scenario. If the environment never produced an item, you must
  not pretend it exists.

    SIMILARITY DETECTION CONTEXT (for understanding why scenarios might be flagged as duplicates):
    - difflib_ratio: measures structural/sequential similarity (longest matching code sequences) - avoid copying similar code structure
    - jaccard_shingles: measures pattern similarity (overlap of 3-token code patterns) - avoid similar token combinations
    - cosine_tokens: measures vocabulary similarity (similarity of token usage frequency) - vary your identifier and keyword choices
    Different thresholds: difflib/jaccard ≥0.8, cosine ≥0.93. If any score exceeds its threshold, the scenario will be rejected.
    If similarity is close to threshold or flagged, immediately PIVOT: change objective/domain, pick different tools combinations,
    alter the event sequence and delays, rename identifiers and titles, and choose different validation targets (IDs, counts, tags).

Key requirements:
    - Initialize all selected apps using the standard PAS pattern
    - Prefer to use at least one tool from each initialized app when meaningful (optional)
    - Follow the same Scenario class structure and methods
    - In build_events_flow, prefer to use initialized apps where they add value; it is acceptable if some initialized apps are unused
    - IMPORTANT: Before any agent proposal, create one or more non-oracle environment events using only VALID ENV tools
      from the selected apps (per notification templates) to establish context. Do NOT use EventRegisterer.create_env_event
      or any EventRegisterer.* placeholder helpers (e.g., env_event, register_env_event); start directly with a real ENV tool call
      on the app (e.g., messaging.create_and_add_message(...), calendar.add_calendar_event(...)).
    - All events (ENV, AGENT, and USER) that participate in the scenario flow MUST be created inside one or more
      'with EventRegisterer.capture_mode():' blocks, mirroring the pattern used in the example scenario
      `very_basic_demo_pas_app`.
    - Create comprehensive event flows that demonstrate the selected applications
    - Import all required tools at the beginning of the file (per import instructions)
    - Maintain a similar validation approach style but target different signals than the example
    - Ensure every selected/available app plays a meaningful role in the scenario workflow
    - MANDATORY: Include proactive interaction pattern (agent proposes action → user responds → agent acts accordingly if user approves)

Return only a single fenced python code block for the new scenario class."""
)

SEED_TASK_WITH_EXAMPLES_BASE = SEED_TASK_BASE + "\n\n{example_code_blocks}"

# ===== Helper Functions =====


def create_repair_note(issues: list[str], previous_code: str | None = None) -> str:
    """Create the repair note message for fixing general issues.

    Args:
        issues: List of issues to fix
        previous_code: The previous code that had issues

    Returns:
        Formatted repair note message
    """
    # Check if we have runtime errors that need special handling
    has_runtime_errors = any("Runtime Error:" in issue or "Missing Method:" in issue for issue in issues)
    has_import_errors = any("import" in issue.lower() or "Import" in issue for issue in issues)
    has_similarity_issues = any(
        "similarity" in issue.lower()
        or "difflib" in issue.lower()
        or "jaccard" in issue.lower()
        or "cosine" in issue.lower()
        for issue in issues
    )

    if has_runtime_errors:
        prompt = (
            "The previous attempt had RUNTIME ERRORS during scenario execution. Fix the method calls and API usage:\n"
        )
    elif has_import_errors:
        prompt = "The previous attempt had IMPORT issues. Fix the import statements:\n"
    elif has_similarity_issues:
        prompt = "The previous attempt was TOO SIMILAR to existing scenarios. Generate a more novel scenario:\n"
    else:
        prompt = "The previous attempt had issues. Here are the problems to fix:\n"

    # Add specific guidance based on error types
    if has_runtime_errors:
        prompt += "\nIMPORTANT: You are fixing RUNTIME ERRORS, not import issues. Focus on:\n"
        prompt += "- Using correct method names that exist on the imported objects\n"
        prompt += "- Checking the available tools and their methods\n"
        prompt += "- Using alternative methods if the desired one doesn't exist\n"
        prompt += "- Following the correct API patterns from the working examples\n"
    elif has_similarity_issues:
        prompt += "\nIMPORTANT: You are creating a NOVEL scenario, not just fixing syntax. Focus on:\n"
        prompt += "- Changing the primary objective/goal of the scenario\n"
        prompt += "- Using different variable names, email subjects, and event titles\n"
        prompt += "- Varying the sequence and number of events\n"
        prompt += "- Using different combinations of apps and interaction patterns\n"
        prompt += "- Modifying the validation logic to check for different signals\n"
        prompt += "- Creating unique identifiers and registry keys\n"

    prompt += "\n".join(f"- {s}" for s in issues)

    if has_similarity_issues:
        prompt += "\n\nHere is the previous code that was too similar (you NEED to change the scenario behavior to make it novel):\n```python\n"
        prompt += previous_code or ""
        prompt += "\n```\n\nReturn a single fenced python code block containing the FULL corrected file."
    else:
        prompt += "\n\nHere is the previous code to fix (do not change scenario behavior):\n```python\n"
        prompt += previous_code or ""
        prompt += "\n```\n\nReturn a single fenced python code block containing the FULL corrected file."

    if has_runtime_errors:
        prompt += "\n\nREMINDER: Ensure all method calls use valid methods from the imported tools. Check the tool descriptions and examples for correct usage."

    return prompt


# ===== Final Formatted Prompts =====

DEFAULT_SCENARIO_GENERATOR_REPAIR_SYSTEM_PROMPT = REPAIR_SYSTEM_PROMPT_BASE

DEFAULT_SCENARIO_GENERATOR_REPAIR_SYSTEM_PROMPT_WITH_INSTRUCTIONS = REPAIR_SYSTEM_PROMPT_WITH_INSTRUCTIONS_BASE

DEFAULT_SCENARIO_GENERATOR_SEED_TASK = SEED_TASK_BASE


# ===== Seed Scenario Generator Prompts =====

SEED_SCENARIO_GENERATOR_SYSTEM_PROMPT_TEMPLATE = textwrap.dedent(
    """You are an expert assistant specialized in generating scenarios using a predefined set of applications and tools.

    CRITICAL REQUIREMENTS:
    1. Initialize all selected apps using the standard PAS pattern
    2. You can ONLY use tools from the provided app definition scenario - no others are allowed
    3. Prefer to incorporate each initialized app into the workflow when it adds value (optional per app)
    4. It is acceptable if some initialized apps are not used in the event flow

    Your task is to generate a comprehensive scenario that:
    1. Initializes all selected apps with the standard PAS pattern
    2. Prefer to use at least one tool from each initialized app when meaningful (optional)
    3. Creates a realistic workflow that demonstrates the capabilities of the selected app ecosystem
    4. Treats the example scenarios as reference material only - for structure, patterns, and inspiration
    5. Creates novel content while following the same API patterns and coding structure
    6. Ensures the generated scenario can run successfully with the selected applications
    7. MANDATORY: Includes a proactive interaction pattern where the agent proposes an action and asks for user permission"""
)

SEED_SCENARIO_GENERATOR_AGENT_HINTS = textwrap.dedent(
    """
    SEED SCENARIO GENERATION GUIDELINES:

    APP CONSTRAINTS (STRICTLY ENFORCED):
    - ONLY use tools from the app definition scenario provided
    - DO NOT use apps or tools that appear in example scenarios but are not in the app definition scenario
    - Imports are STRICTLY LIMITED to the symbols listed in "INSTRUCTIONS TO IMPORT AVAILABLE TOOLS" for the SELECTED APPS ONLY.
      Do NOT import other PAS apps or modules not listed there.

    COMPREHENSIVE APP USAGE (MANDATORY):
    - Initialize all selected apps (or all available apps if none are explicitly selected) using the standard PAS pattern
    - Prefer to use at least one tool from each initialized app when meaningful (optional)
    - Aim for meaningful roles for apps where appropriate; it's acceptable if some apps remain unused
    - Create realistic workflows that demonstrate the selected applications where they add value

    SCENARIO STRUCTURE REQUIREMENTS:
    - Follow the standard Scenario class structure (init_and_populate_apps, build_events_flow, validate)
    - Use the same app initialization pattern as shown in `scenario_with_all_pas_apps` and `very_basic_demo_pas_app`
    - Always initialize HomeScreenSystemApp(name="HomeScreenSystemApp") in init_and_populate_apps, include it in self.apps,
      and retrieve it in build_events_flow via self.get_typed_app(HomeScreenSystemApp) (demo-style usage). Optionally,
      you may use a simple oracle navigation call like system_app.go_home().oracle() or system_app.open_app("Messaging").oracle() if it helps context.
    - In build_events_flow, prefer to use initialized apps with meaningful tool/action calls; it is acceptable if some initialized apps are unused
    - All scenario events (environment context events, agent proposals, user approvals, and agent follow-up actions)
      MUST be emitted inside one or more 'with EventRegisterer.capture_mode():' blocks, just as in `very_basic_demo_pas_app`.
    - IMPORTANT: Before any agent proposal, create one or more non-oracle context events.
      Use only the non-oracle ENV methods listed under "Allowed non-oracle environment methods (by selected app)" below.
      Call these by their exact method names and correct parameters.
    - Create different event flows and proactive behaviors than the examples
    - Maintain similar complexity and validation approach but target different signals

    PROACTIVE INTERACTION PATTERN (MANDATORY):
    - The scenario MUST include this exact pattern in the build_events_flow():
      1. Agent proposes action: aui.send_message_to_user(content="[specific proposal with question]")
      2. User responds: aui.accept_proposal(content="[meaningful, contextual approval like 'Yes, please share it with Jordan' or 'Yes, go ahead and schedule that meeting']") (reject_proposal(...) also allowed)
      3. Agent executes the proposed action based on user approval
    - This pattern should be central to the scenario, not just a minor interaction
    - The proposal should be meaningful, logically motivated, and clearly related to the scenario's main objective
      based on prior environment events or tool outputs (e.g., propose forwarding a photo only if that photo was
      actually received earlier in the conversation, and the recipient has requested it).
    - Use realistic, specific proposals that make sense for the available apps
    - The user should ALWAYS respond with detailed, contextual approval (not just "yes")
    - ENVIRONMENT CONTEXT: Ensure the proposal is preceded by at least one non-oracle environment event
      (e.g., a system notification or incoming message) using the allowed environment tools from the selected apps.

    NOVELTY REQUIREMENTS:
    - Choose a DIFFERENT primary objective than any provided example
    - Use a DIFFERENT mix of the available tools and ENV methods than the examples
    - Vary the event flow: different number of events, different ordering, different delays
    - Use DIFFERENT identifiers: variable names, email subjects, message contents, event titles
    - Change validation signals to check for different outcomes (IDs, counts, tag/state changes) than the examples
    - If similarity is reported, PIVOT immediately: change objective, domain, app combination, structure, identifiers, validation targets
    - IMPORTANT: Novelty is primarily about COMBINATIONS and SEQUENCES of tools across apps (ENV/non-ENV/oracle),
      not just new storyline content. Prefer different cross-app tool flows and step ordering than the examples.

    API CORRECTNESS RULES (STRICT):
    - Do NOT use env_action or env_event. For non-oracle context events, call only the methods listed under
      "Allowed non-oracle environment methods (by selected app)" below, using exact method names and parameters.
      Do NOT use EventRegisterer.env_event, EventRegisterer.create_env_event, EventRegisterer.register_env_event,
      or any EventRegisterer.* placeholders. Always call ENV methods directly on the app instance.
    - Approvals must use PASAgentUserInterface.accept_proposal(...) (or reject_proposal(...)) instead of send_message_to_agent for approvals.
    - Messaging preconditions:
      - In init_and_populate_apps, set messaging.current_user_id and messaging.current_user_name, and add needed users (e.g., messaging.add_users([...])).
      - Create any conversations up-front (e.g., messaging.create_group_conversation(...)) and CAPTURE the returned conversation_id for later use.
      - For create_and_add_message(...), you MUST provide conversation_id and sender_id (valid participants of that conversation). Do NOT use user_name; it is not a valid parameter.
    - System/time:
      - Do not create oracle events just to read time. Prefer environment context events (e.g., wait_for_notification) to set context; use time reads only as regular calls when needed.
    - IDs, data, and handles:
      - Never hardcode non-existent IDs (e.g., conversation_id) or other concrete values (file paths, message IDs, URLs, etc.).
        Always use the values returned by earlier tool calls or those explicitly created in init_and_populate_apps.
      - When acting on existing content (forwarding messages, sharing attachments, updating items), derive the target
        and any required identifiers from prior environment events or tool outputs; do not fabricate new ones.
    - Validation guidance:
      - Calendar: prefer verifying event time ranges, attendee lists, or existence by ID over subjective title checks.
      - Messaging: avoid subjective content checks; prefer checking message presence/count, returned IDs, or structured metadata.

    SIMILARITY AVOIDANCE:
    - difflib_ratio ≥0.8: avoid similar code structure and sequences
    - jaccard_shingles ≥0.8: avoid similar token combinations and patterns
    - cosine_tokens ≥0.93: vary identifier and keyword choices significantly
    - If flagged as similar, completely change the scenario behavior and flow

    """
)

SEED_SCENARIO_GENERATOR_ENVIRONMENT_INSTRUCTIONS = textwrap.dedent(
    """You are an agent operating in a constrained virtual environment for scenario generation.

    ENVIRONMENT CHARACTERISTICS:
    - You have access ONLY to the applications and tools defined in the app definition scenario
    - The example scenarios are for reference and inspiration only
    - You must generate scenarios that work with the available tool set

    AVAILABLE TOOLS:
    <<tool_descriptions>>

    INSTRUCTIONS TO IMPORT AVAILABLE TOOLS:
    <<import_instructions>>

    FUNDAMENTAL RULES FOR SCENARIO GENERATION:
    1. APP INITIALIZATION: Initialize ALL applications from the app definition scenario (mandatory)
    2. APP USAGE: Prefer to use at least one tool from each initialized app when meaningful (optional)
    3. CONSTRAINT: Use only the tools from the app definition scenario
    4. REFERENCE: Use example scenarios for structure and patterns, not for tool selection
    5. NOVELTY: Create unique scenarios that differ significantly from examples. If an 'EXISTING SCENARIO SUMMARIES' section is provided below,
       actively avoid creating scenarios that resemble any of those summaries.
    6. VALIDITY: Ensure all tool calls are valid for the available tools
    7. EXECUTION: Generate complete, runnable scenario code that uses every app
    8. CAPTURE MODE: All scenario events (environment context events, agent proposals, user approvals, agent follow-up actions)
       MUST be created inside one or more 'with EventRegisterer.capture_mode():' blocks (no ad-hoc events outside capture_mode).
    9. PROACTIVE INTERACTION: MUST include agent proposal → user response → agent action pattern if user approves

    === PAS Tool Usage Rules ===
    <<pas_rules_block>>

    <<pas_grouped_block>>

    {seed_scenario_generator_agent_hints}

    <<agent_reminder_description>>
    """
)

DEFAULT_SEED_SCENARIO_GENERATOR_SYSTEM_PROMPT = SYSTEM_PROMPT_TEMPLATE.format(
    general_instructions=SEED_SCENARIO_GENERATOR_SYSTEM_PROMPT_TEMPLATE,
    agent_instructions=SEED_SCENARIO_GENERATOR_AGENT_HINTS,
    environment_instructions=SEED_SCENARIO_GENERATOR_ENVIRONMENT_INSTRUCTIONS.format(
        seed_scenario_generator_agent_hints=""
    ),
)

# ===== PAS Dynamic Blocks =====

PAS_RULES_BLOCK_TEMPLATE = textwrap.dedent(
    """1) In init_and_populate_apps: Only use data tools OR event-only tools (methods with only @event_registered). Do NOT use env_action/env_event helpers.
2) In build_event_flow WITH EventRegisterer.capture_mode():
   - Before any agent proposal, create at least one non-oracle environment event from the allowed list to establish context.
   - For non-oracle events: Only use ENV tools from the selected apps listed below in 'Allowed non-oracle environment methods'.
     Do NOT use EventRegisterer.env_event, EventRegisterer.create_env_event, EventRegisterer.register_env_event, or any EventRegisterer.* placeholders.
     Always call ENV methods directly on the app instance (e.g., messaging.create_and_add_message(...), calendar.add_calendar_event(...)).
   - For oracle events (.oracle()): Any tools from the selected apps are allowed.
3) In build_event_flow OUTSIDE capture_mode: Prefer oracle usage when using non-env tools."""
)

PAS_GROUPED_BLOCK_TEMPLATE = textwrap.dedent(
    """-- Allowed tools in init_and_populate_apps (data + event-only) --
<<init_allowed_block>>

-- Allowed non-oracle environment methods (by selected app) --
<<allowed_non_oracle_by_app_block>>"""
)
