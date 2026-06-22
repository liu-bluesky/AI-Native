# Tauri 本地 liuAgent Runtime 说明

本目录是桌面端本地智能体能力的主入口。当前产品目标是：用户安装桌面端后，智能体工具在用户本机执行；服务端 Docker 只提供账号、项目、员工、规则、技能、模型配置、记忆和审计摘要等数据能力，不能直接读写用户电脑 workspace。

## 架构边界

```text
Vue Desktop UI
  -> Tauri command / event
  -> Agent Gateway / Desktop Adapter
  -> liuAgent Core
  -> Tool Runtime / Permission Gate / Audit / State
  -> 用户本机 workspace

Python FastAPI 服务端
  -> 用户、项目、员工、规则、技能、记忆、模型配置
  -> 工具契约下发和审计摘要保存
  -> 不执行用户本地文件/命令工具
```

## 开发原则

- 本地文件、命令、patch、下载、MCP 本地调用等工具必须在 Tauri/Rust 本地执行。
- Vue 只负责界面、权限弹窗、工具时间线和用户交互。
- 服务端只负责配置和数据，不作为用户本地工具执行主体。
- `docs/liuAgent-cli` 是本地 agent core、工具协议、权限协议、事件协议的设计来源。
- CLI、Desktop、Web Bridge 必须共享同一套协议结构；差异只在 adapter 展示方式。
- ProjectChat 只是 `ProjectChat Adapter`，负责创建 `AgentInvocation` 和展示事件；不能成为 agent core。
- 智能体对话和 MCP 触发任务都必须通过 Unified MCP 记录 `RequirementSession`、任务树、工作事实和审计摘要。
- 外部系统接入也必须走 `Agent Gateway -> RequirementSession -> Desktop Adapter -> liuAgent Core`，不能直接写本地 workspace。

## 通用 Agent Gateway 边界

```text
ProjectChat / External System / CLI / Desktop UI
  -> Agent Gateway
  -> Unified MCP: RequirementSession
  -> ProjectContextBundle / PromptBundle / ToolManifestBundle
  -> Desktop Adapter / Local Runner
  -> liuAgent Core
```

服务端可以下发项目、智能体、提示词、模型配置和技能元数据，但不能执行用户本地工具。即使后续增加服务端模型网关，文件、命令、下载、patch 和本地 MCP 工具仍必须在 Tauri 本机执行。

详细协议以 `docs/liuAgent-cli/design/15-agent-gateway-mcp.md` 为准。

## 目录规划

```text
src/
  main.rs
    Tauri 启动和 command 注册。只保留薄入口，不写工具业务逻辑。

  liuagent_core/
    mod.rs
      Core 对外入口，负责把 ToolCall 分发到 Tool Runtime。
    types.rs
      ToolDefinition、ToolExecutionRequest、ToolExecutionResult、ToolError 等协议结构。
    definitions.rs
      内置工具定义注册表，声明 name / input_schema / action / risk / requires_approval / scope。
    args.rs
      JSON 参数读取和基础 schema 校验。
    workspace.rs
      workspace 路径安全，拒绝绝对路径和 ../ 逃逸。
    permission.rs
      Permission Gate，生成 approval_required 所需结构。
    audit.rs
      本地审计摘要，避免记录敏感全文。
    runtime.rs
      工具调用状态机、ToolBatch、结果聚合和恢复。

    tools/
      mod.rs
      file.rs
        list_files / read_file / search_text / write_file / apply_patch
      command.rs
        check_command_risk / run_command
      network.rs
        http_get / http_post / download_file
      mcp.rs
        list_mcp_tools / read_mcp_resource / call_mcp_tool

    adapters/
      mod.rs
      tauri.rs
        Tauri command/event 适配。
      cli.rs
        CLI adapter，后续可拆到独立 crate。
      protocol.rs
        AdapterCommand / AgentEvent JSON 协议。

    state/
      mod.rs
      store.rs
      transcript.rs
      checkpoints.rs

    security/
      mod.rs
      policy.rs
      secrets.rs
      scope.rs
```

## 当前落地顺序

1. 先完成本地只读工具：`list_files`、`read_file`、`search_text`。
2. 再接权限协议和危险工具：`write_file`、`apply_patch`、`run_command`。
3. 再接网络工具和 MCP 工具。
4. 把项目对话中的模型 tool call 接到本地 `liuagent_execute_tool`，工具结果回传对话继续推理。
5. 持续补齐权限 UI、审计详情和 crate 拆分；协议级事件、outbox 和 MCP framing 已进入可验证主线。

## 当前实现状态

- 已注册 14 个内置工具定义，可通过 Tauri command `liuagent_builtin_tool_definitions` 获取。
- 已开放 Tauri command `liuagent_execute_tool`，前端通过 `src/utils/native-desktop-bridge.js` 调用本地 Rust runtime。
- 已实现并通过测试的本地工具：`list_files`、`read_file`、`search_text`、`write_file`、`apply_patch`、`check_command_risk`、`run_command`、`http_get`、`http_post`、`download_file`。
- `write_file`、`apply_patch`、`run_command` 已接入 Permission Gate；未授权时返回 `permission.required`，前端必须在气泡内确认后带 `permissionDecision` 重试。
- `run_command` 只在 workspace/cwd 内执行，`safe` 命令可直接跑，`medium/high/critical` 必须先确认；带 shell 控制符的命令不会被误判为 safe。
- 网络工具由用户本机发起请求；只允许 `http/https`，拒绝 `Authorization`、`Cookie` 等敏感请求头，响应头只返回非敏感字段，`http_post` 和 `download_file` 必须先确认。
- 项目对话已接入首条桌面本地工具链路：
  - 服务端 Agent Runtime 发现本地内置工具调用后，生成 `desktop_client_tool` 等待任务，不在 Docker/服务端执行用户本地工具。
  - `ProjectChat.vue` 监听 `tool_observation_created`，识别 `raw_result.source=desktop_client_tool`，调用 Tauri `liuagent_execute_tool`。
  - 本地工具如返回 `permission.required`，Vue 弹出确认操作；用户可选择 `approve_once` 或 `approve_session` 后重试。
  - 前端通过 websocket `desktop_tool_result` 回传 `run_id/call_id/tool_name/task_id/tool_result`。
  - 服务端只把桌面结果转成 ToolObservation，并复用 Agent Runtime resume/continuation 继续模型对话。
- 已接入第一条桌面本地对话链路：
  - Tauri command `liuagent_start_local_chat` 由 Vue 直接调用，不先进入后端 WebSocket 执行。
  - 项目 AI 对话主入口默认使用 `local-runner`，发送消息时走桌面端 Tauri liuAgent Runtime；Tauri bridge 不可用或本机工作区未配置时直接失败提示，不再静默切回后端智能体。
  - local-runner 页面发送消息时，`ProjectChat.vue` 优先走 `sendLocalLiuAgentChatRequest`；如果 Tauri bridge 不可用则明确失败，不静默回退到服务端本地工具执行。
  - 当前最小会话会在用户 workspace 下写入 `.ai-employee/requirements/<project_id>/<chat_session_id>.json`。
  - 当前最小会话会执行 `list_files` 只读工具并返回 assistant 消息、工具过程和 requirement 记录路径。
  - 当前 Tauri 会话已经有 `modelRuntime` 契约，记录 `mode/providerId/modelName/temperature/maxTokens` 等模型步骤信息。
  - 当前默认 `mode=mock`，因为服务端 `/llm/providers` 只返回脱敏模型配置，不把 API key 下发到前端；因此未配置桌面端本地直连模型时，不会假装已经真实调用大模型。
  - 已预留 `direct-openai-compatible` 模式：当桌面端安全拿到本地 baseUrl + apiKey/apiKeyEnv + modelName 后，可由 Tauri 本机直接请求 OpenAI-compatible `/chat/completions`。
  - `backend-gateway` 模式只作为未来“服务端模型网关”契约占位；即便使用模型网关，用户本地文件/命令/工具仍必须在 Tauri 本机执行。
  - OpenAI-compatible `tools` / `tool_calls` 主线已迁入 Tauri runtime；请求模型时会带内置工具 schema，响应只消费标准结构化 `tool_calls`。
  - 已实现多轮 Agent Loop：`user -> model -> tool_calls -> tool observations -> model continuation`，支持一轮多个工具顺序执行，并通过最大工具轮数/调用数限制避免死循环。
  - 工具失败、schema 错误和用户拒绝会作为 observation 回传模型；缺少授权时停在 `waiting_approval`，等待 UI 用同一个 `tool_call_id/request_id` 继续。
  - 已实现会话级权限缓存：用户选择“本会话允许”后，Tauri 会把同类 action 授权写入 `.ai-employee/agent-runtime-v2/permissions/<chat_session_id>.json`，后续同会话同 action 的工具调用不再重复弹窗；缓存 grant 只由 runtime 内部标记生效，不能用无 request_id 的外部 `approve_session` 直接绕过权限门。
  - 每次本地对话会写入 runtime state、transcript、audit 和 checkpoint，并同步 canonical query-mcp active/session-history 文件，支持恢复读取 `waiting_approval` 和 `failed` 状态。
  - Transcript 和 `liuagent_start_local_chat` 返回体已包含最小结构化 `AgentRuntimeEvent`：`message`、`approval_required`、`state_changed`、`tool_result`；ProjectChat local-runner 已将这些事件映射到气泡内操作和过程日志。
  - Tauri command `liuagent_recover_runtime_state` 已开放本地状态恢复；ProjectChat 打开会话时会尝试恢复 `waiting_approval` 授权操作和 `failed` 状态提示。
  - MCP 本地 adapter 已接入：从 workspace 的 `.ai-employee/mcp-adapter/servers.json` 读取本地 adapter 命令，通过 stdio JSON-RPC 调用 `tools/list`、`resources/read`、`tools/call`；`call_mcp_tool` 会先进入 Permission Gate。
  - MCP adapter 支持两种 stdio framing：默认逐行 JSON-RPC；当 server 配置 `framing: "content-length"`、`"mcp"` 或 `transport: "stdio-mcp"` 时，按标准 `Content-Length` frame 读写 JSON-RPC。
  - Tauri command `liuagent_list_runtime_events`、`liuagent_list_runtime_outbox`、`liuagent_ack_runtime_outbox` 已开放，用于读取本地 runtime 事件、同步 query-mcp outbox 和确认删除已同步条目。
  - `liuagent_start_local_chat` 会通过 Tauri event `liuagent://runtime-event` 广播本次运行产生的结构化 runtime event；`src/utils/native-desktop-bridge.js` 暴露 `subscribeNativeLiuAgentRuntimeEvents` 订阅入口。
  - 每次本地 runtime 写入 artifacts 时，会追加 query-MCP 兼容 outbox 到 `.ai-employee/query-mcp/outbox/<project_id>__<chat_session_id>.jsonl`；`ProjectChat.vue` 在等待授权、完成和失败路径都会尝试同步 outbox 到项目聊天 requirement 记录，成功后 ack 本地条目。
  - `liuagent_core::adapters::cli` 已保留 CLI 边界，当前提供 `runtime_events_to_ndjson`，用于把 runtime events 渲染成 CLI/Web Bridge 可消费的 NDJSON。
- 待实现：更细的原生权限 UI（授权详情、撤销/清理 session grant、审计摘要详情）。
- 待实现：把 `liuagent_core` 抽成 Tauri/CLI 共用 crate，并补齐更完整的 resume/replay CLI 命令面。

本地 MCP adapter 配置示例：

```json
{
  "servers": {
    "local": {
      "command": "/path/to/adapter",
      "args": ["--stdio"],
      "cwd": ".",
      "framing": "content-length"
    }
  }
}
```

## 禁止事项

- 禁止继续把用户本地工具执行逻辑扩展到 `web-admin/api/services/agent_runtime/builtin_tools` 作为主路径。
- 禁止让 Docker 服务端直接访问用户电脑 workspace。
- 禁止前端绕过 Permission Gate 直接执行写文件、命令、网络写入等高风险动作。
- 禁止把本地凭据、完整文件内容或敏感命令输出无过滤上传到服务端审计。
