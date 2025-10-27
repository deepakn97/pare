"""LiteLLM-backed LLM client used by PAS."""

from __future__ import annotations

import logging
from typing import Any

import litellm
import litellm.types.utils

from pas.proactive.agent import LLMClientProtocol

LOGGER = logging.getLogger(__name__)


class LiteLLMClient(LLMClientProtocol):
    """LLM client that relies on LiteLLM for provider routing."""

    def __init__(
        self, *, model: str = "gpt-5-mini", api_base: str | None = None, request_kwargs: dict[str, object] | None = None
    ) -> None:
        """Initialise the LiteLLM client with model routing details."""
        self._model = model
        self._api_base = api_base
        self._request_kwargs = dict(request_kwargs or {})

        cost_info = litellm.model_cost.get(model, {})
        self._max_input_tokens = cost_info.get("max_input_tokens")
        self._max_output_tokens = cost_info.get("max_output_tokens")
        self._provider = cost_info.get("litellm_provider")

        if self._provider is None and api_base is not None:
            LOGGER.warning(
                "Model %s is not in LiteLLM registry; context and cost checks "
                "may be inaccurate when using api_base=%s.",
                model,
                api_base,
            )

    def complete(self, prompt: str) -> str:
        """Return the text completion for the supplied prompt."""
        message, _ = self.complete_with_metadata(prompt)
        return message

    def complete_with_metadata(self, prompt: str, *, temperature: float | None = None) -> tuple[str, dict[str, object]]:
        """Return both the completion text and token-cost metadata."""
        messages = [{"role": "user", "content": prompt}]
        input_tokens = litellm.utils.token_counter(messages=messages, model=self._model)

        if self._max_input_tokens is not None and input_tokens > self._max_input_tokens:
            raise RuntimeError(
                f"Input tokens {input_tokens} exceed max tokens {self._max_input_tokens} for model {self._model}."
            )

        completion_args: dict[str, Any] = dict(self._request_kwargs)
        if temperature is not None:
            completion_args["temperature"] = temperature
        if self._api_base is not None:
            completion_args["api_base"] = self._api_base
        if self._provider == "anthropic" and self._max_output_tokens is not None:
            completion_args.setdefault("max_tokens", self._max_output_tokens)

        response: litellm.types.utils.ModelResponse = litellm.completion(
            model=self._model, messages=messages, **completion_args
        )

        choices: litellm.types.utils.Choices = response.choices  # type: ignore[assignment]
        if not choices:
            raise RuntimeError("LiteLLM returned no choices.")

        raw_content = getattr(choices[0].message, "content", "")
        content = raw_content if isinstance(raw_content, str) else str(raw_content or "")
        cost = litellm.cost_calculator.completion_cost(response)
        output_tokens = litellm.utils.token_counter(text=content, model=self._model)

        metadata: dict[str, object] = {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "cost": cost,
        }
        return content, metadata


def build_llm_client(
    *, model_name: str = "gpt-5-mini", api_base: str | None = None, request_kwargs: dict[str, object] | None = None
) -> LiteLLMClient:
    """Return a LiteLLM-backed client matching the documentation examples."""
    return LiteLLMClient(model=model_name, api_base=api_base, request_kwargs=request_kwargs)


__all__ = ["LiteLLMClient", "build_llm_client"]
