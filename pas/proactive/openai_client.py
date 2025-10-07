"""Thin OpenAI client wrapper targeting `gpt-5-mini`."""

from __future__ import annotations

from typing import Any, Protocol

from pas.proactive.agent import LLMClientProtocol


class _ResponsePayload(Protocol):
    output_text: str


class _ResponsesClient(Protocol):
    def create(self, *, model: str, **kwargs: object) -> _ResponsePayload:  # pragma: no cover - protocol
        """Create a completion using the OpenAI Responses API."""


class OpenAIClientProtocol(Protocol):
    responses: _ResponsesClient


class OpenAILLMClient(LLMClientProtocol):
    """LLM client that calls OpenAI's Responses API."""

    def __init__(self, *, client: OpenAIClientProtocol, default_parameters: dict[str, Any] | None) -> None:
        """Store the underlying OpenAI client and default request parameters."""
        self._model = "gpt-5-mini"
        self._client = client
        base_parameters: dict[str, Any] = {}
        if default_parameters:
            base_parameters.update(default_parameters)
        self._default_parameters = base_parameters

    def complete(self, prompt: str) -> str:
        """Return text content from the Responses API for the supplied prompt."""
        response = self._client.responses.create(model=self._model, input=prompt, **self._default_parameters)
        return str(response.output_text)


__all__ = ["OpenAILLMClient"]
