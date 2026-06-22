# Agent Gateway 与 MCP 统一记录入口

本文定义 liuAgent Core 如何被 ProjectChat、桌面端、CLI 和外部系统复用。重点不是新增一套后端 agent，而是把智能体会话入口、需求记录入口和本地执行边界固定下来，避免后续把用户本机工具重新做回服务端 Docker。

## 目标

- 让 `liuAgent Core` 成为可被多系统复用的本地智能体运行时。
- 让智能体对话和 MCP 触发任务都通过 `Unified MCP` 记录需求、任务树、工作事实和审计摘要。
- 让 ProjectChat 退回到 `ProjectChat Adapter` 角色，不承载 agent core。
- 让外部系统通过 `Agent Gateway` 创建标准化调用，不直接读写本地 workspace。
- 保持现有统一查询 MCP 语义不变，只在其上增加 agent 会话记录和适配边界。

## 非目标

- 不把用户本地文件、命令、patch、下载、浏览器、本地 MCP 工具迁到服务端 Docker 执行。
- 不让后端保存或下发明文模型 API key 给网页前端。
- 不重写现有统一查询 MCP 的 `bind_project_context`、任务树、工作会话和记忆接口语义。
- 不让业务系统直接调用 Tool Runtime 或绕过 Permission Gate。

## 总体链路

```text
ProjectChat / External System / CLI / Desktop UI
  -> Adapter
  -> Agent Gateway
  -> Unified MCP: RequirementSession + task tree + work facts
  -> ProjectContextBundle / PromptBundle / ToolManifestBundle
  -> Desktop Adapter / Local Runner
  -> liuAgent Core
  -> Tool Runtime / Permission Gate / Audit / State
  -> 用户本机 workspace
```

核心边界：

```text
业务系统不直接驱动 Agent Core，也不直接写本地 workspace。
业务系统通过 Agent Gateway 创建 AgentInvocation，并通过 Unified MCP 记录 RequirementSession。
Desktop Adapter 拉取 ProjectContextBundle 和 PromptBundle 后，在本地生成 AgentRuntimeSession。
本地工具执行只发生在 Desktop/Tauri/Local Runner。
服务端只保存配置、需求、任务树、记忆和审计摘要。
```

## 核心边界

| 模块 | 负责 | 不负责 |
| --- | --- | --- |
| `Agent Gateway` | 标准化创建 `AgentInvocation`，绑定项目、会话、智能体、提示词和 workspace 元数据 | 执行本地工具、读取用户文件、直接调用命令 |
| `Unified MCP` | 记录 `RequirementSession`、任务树、工作事实、记忆和审计摘要 | 替代 Tool Runtime、绕过本地权限 |
| `Desktop Adapter` | 连接 Tauri、本地 workspace、本地权限 UI、本地工具结果回传 | 把本地凭据上传服务端 |
| `ProjectChat Adapter` | 把项目聊天消息转换成 `AgentInvocation`，展示事件和结果 | 自己实现 agent core 或直接执行工具 |
| `External System Adapter` | 把第三方系统需求转换成标准调用并订阅事件 | 直接写 liuAgent 本地状态文件 |
| `Backend` | 提供项目、用户、智能体、提示词、模型配置、需求和记忆数据 | 在 Docker 中执行用户本机文件/命令工具 |

## 核心对象

### AgentGateway

统一接入门面。它接收不同 Adapter 的请求，生成可审计的 `AgentInvocation`。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `gateway_id` | string | 是 | 接入入口标识，例如 `project_chat`、`desktop`、`external_api`。 |
| `protocol_version` | string | 是 | Agent Gateway 协议版本。 |
| `adapter_kind` | string | 是 | `project_chat`、`desktop`、`cli`、`external_system`。 |
| `capabilities` | string[] | 是 | 接入端能力，例如 `event_stream`、`local_runner`、`mcp_recording`。 |

### AgentInvocation

一次业务系统发起的智能体调用请求。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `invocation_id` | string | 是 | 调用 ID，用于幂等和审计。 |
| `source` | string | 是 | 来源系统，例如 `project_chat`、`mcp_trigger`、`external_api`。 |
| `project_id` | string | 是 | 项目 ID。 |
| `chat_session_id` | string | 是 | 需求和任务树绑定会话。 |
| `user_message` | string | 是 | 用户输入或 MCP 触发描述。 |
| `agent_id` | string | 否 | 绑定智能体。为空时由项目默认策略选择。 |
| `workspace_binding` | object | 否 | 本地 workspace 元数据，只保存路径声明和授权状态，不让服务端访问路径内容。 |
| `record_policy` | object | 是 | 是否写入 `RequirementSession`、任务树、工作事实、审计摘要。 |

### RequirementSession

需求记录对象。它是智能体对话和 MCP 任务的统一记录锚点。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `project_id` | string | 是 | 所属项目。 |
| `chat_session_id` | string | 是 | 统一会话 ID。 |
| `requirement_id` | string | 是 | 需求记录 ID。 |
| `source` | string | 是 | `project_chat`、`agent_chat`、`mcp_trigger`、`external_system`。 |
| `root_goal` | string | 是 | 用户目标。 |
| `task_tree_id` | string | 否 | Unified MCP 生成的任务树 ID。 |
| `work_session_id` | string | 否 | 工作会话 ID。 |
| `local_record_path` | string | 否 | 本地 `.ai-employee/requirements/<project_id>/<chat_session_id>.json`。 |
| `sync_state` | string | 是 | `local_only`、`syncing`、`synced`、`failed`。 |

### ProjectContextBundle

服务端下发给本地运行时的项目上下文包。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `project_id` | string | 是 | 项目 ID。 |
| `project_profile` | object | 是 | 项目基础信息。 |
| `agent_bindings` | object[] | 是 | 项目绑定智能体。 |
| `rules` | object[] | 是 | 项目规则和执行约束。 |
| `skills` | object[] | 是 | 可用技能元数据。 |
| `memory_refs` | object[] | 否 | 可读取的记忆引用。 |

`ProjectContextBundle` 只能包含配置、提示词、规则和引用，不包含用户本地文件内容。

### PromptBundle

一次运行可用的提示词包。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `prompt_bundle_id` | string | 是 | 提示词包版本 ID。 |
| `system_prompt` | string | 是 | 系统提示词。 |
| `project_prompt` | string | 否 | 项目提示词。 |
| `agent_prompt` | string | 否 | 智能体提示词。 |
| `tool_instructions` | string | 否 | 工具使用约束。 |
| `mcp_recording_instructions` | string | 是 | RequirementSession 和任务树记录规则。 |

### ToolManifestBundle

工具清单包，用于告诉模型和 Core 当前可调用工具。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `tool_bundle_id` | string | 是 | 工具包版本 ID。 |
| `builtin_tools` | object[] | 是 | 本地内置工具定义。 |
| `mcp_tools` | object[] | 否 | MCP 工具定义。 |
| `risk_policy` | object | 是 | 风险等级和审批策略。 |
| `execution_scope` | object | 是 | workspace、网络、命令执行边界。 |

### AgentRuntimeSession

Desktop/Tauri 本地生成的实际运行会话。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `runtime_session_id` | string | 是 | 本地运行会话 ID。 |
| `requirement_session` | RequirementSession | 是 | 记录锚点。 |
| `project_context` | ProjectContextBundle | 是 | 项目上下文。 |
| `prompt_bundle` | PromptBundle | 是 | 提示词包。 |
| `tool_manifest` | ToolManifestBundle | 是 | 工具清单。 |
| `state_path` | string | 是 | 本地 state/checkpoint 路径。 |

### AgentRuntimeEvent

运行时输出给 Adapter 和 Unified MCP 的事件。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `event_id` | string | 是 | 事件 ID。 |
| `runtime_session_id` | string | 是 | 本地运行会话 ID。 |
| `chat_session_id` | string | 是 | 需求会话 ID。 |
| `type` | string | 是 | `message_delta`、`tool_started`、`tool_result`、`approval_required`、`requirement_recorded`、`work_fact_saved`。 |
| `payload` | object | 是 | 事件内容。 |
| `audit_summary` | object | 否 | 可上传服务端的脱敏审计摘要。 |

## MCP 统一记录命令

Agent Gateway 不新增平行的需求记录系统。它只编排调用现有 Unified MCP 能力：

1. `bind_project_context(project_id, chat_session_id, root_goal, workspace_path)`：绑定项目和会话。
2. `start_work_session(project_id, chat_session_id, goal, workspace_path)`：创建工作轨迹。
3. `get_current_task_tree(project_id, chat_session_id)`：读取当前任务树并确认没有挂到旧需求。
4. `update_task_node_status(...)`：开始或验证节点。
5. `complete_task_node_with_verification(...)`：完成节点并写入验证。
6. `save_work_facts(...)` / `append_session_event(...)`：记录关键事实和阶段事件。

本地也必须维护唯一 requirement 对象：

```text
.ai-employee/requirements/<project_id>/<chat_session_id>.json
```

该文件至少保留：

- `workflow_skill`
- `record_path`
- `storage_scope`
- `task_tree`
- `current_task_node`
- `task_branches`
- `history`

## ProjectChat Adapter

ProjectChat 是业务入口，不是 agent core。

职责：

- 把聊天消息包装成 `AgentInvocation`。
- 从服务端读取项目、智能体、提示词和模型配置元数据。
- 在桌面端可用时把调用交给 Desktop Adapter / Tauri。
- 展示 `AgentRuntimeEvent`、审批请求、工具时间线和最终消息。
- 把本地工具结果和脱敏审计摘要回写到服务端记录。

禁止：

- 在 Vue 里重写 Tool Runtime。
- 在服务端 WebSocket 中直接执行用户 workspace 文件/命令工具。
- 本地运行失败时静默回退到服务端 Docker 执行。

## Desktop Adapter

Desktop Adapter 是本地执行主入口。

职责：

- 读取用户选择或项目绑定的 workspace。
- 拉取 `ProjectContextBundle`、`PromptBundle`、`ToolManifestBundle`。
- 创建 `AgentRuntimeSession`。
- 通过 Tauri 调用本地 Tool Runtime。
- 展示权限 UI，并把用户决策写入本地审计。
- 将脱敏 `AgentRuntimeEvent` 和 requirement 同步到 Unified MCP。

本地工具执行只允许发生在 Desktop/Tauri/Local Runner。服务端只能拿到结构化结果、摘要和审计元数据。

## 外部系统 Adapter

外部系统可以接入，但必须走标准对象：

```text
External System
  -> AgentInvocation
  -> Agent Gateway
  -> Unified MCP RequirementSession
  -> Desktop Adapter / Local Runner
```

外部系统只需要知道：

- 创建需求：传 `project_id`、`chat_session_id`、`user_message`、`source`。
- 订阅事件：消费 `AgentRuntimeEvent`。
- 查询状态：通过 Unified MCP 或项目 API 查任务树、工作事实和交付摘要。

外部系统不需要知道 liuAgent Core 的内部状态机，也不能直接执行本地工具。

## Prompt、项目、智能体如何通讯

1. 后端保存项目绑定的智能体、提示词、规则、模型配置和技能元数据。
2. Adapter 创建 `AgentInvocation` 时只传绑定 ID 和用户输入。
3. Agent Gateway 组装 `ProjectContextBundle`、`PromptBundle`、`ToolManifestBundle`。
4. Desktop Adapter 在本机启动 `AgentRuntimeSession`。
5. liuAgent Core 使用这些 bundle 进行模型请求、工具选择、权限判断和状态推进。
6. 运行事件通过 Adapter 展示，并通过 Unified MCP 写入需求记录。

这样项目、提示词和智能体配置仍由服务端统一管理，但执行发生在用户本地。

## 兼容策略

- 现有统一查询 MCP 是 canonical 记录入口，不改变已有接口含义。
- 新增 Agent Gateway 只作为调用编排层，不能替换 `bind_project_context` 和任务树闭环。
- ProjectChat 现有 WebSocket 可以保留为事件通道，但本地工具执行必须由 Desktop Adapter 完成。
- 旧的服务端 builtin tool 实现只能作为历史兼容或测试参考，不能成为用户本地工具主路径。
- 后续支持服务端模型网关时，也只代理模型调用；用户本地文件、命令和 MCP local tools 仍在本机执行。

## 安全与审计

- 本地凭据不进入服务端审计。
- 审计摘要只能包含工具名、风险等级、路径摘要、命令摘要、结果摘要、错误码和用户决策。
- 写文件、命令、网络写入、下载、MCP 写操作必须经过 Permission Gate。
- 用户拒绝权限后，Adapter 必须把拒绝事件交给 Core，不能自行重试。
- workspace 绑定只证明用户本机选择了路径，不代表服务端可以访问该路径。

## 后续实现顺序

1. 在 Tauri Runtime 中落地 `AgentInvocation`、`RequirementSession`、`AgentRuntimeSession` 类型。
2. 把 `liuagent_start_local_chat` 从 mock 流程升级为本地模型主循环。
3. 将 ProjectChat 的 local-runner 路径改成创建 `AgentInvocation`，再由 Desktop Adapter 执行。
4. 补齐 MCP 本地 adapter：`list_mcp_tools`、`read_mcp_resource`、`call_mcp_tool`。
5. 增加离线 outbox：本地先写 requirement 和审计摘要，网络恢复后同步 Unified MCP。
6. 给外部系统提供最小接入示例：创建 invocation、订阅事件、查询 requirement/task tree。
