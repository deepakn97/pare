"""Shared LLM adapter infrastructure for PAS components.

This module provides common LLM abstractions used across both proactive
and user_proxy modules, avoiding circular dependencies.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from are.simulation.agents.llm.llm_engine import LLMEngine


class LLMClientProtocol(Protocol):
    """Minimal protocol for LLM clients used throughout PAS."""

    def complete(self, prompt: str) -> str:
        """Return a string completion for the provided prompt."""


class PasLLMEngine(LLMEngine):
    """Adapter turning a PAS LLM client into Meta ARE's LLMEngine protocol."""

    def __init__(self, llm: LLMClientProtocol, logger: logging.Logger | None = None) -> None:
        """Store the PAS LLM client for subsequent chat completions."""
        super().__init__(model_name="pas-llm-client")
        self.llm_client = llm
        self.logger = logger or logging.getLogger(__name__)

    @staticmethod
    def _format_messages(messages: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for message in messages:
            role = message.get("role", "assistant").upper()
            content = message.get("content", "")
            parts.append(f"{role}: {content}")
        return "\n\n".join(parts)

    def chat_completion(
        self, messages: list[dict[str, Any]], stop_sequences: list[str] | None = None, **kwargs: Any
    ) -> tuple[str, dict[str, Any] | None]:
        """Format messages for the PAS client and relay the response."""
        prompt = self._format_messages(messages)
        stop_tokens: tuple[str, ...] = tuple(stop_sequences or ())

        response: str
        metadata: dict[str, Any]
        completion_with_metadata = getattr(self.llm_client, "complete_with_metadata", None)
        temperature = kwargs.get("temperature")
        if callable(completion_with_metadata):
            response, metadata = completion_with_metadata(prompt, temperature=temperature)
        else:
            response = self.llm_client.complete(prompt)
            metadata = {}

        if stop_tokens:
            response = self._truncate_at_stop(response, stop_tokens)

        self.logger.debug("Meta ARE bridge prompt:\n%s", prompt)
        self.logger.debug("Meta ARE bridge response: %s", response)
        return response, metadata or {}

    def simple_call(self, prompt: str) -> str:
        """Proxy simple prompts directly to the PAS client."""
        return self.llm_client.complete(prompt)

    @staticmethod
    def _truncate_at_stop(text: str, stop_tokens: tuple[str, ...]) -> str:
        """Return the substring of text before the earliest-occurring stop token."""
        earliest_index = len(text)
        for token in stop_tokens:
            idx = text.find(token)
            if idx != -1 and idx < earliest_index:
                earliest_index = idx
        return text[:earliest_index]


__all__ = ["LLMClientProtocol", "PasLLMEngine"]
