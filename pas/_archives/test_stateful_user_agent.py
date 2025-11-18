"""Test to verify the StatefulUserAgent implementation."""

import logging
import unittest
from unittest.mock import Mock, patch

import pytest

pytest.importorskip("are.simulation")

from are.simulation.agents.default_agent.base_agent import BaseAgent

from pas.apps.contacts.app import StatefulContactsApp
from pas.environment import StateAwareEnvironmentWrapper
from pas.proactive import LLMClientProtocol
from pas.proactive.react_adapter import PasLLMEngine
from pas.user_proxy import StatefulUserAgent, StatefulUserAgentRuntime, ToolInvocation


class TestStatefulUserAgent(unittest.TestCase):
    """Tests for StatefulUserAgent."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.llm_engine = Mock()
        self.tools: dict[str, object] = {}
        self.agent = StatefulUserAgent(llm_engine=self.llm_engine, tools=self.tools, max_turns=5)

    def test_inheritance(self) -> None:
        """Test that StatefulUserAgent inherits from BaseAgent."""
        self.assertIsInstance(self.agent, BaseAgent)
        self.assertIsInstance(self.agent, StatefulUserAgent)

    def test_initialization(self) -> None:
        """Test that StatefulUserAgent initializes correctly."""
        self.assertEqual(self.agent.name, "stateful_user_agent")
        self.assertEqual(self.agent.max_turns, 5)
        self.assertEqual(self.agent.turns_taken, 0)
        self.assertEqual(len(self.agent.transcript), 0)
        self.assertEqual(len(self.agent.tool_history), 0)

    def test_init_conversation(self) -> None:
        """Test the init_conversation method."""
        # Add some data to the agent
        self.agent.turns_taken = 3
        self.agent.transcript_history.append({"role": "agent", "content": "test"})
        self.agent.tool_history_list.append(ToolInvocation(app="contacts", method="show", args={}))

        # Call init_conversation
        result = self.agent.init_conversation()

        # Verify the state is reset
        self.assertEqual(result, "")
        self.assertEqual(self.agent.turns_taken, 0)
        self.assertEqual(len(self.agent.transcript), 0)
        self.assertEqual(len(self.agent.tool_history), 0)

    def test_reply_within_turn_limit(self) -> None:
        """Test the reply method within turn limit."""
        # Mock the run method to return a specific value
        with patch.object(self.agent, "run", return_value="Test response"):
            result = self.agent.reply("Test message")

            # Verify the result and state
            self.assertEqual(result, "Test response")
            self.assertEqual(self.agent.turns_taken, 1)
            self.assertEqual(len(self.agent.transcript), 2)
            self.assertEqual(self.agent.transcript[0]["role"], "agent")
            self.assertEqual(self.agent.transcript[0]["content"], "Test message")
            self.assertEqual(self.agent.transcript[1]["role"], "user")
            self.assertEqual(self.agent.transcript[1]["content"], "Test response")

    def test_transcript_property(self) -> None:
        """Test the transcript property."""
        # Add some entries to transcript
        self.agent.transcript_history.append({"role": "agent", "content": "test1"})
        self.agent.transcript_history.append({"role": "user", "content": "test2"})

        # Verify the property returns the correct data
        transcript = self.agent.transcript
        self.assertEqual(len(transcript), 2)
        self.assertEqual(transcript[0]["role"], "agent")
        self.assertEqual(transcript[1]["role"], "user")

    def test_tool_history_property(self) -> None:
        """Test the tool_history property."""
        # Add some entries to tool_history
        self.agent.tool_history_list.append(ToolInvocation(app="app", method="m1", args={}))
        self.agent.tool_history_list.append(ToolInvocation(app="app", method="m2", args={}))

        # Verify the property returns the correct data
        tool_history = self.agent.tool_history
        self.assertEqual(len(tool_history), 2)
        self.assertEqual(tool_history[0].method, "m1")
        self.assertEqual(tool_history[1].method, "m2")


class _StubLLM(LLMClientProtocol):
    def complete(self, prompt: str) -> str:  # pragma: no cover - deterministic stub
        return prompt

    def complete_with_metadata(self, prompt: str, *, temperature: float | None = None) -> tuple[str, dict[str, object]]:
        return prompt, {"temperature": temperature}


def test_direct_instantiation_creates_agent() -> None:
    """Test direct instantiation pattern (aligned with Meta ARE UserProxy)."""
    llm_engine = PasLLMEngine(_StubLLM())
    agent = StatefulUserAgent(llm_engine=llm_engine, tools={}, max_turns=4, wait_timeout=1.2)
    assert isinstance(agent, StatefulUserAgent)
    assert agent.max_turns == 4


def test_direct_instantiation_creates_runtime() -> None:
    """Test direct runtime instantiation (aligned with Meta ARE UserProxy)."""
    env = StateAwareEnvironmentWrapper()
    contacts = StatefulContactsApp(name="contacts")
    env.register_apps([contacts])

    tools = {tool.name: tool for tool in contacts.get_meta_are_user_tools()}
    llm_engine = PasLLMEngine(_StubLLM())

    agent = StatefulUserAgent(llm_engine=llm_engine, tools=tools, max_turns=3)

    runtime = StatefulUserAgentRuntime(
        agent=agent,
        notification_system=env.notification_system,
        logger=logging.getLogger("tests.user_agent.runtime"),
        max_user_turns=3,
        event_timeout=2.0,
    )
    env.register_user_agent(agent)
    env.subscribe_to_completed_events(runtime._on_event)

    runtime.init_conversation()
    assert runtime.consume_notifications() == []
    assert runtime.last_tool_invocations == ()


if __name__ == "__main__":
    unittest.main()
