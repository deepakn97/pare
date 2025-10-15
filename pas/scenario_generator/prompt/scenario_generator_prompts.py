import textwrap

# ===== Repair Prompt Templates =====

REPAIR_SYSTEM_PROMPT_BASE = textwrap.dedent(
    """You are fixing Python imports in a generated scenario file. \
Your goal is to correct ONLY import statements so they compile, without changing the scenario's logic or behavior.
Return a single COMPLETE fenced python code block that includes corrected imports and the full file."""
)

REPAIR_SYSTEM_PROMPT_WITH_INSTRUCTIONS_BASE = textwrap.dedent(
    """You are fixing Python imports in a generated scenario file. \
Your goal is to correct ONLY import statements so they compile, without changing the scenario's logic or behavior.
Return a single COMPLETE fenced python code block that includes corrected imports and the full file.

Use ONLY the following allowed imports list. If something is missing, prefer equivalents from this list or keep existing working imports.
INSTRUCTIONS TO IMPORT AVAILABLE TOOLS:
{import_instructions}"""
)

# ===== Seed Task Templates =====

SEED_TASK_BASE = textwrap.dedent(
    """Reference scenario(s) (generate a new .py scenario file inspired by these, \
following the Scenario API, be sure to import the tools at the beginning of the file, \
following the INSTRUSTIONS TO IMPORT AVAILABLE TOOLS). Return only a single fenced python code \
block for the new scenario class."""
)

SEED_TASK_WITH_EXAMPLES_BASE = SEED_TASK_BASE + "\n\n{example_code_blocks}"

# ===== Helper Functions =====


def create_repair_note(issues: list[str], previous_code: str | None = None) -> str:
    """Create the repair note message for fixing import issues.

    Args:
        issues: List of import issues to fix
        previous_code: The previous code that had issues

    Returns:
        Formatted repair note message
    """
    return (
        "The previous attempt had import issues. Here are the problems to fix:\n"
        + "\n".join(f"- {s}" for s in issues)
        + "\nHere is the previous code to fix (do not change scenario behavior):\n```python\n"
        + (previous_code or "")
        + "\n```\nReturn a single fenced python code block containing the FULL corrected file."
    )


# ===== Final Formatted Prompts =====

DEFAULT_SCENARIO_GENERATOR_REPAIR_SYSTEM_PROMPT = REPAIR_SYSTEM_PROMPT_BASE

DEFAULT_SCENARIO_GENERATOR_REPAIR_SYSTEM_PROMPT_WITH_INSTRUCTIONS = REPAIR_SYSTEM_PROMPT_WITH_INSTRUCTIONS_BASE

DEFAULT_SCENARIO_GENERATOR_SEED_TASK = SEED_TASK_BASE
