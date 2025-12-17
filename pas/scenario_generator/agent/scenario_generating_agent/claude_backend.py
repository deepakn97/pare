from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookContext,
    HookMatcher,
    TextBlock,
)


@dataclass
class ClaudeFilesystemConfig:
    """Configuration for which paths the Claude Agent may read or edit.

    NOTE: This is currently a declarative configuration only. Enforcement will
    be wired into Claude Agent SDK hooks and tool options in a follow-up
    change.
    """

    read_only_roots: list[Path]
    editable_files: list[Path]


@dataclass
class ClaudeAgentRuntimeConfig:
    """Runtime configuration for using Claude Code as the step agent backend."""

    cwd: Path
    allowed_tools: list[str]
    permission_mode: str = "acceptEdits"
    filesystem: ClaudeFilesystemConfig | None = None


async def _async_run_claude(  # noqa: C901
    *,
    prompt: str,
    system_prompt: str | None,
    config: ClaudeAgentRuntimeConfig,
    step_tag: str,
    iteration: int,
) -> str:
    """Execute a single Claude Code call and return concatenated text blocks."""
    hooks: dict[str, list[HookMatcher]] | None = None
    if config.filesystem is not None:
        filesystem = config.filesystem
        cwd = config.cwd

        async def filesystem_guard(
            input_data: dict[str, Any],
            tool_use_id: str | None,
            context: HookContext,
        ) -> dict[str, Any]:
            """PreToolUse hook that enforces write restrictions based on filesystem config."""
            tool_name = input_data.get("tool_name")
            if tool_name != "Write":
                return {}
            tool_input = input_data.get("tool_input") or {}
            file_path = tool_input.get("file_path")
            if not file_path:
                return {}

            target = Path(str(file_path))
            if not target.is_absolute():
                target = (cwd / target).resolve()

            editable_set = {p.resolve() for p in filesystem.editable_files}
            if target not in editable_set:
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": (
                            f"Write to '{target}' is not permitted. "
                            f"Editable files are limited to: {', '.join(str(p) for p in sorted(editable_set))}"
                        ),
                    }
                }

            return {}

        hooks = {
            "PreToolUse": [
                HookMatcher(hooks=[filesystem_guard]),  # type: ignore[list-item]
            ]
        }

    options_kwargs: dict[str, Any] = {
        "system_prompt": system_prompt,
        "permission_mode": config.permission_mode,
        "cwd": str(config.cwd),
        "allowed_tools": config.allowed_tools,
    }
    if hooks is not None:
        options_kwargs["hooks"] = hooks

    options = ClaudeAgentOptions(**options_kwargs)

    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt, session_id=f"{step_tag}-{iteration}")
        text_chunks: list[str] = []

        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        text_chunks.append(block.text)

        return "".join(text_chunks).strip()

    # Fallback to satisfy static analyzers; normal execution should always
    # return from inside the context block above.
    return ""


def _conversation_to_prompt(
    conversation: list[dict[str, str]],
    *,
    step_tag: str,
    iteration: int,
) -> str:
    """Render a role-based conversation into a single textual prompt.

    The Claude Agent SDK already accepts a separate `system_prompt` via
    `ClaudeAgentOptions`, so this helper intentionally omits system-role
    messages and only inlines user/assistant turns built from the
    user-facing prompt templates in `prompts.py`.
    """
    parts: list[str] = [f"[STEP] {step_tag} | iteration {iteration}"]
    for message in conversation:
        role = message.get("role", "user").upper()
        if role == "SYSTEM":
            continue
        content = message.get("content", "")
        parts.append(f"{role}:\n{content}")
    return "\n\n".join(parts)


def run_claude_conversation(
    conversation: list[dict[str, str]],
    *,
    system_prompt: str | None,
    config: ClaudeAgentRuntimeConfig,
    step_tag: str,
    iteration: int,
) -> str:
    """Synchronous wrapper to run Claude Code for a given step conversation."""
    prompt = _conversation_to_prompt(conversation, step_tag=step_tag, iteration=iteration)
    return asyncio.run(
        _async_run_claude(
            prompt=prompt,
            system_prompt=system_prompt,
            config=config,
            step_tag=step_tag,
            iteration=iteration,
        )
    )
