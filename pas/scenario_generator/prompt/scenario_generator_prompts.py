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
    2. The user responds with detailed approval (using AgentUserInterface__send_message_to_agent with a meaningful, contextual response like "Yes, that sounds good—please go ahead with that" or "Yes, go ahead and schedule that meeting")
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
 - METHOD COMBINATION DIVERSITY: Compared with any input example_scenarios (and scenarios listed via --scenario),
   do not reuse the same method combinations or call chains across apps. Select different sets of app methods and
   different cross-app interaction patterns than the inputs, even if the storyline domain overlaps.
  - Practical guidance: If examples use methods A+B, consider A+C or B+D or A+B+C; include at least one new method
    compared to each prior combination to ensure distinct tool flows.
- EVENT-FLOW DIVERSITY: The ordered list of method calls inside build_events_flow is monitored.
  Reusing the same call order (e.g., single incoming message → proposal → approval → single agent action → confirmation)
  will be rejected. Add extra context steps, branching checks, multi-app reasoning, or different tool chains so that
  each scenario's event flow is structurally distinct.
- ORACLE METHOD COVERAGE: Use a diverse mix of allowed oracle (USER/APP) methods from the selected apps.
  Aim to exercise at least half of the selected-app oracle methods (minimum 3 when available). PASAgentUserInterface
  and HomeScreenSystemApp may be reused freely; diversity is enforced only for the other selected apps.

CONTEXT-GROUNDED BEHAVIOR (critical):
- Do NOT invent new concrete facts (emails, messages, users, file paths, IDs, URLs, event contents, etc.) that do not come from:
  (a) explicit initialization in init_and_populate_apps, or
  (b) the return values or state changes of previous tool calls in this scenario.
- Any action you take (forwarding, sharing, scheduling, attaching files, etc.) MUST be grounded in prior
  environment events or tool outputs in this scenario. If the environment never produced an item, you must
  not pretend it exists.
- Names and recipients: whenever you call get_user_id/lookup_user_id with a user_name, that name MUST have already
  appeared in a previous environment message or conversation title in build_events_flow (e.g., another teammate
  mentions them). Do NOT introduce new people in lookups or proposals without prior mention.
- Oracle actions and proposals: every .oracle() call (including aui.send_message_to_user proposals, add_participant
  calls, reminders, or file forwards) MUST have a clearly visible reason in earlier environment events or oracle
  outputs. Before proposing to invite someone, send a followup, or share a file, ensure that prior messages or
  tool results explicitly motivate that action (e.g., someone asked to be added, requested a file, or mentioned
  needing a reminder).

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
    - TOOL CALLS MUST MATCH THE ALLOWED LISTS: Only call methods that appear in the PAS grouped blocks below
      ("Allowed non-oracle..." and "Allowed oracle..."). If a method (e.g., open_conversation) is not listed for the
      current apps, you must accomplish the workflow using supported tools.

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

    TEMPORAL COHERENCE (IMPORTANT):
    - Use ecologically valid timestamps that align simulation time with scenario data.
    - Set start_time to a realistic date/time (UTC) consistent with the scenario's events and references.
    - Ensure email timestamps, calendar dates, and time-based logic are coherent with start_time.

    PROACTIVE INTERACTION PATTERN (MANDATORY):
    - The scenario MUST include this exact pattern in the build_events_flow():
      1. Agent proposes action: aui.send_message_to_user(content="[specific proposal with question]")
      2. User responds: aui.accept_proposal(content="[meaningful, contextual approval like 'Yes, that sounds good—please go ahead with that' or 'Yes, go ahead and schedule that meeting']") (reject_proposal(...) also allowed)
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
    - METHOD COMBINATION DIVERSITY: Compared with any input example_scenarios (and scenarios listed via --scenario),
      do not reuse the same method combinations or call chains across apps. Select different sets of app methods and
      different cross-app interaction patterns than the inputs, even if the storyline domain overlaps.
      Practical guidance: If examples use methods A+B, consider A+C or B+D or A+B+C; include at least one new method
      compared to each prior combination to ensure distinct tool flows. Each generated scenario MUST include at least
      one oracle/app method that has not appeared in earlier scenarios from this run.
    - EVENT-FLOW DIVERSITY: The generator now compares the ordered list of method calls inside build_events_flow.
      If you repeat the same order (e.g., single incoming message → proposal → approval → single follow-up action → confirmation),
      the scenario will be rejected. Introduce extra context discovery, branch logic, or multi-step tool chains to keep
      the call order distinct from prior outputs.
    - ORACLE METHOD COVERAGE: During build_events_flow, invoke a broad set of allowed oracle methods (USER + APP) from the
      selected apps. Target at least half of those selected-app oracle methods (minimum 3 when available) so approvals,
      navigation, follow-up actions, and confirmations demonstrate diverse tool usage. PASAgentUserInterface and
      HomeScreenSystemApp may repeat methods freely; diversity is enforced only for the other selected apps.
      IMPORTANT: Do NOT add oracle calls just to increase diversity if they are not grounded in earlier events or used
      later in the flow. Every oracle chain should either (a) be clearly motivated by prior environment or oracle output
      events, and (b) have its outputs or side-effects consumed later (e.g., IDs reused, results inspected, messages sent,
      or validation depending on them). Remove or rework any "dangling" oracle calls whose results are never used.

    API CORRECTNESS RULES (STRICT):
    - Do NOT use env_action or env_event. For non-oracle context events, call only the methods listed under
      "Allowed non-oracle environment methods (by selected app)" below, using exact method names and parameters.
      Do NOT use EventRegisterer.env_event, EventRegisterer.create_env_event, EventRegisterer.register_env_event,
      or any EventRegisterer.* placeholders. Always call ENV methods directly on the app instance.
    - Approvals must use PASAgentUserInterface.accept_proposal(...) (or reject_proposal(...)) instead of send_message_to_agent for approvals.
    - Messaging preconditions:
      - In init_and_populate_apps, set messaging.current_user_id and messaging.current_user_name.
      - Do NOT call messaging.add_users(...). Resolve participants via discovery methods (e.g., search/list APIs) or ask the user.
      - Create any conversations up-front (e.g., messaging.create_group_conversation(...)) and CAPTURE the returned conversation_id for later use.
      - For create_and_add_message(...), you MUST provide conversation_id and sender_id (valid participants of that conversation). Do NOT use user_name; it is not a valid parameter.
    - System/time:
      - Do not create oracle events just to read time. Prefer environment context events (e.g., wait_for_notification) to set context; use time reads only as regular calls when needed.
    - IDs, data, and handles:
      - Never hardcode non-existent IDs (e.g., conversation_id, user_id, sender_id, participant_id) or other handles.
        Capture IDs in init_and_populate_apps (e.g., `self.alpha_chat_id`, `self.jordan_id`) or from prior tool outputs and
        reference those variables later. Passing literal strings like "alex-id-123" in build_events_flow will be rejected.
      - When acting on existing content (forwarding messages, sharing attachments, updating items), derive the target
        and any required identifiers from prior environment events or tool outputs; do not fabricate new ones.
      - Unsupported methods: calling a method that is not listed in the PAS grouped block (non-oracle/oracle sections)
        will cause validation to fail. Always double-check that every app call matches one of the allowed tool names.
    - Tool-call hygiene:
      - `get_user_id` ALWAYS requires `user_name=...`. Call it with an explicit string or stored variable; no bare `get_user_id()`.
      - When you need lookup results (e.g., `lookup_user_id`), capture the returned dict immediately and store the IDs in
        your own variables before entering capture_mode. Do NOT rely on `Event.return_value`.
      - Follow exact signatures: e.g., `change_conversation_title` takes `title=...`, not `new_title=...`.
      - Do NOT call unsupported helpers like `.assign(...)` on Event objects.
      - After the proactive proposal, invoke at least three distinct allowed oracle USER/APP methods (e.g., add_participant_to_conversation,
        change_conversation_title, list_recent_conversations, lookup_user_id) before the scenario concludes.
    - Email ID referencing:
      - If the scenario needs to reply to a specific incoming email later, emit it using a method that returns or accepts a known email_id
        (e.g., send_email_to_user_with_id(...)) so reply_to_email(...) can reference it deterministically.
    - Context discovery:
      - Do not assume team membership, recipients, or groups based solely on initialization. Before sending or forwarding, resolve
        recipients and conversation IDs using discovery methods (e.g., search(...), list/read/get APIs),
        or ask the user for clarification via AgentUserInterface if the context is insufficient.
      - Avoid adding context-specific artifacts (e.g., focus-time calendar blocks) unless the prior events or the user's approval make
        them clearly relevant. Prefer general, context-grounded proposals and actions.
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

    METHOD COMBINATIONS RECENTLY USED (avoid reusing these exact combos; prefer adding/replacing methods):
    <<avoid_method_combinations_block>>

    REQUIRED NEW METHODS TO PRIORITIZE (use ≥1 of these if available):
    <<suggested_new_methods_block>>

    SUGGESTED NEW METHODS TO PRIORITIZE (use these before repeating earlier combos):
    <<suggested_new_methods_block>>

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
    """1) In init_and_populate_apps: You may use ANY available tools (APP, USER, ENV, DATA, or event-only). Do NOT use env_action/env_event helpers.
2) In build_event_flow WITH EventRegisterer.capture_mode():
   - Before any agent proposal, create at least one non-oracle environment event from the allowed list to establish context.
   - For non-oracle events: Only use ENV tools from the selected apps listed below in 'Allowed non-oracle environment methods'.
     Do NOT use EventRegisterer.env_event, EventRegisterer.create_env_event, EventRegisterer.register_env_event, or any EventRegisterer.* placeholders.
     Always call ENV methods directly on the app instance (e.g., messaging.create_and_add_message(...), calendar.add_calendar_event(...)).
   - For oracle events (.oracle()): Only USER tools and APP tools are allowed (no ENV/DATA/event-only in the oracle chain).
3) In build_event_flow OUTSIDE capture_mode: Prefer oracle usage when using non-env tools.
4) CONTEXT DISCOVERY (generic): Do NOT assume knowledge that only exists in initialization. Before acting on recipients, groups, or targets,
   first discover or derive them using available methods (e.g., messaging.search(...), contacts.search(...), list/read/get APIs) or by using IDs returned
   from earlier calls. If context is insufficient, ask the user for clarification via AgentUserInterface rather than inventing facts.
5) CONTEXT-DEPENDENT ACTIONS: Avoid adding highly specific actions (e.g., focus-time calendar blocks) unless they are clearly motivated by
   prior environment events or explicitly approved by the user. Prefer proposing and executing actions that follow directly from established context.
6) EMAIL ID REFERENCING: When you need to reply to a specific email later, ensure the incoming email event exposes or accepts a deterministic ID
   (e.g., use send_email_to_user_with_id) so reply_to_email can reference it reliably.
7) METHOD COMBINATION DIVERSITY: Compared with the input example_scenarios (and scenarios listed via --scenario), avoid reusing the same
   combinations of app methods or cross-app chains. Choose different tool combinations and call sequences than those present in the inputs."""
)

PAS_GROUPED_BLOCK_TEMPLATE = textwrap.dedent(
    """-- Allowed non-oracle environment methods (by selected app) --
<<allowed_non_oracle_by_app_block>>

-- Allowed oracle methods (by selected app; USER + APP only) --
<<allowed_oracle_by_app_block>>"""
)


# ===== Targeted Repair Prompts =====

FABRICATED_ID_REPAIR_SYSTEM_PROMPT = textwrap.dedent(
    """You are correcting fabricated identifiers and UNGROUNDED PROPOSAL CONTENT in a PAS scenario file.
Fix BOTH:
1) Hardcoded IDs/handles/paths (conversation_id, user_id, sender_id, participant_id, attachment_id, file paths, etc.) — replace with variables defined in init_and_populate_apps() or IDs returned from earlier tool calls.
2) Ungrounded proposal content — in aui.send_message_to_user and subsequent actions, remove or rewrite any names/files/targets that never appeared in earlier environment/oracle events or init variables; proposals must be justified by earlier context.

Available PAS tools (non-oracle and oracle) for the current selected apps:
<<pas_grouped_block>>

Return the FULL scenario as a single fenced python code block."""
)

FABRICATED_ID_REPAIR_USER_PROMPT = textwrap.dedent(
    """The following fabricated identifier and/or ungrounded proposal-content issues were detected (do NOT ignore them):
{issues}

Update the code so that:
- Every ID/handle/path passed to tools comes from stored variables or previous tool outputs (no literal fabrications).
- Every proposal/action references ONLY names/files/targets that are explicitly present in earlier environment/oracle events or init variables. If needed, add minimal prior events to introduce them, or change the proposal to target existing context.

Scenario needing fixes:
```python
{code}
```

Return ONLY a single fenced python code block with the corrected file."""
)

METHOD_HYGIENE_REPAIR_SYSTEM_PROMPT = textwrap.dedent(
    """You are correcting PAS tool usage and method signatures in a scenario file.
Common fixes include:
- messaging.get_user_id must always include user_name=...
- Do NOT read Event.return_value; store lookup results directly when calling the tool
- Do NOT read Event.output; capture IDs/results directly or store them earlier in variables
- Follow exact tool signatures (e.g., change_conversation_title(title=...))

Available PAS tools (non-oracle and oracle) for the current selected apps:
<<pas_grouped_block>>

Return the FULL scenario as a single fenced python code block."""
)

METHOD_HYGIENE_REPAIR_USER_PROMPT = textwrap.dedent(
    """The following method-usage issues were detected (fix ALL of them):
{issues}

Update the code so every tool call matches the allowed PAS signatures:
- Provide required arguments like user_name=... for get_user_id
- Capture lookup results immediately; do not inspect Event.return_value
- Do not use Event.output; persist needed IDs/results at the time of the tool call
- Use the documented keyword names (title=..., not new_title=..., etc.)

Scenario needing fixes:
```python
{code}
```

Return ONLY a single fenced python code block with the corrected file."""
)

RUNTIME_SAFETY_REPAIR_SYSTEM_PROMPT = textwrap.dedent(
    """You are correcting runtime safety issues in a PAS scenario.
Common fixes:
- Replace lowercase true/false with Python True/False
- Do not call unsupported helpers like Event.assign(...)
- accept_proposal validations must check EventType.AGENT (not USER)
- Ensure IDs and attachments come from real tool outputs

Available PAS tools (non-oracle and oracle) for the current selected apps:
<<pas_grouped_block>>

Return the FULL scenario as a single fenced python code block."""
)

RUNTIME_SAFETY_REPAIR_USER_PROMPT = textwrap.dedent(
    """The following runtime issues were detected:
{issues}

Update the scenario accordingly:
- Use Python True/False
- Remove .assign(...) or other unsupported helper calls
- Validate accept_proposal events as EventType.AGENT entries
- Ensure attachments and IDs come from actual tool outputs

Scenario needing fixes:
```python
{code}
```

Return ONLY a single fenced python code block with the corrected file."""
)

FABRICATED_ID_DETECT_SYSTEM_PROMPT = textwrap.dedent(
    """You are auditing a PAS scenario file for FABRICATED IDENTIFIERS/ATTACHMENT PATHS and UNGROUNDED PROPOSALS/ACTIONS.

General rule:
- Any identifier or handle used in tool calls (IDs, conversation IDs, user IDs, participant IDs, email/message IDs,
  attachment IDs, file/attachment paths, etc.) MUST be grounded in either:
  (a) variables initialized in init_and_populate_apps (e.g., self.* fields), or
  (b) explicit return values from earlier tool calls in this scenario.
- Do NOT fabricate literal IDs or file paths directly inside build_events_flow; they should be derived from prior code.
- UNGROUNDED PROPOSAL CONTENT: Check all aui.send_message_to_user proposals and the actions they lead to. If they
  reference names/files/targets NOT present in earlier environment/oracle events or init variables, these are fabricated (ungrounded).

Concretely check:
1) In both init_and_populate_apps and build_events_flow, look for suspicious literal strings or numbers used as:
   - IDs/handles (conversation_id, user_id, sender_id, participant_id, email_id, message_id, attachment_id, etc.)
   - attachment or file paths (attachment_path, file_path, etc.)
2) A usage is FABRICATED if:
   - The value is a hard-coded literal that is not clearly defined as a constant in init_and_populate_apps, and
   - It is not obviously derived from a prior tool result or stored self.* attribute.
3) A proposal is UNGROUNDED if:
   - It references a person (e.g. "add Jordan") or item (e.g. "file report.pdf") that never appeared in prior events/init.

Reasoning workflow (step-by-step):
- Enumerate proposals and subsequent actions; extract referenced people/files/targets and intended operations.
- Trace earlier events/init variables to find explicit justification (mentions/requests/results).
- If no justification is found, mark as UNGROUNDED and explain which prerequisite is missing.
- Enumerate literal IDs/paths and confirm they originate from init or earlier tool outputs.

Your task:
- List each suspected fabricated identifier, attachment/path, or ungrounded proposal/action reference and briefly explain why it appears fabricated/ungrounded, OR
- If there are no such problems, respond with exactly: NO_FABRICATED_IDENTIFIER_ISSUES

Return a short plain-text report (no code)."""
)

FABRICATED_ID_DETECT_USER_PROMPT = textwrap.dedent(
    """Audit the following scenario code for fabricated identifier and attachment/path issues as described:

```python
{code}
```

Follow the instructions from the system message and either:
- Output 'NO_FABRICATED_IDENTIFIER_ISSUES' (exactly, if every ID/path is grounded), or
- Output a short bullet list of issues, one per line."""
)

ORACLE_DIVERSITY_REPAIR_SYSTEM_PROMPT = textwrap.dedent(
    """You are expanding oracle (USER/APP) tool usage in a PAS scenario.
Add multiple allowed oracle actions in build_events_flow after the proactive proposal.
Ensure build_events_flow uses at least three distinct allowed oracle methods (USER/APP tools) from the selected apps,
and avoid reusing exactly the same set of oracle methods that appeared in earlier generated scenarios for this run.
Examples include: add_participant_to_conversation, change_conversation_title, get_user_id, lookup_user_id, list_recent_conversations.

Allowed PAS tools for the current apps:
<<pas_grouped_block>>

Return the FULL scenario as a single fenced python code block."""
)

ORACLE_DIVERSITY_REPAIR_USER_PROMPT = textwrap.dedent(
    """Oracle method diversity is missing:
{issues}

Add several oracle USER/APP tool calls after the proposal (at least 3 distinct methods), but ONLY when they make
the scenario more meaningful and are clearly grounded in earlier environment/tool events. Prefer a mix of oracle methods
that has not appeared in earlier scenarios from this run (do not repeat the exact same set of oracle methods).
For each added oracle chain:
- Ensure there is a prior environment or oracle event that motivates the action (discovery, follow-up, sharing, etc.).
- Ensure the results/side-effects are used later in the flow (e.g., IDs reused, messages sent, validation checks).
Suggested tools: {suggested}

Scenario needing fixes:
```python
{code}
```

Return ONLY a single fenced python code block with the corrected file."""
)

PROACTIVE_PATTERN_REPAIR_SYSTEM_PROMPT = textwrap.dedent(
    """You are fixing the proactive interaction pattern in a PAS scenario.
Ensure the flow includes:
1) aui.send_message_to_user(...) proposal with a question
2) aui.accept_proposal(...) or reject_proposal(...) with contextual approval
3) Follow-up agent actions that execute the approved request

Allowed PAS tools for the current apps:
<<pas_grouped_block>>

Return the FULL scenario as a single fenced python code block."""
)

PROACTIVE_PATTERN_REPAIR_USER_PROMPT = textwrap.dedent(
    """The proactive interaction pattern is incomplete:
{issues}

Ensure build_events_flow contains the full sequence:
1) Proposal message via aui.send_message_to_user(...)
2) Meaningful user approval via aui.accept_proposal(...) or reject_proposal(...)
3) Follow-up actions that depend on the approval

Scenario needing fixes:
```python
{code}
```

Return ONLY a single fenced python code block with the corrected file."""
)

CONTEXT_GROUNDING_REPAIR_SYSTEM_PROMPT = textwrap.dedent(
    """You are correcting context-grounding issues in a PAS scenario.
Every proactive inference MUST be justified by prior environment events or oracle/tool outputs:
- Do NOT introduce new purposes or recipients (e.g., 'Design Team' group, unnamed collaborators) unless they appear
  in earlier messages, conversation titles, or tool results.
- Do NOT reference human names or group names that only exist in init_and_populate_apps; surface them via oracle calls
  or environment events in build_events_flow before using them in proposals.
    - For any person the agent interacts with in build_events_flow (e.g., Taylor), prefer to resolve and store their user_id
      in init_and_populate_apps (e.g., self.taylor_id from lookup_user_id) and then reuse that stored ID later rather than
      doing first-time lookups or depending on event outputs.

Available PAS tools (non-oracle and oracle) for the current selected apps:
<<pas_grouped_block>>

Return the FULL scenario as a single fenced python code block."""
)

CONTEXT_GROUNDING_REPAIR_USER_PROMPT = textwrap.dedent(
    """Review the scenario and fix any context-grounding mistakes:
- Proposals (aui.send_message_to_user) must clearly reference facts from prior environment events or tool outputs.
- Do NOT propose sharing files or inviting people whose names/chats never appeared in build_events_flow.
- If a collaborator or group is used in init_and_populate_apps, first surface it via an oracle/tool call or
  environment event in build_events_flow before referencing it in messages.
- Every oracle action (any .oracle() call) must have an explicit, earlier "why" in environment or oracle events.
- For example, if the agent proposes "forward this file link to Taylor Nguyen for review", there must be an earlier
  message or tool output where someone asks to include Taylor or requests that they review the file.
- For any recurring teammate name that appears in proposals or oracle calls in build_events_flow,
  prefer to resolve their user_id once in init_and_populate_apps (e.g., using lookup_user_id) and store it on self.*.
  Then reuse that stored ID instead of calling lookup_user_id for the first time in build_events_flow or
  reading IDs from Event/step outputs.
- If a proposal references a specific teammate (e.g., "share this summary with Jordan") but that person was never
  mentioned in earlier environment/oracle events, either (a) add earlier events that explain why they should receive
  the update, or (b) change the proposal to target a collaborator who already appears in the scenario context.
 - Generic action grounding rule: any action (forward/share/download/rename/add/remove/send/reply/schedule/etc.)
   must be motivated by prior events and refer only to targets (people, groups, files, event IDs, titles) that were
   explicitly introduced earlier. Add minimal prior events if necessary, or change the action to use existing context.

The following context-grounding issues were detected (address EACH of them explicitly):
{issues}

Scenario needing fixes:
```python
{code}
```

Return ONLY a single fenced python code block with the corrected file."""
)

CONTEXT_GROUNDING_DETECT_SYSTEM_PROMPT = textwrap.dedent(
    """You are auditing a PAS scenario file for CONTEXT-GROUNDED BEHAVIOR.

General rule:
- EVERY oracle action (any .oracle() call, including proposals, lookups, and follow-up actions) MUST be
  clearly justified by prior environment events or earlier oracle/tool outputs in build_events_flow.

Concretely check:
1) For each get_user_id(user_name=...) or lookup_user_id(user_name=...) in build_events_flow:
   - Verify that the user_name string appears earlier in some environment event content or conversation title
     (e.g., create_and_add_message(..., content=...), create_group_conversation(..., title=...)).
   - If the name never appears prior to the lookup/proposal, that is an UNGROUNDED NAME.
   - Additionally, check whether init_and_populate_apps already resolves and stores a stable user_id for that name
     on self.* (e.g., self.taylor_id via lookup_user_id). If build_events_flow is doing a first-time lookup_user_id
     for a recurring teammate instead of reusing an ID set in init_and_populate_apps, mark this as a MISSING_INIT_USER_ID
     issue and suggest moving the lookup into init_and_populate_apps.
2) For each aui.send_message_to_user(...) proposal or follow-up oracle action:
   - Verify that the reason for the action is explicitly supported by prior environment messages or oracle outputs
     (for example, a teammate asked to be added, a previous message requested a share, or a notification indicated
     the need for follow-up).
   - Concretely: if the agent proposes to "forward this file/link to Taylor Nguyen for review" but earlier events
     only show someone sharing a file (with no mention of Taylor and no request to loop them in or get their review),
     that is an UNGROUNDED ACTION and the name is also ungrounded.
   - If the "why" for the action is not clearly present in earlier events, mark it as an UNGROUNDED ACTION.
   - Group-targeting check: If the proposal targets a group (e.g., “send to the project group”, “post in the team chat”)
     or uses group actions (e.g., send_message_to_group_conversation, add_participant_to_conversation), verify that:
       a) the specific group or conversation has been previously created or mentioned by name/title, and
       b) there is an explicit reason in prior events that motivates notifying that group.
     Otherwise, mark as UNGROUNDED GROUP ACTION.
   - Generic action grounding (apply to all actions such as forward/share/download/rename/add/remove/send/reply/schedule):
     For any action verb (forward/share a file or message; download_attachment; change_conversation_title/rename; add/remove
     participant; send_message/send_message_to_user/send_message_to_group_conversation; reply_to_email; add/edit/delete
     calendar events; etc.), ensure that earlier events introduce the concrete target(s) (files, titles, people, groups,
     event IDs) and provide a clear motivation (request/mention/validation need). If not, mark as UNGROUNDED ACTION.

Reasoning workflow (step-by-step):
- Enumerate proposals and subsequent actions.
- For each, extract the referenced people/items/targets and the intended operation.
- Trace earlier events to find explicit justification (mentions, requests, discovery results, IDs previously obtained).
- If no justification is found, mark as UNGROUNDED and explain which prerequisite is missing.

Your task:
- List each ungrounded name or action and briefly explain why it is ungrounded, and/or each MISSING_INIT_USER_ID issue
  where build_events_flow is doing a first-time lookup that should live in init_and_populate_apps instead, OR
- If there are no such problems, respond with exactly: NO_CONTEXT_GROUNDING_ISSUES

Return a short plain-text report (no code)."""
)

CONTEXT_GROUNDING_DETECT_USER_PROMPT = textwrap.dedent(
    """Audit the following scenario code for context-grounding issues as described:

```python
{code}
```

Follow the instructions from the system message and either:
- Output 'NO_CONTEXT_GROUNDING_ISSUES' (exactly, if everything is grounded), or
- Output a short bullet list of issues, one per line."""
)

ORACLE_MEANINGFULNESS_DETECT_SYSTEM_PROMPT = textwrap.dedent(
    """You are auditing a PAS scenario file for MEANINGFUL ORACLE USAGE.

General rule:
- Oracle (.oracle()) calls must be clearly motivated by earlier environment/oracle events and must have observable
  effects on the scenario (e.g., IDs reused later, messages sent, participants added, validation depending on them).
- Do NOT add oracle calls solely to increase "diversity" if they are unused, redundant, or disconnected from the
  scenario's main objective and validation.

Concretely check in build_events_flow:
1) For each oracle chain (any call where .oracle() is used inside capture_mode):
   - Is there a prior environment or oracle event that explains WHY this action is being taken?
   - Are the results or side-effects of the oracle call used later (e.g., variables reused, branching, follow-up actions,
     or assertions in validate())?
   - If a call simply reads data (e.g., get_user_id, get_user_name_from_id, list_recent_conversations) and the result
     is never used to influence the story or validation, mark it as SUPERFICIAL ORACLE USAGE.

Your task:
- List each superficial oracle usage and briefly explain why it is not meaningfully grounded or used, OR
- If there are no such problems, respond with exactly: NO_ORACLE_MEANINGFULNESS_ISSUES

Return a short plain-text report (no code)."""
)

ORACLE_MEANINGFULNESS_DETECT_USER_PROMPT = textwrap.dedent(
    """Audit the following scenario code for oracle meaningfulness issues as described:

```python
{code}
```

Follow the instructions from the system message and either:
- Output 'NO_ORACLE_MEANINGFULNESS_ISSUES' (exactly, if every oracle chain is meaningful and connected), or
- Output a short bullet list of issues, one per line."""
)

ORACLE_MEANINGFULNESS_REPAIR_SYSTEM_PROMPT = textwrap.dedent(
    """You are correcting superficial or unmotivated oracle (.oracle()) usage in a PAS scenario.

Goals:
- Ensure that every oracle chain in build_events_flow is (a) motivated by earlier environment/oracle events and
  (b) has results or side-effects that matter later in the flow (e.g., IDs reused, messages sent, validation checks).
- Remove or refactor any oracle calls that were added only for diversity and have no real impact on the scenario.

Available PAS tools (non-oracle and oracle) for the current selected apps:
<<pas_grouped_block>>

Return the FULL scenario as a single fenced python code block."""
)

ORACLE_MEANINGFULNESS_REPAIR_USER_PROMPT = textwrap.dedent(
    """The following oracle meaningfulness issues were detected (fix ALL of them):
{issues}

Update the scenario so that:
- Each remaining oracle chain is clearly motivated by earlier environment/oracle events.
- The outputs/side-effects of each oracle call are used in subsequent logic or validation (or the call is removed).
- You may introduce additional non-oracle environment events to create motivation/context for oracle calls when needed,
  but avoid gratuitous complexity.

Scenario needing fixes:
```python
{code}
```

Return ONLY a single fenced python code block with the corrected file."""
)
