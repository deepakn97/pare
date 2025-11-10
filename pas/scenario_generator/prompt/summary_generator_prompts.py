import textwrap

from .system_prompt import SYSTEM_PROMPT_TEMPLATE

# ===== Summary Generator Prompt Templates =====

SUMMARY_GENERATOR_SYSTEM_PROMPT_TEMPLATE = textwrap.dedent(
    """You are an expert assistant specialized in analyzing and summarizing scenario code.

    Your task is to read a scenario Python file and generate a concise, informative summary that captures:
    1. The primary objective/goal of the scenario
    2. The applications and tools used
    3. The key workflow and interaction patterns
    4. The proactive interaction pattern (if present)
    5. The validation criteria

    The summary should be clear, concise, and useful for understanding what the scenario does without reading the full code.
    """
)

SUMMARY_GENERATOR_AGENT_HINTS = textwrap.dedent(
    """
    SUMMARY GENERATION GUIDELINES:

    When analyzing a scenario file, focus on:
    - The scenario's main purpose and objective
    - Which applications are initialized and used (e.g., EmailClientApp, CalendarApp, ContactsApp)
    - The sequence of events and interactions
    - Any proactive interaction patterns (agent proposes action, user responds, agent executes)
    - What the validation method checks for

    The summary should be:
    - 2-4 sentences long
    - Written in clear, natural language
    - Focused on the scenario's behavior and purpose, not implementation details
    - Include key identifiers like app names, event types, and validation criteria

    Return only the summary text, without any additional formatting or explanation.
    """
)

SUMMARY_GENERATOR_ENVIRONMENT_INSTRUCTIONS = textwrap.dedent(
    """You are analyzing scenario code files to generate summaries.

    TASK:
    Analyze the provided scenario Python code and generate a concise summary that describes:
    - What the scenario does (primary objective)
    - Which applications it uses
    - The main workflow and interaction patterns
    - Key validation criteria

    Return a clear, concise summary (2-4 sentences) that captures the essence of the scenario.
    """
)

DEFAULT_SUMMARY_GENERATOR_SYSTEM_PROMPT = SYSTEM_PROMPT_TEMPLATE.format(
    general_instructions=SUMMARY_GENERATOR_SYSTEM_PROMPT_TEMPLATE,
    agent_instructions=SUMMARY_GENERATOR_AGENT_HINTS,
    environment_instructions=SUMMARY_GENERATOR_ENVIRONMENT_INSTRUCTIONS,
)

SUMMARY_TASK_TEMPLATE = textwrap.dedent(
    """Analyze the following scenario code and generate a concise summary (2-4 sentences) that describes:
    - The primary objective/goal of the scenario
    - The applications used
    - The main workflow and interaction patterns
    - Key validation criteria

    Scenario code:
    ```python
    {scenario_code}
    ```

    Return only the summary text, without any additional formatting, code blocks, or explanations.
    """
)
