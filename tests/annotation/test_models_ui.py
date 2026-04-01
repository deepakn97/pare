"""Tests for annotation UI response models."""

from __future__ import annotations

import json

from pare.annotation.models import MessageType, Sample, SampleResponse, UIMessage


class TestUIMessage:
    """Tests for UIMessage model."""

    def test_create_user_action(self) -> None:
        """UIMessage with USER_ACTION type stores all fields correctly."""
        msg = UIMessage(msg_type=MessageType.USER_ACTION, content="open_app()", timestamp=101.0)
        assert msg.msg_type == MessageType.USER_ACTION
        assert msg.content == "open_app()"
        assert msg.timestamp == 101.0

    def test_create_without_timestamp(self) -> None:
        """UIMessage defaults timestamp to None when not provided."""
        msg = UIMessage(msg_type=MessageType.ENVIRONMENT_NOTIFICATION, content="New event")
        assert msg.timestamp is None

    def test_message_type_values(self) -> None:
        """MessageType enum values match expected msg_type strings."""
        assert MessageType.USER_ACTION.value == "user_action"
        assert MessageType.TOOL_OBSERVATION.value == "tool_observation"
        assert MessageType.PROPOSAL.value == "proposal"
        assert MessageType.ENVIRONMENT_NOTIFICATION.value == "environment_notification"


class TestSampleResponse:
    """Tests for SampleResponse model."""

    def test_create_sample_response(self) -> None:
        """SampleResponse stores messages and progress fields."""
        messages = [
            UIMessage(msg_type=MessageType.USER_ACTION, content="open_app()", timestamp=101.0),
            UIMessage(msg_type=MessageType.PROPOSAL, content="I propose X", timestamp=103.0),
        ]
        resp = SampleResponse(
            sample_id="test_id",
            scenario_context="User needs help",
            messages=messages,
            progress_completed=5,
            progress_total=20,
        )
        assert resp.sample_id == "test_id"
        assert len(resp.messages) == 2
        assert resp.progress_completed == 5

    def test_scenario_context_nullable(self) -> None:
        """SampleResponse accepts None for scenario_context."""
        resp = SampleResponse(
            sample_id="test_id",
            scenario_context=None,
            messages=[],
            progress_completed=0,
            progress_total=10,
        )
        assert resp.scenario_context is None


class TestToApiResponse:
    """Tests for Sample.to_api_response() with llm_input parsing."""

    def test_returns_sample_response(self, sample_with_llm_input: Sample) -> None:
        """to_api_response returns a SampleResponse instance."""
        result = sample_with_llm_input.to_api_response(5, 20)
        assert isinstance(result, SampleResponse)

    def test_filters_system_messages(self, sample_with_llm_input: Sample) -> None:
        """to_api_response strips system_prompt, available_tools, current_app_state, unknown."""
        result = sample_with_llm_input.to_api_response(5, 20)
        msg_types = [m.msg_type for m in result.messages]
        assert MessageType.USER_ACTION in msg_types
        assert MessageType.TOOL_OBSERVATION in msg_types
        assert MessageType.PROPOSAL in msg_types
        assert MessageType.ENVIRONMENT_NOTIFICATION in msg_types
        # These should be stripped:
        type_values = [m.msg_type.value for m in result.messages]
        assert "system_prompt" not in type_values
        assert "available_tools" not in type_values
        assert "current_app_state" not in type_values
        assert "unknown" not in type_values

    def test_message_count(self, sample_with_llm_input: Sample) -> None:
        """Exactly 4 of 8 fixture messages survive filtering."""
        result = sample_with_llm_input.to_api_response(5, 20)
        assert len(result.messages) == 4

    def test_preserves_timestamps(self, sample_with_llm_input: Sample) -> None:
        """Timestamps from llm_input are preserved on UIMessage."""
        result = sample_with_llm_input.to_api_response(5, 20)
        user_action = next(m for m in result.messages if m.msg_type == MessageType.USER_ACTION)
        assert user_action.timestamp == 101.0

    def test_preserves_content(self, sample_with_llm_input: Sample) -> None:
        """Proposal content is preserved from llm_input."""
        result = sample_with_llm_input.to_api_response(5, 20)
        proposal = next(m for m in result.messages if m.msg_type == MessageType.PROPOSAL)
        assert "I propose to update your note" in proposal.content

    def test_progress_fields(self, sample_with_llm_input: Sample) -> None:
        """Progress completed and total are passed through."""
        result = sample_with_llm_input.to_api_response(5, 20)
        assert result.progress_completed == 5
        assert result.progress_total == 20

    def test_scenario_context_from_meta_task(self, sample_with_llm_input: Sample) -> None:
        """Non-empty meta_task_description becomes scenario_context."""
        result = sample_with_llm_input.to_api_response(5, 20)
        assert result.scenario_context == "User needs to take notes"

    def test_empty_meta_task_gives_none(self) -> None:
        """Empty meta_task_description results in scenario_context=None."""
        sample = Sample(
            sample_id="test",
            scenario_id="test",
            run_number=1,
            proactive_model_id="gpt-4o",
            user_model_id="gpt-4o",
            trace_file="traces/no_noise_gpt-4o/scenario_a.json",
            user_agent_decision="accept",
            agent_proposal="proposal",
            meta_task_description="",
            llm_input=json.dumps([]),
            final_decision=True,
        )
        result = sample.to_api_response(0, 0)
        assert result.scenario_context is None

    def test_excludes_ground_truth_fields(self, sample_with_llm_input: Sample) -> None:
        """SampleResponse does not contain user_agent_decision, final_decision, or gather_context_delta."""
        result = sample_with_llm_input.to_api_response(5, 20)
        result_dict = result.model_dump()
        assert "user_agent_decision" not in result_dict
        assert "final_decision" not in result_dict
        assert "gather_context_delta" not in result_dict

    def test_formats_tool_observation(self, sample_with_llm_input: Sample) -> None:
        """Tool observation content has Meta-ARE boilerplate stripped."""
        result = sample_with_llm_input.to_api_response(5, 20)
        obs = next(m for m in result.messages if m.msg_type == MessageType.TOOL_OBSERVATION)
        assert "[OUTPUT OF STEP" not in obs.content
        assert "***" not in obs.content

    def test_formats_notification_strips_hex_ids(self, sample_with_llm_input: Sample) -> None:
        """Notification content has hex IDs stripped by format_notification."""
        result = sample_with_llm_input.to_api_response(5, 20)
        notif = next(m for m in result.messages if m.msg_type == MessageType.ENVIRONMENT_NOTIFICATION)
        assert "22c41f3ff12fe5f2a0a02c1da9d15b57" not in notif.content
        assert "abc123" not in notif.content
        assert "Hello!" in notif.content

    def test_empty_llm_input_returns_empty_messages(self) -> None:
        """Empty llm_input JSON array results in empty messages list."""
        sample = Sample(
            sample_id="test",
            scenario_id="test",
            run_number=1,
            proactive_model_id="gpt-4o",
            user_model_id="gpt-4o",
            trace_file="traces/no_noise_gpt-4o/scenario_a.json",
            user_agent_decision="accept",
            agent_proposal="proposal",
            meta_task_description="",
            llm_input=json.dumps([]),
            final_decision=True,
        )
        result = sample.to_api_response(0, 0)
        assert result.messages == []

    def test_tool_observation_before_any_user_action(self) -> None:
        """Tool observation with no preceding user_action uses empty tool name."""
        messages = [
            {"role": "tool-response", "content": "[OUTPUT OF STEP 1] Observation:\n***\nSome result\n***", "timestamp": 101.0, "msg_type": "tool_observation"},
        ]
        sample = Sample(
            sample_id="test",
            scenario_id="test",
            run_number=1,
            proactive_model_id="gpt-4o",
            user_model_id="gpt-4o",
            trace_file="traces/no_noise_gpt-4o/scenario_a.json",
            user_agent_decision="accept",
            agent_proposal="proposal",
            meta_task_description="",
            llm_input=json.dumps(messages),
            final_decision=True,
        )
        result = sample.to_api_response(0, 0)
        assert len(result.messages) == 1
        # Should not crash -- formatter handles empty tool name gracefully
        assert result.messages[0].msg_type == MessageType.TOOL_OBSERVATION

    def test_observation_without_boilerplate_passes_through(self) -> None:
        """Observation content without *** delimiters is passed through as-is."""
        messages = [
            {"role": "assistant", "content": "Thought: test\nAction: System__open_app\nAction Input: {}", "timestamp": 101.0, "msg_type": "user_action"},
            {"role": "tool-response", "content": "Opened Notes App.", "timestamp": 101.0, "msg_type": "tool_observation"},
        ]
        sample = Sample(
            sample_id="test",
            scenario_id="test",
            run_number=1,
            proactive_model_id="gpt-4o",
            user_model_id="gpt-4o",
            trace_file="traces/no_noise_gpt-4o/scenario_a.json",
            user_agent_decision="accept",
            agent_proposal="proposal",
            meta_task_description="",
            llm_input=json.dumps(messages),
            final_decision=True,
        )
        result = sample.to_api_response(0, 0)
        obs = next(m for m in result.messages if m.msg_type == MessageType.TOOL_OBSERVATION)
        assert obs.content == "Opened Notes App."

    def test_null_timestamp_preserved_as_none(self) -> None:
        """Messages with null timestamps get timestamp=None."""
        messages = [
            {"role": "user", "content": "Environment notifications updates:\n***\nTest notification\n***", "timestamp": None, "msg_type": "environment_notification"},
        ]
        sample = Sample(
            sample_id="test",
            scenario_id="test",
            run_number=1,
            proactive_model_id="gpt-4o",
            user_model_id="gpt-4o",
            trace_file="traces/no_noise_gpt-4o/scenario_a.json",
            user_agent_decision="accept",
            agent_proposal="proposal",
            meta_task_description="",
            llm_input=json.dumps(messages),
            final_decision=True,
        )
        result = sample.to_api_response(0, 0)
        assert result.messages[0].timestamp is None

    def test_string_timestamp_treated_as_none(self) -> None:
        """Non-numeric timestamp values are treated as None."""
        messages = [
            {"role": "user", "content": "[TASK]: proposal text", "timestamp": "invalid", "msg_type": "proposal"},
        ]
        sample = Sample(
            sample_id="test",
            scenario_id="test",
            run_number=1,
            proactive_model_id="gpt-4o",
            user_model_id="gpt-4o",
            trace_file="traces/no_noise_gpt-4o/scenario_a.json",
            user_agent_decision="accept",
            agent_proposal="proposal",
            meta_task_description="",
            llm_input=json.dumps(messages),
            final_decision=True,
        )
        result = sample.to_api_response(0, 0)
        assert result.messages[0].timestamp is None
