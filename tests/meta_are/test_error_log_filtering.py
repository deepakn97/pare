"""Tests for ErrorLog.get_content_for_llm filtering by error category.

ServerError category errors (infrastructure failures like RateLimitError,
APIConnectionError) should be excluded from the LLM's prompt history.
Agent errors (tool misuse, format errors) should remain visible to the LLM.
"""

import time

from are.simulation.agents.agent_log import ErrorLog


class TestErrorLogContentForLlm:
    def test_server_error_excluded_from_llm(self):
        """ServerError category should not be included in LLM prompt history."""
        log = ErrorLog(
            error="RateLimitError",
            exception="litellm.RateLimitError: rate limit exceeded",
            category="ServerError",
            agent="test_agent",
            timestamp=time.time(),
            agent_id="test_agent_id",
        )
        assert log.get_content_for_llm() is None

    def test_agent_error_included_in_llm(self):
        """AgentError category should be included in LLM prompt history."""
        log = ErrorLog(
            error="InvalidActionAgentError",
            exception="Tool not found: bad_tool",
            category="AgentError",
            agent="test_agent",
            timestamp=time.time(),
            agent_id="test_agent_id",
        )
        content = log.get_content_for_llm()
        assert content is not None
        assert "InvalidActionAgentError" in content

    def test_format_error_included_in_llm(self):
        """FormatError category should be included in LLM prompt history."""
        log = ErrorLog(
            error="FormatError",
            exception="Missing Thought: token",
            category="FormatError",
            agent="test_agent",
            timestamp=time.time(),
            agent_id="test_agent_id",
        )
        assert log.get_content_for_llm() is not None

    def test_unhandled_error_included_in_llm(self):
        """UnhandledError category should be included in LLM prompt history."""
        log = ErrorLog(
            error="SomeUnexpectedError",
            exception="unexpected",
            category="UnhandledError",
            agent="test_agent",
            timestamp=time.time(),
            agent_id="test_agent_id",
        )
        assert log.get_content_for_llm() is not None

    def test_error_log_type_is_error(self):
        """ErrorLog.get_type() should return 'error' regardless of category."""
        log = ErrorLog(
            error="ServerError",
            exception="test",
            category="ServerError",
            agent="test_agent",
            timestamp=time.time(),
            agent_id="test_agent_id",
        )
        assert log.get_type() == "error"
