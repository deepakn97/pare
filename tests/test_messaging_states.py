"""Tests for StatefulMessagingApp and messaging states."""

from collections.abc import Generator

import pytest

from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.messaging.states import ConversationList, ConversationOpened


@pytest.fixture
def messaging_app() -> Generator[StatefulMessagingApp, None, None]:
    """Create a StatefulMessagingApp instance for testing."""
    yield StatefulMessagingApp(name="messaging")


class TestInitialState:
    """Tests for app initialization."""

    def test_app_initializes_with_conversation_list_state(self, messaging_app: StatefulMessagingApp) -> None:
        """App should initialize with ConversationList as initial state."""
        assert messaging_app.current_state is not None
        assert isinstance(messaging_app.current_state, ConversationList)
        assert len(messaging_app.navigation_stack) == 0


class TestStateTransition:
    """Tests for state transitions."""

    def test_transition_to_conversation_opened(self, messaging_app: StatefulMessagingApp) -> None:
        """Should correctly transition from ConversationList to ConversationOpened."""
        new_state = ConversationOpened(conversation_id="test123")
        messaging_app.set_current_state(new_state)

        assert isinstance(messaging_app.current_state, ConversationOpened)
        assert messaging_app.current_state.conversation_id == "test123"
        assert len(messaging_app.navigation_stack) == 1
        assert isinstance(messaging_app.navigation_stack[0], ConversationList)

    def test_navigation_stack_tracks_history(self, messaging_app: StatefulMessagingApp) -> None:
        """Navigation stack should track state transition history."""
        # Open first conversation
        state1 = ConversationOpened(conversation_id="conv1")
        messaging_app.set_current_state(state1)

        # Open second conversation
        state2 = ConversationOpened(conversation_id="conv2")
        messaging_app.set_current_state(state2)

        assert len(messaging_app.navigation_stack) == 2
        assert messaging_app.navigation_stack[0].__class__.__name__ == "ConversationList"
        assert isinstance(messaging_app.navigation_stack[1], ConversationOpened)
        assert messaging_app.navigation_stack[1].conversation_id == "conv1"


class TestGoBack:
    """Tests for go_back functionality."""

    def test_go_back_from_conversation_to_list(self, messaging_app: StatefulMessagingApp) -> None:
        """Should navigate back from ConversationOpened to ConversationList."""
        # Open a conversation
        new_state = ConversationOpened(conversation_id="test123")
        messaging_app.set_current_state(new_state)

        # Go back
        result = messaging_app.go_back()

        assert isinstance(messaging_app.current_state, ConversationList)
        assert len(messaging_app.navigation_stack) == 0
        assert "ConversationList" in result

    def test_go_back_at_initial_state(self, messaging_app: StatefulMessagingApp) -> None:
        """Should return message when already at initial state."""
        result = messaging_app.go_back()

        assert "Already at the initial state" in result
        assert isinstance(messaging_app.current_state, ConversationList)


class TestUserToolsFiltering:
    """Tests for state-dependent user tool filtering."""

    def test_conversation_list_tools(self, messaging_app: StatefulMessagingApp) -> None:
        """ConversationList state should expose list and search tools."""
        tools = messaging_app.get_user_tools()
        tool_names = [tool.name for tool in tools]

        assert any("list_recent_conversations" in name for name in tool_names)
        assert any("open_conversation" in name for name in tool_names)
        assert any("search_conversations" in name for name in tool_names)
        assert not any("send_message" in name for name in tool_names)
        assert not any("go_back" in name for name in tool_names)  # Stack is empty

    def test_conversation_opened_tools(self, messaging_app: StatefulMessagingApp) -> None:
        """ConversationOpened state should expose message tools and go_back."""
        # Transition to ConversationOpened
        new_state = ConversationOpened(conversation_id="test123")
        messaging_app.set_current_state(new_state)

        tools = messaging_app.get_user_tools()
        tool_names = [tool.name for tool in tools]

        assert any("send_message" in name for name in tool_names)
        assert any("read_messages" in name for name in tool_names)
        assert any("go_back" in name for name in tool_names)  # Stack not empty
        assert not any("list_recent_conversations" in name for name in tool_names)

    def test_go_back_only_available_when_stack_not_empty(self, messaging_app: StatefulMessagingApp) -> None:
        """go_back should only appear in tools when navigation stack has items."""
        # Initially no go_back
        tools = messaging_app.get_user_tools()
        tool_names = [tool.name for tool in tools]
        assert not any("go_back" in name for name in tool_names)

        # After transition, go_back appears
        new_state = ConversationOpened(conversation_id="test123")
        messaging_app.set_current_state(new_state)
        tools = messaging_app.get_user_tools()
        tool_names = [tool.name for tool in tools]
        assert any("go_back" in name for name in tool_names)


class TestLateBinding:
    """Tests for late binding pattern."""

    def test_state_created_without_app_reference(self) -> None:
        """States should be created without app reference."""
        state = ConversationOpened(conversation_id="test123")
        assert state._app is None

    def test_state_bound_when_set(self, messaging_app: StatefulMessagingApp) -> None:
        """State should be bound to app when set_current_state is called."""
        state = ConversationOpened(conversation_id="test123")
        assert state._app is None

        messaging_app.set_current_state(state)

        # State should now be bound
        assert state.app == messaging_app

    def test_binding_only_happens_once(self, messaging_app: StatefulMessagingApp) -> None:
        """Binding should only happen once even if set_current_state called multiple times."""
        state = ConversationOpened(conversation_id="test123")
        messaging_app.set_current_state(state)

        original_app = state._app

        # Set again (shouldn't rebind)
        messaging_app.set_current_state(state)
        assert state._app is original_app


class TestEntryExitHooks:
    """Tests for on_enter and on_exit hooks."""

    def test_on_enter_called_on_state_transition(self, messaging_app: StatefulMessagingApp) -> None:
        """on_enter should be called when transitioning to a state."""

        class TestState(ConversationOpened):
            def __init__(self, conversation_id: str) -> None:
                super().__init__(conversation_id)
                self.enter_called = False

            def on_enter(self) -> None:
                self.enter_called = True

        state = TestState(conversation_id="test123")
        messaging_app.set_current_state(state)

        assert state.enter_called

    def test_on_exit_called_on_state_transition(self, messaging_app: StatefulMessagingApp) -> None:
        """on_exit should be called when leaving a state."""

        class TestState(ConversationList):
            def __init__(self) -> None:
                super().__init__()
                self.exit_called = False

            def on_exit(self) -> None:
                self.exit_called = True

        # Set initial state to TestState
        test_state = TestState()
        messaging_app.set_current_state(test_state)

        # Transition to another state
        new_state = ConversationOpened(conversation_id="test123")
        messaging_app.set_current_state(new_state)

        assert test_state.exit_called
