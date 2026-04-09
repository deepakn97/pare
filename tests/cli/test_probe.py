"""Tests for probe_llm_endpoint with endpoint support."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from are.simulation.agents.are_simulation_agent_config import LLMEngineConfig

from pare.cli.utils import LLMProbeError, probe_llm_endpoint


def test_probe_passes_endpoint_to_litellm() -> None:
    """Probe should pass api_base from engine_config.endpoint to litellm."""
    config = LLMEngineConfig(
        model_name="test-model",
        provider="hosted_vllm",
        endpoint="http://localhost:8001/v1",
    )

    with patch("pare.cli.utils.litellm.completion") as mock_completion:
        probe_llm_endpoint(config)

        mock_completion.assert_called_once()
        call_kwargs = mock_completion.call_args[1]
        assert call_kwargs["api_base"] == "http://localhost:8001/v1"
        assert call_kwargs["custom_llm_provider"] == "hosted_vllm"


def test_probe_passes_none_endpoint_for_api_models() -> None:
    """Probe should pass api_base=None for API models without endpoint."""
    config = LLMEngineConfig(
        model_name="gpt-5",
        provider="openai",
    )

    with patch("pare.cli.utils.litellm.completion") as mock_completion:
        probe_llm_endpoint(config)

        call_kwargs = mock_completion.call_args[1]
        assert call_kwargs["api_base"] is None


def test_probe_retries_on_connection_error() -> None:
    """Probe should retry on connection errors (vLLM still starting)."""
    from litellm.exceptions import APIConnectionError as LiteLLMAPIConnectionError

    config = LLMEngineConfig(
        model_name="test-model",
        provider="hosted_vllm",
        endpoint="http://localhost:8001/v1",
    )

    call_count = 0

    def mock_completion_fn(**kwargs: object) -> None:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise LiteLLMAPIConnectionError(
                message="Connection refused",
                model="test-model",
                llm_provider="hosted_vllm",
            )

    with (
        patch("pare.cli.utils.litellm.completion", side_effect=mock_completion_fn),
        patch("pare.cli.utils.time.sleep"),
    ):
        probe_llm_endpoint(config, timeout_seconds=120, poll_interval=5)

    assert call_count == 3


def test_probe_raises_on_timeout() -> None:
    """Probe should raise LLMProbeError after timeout."""
    from litellm.exceptions import APIConnectionError as LiteLLMAPIConnectionError

    config = LLMEngineConfig(
        model_name="test-model",
        provider="hosted_vllm",
        endpoint="http://localhost:8001/v1",
    )

    with (
        patch(
            "pare.cli.utils.litellm.completion",
            side_effect=LiteLLMAPIConnectionError(
                message="Connection refused",
                model="test-model",
                llm_provider="hosted_vllm",
            ),
        ),
        patch("pare.cli.utils.time.sleep"),
        patch("pare.cli.utils.time.monotonic", side_effect=[0, 0, 610]),
        pytest.raises(LLMProbeError, match="not ready after"),
    ):
        probe_llm_endpoint(config, timeout_seconds=600, poll_interval=30)
