import textwrap

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
but with DIFFERENT content and themes while using SIMILAR API patterns and structure). \
The difficulty of the generated scenario should be similar to the reference scenarios.

NOVELTY AND ANTI-DUPLICATION REQUIREMENTS (critical):
- Choose a DIFFERENT primary objective than any provided example (do not replicate scheduling if example schedules; pick another realistic task).
- Use a DIFFERENT mix of apps or a different interaction pattern across apps.
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

Suggested alternative proactive behaviors (non-exhaustive):
- Following up on tasks or messages from the user
- Scheduling or rescheduling meetings with different constraints
- Organizing or managing contacts information
- Responding to different types of emails or communications
- Managing calendar events differently (reminders, updates, cancellations)
- File finding and management and document organization
- System notifications and proactive alerts

Key requirements:
- Use the same app APIs (AgentUserInterface, CalendarApp, EmailClientApp, ContactsApp, MessagingApp, FileSystem, SystemApp, etc.)
- Follow the same Scenario class structure and methods
- Create different event flows and proactive agent behaviors
- Import the same tools at the beginning of the file (per import instructions)
- Maintain a similar validation approach style but target different signals than the example

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
