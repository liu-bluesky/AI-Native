# Tauri 本地 liuAgent Runtime 技术方案

## 1. 背景与目标

`src-tauri` 是桌面端本地 AI 智能体的运行时入口。它的目标是让 AI 智能体在用户电脑上安全执行本地任务，例如读取项目文件、搜索代码、写入文件、应用 patch、执行命令、调用本地 MCP 工具等。

整体设计采用 `local-first` 模式：

- 用户本地 workspace 的文件和命令只在桌面端 Tauri/Rust 中执行。
- 服务端只负责账号、项目、员工、规则、技能、模型配置、记忆和审计摘要等数据能力。
- 前端 Vue 负责界面展示、权限确认、工具执行过程和用户交互。
- 本地 runtime 负责工具执行、权限判断、状态保存、审计摘要和恢复。

核心原则是：服务端不能直接读写用户电脑，本地高风险操作必须经过权限门。

## 2. 总体架构

```text
Vue Desktop UI
  -> Tauri command / event
  -> Desktop Adapter
  -> liuAgent Core
  -> Tool Runtime / Permission Gate / Audit / State
  -> 用户本机 workspace

Python FastAPI 服务端
  -> 项目、员工、规则、技能、模型配置、记忆、审计摘要
  -> 不直接执行用户本地文件、命令、patch 或 MCP 工具
```

通用调用链路：

```text
ProjectChat / External System / CLI / Desktop UI
  -> Agent Gateway
  -> Unified MCP RequirementSession
  -> ProjectContextBundle / PromptBundle / ToolManifestBundle
  -> Desktop Adapter / Local Runner
  -> liuAgent Core
```

这个边界保证了：服务端可以下发上下文、提示词和工具契约，但真正涉及用户电脑的操作必须落到本地 runtime。

## 3. 核心模块

```text
src/
  main.rs
    Tauri command 注册和事件广播入口，保持薄入口。

  liuagent_core/
    mod.rs
      Core 对外入口，负责工具分发。

    types.rs
      定义 ToolExecutionRequest、LocalChatRequest、ToolExecutionResult 等 JSON 协议结构。

    definitions.rs
      内置工具定义注册表，声明工具名、参数 schema、风险等级和权限要求。

    runtime.rs
      本地智能体会话运行时，负责 model loop、tool calls、状态机、恢复和 outbox。

    permission.rs
      权限门，负责生成 approval_required，并处理 approve_once / approve_session。

    workspace.rs
      workspace 路径安全校验，拒绝绝对路径逃逸和 `../` 逃逸。

    audit.rs
      本地审计摘要，避免上传完整敏感内容。

    tools/
      file.rs      文件读取、搜索、写入和 patch。
      command.rs   命令风险识别和执行。
      network.rs   HTTP 请求和下载。
      mcp.rs       本地 MCP tools/list、resources/read、tools/call。

    adapters/
      protocol.rs  Runtime event / adapter event 协议。
      cli.rs       CLI / Web Bridge 可复用边界。

    state/
      本地 transcript、checkpoint、runtime state、outbox 持久化。
```

## 4. 智能体工作模式

本地智能体的执行主线是多轮 Agent Loop：

```text
user
  -> model
  -> tool_calls
  -> local tools
  -> tool observations
  -> model continuation
  -> final answer
```

执行过程不是一次性脚本，而是由模型逐步决定是否需要工具：

1. 用户在项目聊天里提出需求。
2. 前端调用 `liuagent_start_local_chat`。
3. Rust runtime 创建或恢复本地会话。
4. runtime 准备项目上下文、历史消息、工具定义和模型配置。
5. 模型返回结构化 `tool_calls`。
6. runtime 在本机执行工具，得到 observation。
7. observation 回传模型继续推理。
8. 最终返回 assistant 消息和过程事件。

如果工具调用失败、参数错误或用户拒绝授权，结果也会作为 observation 回传给模型，让模型继续解释或调整。

## 5. 需求执行规则

### 5.1 清晰度判断

执行前先判断用户需求是否足够清晰：

- 如果只是查询、解释或说明，且目标明确，可以直接回答。
- 如果涉及实现、修改、写入、执行命令，需要用户已有明确执行意图，例如“修复”“修改”“开始”“继续”“按这个做”。
- 如果需求不清晰、对象不明确或存在多种理解，需要先说明理解和风险，再请求确认。

### 5.2 本地执行边界

所有会影响用户电脑的操作都必须在本机执行：

- 文件读取、写入、搜索和 patch 只能作用于 workspace 内。
- 命令执行必须限制在 workspace/cwd 内。
- 本地 MCP 调用从 workspace 的 `.ai-employee/mcp-adapter/servers.json` 读取配置。
- 禁止服务端 Docker 直接访问用户电脑 workspace。

### 5.3 权限门规则

高风险操作必须进入 Permission Gate：

- `write_file`
- `apply_patch`
- `run_command`
- `http_post`
- `download_file`
- `call_mcp_tool`

权限结果分为：

- `approve_once`：只允许本次工具调用。
- `approve_session`：同一会话内同类 action 可复用授权。
- `reject`：拒绝执行，并把拒绝结果作为 observation 回传模型。

会话级授权会写入：

```text
.ai-employee/agent-runtime-v2/permissions/<chat_session_id>.json
```

外部不能伪造无 `request_id` 的 session 授权来绕过权限门。

## 6. 状态、审计与恢复

每次本地会话都会写入运行状态，便于恢复和审计：

```text
.ai-employee/requirements/<project_id>/<chat_session_id>.json
.ai-employee/query-mcp/active-sessions/<chat_session_id>.json
.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json
.ai-employee/query-mcp/outbox/<project_id>__<chat_session_id>.jsonl
```

runtime 会记录：

- 用户需求 requirement。
- transcript 对话过程。
- runtime state。
- tool result。
- approval_required。
- audit 摘要。
- checkpoint。
- outbox 同步事件。

当 ProjectChat 重新打开会话时，可以通过 `liuagent_recover_runtime_state` 恢复 `waiting_approval`、`failed` 等状态。

## 7. 事件协议

runtime 会通过 Tauri event 广播结构化事件：

```text
liuagent-runtime-event
liuagent://runtime-event
```

常见事件包括：

- `message`
- `model_call_started`
- `model_step`
- `tool_call_started`
- `tool_result`
- `approval_required`
- `state_changed`
- `progress_update`

前端通过这些事件展示工具过程、权限按钮、失败状态和最终回答。

## 8. 模型运行模式

当前支持或预留的模式：

- `mock`：默认模式，不假装真实调用模型。
- `direct-openai-compatible`：桌面端拿到本地安全配置后，直接请求 OpenAI-compatible `/chat/completions`。
- `backend-gateway`：未来服务端模型网关占位；即便使用该模式，本地文件和命令工具仍必须在 Tauri 本机执行。

模型请求会携带内置工具 schema，并只消费标准结构化 `tool_calls`。

## 9. 已实现能力

- 已注册内置工具定义，可通过 `liuagent_builtin_tool_definitions` 获取。
- 已开放 `liuagent_execute_tool` 执行单个本地工具。
- 已开放 `liuagent_start_local_chat` 启动本地智能体会话。
- 已开放 `liuagent_recover_runtime_state` 恢复本地状态。
- 已开放 runtime events / outbox 查询和 ack command。
- 已实现文件、命令、网络下载、本地 MCP adapter 等基础工具。
- 已实现多轮 Agent Loop。
- 已实现工具权限确认和会话级权限缓存。
- 已实现 transcript、audit、checkpoint、outbox 本地持久化。

## 10. 禁止事项

- 禁止把用户本地工具执行逻辑继续扩展到服务端作为主路径。
- 禁止 Docker 服务端直接访问用户电脑 workspace。
- 禁止前端绕过 Permission Gate 执行写文件、命令或网络写入。
- 禁止把本地凭据、完整文件内容或敏感命令输出无过滤上传到服务端审计。
- 禁止用静默降级掩盖本地 Tauri bridge 不可用的问题。

## 11. 后续方向

- 补齐更细的原生权限 UI：授权详情、撤销授权、清理 session grant。
- 抽出 `liuagent_core` 为 Desktop / CLI 共用 crate。
- 补齐更完整的 resume / replay CLI 能力。
- 完善审计摘要查看和 outbox 同步可观测性。
- 增强本地 MCP adapter 的错误恢复和工具发现体验。
