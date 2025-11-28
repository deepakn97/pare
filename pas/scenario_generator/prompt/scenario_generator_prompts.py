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
but with DIFFERENT content and themes while using ALL available API tools and apps). \
The difficulty of the generated scenario should be similar to the reference scenarios.

    CRITICAL REQUIREMENT: You MUST use ALL applications available in the tool descriptions, and use at least one tool from each app. \
Create a comprehensive scenario that demonstrates the full ecosystem of available applications.

    PROACTIVE INTERACTION REQUIREMENT (MANDATORY): The scenario MUST include a proactive interaction pattern where:
    1. The agent proposes a specific action to the user (using AgentUserInterface__send_message_to_user)
    2. The user responds with detailed approval (using AgentUserInterface__send_message_to_agent with meaningful, contextual response like "Yes, please share it with Jordan" or "Yes, go ahead and schedule that meeting")
    3. The agent then executes the proposed action based on user approval
    4. This pattern should be central to the scenario's workflow, not just a minor interaction

NOVELTY AND ANTI-DUPLICATION REQUIREMENTS (critical):
- Choose a DIFFERENT primary objective than any provided example (do not replicate scheduling if example schedules; pick another realistic task).
- Use a COMPREHENSIVE mix of ALL available apps - every single app must be used meaningfully.
- Vary the event flow: different number of events (±2 or more), different ordering, different delays, and different combination of event types.
- Use DIFFERENT local identifiers: variable names, temporary IDs, email subjects, message contents, event titles, and registry IDs MUST differ from examples. \
  Do not reuse example identifiers except API-required class/method names.
- Change validation signals: assert success via different cues (e.g., different function args checked, counts, or presence of reminders/updates rather than creation of the same item).
- Avoid long token reuse: aside from API symbols, avoid reusing any 5+ consecutive identifier/keyword token sequences seen in examples.
- Ensure the generated class name and @register_scenario key are unique and not present in the references.

    SIMILARITY DETECTION CONTEXT (for understanding why scenarios might be flagged as duplicates):
    - difflib_ratio: measures structural/sequential similarity (longest matching code sequences) - avoid copying similar code structure
    - jaccard_shingles: measures pattern similarity (overlap of 3-token code patterns) - avoid similar token combinations
    - cosine_tokens: measures vocabulary similarity (similarity of token usage frequency) - vary your identifier and keyword choices
    Different thresholds: difflib/jaccard ≥0.8, cosine ≥0.93. If any score exceeds its threshold, the scenario will be rejected.

Key requirements:
- Use ALL available applications from the tool descriptions (every single app must be used)
- Use at least one tool from each available app
- Follow the same Scenario class structure and methods
- In build_events_flow, you MUST use every initialized app at least once; do not only initialize
  apps in init_and_populate_apps without using them in the event flow
- Create comprehensive event flows that demonstrate all available applications
- Import all required tools at the beginning of the file (per import instructions)
- Maintain a similar validation approach style but target different signals than the example
- Ensure every app plays a meaningful role in the scenario workflow
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
    1. You MUST use ALL applications available from the app definition scenario
    2. You can ONLY use tools from the provided app definition scenario - no others are allowed
    3. Every single app must be incorporated into the scenario workflow (use at least one tool from each app)
    4. Do not ignore or skip any available applications

    Your task is to generate a comprehensive scenario that:
    1. Uses ALL applications available from the app definition scenario (mandatory requirement)
    2. Uses at least one tool from each available app
    3. Creates a realistic workflow that demonstrates the full capabilities of the available app ecosystem
    4. Treats the example scenarios as reference material only - for structure, patterns, and inspiration
    5. Creates novel content while following the same API patterns and coding structure
    6. Ensures the generated scenario can run successfully with all available applications
    7. MANDATORY: Includes a proactive interaction pattern where the agent proposes an action and asks for user permission"""
)

SEED_SCENARIO_GENERATOR_AGENT_HINTS = textwrap.dedent(
    """
    SEED SCENARIO GENERATION GUIDELINES:

    APP CONSTRAINTS (STRICTLY ENFORCED):
    - ONLY use tools from the app definition scenario provided
    - DO NOT use apps or tools that appear in example scenarios but are not in the app definition scenario
    - Import only the tools that are available in the app definition scenario
    - If an example scenario uses an app not in the app definition scenario, find an alternative approach using available tools

    COMPREHENSIVE APP USAGE (MANDATORY):
    - You MUST incorporate ALL available apps into the scenario workflow
    - Use at least one tool from each available app
    - Every app should play a meaningful role in the scenario
    - Create realistic workflows that demonstrate the full ecosystem of available applications
    - Ensure no app is left unused in the generated scenario

    SCENARIO STRUCTURE REQUIREMENTS:
    - Follow the standard Scenario class structure (init_and_populate_apps, build_events_flow, validate)
    - Use the same app initialization pattern as the app definition scenario
    - In build_events_flow, ENSURE all apps initialized in init_and_populate_apps are actually used at least once
      with meaningful tool/action calls; do NOT leave any initialized app unused
    - Create different event flows and proactive behaviors than the examples
    - Maintain similar complexity and validation approach but target different signals

    PROACTIVE INTERACTION PATTERN (MANDATORY):
    - The scenario MUST include this exact pattern in the build_events_flow():
      1. Agent proposes action: aui.send_message_to_user(content="[specific proposal with question]")
      2. User responds: aui.send_message_to_agent(content="[meaningful, contextual approval like 'Yes, please share it with Jordan' or 'Yes, go ahead and schedule that meeting']")
      3. Agent executes the proposed action based on user approval
    - This pattern should be central to the scenario, not just a minor interaction
    - The proposal should be meaningful and related to the scenario's main objective
    - Use realistic, specific proposals that make sense for the available apps
    - The user should ALWAYS respond with detailed, contextual approval (not just "yes")

    NOVELTY REQUIREMENTS:
    - Choose a DIFFERENT primary objective than any provided example
    - Use a DIFFERENT mix of the available apps
    - Vary the event flow: different number of events, different ordering, different delays
    - Use DIFFERENT identifiers: variable names, email subjects, message contents, event titles
    - Change validation signals to check for different outcomes than the examples
    - Avoid copying token sequences from examples; reuse only API method names

    COMPREHENSIVE APP USAGE (MANDATORY):
    - Use ALL applications exactly as defined in the app definition scenario
    - Use at least one tool from each available app
    - Follow the same method signatures and parameter patterns for all tools
    - Ensure all method calls are valid for the available tools
    - Test your app usage mentally against the available tool descriptions
    - Every app must be used at least once in a meaningful way
    - Create realistic workflows that demonstrate each app's purpose

    SIMILARITY AVOIDANCE:
    - difflib_ratio ≥0.8: avoid similar code structure and sequences
    - jaccard_shingles ≥0.8: avoid similar token combinations and patterns
    - cosine_tokens ≥0.93: vary identifier and keyword choices significantly
    - If flagged as similar, completely change the scenario behavior and flow

    AVAILABLE TOOLS:
    <<tool_descriptions>>

    INSTRUCTIONS TO IMPORT AVAILABLE TOOLS:
    <<import_instructions>>

    <<curent_time_description>>
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
    1. COMPREHENSIVE USAGE: Use ALL applications from the app definition scenario (mandatory)
    2. APP USAGE: Use at least one tool from each available app
    3. CONSTRAINT: Use only the tools from the app definition scenario
    4. REFERENCE: Use example scenarios for structure and patterns, not for tool selection
    5. NOVELTY: Create unique scenarios that differ significantly from examples
    6. VALIDITY: Ensure all tool calls are valid for the available tools
    7. EXECUTION: Generate complete, runnable scenario code that uses every app
    8. PROACTIVE INTERACTION: MUST include agent proposal → user response → agent action pattern if user approves

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
