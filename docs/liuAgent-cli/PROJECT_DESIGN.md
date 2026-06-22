# liuAgent CLI 项目设计

## 项目目标

liuAgent CLI 的目标是做一个可被终端、网页和桌面复用的本地智能体运行时。CLI 不是唯一入口，真正要沉淀的是一套稳定的 agent core、工具协议、权限协议和事件协议。

核心原则：

- agent core 负责能力，不绑定具体 UI。
- CLI、Web、Desktop 只是不同 adapter。
- 工具执行必须可审计、可确认、可回放。
- 授权、打开链接、审批、选择等交互要抽成事件，而不是写死在 stdin/stdout。

## 总体架构

```text
liuAgent Core
  -> Model Runtime
  -> Tool Runtime
  -> Permission Gate
  -> Event Bus
  -> Session State

Adapters
  -> CLI Adapter
  -> Web Adapter
  -> Desktop Adapter

Agent Gateway
  -> ProjectChat Adapter
  -> External System Adapter
  -> Unified MCP RequirementSession
```

## 详细设计目录

更细的数据结构、协议分类和名词解释放在 [design/README.md](./design/README.md)。

通用智能体接入、ProjectChat 边界、外部系统接入和 MCP 统一记录入口放在 [design/15-agent-gateway-mcp.md](./design/15-agent-gateway-mcp.md)。

## 核心模块

### Agent Core

负责智能体主循环：

- 接收用户输入
- 调用模型
- 解析 tool call
- 执行工具
- 回传 observation
- 生成最终输出

Agent Core 不直接读写终端，不直接弹窗，也不直接控制浏览器。

### Agent Gateway

Agent Gateway 是 ProjectChat、桌面端、CLI 和外部系统进入 liuAgent Core 的标准入口。它创建 `AgentInvocation`，绑定项目、会话、智能体、提示词和 workspace 元数据，并通过 Unified MCP 记录 `RequirementSession`。

Agent Gateway 不执行用户本地工具。用户本地文件、命令、patch、下载和本地 MCP 工具只能由 Desktop/Tauri/Local Runner 执行；服务端只保存配置、需求、任务树、记忆和审计摘要。

### Tool Runtime

负责注册和执行工具。

第一批工具：

- 文件工具：`list_files`、`read_file`、`search_text`、`apply_patch`、`write_file`
- 命令工具：`run_command`、`check_command_risk`
- 网络工具：`http_get`、`http_post`、`download_file`
- MCP 工具：`list_mcp_tools`、`call_mcp_tool`、`read_mcp_resource`

所有工具都必须声明 `input_schema`、风险等级和执行边界。

### Permission Gate

负责统一拦截高风险行为。

必须处理：

- 写文件
- 执行命令
- 删除或覆盖
- 网络写入
- 打开外部链接
- 发消息或提交表单
- 读取或外传本地凭据
- 部署和远程操作

权限结果统一输出为事件，交给当前 adapter 展示。

### Event Bus

Event Bus 是让 CLI、Web、Desktop 保持同一套能力的关键。

典型事件：

```json
{
  "event_id": "evt_approval_001",
  "type": "approval_required",
  "session_id": "sess_001",
  "run_id": "run_001",
  "created_at": "2026-06-20T07:00:00Z",
  "payload": {
    "request_id": "perm_001",
    "title": "允许执行命令？",
    "risk": "high",
    "action": "command.run",
    "scope": "workspace",
    "options": [
      {
        "decision": "approve_once",
        "label": "允许一次",
        "grant_scope": "once"
      },
      {
        "decision": "deny",
        "label": "拒绝"
      }
    ]
  }
}
```

```json
{
  "event_id": "evt_open_url_001",
  "type": "open_url",
  "session_id": "sess_001",
  "run_id": "run_001",
  "created_at": "2026-06-20T07:00:01Z",
  "payload": {
    "open_url_id": "url_001",
    "url": "https://example.com/auth",
    "reason": "需要完成授权",
    "requires_user_action": true,
    "request_id": "perm_002"
  }
}
```

```json
{
  "event_id": "evt_tool_result_001",
  "type": "tool_result",
  "session_id": "sess_001",
  "run_id": "run_001",
  "created_at": "2026-06-20T07:00:02Z",
  "payload": {
    "tool_result_id": "result_001",
    "tool_call_id": "call_001",
    "ok": true,
    "summary": "读取 120 行",
    "created_at": "2026-06-20T07:00:02Z"
  }
}
```

## 多端适配

### CLI Adapter

CLI 负责终端体验：

- 打印模型输出
- 展示审批问题
- 读取用户输入
- 打印授权链接
- 支持 Ctrl+C 和终端 resize

CLI 可以作为最小产品入口，但不应该承载业务核心。

### Web Adapter

Web 负责浏览器体验：

- 用按钮处理审批
- 用弹窗或新窗口打开授权链接
- 用 WebSocket 接收事件
- 展示任务状态、工具调用和执行结果

如果需要完整复原终端交互，可以使用 `xterm.js + WebSocket + PTY`。

如果需要产品化体验，应走 Event Bus，而不是直接复刻终端输入输出。

### Desktop Adapter

Desktop 负责本机集成：

- 原生弹窗
- 系统通知
- 打开外部链接
- 文件选择器
- 剪贴板
- 本地 Runner 能力

桌面端权限更强，所以必须比 Web 和 CLI 更严格记录审计。

## 两种交互模式

### PTY 模式

目标是最大程度复原 CLI。

```text
Browser/Desktop -> PTY Bridge -> liuAgent CLI
```

优点：

- 能复原终端菜单、ANSI、流式输出和 TUI。
- 对 CLI 改造少。

缺点：

- 页面体验受终端限制。
- 审批、授权、按钮等产品化交互难做精细。

### Event 模式

目标是多端共享同一套能力。

```text
Browser/Desktop/CLI -> Adapter -> Event Bus -> Agent Core
```

优点：

- Web 和 Desktop 可以做原生交互。
- 权限和审计更清晰。
- 后续适合扩展多人协作和任务状态。

缺点：

- 需要把 CLI 里的交互逻辑抽出来。

建议：第一阶段保留 PTY 模式兜底，同时建设 Event 模式作为长期主线。

## 最小 MVP

第一版只做这些：

1. Agent Core 主循环。
2. Tool Registry 和 Tool Runtime。
3. Permission Gate。
4. Event Bus。
5. CLI Adapter。
6. Web Adapter 的基础事件展示。
7. `open_url`、`approval_required`、`tool_result` 三类事件。

暂不做：

- 完整多智能体调度
- 长期记忆系统
- 复杂桌面自动化
- 远程部署自动化
- 完整任务树产品

## 成功标准

第一阶段完成后，应能做到：

- CLI 可以正常运行 agent。
- Web 可以接收 agent 事件并处理审批。
- 授权链接不再只依赖终端打印。
- 工具调用经过统一权限闸门。
- 同一个工具执行结果可以被 CLI 和 Web 以不同 UI 展示。
- 高风险动作必须有明确确认记录。

## 后续扩展

稳定后再扩展：

- Desktop Adapter
- MCP 工具市场
- 任务树和工作轨迹
- 长期记忆
- 多 agent 协作
- 本地 Runner 与远程 Runner 分离
- 更细的权限策略和审计日志
