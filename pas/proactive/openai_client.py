"""Thin OpenAI client wrapper targeting `gpt-5-mini`."""

from __future__ import annotations

from typing import Any, Protocol, cast

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

    def __init__(
        self,
        *,
        client: OpenAIClientProtocol | None = None,
        request_parameters: dict[str, Any] | None = None,
        model: str = "gpt-5-mini",
    ) -> None:
        """Optionally accept a preconfigured OpenAI client and request defaults."""
        if client is None:
            from openai import OpenAI  # local import to avoid mandatory dependency at import time

            client = cast("OpenAIClientProtocol", OpenAI())

        self._model = model
        self._client: OpenAIClientProtocol = client
        self._request_parameters = dict(request_parameters or {})

    def complete(self, prompt: str) -> str:
        """Return text content from the Responses API for the supplied prompt."""
        response = self._client.responses.create(model=self._model, input=prompt, **self._request_parameters)
        return str(response.output_text)


__all__ = ["OpenAILLMClient"]
