"""Thin OpenAI client wrapper targeting chat completions-capable models."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:  # pragma: no cover - type hints only
    from openai.types.chat import ChatCompletion

from pas.proactive.agent import LLMClientProtocol


class _ChatCompletionsClient(Protocol):
    def create(self, *, model: str, **kwargs: object) -> ChatCompletion:  # pragma: no cover - protocol
        """Create a chat completion for the supplied messages."""


class _ChatClient(Protocol):
    completions: _ChatCompletionsClient


class OpenAIClientProtocol(Protocol):
    chat: _ChatClient  # pragma: no cover - attribute hook


class OpenAILLMClient(LLMClientProtocol):
    """LLM client that calls OpenAI's Chat Completions API."""

    def __init__(
        self,
        *,
        client: OpenAIClientProtocol | None = None,
        request_parameters: dict[str, object] | None = None,
        model: str = "gpt-5-mini",
    ) -> None:
        """Optionally accept a preconfigured OpenAI client and request defaults."""
        if client is None:
            from openai import OpenAI  # local import to avoid mandatory dependency at import time

            client = cast("OpenAIClientProtocol", OpenAI())

        self._model = model
        self._client: OpenAIClientProtocol = client
        self._chat_completions = client.chat.completions
        self._request_parameters = dict(request_parameters or {})

    def complete(self, prompt: str) -> str:
        """Return text content for the supplied prompt."""
        message, _ = self.complete_with_metadata(prompt)
        return message

    def complete_with_metadata(self, prompt: str, *, temperature: float | None = None) -> tuple[str, dict[str, object]]:
        """Return the assistant message together with token usage metadata."""
        kwargs: dict[str, object] = dict(self._request_parameters)
        if temperature is not None:
            kwargs["temperature"] = temperature

        response = self._chat_completions.create(
            model=self._model, messages=[{"role": "user", "content": prompt}], **kwargs
        )

        choice = response.choices[0] if response.choices else None
        content = ""
        if choice is not None:
            content = choice.message.content or ""

        usage = getattr(response, "usage", None)
        metadata: dict[str, object] = {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0),
            "completion_tokens": getattr(usage, "completion_tokens", 0),
            "total_tokens": getattr(usage, "total_tokens", 0),
            "completion_duration": getattr(response, "response_ms", 0) / 1000
            if hasattr(response, "response_ms")
            else 0,
        }
        return content, metadata


__all__ = ["OpenAILLMClient"]
