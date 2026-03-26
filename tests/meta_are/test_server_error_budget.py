"""Tests for BaseAgent consecutive server error budget.

The agent loop should track consecutive ServerErrors and exit after
MAX_CONSECUTIVE_SERVER_ERRORS is reached. Counter resets on successful steps.

Tests exercise the real BaseAgent flow: LLM engine raises ServerError ->
propagates through step() -> caught by execute_agent_loop().
"""

from typing import Any

from are.simulation.agents.agent_log import ErrorLog
from are.simulation.agents.default_agent.base_agent import BaseAgent
from are.simulation.agents.default_agent.tools.json_action_executor import (
    JsonActionExecutor,
)
from are.simulation.agents.llm.llm_engine import LLMEngine
from are.simulation.exceptions import ServerError
from are.simulation.time_manager import TimeManager

# Valid LLM output that the BaseAgent can parse and execute to terminate
FINAL_ANSWER_OUTPUT = 'Thought: Done.\nAction:\n{"action": "final_answer", "action_input": "done"}<end_action>'


class FailThenSucceedLLMEngine(LLMEngine):
    """LLM engine that raises ServerError for a configurable number of calls, then returns valid output."""

    def __init__(self, fail_count: int):
        super().__init__("fail-then-succeed-engine")
        self.call_count = 0
        self.fail_count = fail_count

    def chat_completion(
        self,
        messages: list[dict[str, Any]],
        stop_sequences: list[str] = [],
        **kwargs: Any,
    ) -> tuple[str, dict | None]:
        self.call_count += 1
        if self.call_count <= self.fail_count:
            raise ServerError(f"Server error on call {self.call_count}")
        return FINAL_ANSWER_OUTPUT, None


def _make_agent(fail_count: int, max_iterations: int = 10, max_consecutive: int = 3):
    """Create a BaseAgent with a FailThenSucceedLLMEngine."""
    engine = FailThenSucceedLLMEngine(fail_count=fail_count)
    action_executor = JsonActionExecutor(tools={})
    agent = BaseAgent(
        llm_engine=engine,
        system_prompts={"system_prompt": "You are a test agent."},
        tools={},
        action_executor=action_executor,
        max_iterations=max_iterations,
        total_iterations=max_iterations * 2,
        time_manager=TimeManager(),
        use_custom_logger=False,
    )
    agent.MAX_CONSECUTIVE_SERVER_ERRORS = max_consecutive
    return agent, engine


class TestServerErrorBudget:
    def test_exits_after_consecutive_server_errors(self):
        """Agent loop should exit after MAX_CONSECUTIVE_SERVER_ERRORS consecutive ServerErrors."""
        agent, engine = _make_agent(fail_count=100, max_iterations=20, max_consecutive=3)

        agent.run(task="test task")

        # Should have exactly 3 LLM calls (one per server error before budget exhausted)
        assert engine.call_count == 3

        error_logs = [
            log for log in agent.logs
            if isinstance(log, ErrorLog) and log.category == "ServerError"
        ]
        assert len(error_logs) == 3

    def test_resets_counter_on_success(self):
        """Counter should reset after a successful step."""
        # First 2 calls fail, 3rd succeeds (returns final_answer)
        agent, engine = _make_agent(fail_count=2, max_iterations=10, max_consecutive=3)

        agent.run(task="test task")

        # Should have made it past the 2 failures
        assert engine.call_count > 2

        error_logs = [
            log for log in agent.logs
            if isinstance(log, ErrorLog) and log.category == "ServerError"
        ]
        assert len(error_logs) == 2

    def test_budget_of_one(self):
        """With budget of 1, should exit on first ServerError."""
        agent, engine = _make_agent(fail_count=100, max_iterations=10, max_consecutive=1)

        agent.run(task="test task")

        assert engine.call_count == 1

    def test_server_error_does_not_set_failed_state(self):
        """ServerError budget exhaustion should not set FAILED state (unlike FatalError)."""
        agent, engine = _make_agent(fail_count=100, max_iterations=10, max_consecutive=2)

        agent.run(task="test task")

        from are.simulation.agents.default_agent.base_agent import RunningState
        assert agent.custom_state.get("running_state") != RunningState.FAILED

    def test_server_error_not_in_llm_history(self):
        """ServerError should not appear in the LLM prompt history (combined with Task 1 fix)."""
        # 2 failures then success
        agent, engine = _make_agent(fail_count=2, max_iterations=10, max_consecutive=3)

        agent.run(task="test task")

        error_logs = [
            log for log in agent.logs
            if isinstance(log, ErrorLog) and log.category == "ServerError"
        ]
        for log in error_logs:
            assert log.get_content_for_llm() is None
