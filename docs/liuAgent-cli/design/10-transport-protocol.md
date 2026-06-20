# 传输协议

传输协议负责把同一个 Agent Core 接到 CLI、Web 和 Desktop。它不重新定义事件和工具，只定义事件如何被传送、确认、恢复和降级。

## 目标

- Web 可以用浏览器页面控制 Agent Core，包括审批、打开链接、取消、恢复。
- Desktop 可以在本机 Runner 上执行更强能力，但仍然通过同一套事件和权限协议。
- CLI 可以继续保持终端体验，也可以被 Web/Desktop 通过 PTY 快速复刻。
- 所有传输都必须支持断线恢复、事件去重和有序回放。

## 推荐模式

| 模式 | 适用场景 | 优点 | 限制 |
| --- | --- | --- | --- |
| Event Stream | 正式产品化 Web/Desktop | 结构化、可审计、可恢复 | 需要 Core 输出完整事件 |
| HTTP Command | 提交审批、取消、恢复等一次性命令 | 简单、易做鉴权 | 不适合流式模型输出 |
| PTY Bridge | 快速把已有 CLI 放到浏览器 | 复刻成本低 | 难做精细状态和按钮交互 |
| Local Runner RPC | Desktop 调本机能力 | 能访问本机文件和系统能力 | 权限边界更重 |

长期主线是 Event Stream + HTTP Command。PTY Bridge 只能作为兼容层或过渡层。

## TransportEnvelope

所有跨进程、跨端消息都使用统一信封。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `envelope_id` | ID | 是 | 传输层消息 ID，用于去重。 |
| `session_id` | ID | 是 | 会话 ID。 |
| `run_id` | ID | 否 | 所属 Run。 |
| `direction` | TransportDirection | 是 | 消息方向：`server_to_client`、`client_to_server`。 |
| `kind` | TransportKind | 是 | `event`、`command`、`ack`、`hello`、`heartbeat`、`error`。 |
| `seq` | number | 是 | 会话内单调递增序号。 |
| `payload` | TransportPayload | 是 | 由 `kind` 决定的业务载荷。 |
| `created_at` | Timestamp | 是 | 创建时间。 |

`TransportEnvelope.payload` 映射规则：

| TransportKind | Payload 类型 |
| --- | --- |
| `event` | `AgentEvent` |
| `command` | `CommandFrame` |
| `ack` | `AckFrame` |
| `hello` | `ClientHello` |
| `heartbeat` | `HeartbeatPayload` |
| `error` | `ErrorPayload` |

示例：

```json
{
  "envelope_id": "env_001",
  "session_id": "sess_001",
  "run_id": "run_001",
  "direction": "server_to_client",
  "kind": "event",
  "seq": 42,
  "payload": {
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
  },
  "created_at": "2026-06-20T07:00:00Z"
}
```

## ClientHello

客户端连接时先声明自身能力。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `client_id` | ID | 是 | 客户端实例 ID。 |
| `adapter` | AdapterKind | 是 | 适配器类型：`cli`、`web`、`desktop`。 |
| `protocol_version` | string | 是 | 传输协议版本。 |
| `last_seen_seq` | number | 否 | 客户端最后处理的序号。 |
| `capabilities` | string[] | 是 | 能力声明。 |

常见能力：

- `event_stream`
- `http_command`
- `open_url`
- `approval_buttons`
- `local_runner`
- `pty_bridge`
- `file_picker`

## StreamFrame

Event Stream 使用 `TransportEnvelope` 包装 `AgentEvent`。

```json
{
  "envelope_id": "env_043",
  "session_id": "sess_001",
  "run_id": "run_001",
  "direction": "server_to_client",
  "kind": "event",
  "seq": 43,
  "payload": {
    "event_id": "evt_msg_001",
    "type": "message_delta",
    "session_id": "sess_001",
    "run_id": "run_001",
    "created_at": "2026-06-20T07:00:01Z",
    "payload": {
      "message_id": "msg_001",
      "delta": "正在分析文件"
    }
  },
  "created_at": "2026-06-20T07:00:01Z"
}
```

客户端必须按 `seq` 处理事件。发现断号时，不继续猜测状态，应该调用恢复接口拉取缺失事件。

## CommandFrame

客户端响应事件时发送命令。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `command_id` | ID | 是 | 命令 ID。 |
| `event_id` | ID | 否 | 对应事件。 |
| `type` | AdapterCommandType | 是 | `submit_text`、`permission_decision`、`cancel`、`resume`、`open_url_done`。 |
| `payload` | SubmitTextCommandPayload \| PermissionDecisionCommandPayload \| CancelCommandPayload \| ResumeCommandPayload \| OpenUrlDoneCommandPayload | 是 | 命令参数。 |
| `idempotency_key` | string | 条件必填 | 状态变化或副作用命令必须填写；`submit_text` 可选。 |

状态变化或副作用命令必须幂等。Web 用户重复点击审批按钮时，Core 只能接受第一次有效决策。审批命令的 `payload.decision` 必须使用 `approve_once`、`approve_run`、`approve_session`、`approve_workspace`、`deny`、`revise`，不能使用 UI 文案或按钮名作为协议值。批准类审批命令必须填写 `payload.grant_scope`，且不能超过策略允许范围；`deny` / `revise` 不得携带 `grant_scope`。批准类决策必须按 `approve_once -> once`、`approve_run -> run`、`approve_session -> session`、`approve_workspace -> workspace` 映射。

`submit_text` payload 必须使用 `SubmitTextCommandPayload`，至少包含 `content`。`cancel` 和 `resume` payload 必须分别使用 `CancelCommandPayload` 和 `ResumeCommandPayload`，并携带与顶层完全一致的 `idempotency_key`。

`open_url_done` payload 必须使用 `OpenUrlDoneCommandPayload`，并至少包含：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `open_url_id` | ID | 是 | 对应 `open_url` 事件。 |
| `status` | `opened` \| `completed` \| `failed` \| `cancelled` | 是 | 外部链接动作状态。 |
| `message` | string | 否 | 可展示说明。 |
| `error_code` | string | 否 | 失败时的稳定错误码。 |

`opened` 只表示客户端完成打开动作，不能让 Core 自动恢复 Run；`completed` 才表示用户已完成外部动作。

`CommandFrame.idempotency_key` 是传输层权威幂等键。`permission_decision`、`cancel`、`resume`、`open_url_done` 必须携带该字段；`submit_text` 可以省略，如果提供则也按相同幂等规则进入 `CommandReceipt`。若命令被转换成直接 `AdapterCommand`，Adapter 层必须把同一值复制到需要幂等的 `payload.idempotency_key`，两处不一致时必须拒绝；不能让 payload 覆盖顶层幂等键。

## AckFrame

客户端可以批量确认已处理事件。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `client_id` | ID | 是 | 客户端实例 ID。 |
| `ack_seq` | number | 是 | 已处理到的最大序号。 |
| `received_event_ids` | ID[] | 否 | 已接收事件 ID。 |

Ack 不等于业务完成。它只说明客户端已收到并处理到某个序号。

## HeartbeatPayload

心跳只用于连接保活和辅助恢复，不承载业务动作。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `client_id` | ID | 否 | 客户端实例 ID。 |
| `last_seen_seq` | number | 否 | 客户端最后处理的序号。 |
| `sent_at` | Timestamp | 是 | 发送时间。 |

## 恢复接口

断线恢复至少需要两个能力：

- `GET /sessions/{session_id}/events?after_seq=<seq>`：读取缺失事件。
- `GET /sessions/{session_id}/state`：读取当前 `SessionState`。

恢复流程：

1. 客户端重连并发送 `ClientHello.last_seen_seq`。
2. 服务端返回缺失 `TransportEnvelope`。
3. 客户端按序回放事件。
4. 客户端读取当前 `SessionState` 做最终校准。
5. 如果存在 `pending_permissions`，恢复为等待审批界面。
6. 如果存在 `pending_adapter_actions`，恢复为对应外部动作界面，例如等待 `open_url_done`。
7. 如果存在 `pending_tool_batches`，只展示进度或终态，不由客户端重放工具。

## PTY Bridge 边界

PTY Bridge 是把 CLI 作为终端进程接到 Web/Desktop：

```text
Browser UI
  -> PTY WebSocket
  -> CLI Process
  -> Agent Core
```

允许：

- 快速复刻现有 CLI 文本交互。
- 保留 CLI 的颜色、光标和输入行为。
- 在早期验证 Web 控制 CLI 的可行性。

不允许：

- 把终端文本解析成权限决策的唯一依据。
- 绕过 `PermissionGate` 直接执行命令。
- 让 Web 自己猜测 ToolCall、RunState 或 AuditLog。

正式产品化时，PTY 可以作为调试视图，但业务 UI 必须消费结构化事件。

## 多客户端并发

同一个 `session_id` 可能同时连接 CLI、Web、Desktop。

规则：

- `message_delta`、`tool_started`、`tool_result` 可以广播给全部客户端。
- `approval_required` 可以广播，但同一个 `request_id` 只能产生一个有效 `PermissionDecision`。
- `open_url` 可以广播给有 `open_url` 能力的客户端；第一个成功处理并回传 `open_url_done` 的客户端成为该动作的 `owner_client_id`。
- `cancel`、`resume`、`permission_decision` 这类命令必须使用 `idempotency_key`。
- `open_url_done` 必须使用 `idempotency_key`，重复提交通过 `CommandReceipt` 返回第一次处理结果；相同幂等键但 payload 哈希不同必须报冲突。
- Desktop 发起本机能力调用时，必须把 `client_id` 写入审计记录。

## 传输错误

| 错误码 | 含义 | 处理 |
| --- | --- | --- |
| `transport.seq_gap` | 事件序号不连续 | 拉取缺失事件。 |
| `transport.duplicate_command` | 重复命令 | 返回第一次处理结果。 |
| `transport.unsupported_capability` | 客户端缺少能力 | 降级或返回可操作替代方案。 |
| `transport.session_not_found` | 会话不存在 | 要求重新创建或恢复会话。 |
| `transport.client_not_authorized` | 客户端无权连接 | 拒绝连接并记录审计。 |
