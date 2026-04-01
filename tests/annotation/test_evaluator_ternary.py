"""Tests for ternary evaluator functions.

Tests evaluate_single_decision_ternary, aggregate_evaluations,
and evaluate_samples_ternary using LiteLLM mock engine.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import polars as pl
import pytest
from are.simulation.agents.llm.litellm.litellm_engine import LiteLLMEngine, LiteLLMModelConfig

from pare.annotation.evaluator import (
    aggregate_evaluations,
    evaluate_samples_ternary,
    evaluate_single_decision_ternary,
)

ACCEPT_RESPONSE = (
    "Thought: The proposal looks good.\n"
    "Action:\n"
    '{"action": "PAREAgentUserInterface__accept_proposal", '
    '"action_input": {"content": "Yes"}}'
)

REJECT_RESPONSE = (
    "Thought: I do not need this.\n"
    "Action:\n"
    '{"action": "PAREAgentUserInterface__reject_proposal", '
    '"action_input": {"content": "No thanks"}}'
)

GATHER_CONTEXT_RESPONSE = (
    "Thought: Let me check my calendar first.\n"
    "Action:\n"
    '{"action": "Calendar__list_events", '
    '"action_input": {}}'
)

UNPARSEABLE_RESPONSE = "I think I should accept this proposal."


def _make_engine(mock_response: str = ACCEPT_RESPONSE) -> LiteLLMEngine:
    """Create a LiteLLM mock engine with a custom response.

    Args:
        mock_response: The text the engine should return from chat_completion.

    Returns:
        LiteLLMEngine in mock mode with the specified response.
    """
    config = LiteLLMModelConfig(model_name="test-model", provider="mock")
    engine = LiteLLMEngine(config)
    engine.mock_response = mock_response
    return engine


def _make_messages() -> list[dict[str, str]]:
    """Return minimal llm_input messages for testing.

    Returns:
        List of message dicts with system and user roles.
    """
    return [
        {"role": "system", "content": "You are simulating a real human user"},
        {"role": "user", "content": "[TASK]: Agent proposes to help"},
    ]


class TestEvaluateSingleDecisionTernary:
    """Tests for evaluate_single_decision_ternary classification logic."""

    def test_accept_classification(self) -> None:
        """accept_proposal tool call returns ('accept', True)."""
        engine = _make_engine(ACCEPT_RESPONSE)
        decision, valid = evaluate_single_decision_ternary(_make_messages(), engine)
        assert decision == "accept"
        assert valid is True

    def test_reject_classification(self) -> None:
        """reject_proposal tool call returns ('reject', True)."""
        engine = _make_engine(REJECT_RESPONSE)
        decision, valid = evaluate_single_decision_ternary(_make_messages(), engine)
        assert decision == "reject"
        assert valid is True

    def test_gather_context_classification(self) -> None:
        """Non-accept/reject tool call returns ('gather_context', True)."""
        engine = _make_engine(GATHER_CONTEXT_RESPONSE)
        decision, valid = evaluate_single_decision_ternary(_make_messages(), engine)
        assert decision == "gather_context"
        assert valid is True

    def test_unparseable_returns_invalid(self) -> None:
        """Output without Action: token returns (None, False) after retries."""
        engine = _make_engine(UNPARSEABLE_RESPONSE)
        decision, valid = evaluate_single_decision_ternary(_make_messages(), engine)
        assert decision is None
        assert valid is False

    def test_no_retry_on_valid_tool_call(self) -> None:
        """Does not retry when a valid tool call is found."""
        engine = _make_engine(GATHER_CONTEXT_RESPONSE)
        with patch.object(engine, "chat_completion", wraps=engine.chat_completion) as wrapped:
            decision, valid = evaluate_single_decision_ternary(_make_messages(), engine)
            assert decision == "gather_context"
            assert valid is True
            assert wrapped.call_count == 1

    def test_retries_on_missing_action_token(self) -> None:
        """Retries when output lacks Action: token, succeeds when it appears."""
        engine = _make_engine(UNPARSEABLE_RESPONSE)
        call_count = 0

        original_chat = engine.chat_completion

        def side_effect(*args: object, **kwargs: object) -> tuple[str, None]:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return (UNPARSEABLE_RESPONSE, None)
            return (ACCEPT_RESPONSE, None)

        with patch.object(engine, "chat_completion", side_effect=side_effect):
            decision, valid = evaluate_single_decision_ternary(_make_messages(), engine)
            assert decision == "accept"
            assert valid is True
            assert call_count == 3

    def test_api_error_retries(self) -> None:
        """Retries on API errors, succeeds when call succeeds."""
        engine = _make_engine(REJECT_RESPONSE)
        call_count = 0

        def side_effect(*args: object, **kwargs: object) -> tuple[str, None]:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("API connection error")
            return (REJECT_RESPONSE, None)

        with patch.object(engine, "chat_completion", side_effect=side_effect):
            decision, valid = evaluate_single_decision_ternary(_make_messages(), engine)
            assert decision == "reject"
            assert valid is True
            assert call_count == 3

    def test_all_retries_exhausted(self) -> None:
        """Returns (None, False) when all retries fail with errors."""
        engine = _make_engine(ACCEPT_RESPONSE)
        with patch.object(engine, "chat_completion", side_effect=RuntimeError("Always fails")):
            decision, valid = evaluate_single_decision_ternary(_make_messages(), engine)
            assert decision is None
            assert valid is False


class TestAggregateEvaluations:
    """Tests for aggregate_evaluations soft labels and hard labels."""

    def _make_eval_df(self, rows: list[dict[str, object]]) -> pl.DataFrame:
        """Create an evaluation DataFrame from row dicts.

        Args:
            rows: List of dicts matching raw evaluation schema.

        Returns:
            Polars DataFrame.
        """
        return pl.DataFrame(rows)

    def test_unanimous_accept(self) -> None:
        """All valid runs are accept -> accept_prob=1.0, hard_label=accept."""
        rows = [
            {"sample_id": "s1", "scenario_id": "sc1", "proactive_model_id": "m1",
             "user_model_id": "u1", "user_agent_decision": "accept", "run": i, "valid_response": True}
            for i in range(1, 4)
        ]
        agg = aggregate_evaluations(self._make_eval_df(rows))
        assert len(agg) == 1
        row = agg.row(0, named=True)
        assert row["accept_count"] == 3
        assert row["reject_count"] == 0
        assert row["gather_context_count"] == 0
        assert row["accept_prob"] == pytest.approx(1.0)
        assert row["hard_label"] == "accept"

    def test_mixed_decisions(self) -> None:
        """Mixed decisions produce correct soft labels."""
        rows = [
            {"sample_id": "s1", "scenario_id": "sc1", "proactive_model_id": "m1",
             "user_model_id": "u1", "user_agent_decision": "accept", "run": 1, "valid_response": True},
            {"sample_id": "s1", "scenario_id": "sc1", "proactive_model_id": "m1",
             "user_model_id": "u1", "user_agent_decision": "reject", "run": 2, "valid_response": True},
            {"sample_id": "s1", "scenario_id": "sc1", "proactive_model_id": "m1",
             "user_model_id": "u1", "user_agent_decision": "gather_context", "run": 3, "valid_response": True},
        ]
        agg = aggregate_evaluations(self._make_eval_df(rows))
        row = agg.row(0, named=True)
        assert row["accept_prob"] == pytest.approx(1 / 3)
        assert row["reject_prob"] == pytest.approx(1 / 3)
        assert row["gather_context_prob"] == pytest.approx(1 / 3)

    def test_hard_label_is_argmax(self) -> None:
        """Hard label is the most frequent decision."""
        rows = [
            {"sample_id": "s1", "scenario_id": "sc1", "proactive_model_id": "m1",
             "user_model_id": "u1", "user_agent_decision": "reject", "run": 1, "valid_response": True},
            {"sample_id": "s1", "scenario_id": "sc1", "proactive_model_id": "m1",
             "user_model_id": "u1", "user_agent_decision": "reject", "run": 2, "valid_response": True},
            {"sample_id": "s1", "scenario_id": "sc1", "proactive_model_id": "m1",
             "user_model_id": "u1", "user_agent_decision": "accept", "run": 3, "valid_response": True},
        ]
        agg = aggregate_evaluations(self._make_eval_df(rows))
        assert agg["hard_label"][0] == "reject"

    def test_tie_breaking_is_deterministic(self) -> None:
        """Tied decisions use hash-based tie-breaking, same result every time."""
        rows = [
            {"sample_id": "s1", "scenario_id": "sc1", "proactive_model_id": "m1",
             "user_model_id": "u1", "user_agent_decision": "accept", "run": 1, "valid_response": True},
            {"sample_id": "s1", "scenario_id": "sc1", "proactive_model_id": "m1",
             "user_model_id": "u1", "user_agent_decision": "reject", "run": 2, "valid_response": True},
        ]
        df = self._make_eval_df(rows)
        agg1 = aggregate_evaluations(df)
        agg2 = aggregate_evaluations(df)
        assert agg1["hard_label"][0] == agg2["hard_label"][0]

    def test_invalid_responses_excluded(self) -> None:
        """Invalid responses are filtered out before aggregation."""
        rows = [
            {"sample_id": "s1", "scenario_id": "sc1", "proactive_model_id": "m1",
             "user_model_id": "u1", "user_agent_decision": "accept", "run": 1, "valid_response": True},
            {"sample_id": "s1", "scenario_id": "sc1", "proactive_model_id": "m1",
             "user_model_id": "u1", "user_agent_decision": None, "run": 2, "valid_response": False},
            {"sample_id": "s1", "scenario_id": "sc1", "proactive_model_id": "m1",
             "user_model_id": "u1", "user_agent_decision": "reject", "run": 3, "valid_response": True},
        ]
        agg = aggregate_evaluations(self._make_eval_df(rows))
        row = agg.row(0, named=True)
        assert row["valid_runs"] == 2
        assert row["accept_count"] == 1
        assert row["reject_count"] == 1

    def test_all_invalid_drops_pair(self) -> None:
        """Pair with all invalid responses is excluded from output."""
        rows = [
            {"sample_id": "s1", "scenario_id": "sc1", "proactive_model_id": "m1",
             "user_model_id": "u1", "user_agent_decision": None, "run": 1, "valid_response": False},
            {"sample_id": "s1", "scenario_id": "sc1", "proactive_model_id": "m1",
             "user_model_id": "u1", "user_agent_decision": None, "run": 2, "valid_response": False},
        ]
        agg = aggregate_evaluations(self._make_eval_df(rows))
        assert len(agg) == 0

    def test_multiple_sample_model_pairs(self) -> None:
        """Aggregates independently per (sample_id, user_model_id)."""
        rows = [
            {"sample_id": "s1", "scenario_id": "sc1", "proactive_model_id": "m1",
             "user_model_id": "u1", "user_agent_decision": "accept", "run": 1, "valid_response": True},
            {"sample_id": "s1", "scenario_id": "sc1", "proactive_model_id": "m1",
             "user_model_id": "u2", "user_agent_decision": "reject", "run": 1, "valid_response": True},
            {"sample_id": "s2", "scenario_id": "sc2", "proactive_model_id": "m1",
             "user_model_id": "u1", "user_agent_decision": "gather_context", "run": 1, "valid_response": True},
        ]
        agg = aggregate_evaluations(self._make_eval_df(rows))
        assert len(agg) == 3


class TestEvaluateSamplesTernary:
    """Tests for evaluate_samples_ternary end-to-end with mock engine."""

    def _make_samples_df(self, n_samples: int = 2) -> pl.DataFrame:
        """Create a minimal samples DataFrame with llm_input.

        Args:
            n_samples: Number of samples to create.

        Returns:
            DataFrame matching the ternary samples parquet schema.
        """
        messages = [{"role": "system", "content": "You are simulating a real human user"}]
        return pl.DataFrame({
            "sample_id": [f"s{i}" for i in range(n_samples)],
            "scenario_id": [f"sc{i}" for i in range(n_samples)],
            "proactive_model_id": ["m1"] * n_samples,
            "user_model_id": ["gpt-5-mini"] * n_samples,
            "user_agent_decision": ["accept"] * n_samples,
            "llm_input": [json.dumps(messages)] * n_samples,
            "agent_proposal": [f"proposal {i}" for i in range(n_samples)],
            "final_decision": [True] * n_samples,
            "meta_task_description": [f"task {i}" for i in range(n_samples)],
            "trace_file": [f"trace{i}.json" for i in range(n_samples)],
            "run_number": [1] * n_samples,
            "gather_context_delta": [None] * n_samples,
        })

    def test_returns_correct_schema(self) -> None:
        """Output DataFrame has expected columns."""
        samples_df = self._make_samples_df()
        models_map = {"test-model": {"model_name": "test-model", "provider": "mock"}}

        eval_df = evaluate_samples_ternary(
            samples_df=samples_df,
            user_models=["test-model"],
            models_map=models_map,
            runs=1,
        )
        expected_cols = {"sample_id", "scenario_id", "proactive_model_id",
                         "user_model_id", "user_agent_decision", "run", "valid_response"}
        assert set(eval_df.columns) == expected_cols

    def test_correct_number_of_results(self) -> None:
        """Produces samples * models * runs result rows."""
        samples_df = self._make_samples_df()
        models_map = {"test-model": {"model_name": "test-model", "provider": "mock"}}

        eval_df = evaluate_samples_ternary(
            samples_df=samples_df,
            user_models=["test-model"],
            models_map=models_map,
            runs=3,
        )
        # 2 samples * 1 model * 3 runs = 6
        assert len(eval_df) == 6

    def test_all_responses_valid_with_mock(self) -> None:
        """Mock engine always produces valid responses."""
        samples_df = self._make_samples_df()
        models_map = {"test-model": {"model_name": "test-model", "provider": "mock"}}

        eval_df = evaluate_samples_ternary(
            samples_df=samples_df,
            user_models=["test-model"],
            models_map=models_map,
            runs=2,
        )
        assert eval_df["valid_response"].all()

    def test_smoke_test_limits_samples(self) -> None:
        """Smoke test mode limits to 10 samples."""
        samples_df = self._make_samples_df(n_samples=20)
        models_map = {"test-model": {"model_name": "test-model", "provider": "mock"}}

        eval_df = evaluate_samples_ternary(
            samples_df=samples_df,
            user_models=["test-model"],
            models_map=models_map,
            runs=1,
            smoke_test=True,
        )
        # 10 samples * 1 model * 1 run = 10
        assert len(eval_df) == 10

    def test_multiple_user_models(self) -> None:
        """Evaluates with multiple user models."""
        samples_df = self._make_samples_df(n_samples=2)
        models_map = {
            "model-a": {"model_name": "model-a", "provider": "mock"},
            "model-b": {"model_name": "model-b", "provider": "mock"},
        }

        eval_df = evaluate_samples_ternary(
            samples_df=samples_df,
            user_models=["model-a", "model-b"],
            models_map=models_map,
            runs=2,
        )
        # 2 samples * 2 models * 2 runs = 8
        assert len(eval_df) == 8
        assert set(eval_df["user_model_id"].unique().to_list()) == {"model-a", "model-b"}
