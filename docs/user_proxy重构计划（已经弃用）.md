## 用户代理和 Proxy 重构计划

### 现状分析
当前的 `StatefulUserAgentProxy` 实现有以下问题：
1. 直接依赖 `StateAwareEnvironmentWrapper`，违反了依赖倒置原则
2. 实现了自定义的工具查找和执行逻辑 (`_find_tool`, `_execute_tool` 等)
3. 实现了自定义的消息解析逻辑 (`_parse_json_plan`, `_parse_command_plan` 等)
4. 没有复用 Meta-ARE 的成熟代理框架
5. PAS应用的用户工具没有遵循Meta-ARE工具规范

### 重构目标
重构 UserAgent 以完全复用 Meta-Agents Research Environments 的基础设施，包括：
1. 继承 `BaseAgent` 类以复用其 ReAct 框架
2. 重新设计PAS应用的用户工具，使其遵循Meta-ARE工具规范
3. 移除自定义的工具查找和执行逻辑
4. 保持与现有接口的兼容性

### 详细实现方案

#### 1. 重新设计PAS应用的用户工具
在原生的Meta-ARE中，工具需要遵循特定的规范：
- 继承自 `Tool` 基类
- 具有 `name` 和 `description` 属性
- 实现 `__call__` 方法

我们需要修改PAS应用的用户工具定义，使其符合Meta-ARE规范：

```python
# 示例：重新设计PAS应用的用户工具
class ListContactsTool(Tool):
    name = "list_contacts"
    description = "List all contacts in the address book"

    def __init__(self, app_instance):
        self.app_instance = app_instance

    def __call__(self) -> str:
        try:
            result = self.app_instance.list_contacts()
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as e:
            return f"Error listing contacts: {str(e)}"
```

#### 2. 创建 `StatefulUserAgent` 类
```python
class StatefulUserAgent(BaseAgent):
    def __init__(
        self,
        llm_engine: Callable,
        tools: dict[str, Tool] = {},
        system_prompts: dict[str, str] = {},
        max_iterations: int = 10,
        max_turns: int = 40,
        summary_style: Literal["plain", "structured"] = "plain",
        **kwargs
    ):
        # 使用 JsonActionExecutor
        action_executor = JsonActionExecutor(llm_engine=llm_engine)

        # 设置默认系统提示
        if not system_prompts:
            system_prompts = {
                "system_prompt": self._get_default_system_prompt()
            }

        # 调用父类构造函数
        super().__init__(
            llm_engine=llm_engine,
            system_prompts=system_prompts,
            tools=tools,
            action_executor=action_executor,
            max_iterations=max_iterations,
            **kwargs
        )

        self.name = "stateful_user_agent"
        self.max_turns = max_turns
        self.summary_style = summary_style
        self.turns_taken = 0
        self.transcript: list[dict[str, str]] = []
        self.tool_history: list[ToolInvocation] = []

    def _get_default_system_prompt(self) -> str:
        return """You are an AI user agent that interacts with other agents on behalf of a human user.

Your role is to:
1. Receive messages from other agents
2. Determine appropriate actions based on available tools
3. Execute actions and respond to agents

Key principles:
- Always think step by step and explain your reasoning
- Be concise and clear in your communications
- Only use the tools provided to you
- When you need to send a message to the user, use the 'AgentUserInterface__send_message_to_user' tool

Available tools: <<tool_descriptions>>

Always format your responses in JSON format when using tools."""
```

#### 3. 系统提示设计
设计专门针对用户代理的系统提示，明确其角色和职责：

```python
USER_AGENT_SYSTEM_PROMPT = """You are an AI user agent that interacts with other agents on behalf of a human user.

Your role is to:
1. Receive messages from other agents
2. Determine appropriate actions based on user tools
3. Execute actions and respond to agents

Key principles:
- Always think step by step and explain your reasoning
- Be concise and clear in your communications
- Only use the tools provided to you
- When you need to send a message to the user, use the 'AgentUserInterface__send_message_to_user' tool
- When you need to execute a user action, use the appropriate app tool (e.g., 'Contacts__list_contacts')

Available tools: <<tool_descriptions>>

Current time: <<curent_time_description>>
Notification system: <<notification_system_description>>

Remember, you are representing a human user, so act accordingly."""
```

#### 4. 接口兼容性实现
为了保持与现有代码的兼容性，需要实现以下接口：

```python
class StatefulUserAgent(BaseAgent):
    # ... 其他代码 ...

    @property
    def transcript(self) -> list[dict[str, str]]:
        """Conversation transcript for debugging purposes."""
        return self.transcript

    @property
    def tool_history(self) -> list:
        """Executed tool invocations in chronological order."""
        return self.tool_history

    def init_conversation(self) -> str:
        """Reset session state and return an empty opener."""
        self.turns_taken = 0
        self.transcript.clear()
        self.tool_history.clear()
        return ""

    def reply(self, message: str) -> str:
        """Plan and execute user actions in response to an agent message."""
        if self.turns_taken >= self.max_turns:
            raise TurnLimitReached("Maximum user turns exhausted")

        # 运行代理处理消息
        result = self.run(task=message)
        self.turns_taken += 1
        return result
```

#### 5. 场景构建逻辑更新
在 `pas/scenarios/base.py` 中更新构建逻辑：

```python
# 替换原有的 StatefulUserAgentProxy 实例化
def build_proactive_stack(...):
    # ... 其他代码 ...

    # 创建用户代理工具
    # PAS应用的用户工具现在遵循Meta-ARE规范，可以直接使用
    user_tools = {}
    for app in stateful_apps:
        # 从遵循Meta-ARE规范的PAS应用中获取用户工具
        app_user_tools = app.get_meta_are_user_tools()  # 新方法
        for tool in app_user_tools:
            user_tools[f"{app.name}__{tool.name}"] = tool

    # 创建 StatefulUserAgent
    user_agent = StatefulUserAgent(
        llm_engine=user_llm,
        tools=user_tools,
        max_turns=max_user_turns,
        summary_style="structured"
    )

    # 使用 user_agent 替代 user_proxy
    # ...
```

### 实施步骤

1. **重构PAS应用的用户工具**
   - 修改现有PAS应用的用户工具，使其继承自Meta-ARE的`Tool`基类
   - 确保工具具有正确的`name`和`description`属性
   - 实现`__call__`方法以提供工具功能
   - 为每个应用添加`get_meta_are_user_tools()`方法

2. **创建核心类**
   - 实现 `StatefulUserAgent` 类，继承自 `BaseAgent`
   - 实现系统提示和工具处理逻辑

3. **接口兼容性实现**
   - 确保新的 `StatefulUserAgent` 提供与原有 `StatefulUserAgentProxy` 相同的公共接口
   - 实现 `transcript`, `tool_history`, `init_conversation`, `reply` 等属性和方法

4. **场景构建逻辑更新**
   - 修改 `pas/scenarios/base.py` 中的 `build_proactive_stack` 函数
   - 确保工具正确注入到新的 `StatefulUserAgent` 中
   - 确保 `AgentUserInterface` 工具能够被自动注入

5. **测试验证**
   - 更新相关测试用例
   - 验证重构后的功能与原有实现一致
   - 确保所有现有测试都能通过

6. **文档更新**
   - 更新相关文档说明新的实现方式
   - 提供迁移指南

### 预期收益

1. **完全遵循Meta-ARE规范**：PAS应用的用户工具现在完全符合Meta-ARE工具规范
2. **复用成熟框架**：完全复用 Meta-ARE 的 ReAct 框架，减少维护成本
3. **更好的扩展性**：通过标准工具机制，更容易添加新功能
4. **更清晰的架构**：符合依赖倒置原则，降低模块间耦合
5. **更好的日志和监控**：复用 Meta-ARE 的日志系统
6. **更好的错误处理**：复用 Meta-ARE 的错误处理机制
7. **与Meta-ARE生态系统完全兼容**：能够使用Meta-ARE的所有特性和工具
