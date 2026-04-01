from __future__ import annotations

import textwrap

SYSTEM_PROMPT_TEMPLATE = textwrap.dedent(
    """<general_instructions>
{general_instructions}
</general_instructions>

<agent_instructions>
{agent_instructions}
</agent_instructions>

<environment_instructions>
{environment_instructions}
</environment_instructions>"""
)
