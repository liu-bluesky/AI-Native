# 事件协议

事件协议是 Core 与 CLI、Web、Desktop 保持能力一致的关键。Core 输出结构化事件，Adapter 决定如何展示和如何收集用户响应。

## AgentEvent

所有事件共享同一个信封结构。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `event_id` | ID | 是 | 事件 ID。 |
| `type` | EventType | 是 | 事件类型。 |
| `session_id` | ID | 是 | 所属会话。 |
| `run_id` | ID | 否 | 所属执行。 |
| `created_at` | Timestamp | 是 | 创建时间。 |
| `payload` | AgentEventPayload | 是 | 由 `type` 决定的事件数据。 |

## message_delta

模型输出增量。

```json
{
  "event_id": "evt_msg_delta_001",
  "type": "message_delta",
  "session_id": "sess_001",
  "run_id": "run_001",
  "created_at": "2026-06-20T07:00:00Z",
  "payload": {
    "message_id": "msg_001",
    "delta": "正在读取文件"
  }
}
```

CLI 可以流式打印，Web 可以追加到消息节点，Desktop 可以按窗口状态决定是否通知。

## approval_required

需要用户授权。

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

Adapter 必须把用户选择回传为 `AdapterCommand`，不能由工具自行继续执行。回传的 `decision + grant_scope` 必须匹配 `options` 中的一个结构化选项，不能只回传 UI 文案。

## open_url

请求打开外部链接。

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
    "reason": "完成 OAuth 授权",
    "requires_user_action": true,
    "request_id": "perm_001",
    "return_hint": "授权完成后回到当前会话"
  }
}
```

CLI 打印链接，Web 打开新窗口或弹窗，Desktop 调用系统浏览器。

`open_url` 只表示 Core 请求 Adapter 打开链接，不表示页面操作已经完成。若 `requires_user_action=true`，Core 必须进入 `waiting_user`，并等待 Adapter 回传 `open_url_done` 命令。

`open_url` payload 规则：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `open_url_id` | ID | 是 | 本次打开链接动作 ID，用于和 `open_url_done` 对齐。 |
| `url` | string | 是 | 需要打开的 URL。 |
| `reason` | string | 是 | 打开原因，必须可展示。 |
| `requires_user_action` | boolean | 是 | 是否需要用户在浏览器完成授权、确认或表单动作。 |
| `request_id` | ID | 否 | 若打开链接前经过权限确认，关联 `PermissionRequest.request_id`。 |
| `return_hint` | string | 否 | 给用户看的返回提示，不参与协议判断。 |

`open_url_done` 由 Adapter 作为 `AdapterCommand` 回传，不能伪造成 `tool_result`。Core 收到后按 `open_url_id` 和 `idempotency_key` 去重，再决定恢复 Run 或进入失败。

```json
{
  "command_id": "cmd_url_001_completed",
  "type": "open_url_done",
  "idempotency_key": "idem_url_001_completed",
  "payload": {
    "open_url_id": "url_001",
    "status": "completed",
    "message": "用户已完成授权",
    "idempotency_key": "idem_url_001_completed"
  }
}
```

若命令通过 `TransportEnvelope` / `CommandFrame` 发送，`idempotency_key` 必须位于命令顶层；为了兼容直接 `AdapterCommand` 输入，payload 内也必须携带同一个值。Core 校验时两者不一致应拒绝该命令。所有 `AdapterCommand` 都必须携带 `command_id`，不能只提交 `type + payload`。

`status` 只能使用：

- `opened`：Adapter 已打开链接，但不代表用户完成动作。
- `completed`：用户明确完成外部动作，Core 可以从 `waiting_user` 回到 `running`。
- `failed`：打开失败或外部动作失败，Core 进入 `failed` 或重新请求用户。
- `cancelled`：用户取消外部动作，Core 进入 `cancelled` 或等待用户下一步。

## tool_started

工具开始执行。

```json
{
  "event_id": "evt_tool_started_001",
  "type": "tool_started",
  "session_id": "sess_001",
  "run_id": "run_001",
  "created_at": "2026-06-20T07:00:00Z",
  "payload": {
    "tool_call_id": "call_001",
    "name": "read_file",
    "started_at": "2026-06-20T07:00:00Z"
  }
}
```

## tool_result

工具执行完成。

```json
{
  "event_id": "evt_tool_result_001",
  "type": "tool_result",
  "session_id": "sess_001",
  "run_id": "run_001",
  "created_at": "2026-06-20T07:00:01Z",
  "payload": {
    "tool_result_id": "result_001",
    "tool_call_id": "call_001",
    "ok": true,
    "summary": "读取 120 行",
    "created_at": "2026-06-20T07:00:01Z"
  }
}
```

`tool_result.payload.tool_result_id` 必须和 `ToolResult.tool_result_id` 一致，供 `AuditResult.tool_result_id`、UI 时间线和 replay 去重追踪。不能只用 `tool_call_id` 表示结果，因为同一个工具调用的失败、重试和最终结果需要稳定区分。

## state_changed

会话或 Run 状态变化。

```json
{
  "event_id": "evt_state_changed_001",
  "type": "state_changed",
  "session_id": "sess_001",
  "run_id": "run_001",
  "created_at": "2026-06-20T07:00:00Z",
  "payload": {
    "from": "running",
    "to": "waiting_approval",
    "waiting_for": "approval",
    "pending_request_id": "perm_001",
    "pending_tool_call_ids": [],
    "pending_tool_batch_id": null,
    "pending_adapter_action_id": null
  }
}
```

`state_changed` 不使用单独的 `status` 字段。新状态统一放在 `to`，旧状态放在 `from`，以便 Adapter 能判断状态转移而不是只看到最终状态。

等待对象字段规则：

- `waiting_for=approval` 时，必须填写 `pending_request_id`。
- `waiting_for=tool` 时，必须填写 `pending_tool_call_ids` 或 `pending_tool_batch_id`。
- `waiting_for=adapter_action` 或等待 `open_url_done` 时，必须填写 `pending_adapter_action_id`。
- 不相关的 pending 字段必须为空数组、`null` 或省略，不能复用 `pending_request_id` 表达不同概念。

## Desktop runtime broadcast

Desktop/Tauri 入口除了把事件写入 transcript，还必须把本次运行产生的结构化 runtime event 广播给前端 Adapter。当前事件名固定为：

```text
liuagent://runtime-event
```

广播 payload 必须保持 `AgentRuntimeEvent` 原始结构，不在前端事件层改写 `type`、`event_id`、`payload`。前端桥接层通过 `subscribeNativeLiuAgentRuntimeEvents(handler)` 订阅该事件，并把 payload 原样交给 UI、调试面板或外部集成消费。

广播只用于实时展示和边车订阅，不能替代本地 transcript、checkpoint 或 query-mcp outbox；恢复和审计仍以本地追加事实源为准。

## CLI NDJSON boundary

CLI Adapter 面向终端和脚本时可以把 `AgentRuntimeEvent[]` 渲染为 NDJSON：

```text
{"event_id":"evt_001","type":"message","payload":{"content":"..."}}
{"event_id":"evt_002","type":"state_changed","payload":{"to":"completed"}}
```

NDJSON 每行必须是完整 JSON 对象；对象内容仍使用 runtime event 原始结构。CLI 层只能负责序列化和展示，不能在渲染时补造授权、状态或工具结果。
