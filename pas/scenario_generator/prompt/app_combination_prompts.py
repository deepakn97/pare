import textwrap

from are.simulation.scenarios.scenario import Scenario
from are.simulation.tool_box import Tool

# ===== App Combination Selection Prompts =====

APP_COMBINATION_SYSTEM_PROMPT = textwrap.dedent(
    """You are an expert at selecting app combinations for AI agent scenario generation.
Your task is to suggest meaningful combinations of apps that can work together to create interesting and realistic scenarios.

You must generate a COMPLETE set of distinct app combinations that will be used for multiple scenario generations.
Each combination should be carefully crafted to create diverse, engaging, and realistic scenarios.

CRITICAL REQUIREMENTS:
1. Generate EXACTLY the requested number of combinations
2. Each combination must be UNIQUE and DISTINCT from all others
3. Each combination should contain EXACTLY the specified number of apps
4. All combinations must use ONLY apps from the available apps list
5. Consider app compatibility and natural interactions
6. Create diverse scenarios that cover different use cases and workflows
7. Ensure good distribution across app categories and interaction patterns

Your response must be a valid JSON array of app combinations.
Example format: [["EmailClientApp", "CalendarApp", "ContactsApp"], ["MessagingApp", "Files", "SystemApp"]]

Return ONLY the JSON array, no additional text or explanation."""
)

APP_COMBINATION_USER_PROMPT_TEMPLATE = textwrap.dedent(
    """Generate {total_scenarios} distinct app combinations for scenario generation.

REQUIREMENTS:
- Total combinations needed: {total_scenarios}
- Apps per combination: {apps_per_scenario}
- Available apps: {available_apps}

APP TOOLS SUMMARY:
{app_tools_summary}

EXAMPLE SCENARIOS CONTEXT:
{example_context}

GUIDELINES FOR COMBINATION SELECTION:
1. DIVERSITY: Ensure combinations cover different app categories and use cases
2. COMPATIBILITY: Select apps that naturally work together in real-world scenarios
3. UNIQUENESS: Each combination must be completely different from others
4. REALISM: Choose combinations that represent realistic user workflows
5. BALANCE: Distribute apps across combinations to avoid overuse of popular apps

SCENARIO TYPES TO CONSIDER:
- Communication & Organization (Email + Calendar + Contacts)
- File Management & Collaboration (Files + Messaging + System)
- Lifestyle & Services (Shopping + Cab + Apartment)
- Productivity & Planning (Calendar + Reminder + Files)
- Social & Communication (Messaging + Contacts + Calendar)
- Business & Organization (Email + Calendar + Contacts + Files)
- Personal & Lifestyle (Shopping + Apartment + Cab + City)

Return a JSON object with two fields:
1. "combinations": An array with exactly {total_scenarios} combinations, each containing exactly {apps_per_scenario} apps
2. "summaries": An array with exactly {total_scenarios} one-sentence summaries describing what each scenario will look like, including which tools will be used and what the final event stream will accomplish

Example format:
{{
  "combinations": [
    ["EmailClientApp", "CalendarApp", "ContactsApp", "ReminderApp"],
    ["MessagingApp", "Files", "SystemApp", "ContactsApp"]
  ],
  "summaries": [
    "A proactive email management scenario that uses email tools to organize incoming messages, calendar tools to schedule follow-up meetings, contacts tools to update contact information, and reminder tools to set follow-up tasks, resulting in an organized inbox with scheduled meetings and updated contacts.",
    "A file sharing and collaboration scenario that uses messaging tools to send file links, file system tools to organize shared documents, system tools to manage notifications, and contacts tools to coordinate with team members, resulting in a streamlined document sharing workflow."
  ]
}}"""
)

# ===== Helper Functions =====


def build_app_tools_summary(app_tools_info: dict[str, list[Tool]]) -> str:
    """Build a summary of available apps and their tools.

    Args:
        app_tools_info: Dictionary mapping app names to their tools

    Returns:
        Formatted text describing available apps and tools
    """
    if not app_tools_info:
        return "No app tools information available."

    summary_parts = ["Available apps and their tools:"]

    for app_name, tools in app_tools_info.items():
        summary_parts.append(f"\n{app_name}:")
        if tools:
            for tool in tools:
                summary_parts.append(f"  - {tool.name}: {tool.description}")
        else:
            summary_parts.append("  - No tools available")

    return "\n".join(summary_parts)


def build_example_context_text(example_scenarios: list[Scenario]) -> str:
    """Build text describing example scenarios context.

    Args:
        example_scenarios: List of example scenarios

    Returns:
        Formatted example context text
    """
    if not example_scenarios:
        return "No example scenarios provided"

    context_parts = [f"Example scenarios available: {len(example_scenarios)}"]

    # Extract app usage patterns from example scenarios
    app_usage: dict[str, int] = {}
    for scenario in example_scenarios:
        if hasattr(scenario, "apps") and scenario.apps:
            for app in scenario.apps:
                app_name = app.__class__.__name__
                app_usage[app_name] = app_usage.get(app_name, 0) + 1

    if app_usage:
        context_parts.append("App usage in examples:")
        for app, count in sorted(app_usage.items()):
            context_parts.append(f"  {app}: used in {count} example(s)")

    return "\n".join(context_parts)


def create_app_combination_prompt(
    total_scenarios: int,
    apps_per_scenario: int,
    available_apps: list[str],
    app_tools_info: dict[str, list[Tool]],
    example_scenarios: list[Scenario] | None = None,
) -> tuple[str, str]:
    """Create the complete prompt for app combination generation.

    Args:
        total_scenarios: Total number of combinations to generate
        apps_per_scenario: Number of apps per combination
        available_apps: List of available app names
        app_tools_info: Dictionary mapping app names to their tools
        example_scenarios: Optional example scenarios for context

    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    system_prompt = APP_COMBINATION_SYSTEM_PROMPT

    # Build app tools summary for the prompt
    app_tools_summary = build_app_tools_summary(app_tools_info)

    user_prompt = APP_COMBINATION_USER_PROMPT_TEMPLATE.format(
        total_scenarios=total_scenarios,
        apps_per_scenario=apps_per_scenario,
        available_apps=available_apps,
        app_tools_summary=app_tools_summary,
        used_combinations="No previously used combinations (generating all at once)",
        example_context=build_example_context_text(example_scenarios or []),
    )

    return system_prompt, user_prompt
