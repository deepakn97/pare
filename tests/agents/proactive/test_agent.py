"""Tests for ProactiveAgent wrapper class - focused on OUR logic."""

from unittest.mock import MagicMock, Mock, patch

import pytest
from are.simulation.agents.agent_log import ToolCallLog
from are.simulation.agents.default_agent.base_agent import BaseAgent
from are.simulation.notification_system import BaseNotificationSystem, Message

from pas.agents.proactive.agent import ProactiveAgent, ProactiveAgentMode
from pas.notification_system import PASMessageType


@pytest.fixture
def mock_observe_llm_engine():
    """Mock LLM engine for observe agent."""
    mock = MagicMock()
    mock.model_name = "gpt-4-observe"
    return mock


@pytest.fixture
def mock_execute_llm_engine():
    """Mock LLM engine for execute agent."""
    mock = MagicMock()
    mock.model_name = "gpt-4-execute"
    return mock


@pytest.fixture
def mock_observe_agent():
    """Mock observe BaseAgent."""
    agent = Mock(spec=BaseAgent)
    agent.notification_system = None
    agent.custom_state = {}
    agent.tools = {}
    agent.init_system_prompts = {
        "system_prompt": "Observe prompt <<notification_system_description>> <<curent_time_description>> <<agent_reminder_description>>"
    }
    agent.get_agent_logs = Mock(return_value=[])
    agent.run = Mock(return_value="observe_result")
    return agent


@pytest.fixture
def mock_execute_agent():
    """Mock execute BaseAgent."""
    agent = Mock(spec=BaseAgent)
    agent.notification_system = None
    agent.custom_state = {}
    agent.tools = {}
    agent.init_system_prompts = {
        "system_prompt": "Execute prompt <<notification_system_description>> <<curent_time_description>> <<agent_reminder_description>>"
    }
    agent.run = Mock(return_value="execute_result")
    return agent


@pytest.fixture
def mock_time_manager():
    """Mock TimeManager."""
    manager = Mock()
    manager.time.return_value = 1609459200.0  # 2021-01-01 00:00:00
    return manager


@pytest.fixture
def mock_notification_system():
    """Mock notification system."""
    system = Mock(spec=BaseNotificationSystem)
    system.message_queue = Mock()
    system.message_queue.get_by_timestamp.return_value = []
    system.message_queue.put = Mock()
    return system


@pytest.fixture
def proactive_agent(
    mock_observe_llm_engine, mock_execute_llm_engine, mock_observe_agent, mock_execute_agent, mock_time_manager
):
    """Create ProactiveAgent with mocked dependencies."""
    return ProactiveAgent(
        log_callback=Mock(),
        pause_env=Mock(),
        resume_env=Mock(),
        observe_llm_engine=mock_observe_llm_engine,
        observe_agent=mock_observe_agent,
        execute_llm_engine=mock_execute_llm_engine,
        execute_agent=mock_execute_agent,
        time_manager=mock_time_manager,
        observe_max_iterations=1,
        execute_max_iterations=20,
    )


# ==================== Initialization Tests ====================


def test_initialization_sets_both_agents_properties(
    proactive_agent, mock_observe_llm_engine, mock_execute_llm_engine, mock_observe_agent, mock_execute_agent
):
    """Test that ProactiveAgent sets properties on both observe and execute agents."""
    # Observe agent
    assert mock_observe_agent.llm_engine == mock_observe_llm_engine
    assert mock_observe_agent.max_iterations == 1
    assert proactive_agent.observe_agent == mock_observe_agent

    # Execute agent
    assert mock_execute_agent.llm_engine == mock_execute_llm_engine
    assert mock_execute_agent.max_iterations == 20
    assert proactive_agent.execute_agent == mock_execute_agent


def test_initialization_sets_initial_state(proactive_agent):
    """Test that ProactiveAgent initializes with correct state."""
    assert proactive_agent.mode == ProactiveAgentMode.OBSERVE
    assert proactive_agent.pending_goal is None
    assert proactive_agent._initialized is False


# ==================== Proposal Detection Tests ====================


def test_check_for_proposal_dict_tool_arguments(proactive_agent):
    """Test check_for_proposal extracts content from dict tool_arguments."""
    # Create ToolCallLog with dict tool_arguments
    tool_log = Mock(spec=ToolCallLog)
    tool_log.tool_name = "ProactiveAgentUserInterface__send_message_to_user"
    tool_log.tool_arguments = {"content": "Shall I reply to Alice's email?"}

    proactive_agent.observe_agent.get_agent_logs.return_value = [tool_log]

    proposal_made, content = proactive_agent.check_for_proposal()

    assert proposal_made is True
    assert content == "Shall I reply to Alice's email?"


def test_check_for_proposal_string_tool_arguments(proactive_agent):
    """Test check_for_proposal converts string tool_arguments."""
    # Create ToolCallLog with string tool_arguments
    tool_log = Mock(spec=ToolCallLog)
    tool_log.tool_name = "send_message_to_user"
    tool_log.tool_arguments = "Shall I schedule a meeting?"

    proactive_agent.observe_agent.get_agent_logs.return_value = [tool_log]

    proposal_made, content = proactive_agent.check_for_proposal()

    assert proposal_made is True
    assert content == "Shall I schedule a meeting?"


def test_check_for_proposal_no_send_message_to_user_in_logs(proactive_agent):
    """Test check_for_proposal returns (False, None) when no send_message_to_user in logs."""
    # Create logs without send_message_to_user
    other_log = Mock()
    other_log.tool_name = "Contacts__list_contacts"

    proactive_agent.observe_agent.get_agent_logs.return_value = [other_log]

    proposal_made, content = proactive_agent.check_for_proposal()

    assert proposal_made is False
    assert content is None


# ==================== OBSERVE Mode Tests ====================


def test_observe_mode_proposal_detected_transitions_to_awaiting(proactive_agent, mock_notification_system):
    """Test _run_observe_mode transitions to AWAITING_CONFIRMATION when proposal detected."""
    proactive_agent.observe_agent.notification_system = mock_notification_system

    # Mock ToolCallLog for proposal detection
    tool_log = Mock(spec=ToolCallLog)
    tool_log.tool_name = "send_message_to_user"
    tool_log.tool_arguments = {"content": "Shall I reply to Alice?"}
    proactive_agent.observe_agent.get_agent_logs.return_value = [tool_log]

    # Create user message
    user_msg = Mock(spec=Message)
    user_msg.message = "test"
    user_msg.attachments = []

    result = proactive_agent._run_observe_mode([user_msg], [])

    assert proactive_agent.mode == ProactiveAgentMode.AWAITING_CONFIRMATION
    assert proactive_agent.pending_goal == "Shall I reply to Alice?"
    assert result == "observe_result"
    assert proactive_agent.observe_agent.run.called


def test_observe_mode_no_proposal_stays_in_observe(proactive_agent, mock_notification_system):
    """Test _run_observe_mode stays in OBSERVE when no proposal detected."""
    proactive_agent.observe_agent.notification_system = mock_notification_system
    proactive_agent.observe_agent.get_agent_logs.return_value = []  # No proposal

    user_msg = Mock(spec=Message)
    user_msg.message = "test"
    user_msg.attachments = []

    result = proactive_agent._run_observe_mode([user_msg], [])

    assert proactive_agent.mode == ProactiveAgentMode.OBSERVE
    assert proactive_agent.pending_goal is None
    assert result == "observe_result"


# ==================== AWAITING_CONFIRMATION Mode Tests ====================


def test_check_confirmation_accept(proactive_agent):
    """Test _check_confirmation returns True for accept message."""
    accept_msg = Mock(spec=Message)
    accept_msg.message = "[ACCEPT] yes, please go ahead with that"

    accepted, response = proactive_agent._check_confirmation([accept_msg])

    assert accepted is True
    assert response == "[ACCEPT] yes, please go ahead with that"


def test_check_confirmation_reject(proactive_agent):
    """Test _check_confirmation transitions to OBSERVE on reject."""
    proactive_agent.mode = ProactiveAgentMode.AWAITING_CONFIRMATION

    reject_msg = Mock(spec=Message)
    reject_msg.message = "[REJECT] no, I don't want that"

    accepted, response = proactive_agent._check_confirmation([reject_msg])

    assert accepted is False
    assert response is None
    assert proactive_agent.mode == ProactiveAgentMode.OBSERVE


def test_check_confirmation_unclear_stays_awaiting(proactive_agent):
    """Test _check_confirmation stays in AWAITING on unclear response."""
    proactive_agent.mode = ProactiveAgentMode.AWAITING_CONFIRMATION

    unclear_msg = Mock(spec=Message)
    unclear_msg.message = "What do you mean?"

    accepted, response = proactive_agent._check_confirmation([unclear_msg])

    assert accepted is False
    assert response is None
    assert proactive_agent.mode == ProactiveAgentMode.AWAITING_CONFIRMATION


# ==================== EXECUTE Mode Tests ====================


def test_execute_mode_clears_pending_goal_and_returns_to_observe(proactive_agent, mock_notification_system):
    """Test _run_execute_mode clears pending_goal and transitions to OBSERVE."""
    proactive_agent.mode = ProactiveAgentMode.EXECUTE
    proactive_agent.pending_goal = "Reply to Alice's email"
    proactive_agent.execute_agent.notification_system = mock_notification_system

    user_msg = Mock(spec=Message)
    user_msg.message = "Use friendly tone"
    user_msg.attachments = []

    result = proactive_agent._run_execute_mode([user_msg], [])

    assert proactive_agent.mode == ProactiveAgentMode.OBSERVE
    assert proactive_agent.pending_goal is None
    assert result == "execute_result"
    assert proactive_agent.execute_agent.run.called


def test_execute_mode_raises_if_pending_goal_is_none(proactive_agent, mock_notification_system):
    """Test _run_execute_mode raises RuntimeError if pending_goal is None."""
    proactive_agent.pending_goal = None
    proactive_agent.execute_agent.notification_system = mock_notification_system

    user_msg = Mock(spec=Message)
    user_msg.message = "test"
    user_msg.attachments = []

    with pytest.raises(RuntimeError, match="Execute mode called without pending_goal"):
        proactive_agent._run_execute_mode([user_msg], [])


# ==================== agent_loop Core Logic Tests ====================


def test_agent_loop_raises_if_notification_system_none_on_either_agent(proactive_agent):
    """Test agent_loop raises RuntimeError if notification_system is None on either agent."""
    # Test with observe_agent.notification_system = None
    proactive_agent.observe_agent.notification_system = None
    proactive_agent.execute_agent.notification_system = Mock()

    with pytest.raises(RuntimeError, match="Notification system not set"):
        proactive_agent.agent_loop()

    # Test with execute_agent.notification_system = None
    proactive_agent.observe_agent.notification_system = Mock()
    proactive_agent.execute_agent.notification_system = None

    with pytest.raises(RuntimeError, match="Notification system not set"):
        proactive_agent.agent_loop()


def test_agent_loop_environment_stop_returns_none(proactive_agent, mock_notification_system):
    """Test agent_loop returns None on ENVIRONMENT_STOP message."""
    proactive_agent.observe_agent.notification_system = mock_notification_system
    proactive_agent.execute_agent.notification_system = mock_notification_system

    # Mock ENVIRONMENT_STOP
    stop_msg = Mock(spec=Message)
    stop_msg.message_type = PASMessageType.ENVIRONMENT_STOP
    mock_notification_system.message_queue.get_by_timestamp.return_value = [stop_msg]

    result = proactive_agent.agent_loop()

    assert result is None
    assert not proactive_agent.observe_agent.run.called
    assert not proactive_agent.execute_agent.run.called


def test_agent_loop_initial_task_injection(proactive_agent, mock_notification_system):
    """Test initial_task is injected as USER_MESSAGE with timestamp."""
    proactive_agent.observe_agent.notification_system = mock_notification_system
    proactive_agent.execute_agent.notification_system = mock_notification_system

    # Initialize custom_state with notifications list
    proactive_agent.observe_agent.custom_state = {"notifications": []}

    # Mock empty notifications
    mock_notification_system.message_queue.get_by_timestamp.return_value = []

    proactive_agent.agent_loop(initial_task="Please help with task X")

    # Verify message was added to custom_state notifications
    notifications = proactive_agent.observe_agent.custom_state["notifications"]
    assert len(notifications) == 1
    assert notifications[0].message_type == PASMessageType.USER_MESSAGE
    assert notifications[0].message == "Please help with task X"


# ==================== Full Integration Flow Tests ====================


def test_full_accept_flow_observe_to_execute_to_observe(proactive_agent, mock_notification_system):
    """Test full integration: OBSERVE → proposal → AWAITING → accept → EXECUTE → OBSERVE."""
    proactive_agent.observe_agent.notification_system = mock_notification_system
    proactive_agent.execute_agent.notification_system = mock_notification_system

    # Step 1: OBSERVE mode with no proposal
    assert proactive_agent.mode == ProactiveAgentMode.OBSERVE
    proactive_agent.observe_agent.get_agent_logs.return_value = []

    user_msg1 = Mock(spec=Message)
    user_msg1.message = "test"
    user_msg1.message_type = PASMessageType.USER_MESSAGE
    user_msg1.attachments = []
    mock_notification_system.message_queue.get_by_timestamp.return_value = [user_msg1]

    result1 = proactive_agent.agent_loop()
    assert proactive_agent.mode == ProactiveAgentMode.OBSERVE
    assert result1 == "observe_result"

    # Step 2: OBSERVE mode with proposal
    tool_log = Mock(spec=ToolCallLog)
    tool_log.tool_name = "send_message_to_user"
    tool_log.tool_arguments = {"content": "Shall I reply to Alice?"}
    proactive_agent.observe_agent.get_agent_logs.return_value = [tool_log]

    result2 = proactive_agent.agent_loop()
    assert proactive_agent.mode == ProactiveAgentMode.AWAITING_CONFIRMATION
    assert proactive_agent.pending_goal == "Shall I reply to Alice?"

    # Step 3: AWAITING mode with accept
    accept_msg = Mock(spec=Message)
    accept_msg.message = "[ACCEPT] yes, please proceed"
    accept_msg.message_type = PASMessageType.USER_MESSAGE
    accept_msg.attachments = []
    mock_notification_system.message_queue.get_by_timestamp.return_value = [accept_msg]

    result3 = proactive_agent.agent_loop()
    # Should execute and return to OBSERVE
    assert proactive_agent.mode == ProactiveAgentMode.OBSERVE
    assert proactive_agent.pending_goal is None
    assert result3 == "execute_result"


def test_reject_flow_observe_to_awaiting_to_observe_skip_execute(proactive_agent, mock_notification_system):
    """Test rejection flow: OBSERVE → proposal → AWAITING → reject → back to OBSERVE (skips EXECUTE)."""
    proactive_agent.observe_agent.notification_system = mock_notification_system
    proactive_agent.execute_agent.notification_system = mock_notification_system

    # Step 1: OBSERVE mode with proposal
    tool_log = Mock(spec=ToolCallLog)
    tool_log.tool_name = "send_message_to_user"
    tool_log.tool_arguments = {"content": "Shall I delete all contacts?"}
    proactive_agent.observe_agent.get_agent_logs.return_value = [tool_log]

    user_msg = Mock(spec=Message)
    user_msg.message = "test"
    user_msg.message_type = PASMessageType.USER_MESSAGE
    user_msg.attachments = []
    mock_notification_system.message_queue.get_by_timestamp.return_value = [user_msg]

    proactive_agent.agent_loop()
    assert proactive_agent.mode == ProactiveAgentMode.AWAITING_CONFIRMATION
    assert proactive_agent.pending_goal == "Shall I delete all contacts?"

    # Step 2: AWAITING mode with reject
    reject_msg = Mock(spec=Message)
    reject_msg.message = "[REJECT] no, please don't do that"
    reject_msg.message_type = PASMessageType.USER_MESSAGE
    reject_msg.attachments = []
    mock_notification_system.message_queue.get_by_timestamp.return_value = [reject_msg]

    # Reset execute mock to verify it's NOT called
    proactive_agent.execute_agent.run.reset_mock()

    result = proactive_agent.agent_loop()

    # Should NOT call execute_agent
    assert not proactive_agent.execute_agent.run.called
    # Should return to OBSERVE
    assert proactive_agent.mode == ProactiveAgentMode.OBSERVE
    assert result is None
