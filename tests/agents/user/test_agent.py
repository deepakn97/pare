"""Tests for UserAgent wrapper class."""

from unittest.mock import MagicMock, Mock, patch

import pytest
from are.simulation.agents.default_agent.base_agent import BaseAgent, BaseAgentLog, RunningState
from are.simulation.notification_system import BaseNotificationSystem, Message, MessageType
from are.simulation.scenarios.scenario import Scenario

from pas.agents.user.agent import UserAgent
from pas.notification_system import PASMessageType


@pytest.fixture
def mock_llm_engine():
    """Mock LLM engine following Meta-ARE pattern."""
    mock = MagicMock()
    mock.model_name = "gpt-4"
    return mock


@pytest.fixture
def mock_base_agent():
    """Mock BaseAgent with common setup."""
    agent = Mock(spec=BaseAgent)
    agent.notification_system = None
    agent.custom_state = {}
    agent.tools = {}
    agent.init_system_prompts = {
        "system_prompt": "Test prompt <<task_description>> <<notification_system_description>> <<curent_time_description>> <<agent_reminder_description>>"
    }
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
def user_agent(mock_llm_engine, mock_base_agent, mock_time_manager):
    """Create UserAgent with mocked dependencies."""
    return UserAgent(
        log_callback=Mock(),
        pause_env=Mock(),
        resume_env=Mock(),
        llm_engine=mock_llm_engine,
        base_agent=mock_base_agent,
        time_manager=mock_time_manager,
        max_iterations=1,
    )


# ==================== Property Tests ====================


def test_agent_framework_property(user_agent):
    """Test agent_framework property returns correct name."""
    assert user_agent.agent_framework == "PASUserAgent"


def test_model_property(user_agent, mock_llm_engine):
    """Test model property returns llm_engine.model_name."""
    assert user_agent.model == "gpt-4"
    assert user_agent.model == mock_llm_engine.model_name


# ==================== Initialization Tests ====================


def test_initialization_sets_properties(user_agent, mock_llm_engine, mock_base_agent, mock_time_manager):
    """Test that UserAgent initializes with correct properties."""
    assert user_agent.llm_engine == mock_llm_engine
    assert user_agent.time_manager == mock_time_manager
    assert user_agent.max_iterations == 1
    assert user_agent.tools is None
    assert user_agent.react_agent == mock_base_agent
    assert user_agent._initialized is False


def test_initialization_sets_base_agent_properties(user_agent, mock_llm_engine, mock_time_manager, mock_base_agent):
    """Test that UserAgent sets properties on base_agent during init."""
    assert mock_base_agent.llm_engine == mock_llm_engine
    assert mock_base_agent.time_manager == mock_time_manager
    assert mock_base_agent.max_iterations == 1


# ==================== Notification System Tests ====================


def test_init_notification_system(user_agent, mock_notification_system):
    """Test init_notification_system sets notification_system on base_agent."""
    user_agent.init_notification_system(mock_notification_system)
    assert user_agent.react_agent.notification_system == mock_notification_system


def test_init_notification_system_with_none(user_agent):
    """Test init_notification_system with None does not change base_agent."""
    original = user_agent.react_agent.notification_system
    user_agent.init_notification_system(None)
    assert user_agent.react_agent.notification_system == original


# ==================== get_notifications Tests ====================


def test_get_notifications_filters_agent_messages(user_agent, mock_notification_system):
    """Test get_notifications filters AGENT_MESSAGE type correctly."""
    agent_msg = Mock(spec=Message)
    agent_msg.message_type = PASMessageType.AGENT_MESSAGE

    mock_notification_system.message_queue.get_by_timestamp.return_value = [agent_msg]
    user_agent.react_agent.notification_system = mock_notification_system

    agent_messages, env_notifications, env_stop = user_agent.get_notifications(mock_notification_system)

    assert len(agent_messages) == 1
    assert agent_messages[0] == agent_msg
    assert len(env_notifications) == 0
    assert len(env_stop) == 0


def test_get_notifications_filters_env_notifications(user_agent, mock_notification_system):
    """Test get_notifications filters ENVIRONMENT_NOTIFICATION type correctly."""
    env_msg = Mock(spec=Message)
    env_msg.message_type = MessageType.ENVIRONMENT_NOTIFICATION

    mock_notification_system.message_queue.get_by_timestamp.return_value = [env_msg]
    user_agent.react_agent.notification_system = mock_notification_system

    agent_messages, env_notifications, env_stop = user_agent.get_notifications(mock_notification_system)

    assert len(agent_messages) == 0
    assert len(env_notifications) == 1
    assert env_notifications[0] == env_msg
    assert len(env_stop) == 0


def test_get_notifications_filters_env_stop(user_agent, mock_notification_system):
    """Test get_notifications filters ENVIRONMENT_STOP type correctly."""
    stop_msg = Mock(spec=Message)
    stop_msg.message_type = MessageType.ENVIRONMENT_STOP

    mock_notification_system.message_queue.get_by_timestamp.return_value = [stop_msg]
    user_agent.react_agent.notification_system = mock_notification_system

    agent_messages, env_notifications, env_stop = user_agent.get_notifications(mock_notification_system)

    assert len(agent_messages) == 0
    assert len(env_notifications) == 0
    assert len(env_stop) == 1
    assert env_stop[0] == stop_msg


def test_get_notifications_puts_env_notifications_back(user_agent, mock_notification_system):
    """Test get_notifications puts env notifications back in queue."""
    env_msg = Mock(spec=Message)
    env_msg.message_type = MessageType.ENVIRONMENT_NOTIFICATION

    mock_notification_system.message_queue.get_by_timestamp.return_value = [env_msg]
    user_agent.react_agent.notification_system = mock_notification_system

    user_agent.get_notifications(mock_notification_system)

    # Verify message was put back in queue
    mock_notification_system.message_queue.put.assert_called_once_with(env_msg)


def test_get_notifications_raises_without_system(user_agent):
    """Test get_notifications raises RuntimeError when notification_system is None."""
    with pytest.raises(RuntimeError, match="Notification system not set"):
        user_agent.get_notifications(None)


def test_get_notifications_handles_mixed_messages(user_agent, mock_notification_system):
    """Test get_notifications correctly filters mixed message types."""
    agent_msg = Mock(spec=Message)
    agent_msg.message_type = PASMessageType.AGENT_MESSAGE

    env_msg = Mock(spec=Message)
    env_msg.message_type = MessageType.ENVIRONMENT_NOTIFICATION

    stop_msg = Mock(spec=Message)
    stop_msg.message_type = MessageType.ENVIRONMENT_STOP

    mock_notification_system.message_queue.get_by_timestamp.return_value = [agent_msg, env_msg, stop_msg]
    user_agent.react_agent.notification_system = mock_notification_system

    agent_messages, env_notifications, env_stop = user_agent.get_notifications(mock_notification_system)

    assert len(agent_messages) == 1
    assert len(env_notifications) == 1
    assert len(env_stop) == 1


# ==================== build_task_from_notifications Tests ====================


def test_build_task_empty_list(user_agent):
    """Test build_task_from_notifications with empty list returns empty string."""
    result = user_agent.build_task_from_notifications([])
    assert result == ""


def test_build_task_single_message(user_agent):
    """Test build_task_from_notifications with single message."""
    msg = Mock(spec=Message)
    msg.message = "Test message"

    result = user_agent.build_task_from_notifications([msg])
    assert result == "Test message"


def test_build_task_multiple_messages(user_agent):
    """Test build_task_from_notifications joins multiple messages with newlines."""
    msg1 = Mock(spec=Message)
    msg1.message = "First message"

    msg2 = Mock(spec=Message)
    msg2.message = "Second message"

    result = user_agent.build_task_from_notifications([msg1, msg2])
    assert result == "First message\nSecond message"


# ==================== prepare_user_agent_run Tests ====================


def test_prepare_user_agent_run_sets_initialized(user_agent, mock_notification_system):
    """Test prepare_user_agent_run sets _initialized flag."""
    scenario = Mock(spec=Scenario)
    scenario.get_user_tools.return_value = []
    scenario.additional_system_prompt = None
    scenario.apps = []
    scenario.start_time = 0

    assert user_agent._initialized is False
    user_agent.prepare_user_agent_run(scenario, mock_notification_system)
    assert user_agent._initialized is True


def test_prepare_user_agent_run_initializes_notification_system(user_agent, mock_notification_system):
    """Test prepare_user_agent_run sets notification system."""
    scenario = Mock(spec=Scenario)
    scenario.get_user_tools.return_value = []
    scenario.additional_system_prompt = None
    scenario.apps = []
    scenario.start_time = 0

    user_agent.prepare_user_agent_run(scenario, mock_notification_system)
    assert user_agent.react_agent.notification_system == mock_notification_system


@patch("pas.agents.user.agent.get_notification_system_prompt")
def test_prepare_user_agent_run_initializes_system_prompt(mock_get_prompt, user_agent, mock_notification_system):
    """Test prepare_user_agent_run initializes system prompt."""
    mock_get_prompt.return_value = "Notification system description"

    scenario = Mock(spec=Scenario)
    scenario.get_user_tools.return_value = []
    scenario.additional_system_prompt = "Additional prompt"
    scenario.apps = []
    scenario.start_time = 1609459200  # 2021-01-01 00:00:00

    user_agent.prepare_user_agent_run(scenario, mock_notification_system)

    # Verify prompt was modified
    prompt = user_agent.react_agent.init_system_prompts["system_prompt"]
    assert "Additional prompt" in prompt
    assert "Notification system description" in prompt
    assert "2021-01-01 00" in prompt
    assert "<<task_description>>" not in prompt
    assert "<<notification_system_description>>" not in prompt
    assert "<<curent_time_description>>" not in prompt


def test_prepare_user_agent_run_replays_initial_logs(user_agent, mock_notification_system):
    """Test prepare_user_agent_run replays initial agent logs."""
    scenario = Mock(spec=Scenario)
    scenario.get_user_tools.return_value = []
    scenario.additional_system_prompt = None
    scenario.apps = []
    scenario.start_time = 0

    initial_logs = [Mock(spec=BaseAgentLog)]
    user_agent.react_agent.replay = Mock()

    user_agent.prepare_user_agent_run(scenario, mock_notification_system, initial_agent_logs=initial_logs)

    user_agent.react_agent.replay.assert_called_once_with(initial_logs)


def test_prepare_user_agent_run_raises_without_pause_resume(user_agent, mock_notification_system):
    """Test prepare_user_agent_run raises when simulated_generation_time_config but no pause/resume."""
    scenario = Mock(spec=Scenario)
    scenario.get_user_tools.return_value = []
    scenario.additional_system_prompt = None
    scenario.apps = []
    scenario.start_time = 0

    # Create user agent without pause/resume callbacks
    user_agent_no_callbacks = UserAgent(
        log_callback=Mock(),
        pause_env=None,
        resume_env=None,
        llm_engine=user_agent.llm_engine,
        base_agent=user_agent.react_agent,
        time_manager=user_agent.time_manager,
        max_iterations=1,
        simulated_generation_time_config=Mock(),  # Set config but no callbacks
    )

    with pytest.raises(Exception, match="Pause and resume environment functions must be provided"):
        user_agent_no_callbacks.prepare_user_agent_run(scenario, mock_notification_system)


# ==================== agent_loop Tests ====================


def test_agent_loop_raises_when_not_initialized(user_agent):
    """Test agent_loop raises RuntimeError when not initialized."""
    with pytest.raises(RuntimeError, match="User agent must be initialized before running a turn"):
        user_agent.agent_loop(current_tools=[])


def test_agent_loop_raises_when_no_notification_system(user_agent):
    """Test agent_loop raises RuntimeError when notification_system is None."""
    user_agent._initialized = True

    with pytest.raises(RuntimeError, match="Notification system not set"):
        user_agent.agent_loop(current_tools=[])


@patch("pas.agents.user.agent.time.sleep")
def test_agent_loop_initializes_tools(mock_sleep, user_agent, mock_notification_system):
    """Test agent_loop calls init_tools with current_tools."""
    user_agent._initialized = True
    user_agent.react_agent.notification_system = mock_notification_system
    user_agent.init_tools = Mock()

    # No notifications, will sleep once then hit max_turns
    mock_notification_system.message_queue.get_by_timestamp.return_value = []

    user_agent.agent_loop(current_tools=["tool1", "tool2"], max_turns=0)

    user_agent.init_tools.assert_called_once_with(["tool1", "tool2"])


@patch("pas.agents.user.agent.time.sleep")
def test_agent_loop_handles_agent_messages(mock_sleep, user_agent, mock_notification_system):
    """Test agent_loop processes agent messages and calls base_agent.run()."""
    user_agent._initialized = True
    user_agent.react_agent.notification_system = mock_notification_system
    user_agent.init_tools = Mock()

    # Create agent message
    msg = Mock(spec=Message)
    msg.message = "Test proposal"
    msg.message_type = PASMessageType.AGENT_MESSAGE
    msg.attachments = []

    # Mock get_notifications to control loop behavior
    user_agent.get_notifications = Mock(side_effect=[
        ([msg], [], []),  # First call: has agent message
        ([], [], []),      # Second call: no messages, will exit due to max_turns
    ])

    # Mock base_agent.run() to return result and set TERMINATED state
    user_agent.react_agent.run = Mock(return_value="Agent response")
    user_agent.react_agent.custom_state = {"running_state": RunningState.TERMINATED}

    result = user_agent.agent_loop(current_tools=[], max_turns=1)

    # Verify base_agent.run() was called
    user_agent.react_agent.run.assert_called_once()
    call_args = user_agent.react_agent.run.call_args
    assert call_args.kwargs["task"] == "Test proposal"
    assert call_args.kwargs["reset"] is True
    assert result == "Agent response"


@patch("pas.agents.user.agent.time.sleep")
def test_agent_loop_handles_env_stop(mock_sleep, user_agent, mock_notification_system):
    """Test agent_loop breaks on ENVIRONMENT_STOP message."""
    user_agent._initialized = True
    user_agent.react_agent.notification_system = mock_notification_system
    user_agent.init_tools = Mock()

    stop_msg = Mock(spec=Message)
    stop_msg.message_type = MessageType.ENVIRONMENT_STOP

    # Return stop message and empty lists
    mock_notification_system.message_queue.get_by_timestamp.return_value = [stop_msg]

    # Mock get_notifications to return stop message
    user_agent.get_notifications = Mock(return_value=([], [], [stop_msg]))

    result = user_agent.agent_loop(current_tools=[], max_turns=10)

    # Should break immediately without running agent
    assert user_agent.react_agent.run.call_count == 0


@patch("pas.agents.user.agent.time.sleep")
def test_agent_loop_handles_failed_state(mock_sleep, user_agent, mock_notification_system):
    """Test agent_loop raises RuntimeError on FAILED state."""
    user_agent._initialized = True
    user_agent.react_agent.notification_system = mock_notification_system
    user_agent.init_tools = Mock()

    msg = Mock(spec=Message)
    msg.message = "Test"
    msg.message_type = PASMessageType.AGENT_MESSAGE
    msg.attachments = []

    # Mock get_notifications to provide one message
    user_agent.get_notifications = Mock(return_value=([msg], [], []))

    # Mock base_agent.run() to return FAILED state
    user_agent.react_agent.run = Mock(return_value="")
    user_agent.react_agent.custom_state = {"running_state": RunningState.FAILED}
    user_agent.react_agent.get_agent_logs = Mock(return_value=[Mock()])

    with pytest.raises(RuntimeError, match="User agent failed"):
        user_agent.agent_loop(current_tools=[], max_turns=1)


@patch("pas.agents.user.agent.time.sleep")
def test_agent_loop_respects_max_turns(mock_sleep, user_agent, mock_notification_system):
    """Test agent_loop stops after max_turns."""
    user_agent._initialized = True
    user_agent.react_agent.notification_system = mock_notification_system
    user_agent.init_tools = Mock()

    msg = Mock(spec=Message)
    msg.message = "Test"
    msg.message_type = PASMessageType.AGENT_MESSAGE
    msg.attachments = []

    # Mock get_notifications to always return a message (would loop forever without max_turns)
    user_agent.get_notifications = Mock(return_value=([msg], [], []))

    user_agent.react_agent.run = Mock(return_value="Response")
    user_agent.react_agent.custom_state = {"running_state": RunningState.TERMINATED}

    user_agent.agent_loop(current_tools=[], max_turns=3)

    # Should have called run() exactly 3 times
    assert user_agent.react_agent.run.call_count == 3


@patch("pas.agents.user.agent.time.sleep")
def test_agent_loop_sleeps_when_no_notifications(mock_sleep, user_agent, mock_notification_system):
    """Test agent_loop sleeps when no notifications are available."""
    user_agent._initialized = True
    user_agent.react_agent.notification_system = mock_notification_system
    user_agent.init_tools = Mock()

    # Mock get_notifications to return empty lists (avoid infinite loop)
    user_agent.get_notifications = Mock(side_effect=[
        ([], [], []),  # First call: no notifications, will sleep
        ([], [], [MessageType.ENVIRONMENT_STOP]),  # Second call: stop to exit loop
    ])

    # Run agent loop
    user_agent.agent_loop(current_tools=[])

    # Verify sleep was called once
    mock_sleep.assert_called_once_with(1)
