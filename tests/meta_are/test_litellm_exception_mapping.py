"""Tests for LiteLLMEngine exception mapping to Meta-ARE error hierarchy.

Verifies that litellm exceptions are correctly mapped to:
- FatalError: unrecoverable errors (auth, permission, bad request)
- ServerError: transient/retryable errors (rate limit, connection, server)
- PromptTooLongException: context window exceeded
"""

from unittest.mock import patch

import httpx
import litellm
from litellm.exceptions import (
    ContentPolicyViolationError,
    ContextWindowExceededError,
    NotFoundError,
    PermissionDeniedError,
)

from are.simulation.agents.llm.exceptions import PromptTooLongException
from are.simulation.agents.llm.litellm.litellm_engine import (
    LiteLLMEngine,
    LiteLLMModelConfig,
)
from are.simulation.exceptions import FatalError, ServerError

MOCK_RESPONSE = httpx.Response(
    status_code=400,
    request=httpx.Request("GET", "https://test.com"),
)


def _make_engine():
    config = LiteLLMModelConfig(model_name="test-model", provider="mock")
    engine = LiteLLMEngine(config)
    engine.mock_response = None  # disable mock mode so completion() is called
    return engine


def _make_messages():
    return [{"role": "user", "content": "test"}]


class TestRetryableErrorsMappedToServerError:
    """Transient errors should be mapped to ServerError."""

    @patch("are.simulation.agents.llm.litellm.litellm_engine.completion")
    def test_rate_limit_error(self, mock_completion):
        mock_completion.side_effect = litellm.RateLimitError(
            message="rate limit exceeded",
            model="test-model",
            llm_provider="openai",
        )
        try:
            _make_engine().chat_completion(_make_messages())
            assert False, "Should have raised"
        except ServerError as e:
            assert "RateLimitError" in str(e)
            assert e.__cause__ is mock_completion.side_effect

    @patch("are.simulation.agents.llm.litellm.litellm_engine.completion")
    def test_internal_server_error(self, mock_completion):
        mock_completion.side_effect = litellm.InternalServerError(
            message="internal server error",
            model="test-model",
            llm_provider="openai",
        )
        try:
            _make_engine().chat_completion(_make_messages())
            assert False, "Should have raised"
        except ServerError:
            pass

    @patch("are.simulation.agents.llm.litellm.litellm_engine.completion")
    def test_service_unavailable(self, mock_completion):
        mock_completion.side_effect = litellm.ServiceUnavailableError(
            message="service unavailable",
            model="test-model",
            llm_provider="openai",
        )
        try:
            _make_engine().chat_completion(_make_messages())
            assert False, "Should have raised"
        except ServerError:
            pass

    @patch("are.simulation.agents.llm.litellm.litellm_engine.completion")
    def test_api_connection_error(self, mock_completion):
        mock_completion.side_effect = litellm.APIConnectionError(
            message="connection failed",
            model="test-model",
            llm_provider="openai",
        )
        try:
            _make_engine().chat_completion(_make_messages())
            assert False, "Should have raised"
        except ServerError:
            pass

    @patch("are.simulation.agents.llm.litellm.litellm_engine.completion")
    def test_timeout(self, mock_completion):
        mock_completion.side_effect = litellm.Timeout(
            message="request timed out",
            model="test-model",
            llm_provider="openai",
        )
        try:
            _make_engine().chat_completion(_make_messages())
            assert False, "Should have raised"
        except ServerError:
            pass

    @patch("are.simulation.agents.llm.litellm.litellm_engine.completion")
    def test_generic_api_error(self, mock_completion):
        mock_completion.side_effect = litellm.APIError(
            message="generic api error",
            model="test-model",
            llm_provider="openai",
            status_code=500,
        )
        try:
            _make_engine().chat_completion(_make_messages())
            assert False, "Should have raised"
        except ServerError:
            pass


class TestNonRetryableErrorsMappedToFatalError:
    """Unrecoverable errors should be mapped to FatalError."""

    @patch("are.simulation.agents.llm.litellm.litellm_engine.completion")
    def test_authentication_error(self, mock_completion):
        mock_completion.side_effect = litellm.AuthenticationError(
            message="invalid api key",
            model="test-model",
            llm_provider="openai",
        )
        try:
            _make_engine().chat_completion(_make_messages())
            assert False, "Should have raised"
        except FatalError as e:
            assert "AuthenticationError" in str(e)

    @patch("are.simulation.agents.llm.litellm.litellm_engine.completion")
    def test_permission_denied(self, mock_completion):
        mock_completion.side_effect = PermissionDeniedError(
            message="permission denied",
            model="test-model",
            llm_provider="openai",
            response=MOCK_RESPONSE,
        )
        try:
            _make_engine().chat_completion(_make_messages())
            assert False, "Should have raised"
        except FatalError:
            pass

    @patch("are.simulation.agents.llm.litellm.litellm_engine.completion")
    def test_not_found(self, mock_completion):
        mock_completion.side_effect = NotFoundError(
            message="model not found",
            model="test-model",
            llm_provider="openai",
        )
        try:
            _make_engine().chat_completion(_make_messages())
            assert False, "Should have raised"
        except FatalError:
            pass

    @patch("are.simulation.agents.llm.litellm.litellm_engine.completion")
    def test_bad_request(self, mock_completion):
        mock_completion.side_effect = litellm.BadRequestError(
            message="bad request",
            model="test-model",
            llm_provider="openai",
        )
        try:
            _make_engine().chat_completion(_make_messages())
            assert False, "Should have raised"
        except FatalError:
            pass

    @patch("are.simulation.agents.llm.litellm.litellm_engine.completion")
    def test_content_policy_violation(self, mock_completion):
        mock_completion.side_effect = ContentPolicyViolationError(
            message="content policy violation",
            model="test-model",
            llm_provider="openai",
        )
        try:
            _make_engine().chat_completion(_make_messages())
            assert False, "Should have raised"
        except FatalError:
            pass


class TestContextWindowMappedToPromptTooLong:
    """Context window exceeded should map to PromptTooLongException."""

    @patch("are.simulation.agents.llm.litellm.litellm_engine.completion")
    def test_context_window_exceeded(self, mock_completion):
        mock_completion.side_effect = ContextWindowExceededError(
            message="context window exceeded",
            model="test-model",
            llm_provider="openai",
        )
        try:
            _make_engine().chat_completion(_make_messages())
            assert False, "Should have raised"
        except PromptTooLongException as e:
            assert "ContextWindowExceededError" in str(e)

    @patch("are.simulation.agents.llm.litellm.litellm_engine.completion")
    def test_context_window_not_caught_as_bad_request(self, mock_completion):
        """ContextWindowExceededError is a BadRequestError subclass but should NOT map to FatalError."""
        mock_completion.side_effect = ContextWindowExceededError(
            message="context window exceeded",
            model="test-model",
            llm_provider="openai",
        )
        try:
            _make_engine().chat_completion(_make_messages())
            assert False, "Should have raised"
        except FatalError:
            assert False, "ContextWindowExceededError should not be FatalError"
        except PromptTooLongException:
            pass  # correct


class TestExceptionChaining:
    """Original litellm exception should be preserved via __cause__."""

    @patch("are.simulation.agents.llm.litellm.litellm_engine.completion")
    def test_original_exception_chained_on_server_error(self, mock_completion):
        original = litellm.RateLimitError(
            message="rate limit",
            model="test-model",
            llm_provider="openai",
        )
        mock_completion.side_effect = original
        try:
            _make_engine().chat_completion(_make_messages())
            assert False, "Should have raised"
        except ServerError as e:
            assert e.__cause__ is original

    @patch("are.simulation.agents.llm.litellm.litellm_engine.completion")
    def test_original_exception_chained_on_fatal_error(self, mock_completion):
        original = litellm.AuthenticationError(
            message="bad key",
            model="test-model",
            llm_provider="openai",
        )
        mock_completion.side_effect = original
        try:
            _make_engine().chat_completion(_make_messages())
            assert False, "Should have raised"
        except FatalError as e:
            assert e.__cause__ is original
