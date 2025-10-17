# StatefulUserAgent 重构计划

## 背景与目标
- 目前存在两套用户交互实现：旧的 `StatefulUserAgentProxy`（`pas/user_proxy/stateful.py:33`）以及实验性的 `StatefulUserAgent`（`pas/user_proxy/agent.py:39`）。两者都没有完全复用 Meta ARE 提供的 agent builder 机制，导致工具注册、生命周期管理与官方实现脱节。
- 文档《重构铁律》（`docs/重构铁律.md`）要求我们严格对齐 Meta ARE 框架：仿照官方文档中的 `MyCustomAgent` 模式，仅向代理传入工具和 LLM，引入必要的配置类，避免手写 `_find_tool`、`_execute_tool` 等设施，并遵循命名约定。
- 重构目标是在尽量精简代码的前提下，迁移到一套“官方推荐”架构，使用户代理完全复用 Meta ARE 设施，同时保留现有 PAS 功能（转录、通知消费、规划器接口等）。

## Meta ARE 约束与启示
- `BaseAgent` 负责所有回合（step）调度、日志记录、LLM 搭桥和工具调用。自定义代理只需要：
  - 设定系统提示、动作执行器（常用 `JsonActionExecutor`）和可选的 `ConditionalStep` 钩子；
  - 通过 `run()/step()` 触发推理，无需管理事件循环；
  - 在 `initialize()` 之后保证工具初始化（`init_tools()`）；
  - 使用 `append_agent_log()`/`build_history_from_logs()` 等提供的日志 API。
- Agent builder（`are.simulation.agents.default_agent.agent_factory`）通常依靠配置（如 `ARESimulationReactBaseAgentConfig`）实例化代理。没有匹配的配置类，Meta ARE 的统一装配流程无法构建我们的代理。
- 工具约定：
  - 全部 `Tool` 子类必须设置 `name`、`description`、`inputs`（参数 schema）并实现 `forward` 方法；
  - 工具注册统一交给 `JsonActionExecutor`，无需再扩展自定义 executor；
  - 代理通过 `self.tools` 维护可调用工具集，`Toolbox` 仅用于生成描述文本。

## 现状痛点
- `StatefulUserAgentProxy` 将环境指针与工具执行耦合在一起（`pas/user_proxy/stateful.py:69`），并手写 `_execute_tool`、`_find_tool`（`stateful.py:126`、`stateful.py:164`），与重构目标相悖。
- `StatefulUserAgent` 试图继承 `BaseAgent`，但：
  - 缺少配套配置类与 builder，无法参与统一装配；
  - `_transcript`、`_tool_history` 等内部字段与公开属性并存，接口层面缺少清晰的状态抽象；
  - 调用 `run()` 后直接把返回值转换成纯字符串输出，忽略了 `BaseAgent` 提供的日志、终止标记等结构化结果，导致上层难以获取丰富上下文；
  - 没有处理 `CompletedEvent` 日志，也没有公开行动摘要供 planner 回溯。
- `StatefulApp.get_meta_are_user_tools()`（`pas/apps/core.py:186`）将 Meta ARE Tool 生成逻辑塞在基类中，使用临时类嵌套，类型信息缺失，且不同 app 之间无法共享适配逻辑。
- 规划器 `build_stateful_user_planner`（`pas/system/user.py:38`）直接读取 `StatefulUserAgentProxy.last_tool_invocations`（以及可选的通知元信息）；完全替换为 Meta Agent 后必须提供等价的上下文出口。

## 重构设计

### 1. Agent 架构对齐
- 新建 `StatefulUserAgent` 模块（沿用 `pas/user_proxy/agent.py`）：
  - 继承 `BaseAgent`（与官方 `MyCustomAgent` 一致），通过组合方式暴露与 `UserProxy` 兼容的 `reply()/init_conversation()` API；
  - 仿照默认 `are_simulation_react_json_agent` 配置系统提示、`JsonActionExecutor`、`ConditionalStep` 以及终止逻辑；
  - 审视状态字段的命名与封装，保留现有私有存储（如 `_transcript`）与只读属性的分离，同时确保新接口不再暴露多余前缀给调用方；
  - 将通知消费、事件响应逻辑包装成 `consume_notifications()`、`react_to_event()`，直接使用 `self.notification_system`；
  - 引入 `_record_tool_call()` 等内部辅助方法，统一通过 `append_agent_log()` 等基础 API 跟踪执行，而不是维护独立队列。
- 自定义系统提示策略：
  - 提供基础指令模板，明确代理的角色（模拟用户）、行为准则、工具使用规范以及总结/汇报方式。
  - 设计一个上下文注入器，将当前聚焦 app、最新通知摘要、时间信息等动态内容拼接进系统提示，让 ReAct 循环拥有完整情境。
  - 为不同场景预留可选段落（如紧急通知优先级、planner 建议等），使用配置对象控制启用，减少 prompt 重复。
  - 建立单元测试/快照测试验证 prompt 结构，避免回归。
- 增加配置与工厂：
  - 已实现 `StatefulUserAgentConfig`（继承 `ARESimulationReactBaseAgentConfig`），用于描述系统提示、最大迭代数以及写操作超时时间；
  - 后续仍需提供 `StatefulUserAgentRunnableConfig`（实现 `RunnableARESimulationAgentConfig`），以便与 `AgentBuilder` 协同；
  - 已提供 `stateful_user_agent_factory()` 和 `StatefulUserAgentBuilder`，结合 runnable config 可在 PAS 侧完成装配；
  - 下一步是与 Meta ARE 原生 `AgentBuilder` / 场景 JSON 对接，使官方流水线也能识别 `pas_stateful_user_agent`。

### 2. 工具链适配
- 抽出独立的 PAS→Meta ARE 工具适配器（可参考 `pas/proactive/react_adapter.py:57` 中的 `PasToolAdapter`）：
  - 将 `StatefulApp.get_meta_are_user_tools()` 重构为复用适配器；避免在方法内部动态定义类；
  - 对工具 `name` 采用 Meta ARE 既有约定：`{app_name}__{function}`，保持与 `JsonActionExecutor` 解析逻辑兼容；
  - 完善参数 `inputs` 的类型和值描述，必要时为常用类型映射 JSON schema；
  - 明确工具是否写操作，借助 `AppTool.write_operation` 记录元数据，并在自定义 action executor 或环境事件回调中等待对应 `CompletedEvent`；不要依赖 `JsonActionExecutor` 默认行为。
- 统一在环境装配时（`pas/scenarios/base.py:73`）读取 adapter 输出，填充 `Toolbox`，由 `StatefulUserAgentConfig` 消费。

### 3. 规划接口整合
- 充分依赖 `BaseAgent` 的 ReAct 循环和 `JsonActionExecutor`：默认路径下由代理内部完成思考→选工具→执行→反思。
- 保留可插拔规划器入口：重构 `build_stateful_user_planner` 与 `LLMUserPlanner`，让它们改用新的协议访问代理状态。这样既满足《重构铁律》中“可以使用 llm planner 组合”的要求，也能继续支持人工或脚本化 planner。
- 为 planner 提供标准化上下文对象：包括最近工具调用、活动 app、通知摘要等，避免直接依赖内部字段。
- 在代理内部维护最近一次工具执行记录（供分析/调试），并通过协议暴露给外部 planner；默认为空时则退回纯 ReAct 流程。

### 4. 环境与通知集成
- 移除 `StatefulUserAgentProxy` 对环境的直接依赖：`notification_system.message_queue` 仍负责转交用户/系统消息，但 `CompletedEvent` 需要通过 `StateAwareEnvironmentWrapper.subscribe_to_completed_events()` 继续派发给代理以驱动导航状态与写操作确认。
- 在代理内部实现统一的通知消费入口（例如 `consume_notifications()`），读取消息队列输出；由 runner 或包装器订阅 `CompletedEvent` 并更新代理维护的状态缓存。
- 通过扩展 `JsonActionExecutor` 或注入 `conditional_post_steps`，在每次工具执行后触发对 `CompletedEvent` 的等待与处理，替代原有 `_find_tool`/`_execute_tool` 逻辑。
- 明确代理与 `StateAwareEnvironmentWrapper` 的交互边界：由 runner 统一持有环境引用并向代理提供事件视图，避免在代理中直接调用 `env.*`。
- `ProactiveAgentUserInterface`（`pas/apps/proactive_agent_ui.py`）改为持有 `StatefulUserAgentProxy`，与现有 `UserProxy` 合约兼容，同时通过协议访问扩展能力。

### 5. 日志与监控
- 统一使用 Meta ARE 的日志机制：
  - 为代理设置专用 logger 名称（例如 `pas.user_agent`）并通过 `BaseAgent.logger` 输出；
  - 利用 `get_agent_logs()` 生成最终的对话/工具流水，替换现有的自管 transcript；
  - 需要自定义 summary 时，统一通过 `summary_builder` 钩子实现，避免在 `run()` 后再读取 `self.last_tool_summary` 等内部字段。

### 6. 接口适配
- 定义最小化的 `UserAgentProtocol`（覆盖 `init_conversation()`、`reply()`、`react_to_event()`、`consume_notifications()`、`transcript` 等属性/方法），作为应用层依赖的统一契约。
- 新增 `StatefulUserAgentProxy`（继承 Meta ARE 原生 `UserProxy`），内部持有 `StatefulUserAgent`，将 `reply()/init_conversation()` 调用委托给代理，保持官方 runner 对 `UserProxy` 的预期不变。
- 更新所有依赖 `StatefulUserAgentProxy` 的组件以使用该协议与包装器：
  - `ProactiveAgentUserInterface` 构造函数仍注入 `UserProxy`，因此传入 `StatefulUserAgentProxy`；同时在需要直接访问扩展能力的地方注入 `UserAgentProtocol`。
  - `ScenarioSetup`、`pas/system/session.py`、`pas/system/user.py` 等数据结构和类型注解迁移到协议；
  - `pas/user_proxy/__init__.py` 仅导出新的代理与协议符号，移除旧 proxy 入口。
- 调整测试、脚本及其他调用点，使其直接引用 `StatefulUserAgent`（或协议实例），并在需要 `UserProxy` 的位置统一使用 `StatefulUserAgentProxy`，彻底切断对旧 proxy API 的依赖。

### 7. 运行调度对齐
- 参考 `are.simulation.agents.default_agent.are_simulation_main.ARESimulationAgent`：
  - `StatefulUserAgentRuntime` 作为 PAS 内的 runner，负责完成工具初始化、系统提示占位符填充、通知轮询与回合循环；
  - 支持订阅 `CompletedEvent`、记录工具调用和超时控制，后续可视需要加入 `pause_env/resume_env` 等高级特性；
  - 在 scenario 装配时，通过 `stateful_user_agent_factory()` + runtime 实例化用户代理，避免手写执行循环；
  - 下一步是在 `AgentBuilder`/场景 JSON 中引用该 runtime，提供统一的配置化装配路径。

## 实施步骤
1. **准备阶段**：梳理 `BaseAgent` 支持的钩子与日志 API；补充针对 `JsonActionExecutor` 的理解和使用范式。
2. **工具适配抽象化**：在 `pas/meta_adapter.py` 中实现 `PasToolAdapter`，重构 `StatefulApp.get_meta_are_user_tools()` 以复用；完善类型映射与错误处理。
3. **代理核心改造**：
   - 重写 `pas/user_proxy/agent.py`，引入配置类、去下划线命名、整合通知/日志；
   - 已实现 `StatefulUserAgentConfig` 与 `stateful_user_agent_factory()`，下一步是补充可序列化的 runnable 配置；
   - 构建系统提示与上下文注入逻辑，支持 ReAct 决策所需的环境/通知信息。
4. **规划器整合**：保留并升级 `LLMUserPlanner`/`build_stateful_user_planner`，通过新协议获取上下文；丰富测试覆盖。
5. **环境装配更新**：在 `pas/scenarios/base.py`、`pas/meta_adapter.py` 等处使用新的代理和工具装配流程；清理对旧 proxy 与 planner 特有字段的访问。
6. **运行调度整合**：`StatefulUserAgentRuntime` 已负责工具注入、通知轮询与事件监听；后续需在 AgentBuilder / 场景 JSON 中引用它，实现真正的配置化装配。
7. **接口适配**：实现 `UserAgentProtocol` 并更新所有依赖 `StatefulUserAgentProxy` 的组件（包括 `ProactiveAgentUserInterface`、`ScenarioSetup`、session 管线、测试等）。
8. **测试与验证**：
   - 改写现有单测 `tests/test_stateful_user_agent.py`，覆盖配置类、工具执行、通知消费、planner 交互；
   - 新增集成测试（例如在一个最小场景下跑一轮 agent-环境交互）确保执行链成立；
   - 运行现有回归测试，确认无破坏。
9. **清理旧实现**：移除 `StatefulUserAgentProxy` 与 planner 相关的残留代码，更新 README/文档说明新的单一实现，并确保外部模块只依赖 `StatefulUserAgent` 或其协议。

## 风险与应对
- **Meta ARE API 演进风险**：配置类和 builder 接口可能因版本差异有所不同。方案中将 `StatefulUserAgentConfig` 与 builder 封装在 PAS 内部，必要时通过适配层隔离外部变化。
- **代理上下文注入**：将原本由 `LLMUserPlanner` 拼装的上下文信息迁移到代理系统提示，需要验证提示格式是否满足 ReAct 需求并在主要场景里调通。
- **工具兼容性**：`PasToolAdapter` 必须覆盖全部 app 的参数类型与默认值，否则 LLM 容易生成无法执行的调用。计划先实现通用逻辑，再针对 Calendar/Email/Messaging 等关键应用添加单元测试。
- **日志/转录一致性**：重构后 transcript 来源于 `BaseAgent`；一旦格式调整，必须同步更新上层消费逻辑。提前梳理日志使用方，保证迁移平滑。

## 验证清单
- ☐ Agent 能通过 Meta ARE builder/场景配置成功实例化，并能处理至少一次 `run()` 调用；
- ✅ 代理内部的 ReAct 循环能够调用工具并得到期望的环境反馈；
- ✅ 通知队列与写操作事件（`CompletedEvent`）在新代理中被正确消费；
- ✅ 所有关联测试（单元 + 集成）通过；
- ☐ 文档与示例代码更新，指导未来开发遵循 Meta ARE 规范。

---
该计划以 Meta ARE 官方 `MyCustomAgent` 模式为蓝本，确保用户代理在 PAS 中与官方生态保持一致，同时逐步淘汰历史遗留的 proxy 实现。
