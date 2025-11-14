from __future__ import annotations

from are.simulation.apps.app import ToolType
from are.simulation.tool_utils import ToolAttributeName

from pas.apps.messaging.app import StatefulMessagingApp
from pas.apps.messaging.states import ConversationList


def _func_names(tools):
    return {t.func_name for t in tools if getattr(t, "function", None) is not None}


def test_user_tools_from_state_are_discovered_and_bound_to_state():
    app = StatefulMessagingApp()
    # Ensure we start at ConversationList
    assert isinstance(app.current_state, ConversationList)

    # Discover USER tools via PAS override
    user_tools = app.get_tools_with_attribute(
        ToolAttributeName.USER, ToolType.USER
    )
    names = _func_names(user_tools)

    # Verify state-defined user tools are present
    assert {"list_recent_conversations", "search_conversations", "open_conversation"} <= names

    # Verify tools are bound to the state instance (not the app)
    state = app.current_state
    assert state is not None
    for tool in user_tools:
        assert tool.class_instance is state


def test_event_only_tools_include_add_conversation():
    app = StatefulMessagingApp()
    # Special (None, None) path should find event-registered methods without tool decorators
    event_only_tools = app.get_tools_with_attribute(None, None)
    names = _func_names(event_only_tools)

    # MessagingAppV2.add_conversation is decorated with @event_registered only
    assert "add_conversation" in names

    # Ensure write operation is detected from @event_registered(OperationType.WRITE)
    add_conv_tool = next(t for t in event_only_tools if t.func_name == "add_conversation")
    assert add_conv_tool.write_operation is True


def test_app_tools_fallback_to_meta_are_behavior():
    app = StatefulMessagingApp()
    # Should include app-level tools from MessagingAppV2 (decorated with @app_tool)
    app_tools = app.get_tools_with_attribute(ToolAttributeName.APP, ToolType.APP)
    names = _func_names(app_tools)

    # A few representative MessagingAppV2 app tools
    expected = {"get_user_id", "get_user_name_from_id", "lookup_user_id", "send_message"}
    assert expected & names  # intersection non-empty to avoid coupling to all functions


def test_env_tools_are_discovered_from_base_app():
    app = StatefulMessagingApp()
    env_tools = app.get_tools_with_attribute(ToolAttributeName.ENV, ToolType.ENV)
    names = _func_names(env_tools)

    # Representative env tools from MessagingAppV2
    expected_env = {
        "create_group_conversation",
        "create_and_add_message",
        "add_participant_to_conversation",
        "remove_participant_from_conversation",
        "change_conversation_title",
    }
    # Must contain at least a subset (in case of future changes)
    assert expected_env & names


def test_data_tools_are_empty_for_stateful_messaging_app():
    app = StatefulMessagingApp()
    data_tools = app.get_tools_with_attribute(ToolAttributeName.DATA, ToolType.DATA)
    # MessagingAppV2 does not define data_tools
    assert _func_names(data_tools) == set()
