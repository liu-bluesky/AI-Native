# 适配器协议

Adapter 负责把不同入口接入同一个 Agent Core。它不拥有工具系统，也不绕过权限系统。

## AdapterInput

Adapter 传给 Core 的输入。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `input_id` | ID | 是 | 输入 ID。 |
| `session_id` | ID | 是 | 会话 ID。 |
| `type` | AdapterInputType | 是 | `user_message`、`permission_decision`、`adapter_command`、`interrupt`、`resume`。 |
| `payload` | AdapterInputPayload | 是 | 输入内容；必须由 `type` 决定。 |
| `source` | `cli` \| `web` \| `desktop` | 是 | 输入来源。 |

`AdapterInput.payload` 映射规则：

| AdapterInputType | Payload 类型 |
| --- | --- |
| `user_message` | `SubmitTextCommandPayload` |
| `permission_decision` | `AdapterCommand`，且 `AdapterCommand.type=permission_decision` |
| `adapter_command` | `AdapterCommand` |
| `interrupt` | `AdapterCommand`，且 `AdapterCommand.type=cancel` |
| `resume` | `AdapterCommand`，且 `AdapterCommand.type=resume` |

除 `user_message` 外，Adapter 输入状态变化必须携带完整 `AdapterCommand`，不能只传裸 payload。这样 `command_id`、`event_id`、顶层 `idempotency_key` 和 `CommandReceipt` 才能在 CLI、Web、Desktop 之间保持一致。

## AdapterOutput

Core 输出给 Adapter 的内容。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `output_id` | ID | 是 | 输出 ID。 |
| `session_id` | ID | 是 | 会话 ID。 |
| `events` | AgentEvent[] | 是 | 待展示或处理的事件。 |
| `state` | RunState | 是 | 最新状态。 |

## AdapterCommand

Adapter 对事件的响应。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `command_id` | ID | 是 | 命令 ID。 |
| `event_id` | ID | 否 | 对应事件。 |
| `type` | AdapterCommandType | 是 | `submit_text`、`permission_decision`、`cancel`、`resume`、`open_url_done`。 |
| `payload` | SubmitTextCommandPayload \| PermissionDecisionCommandPayload \| CancelCommandPayload \| ResumeCommandPayload \| OpenUrlDoneCommandPayload | 是 | 响应数据。 |
| `idempotency_key` | string | 条件必填 | 会改变状态或产生副作用的命令必须填写；通过 `CommandFrame` 传输时也必须在顶层填写同一个值。 |

当 `type=submit_text` 时，`payload` 必须使用 `SubmitTextCommandPayload`，至少包含 `content`。`submit_text` 不产生外部副作用，可以没有幂等键；如果客户端提供幂等键，Core 仍应按同一幂等规则去重。

当 `type=permission_decision` 时，`payload` 至少包含 `request_id`、`decision` 和 `idempotency_key`；批准类决策必须额外包含 `grant_scope`，`deny` / `revise` 不得携带 `grant_scope`。`AdapterCommand.idempotency_key` 必须存在，且两处幂等键必须完全一致，否则 Core 必须拒绝该命令。`decision` 必须使用 `PermissionDecision.decision` 的取值，不再使用 `approve` / `deny` 作为协议值。批准类决策必须按 `approve_once -> once`、`approve_run -> run`、`approve_session -> session`、`approve_workspace -> workspace` 映射 `grant_scope`。

当 `type=cancel` 或 `type=resume` 时，`payload` 必须分别使用 `CancelCommandPayload` 或 `ResumeCommandPayload`，且必须携带与顶层完全一致的 `idempotency_key`。

当 `type=open_url_done` 时，`payload` 至少包含 `open_url_id`、`status` 和 `idempotency_key`，`AdapterCommand.idempotency_key` 必须存在，且两处幂等键必须完全一致，否则 Core 必须拒绝该命令。`status` 必须使用 `opened`、`completed`、`failed`、`cancelled`，其中 `opened` 只表示链接已打开，不能让 Core 自动从 `waiting_user` 继续执行。

`submit_text` 可以没有幂等键，但 `permission_decision`、`cancel`、`resume`、`open_url_done` 必须有幂等键。Core 按 `session_id + type + idempotency_key` 写入 `CommandReceipt` 并去重；相同幂等键且 payload 哈希一致时返回第一次 `CommandResult`，payload 不一致时返回冲突错误，不允许静默覆盖第一次结果。

## CLI Adapter

职责：

- 接收终端输入并生成 `AdapterInput`。
- 把 `message_delta` 渲染成流式文本。
- 把 `approval_required` 渲染成终端确认问题。
- 把 `open_url` 渲染成可点击或可复制链接。

CLI Adapter 不应该直接执行工具。

## Web Adapter

职责：

- 通过 HTTP 或 WebSocket 接入事件流。
- 用按钮、弹窗、状态条展示 `AgentEvent`。
- 把审批按钮结果转换成 `AdapterCommand`。
- 展示工具调用时间线和结果摘要。

Web 若只想复刻终端，可使用 PTY 模式；若要产品化体验，应优先使用事件协议。

## Desktop Adapter

职责：

- 使用系统浏览器打开授权链接。
- 调用原生文件选择器、通知和剪贴板。
- 通过本地 Runner 执行桌面能力。
- 记录比 Web 更严格的权限审计。

Desktop Adapter 权限更强，所有本机动作都必须进入 Permission Gate。
