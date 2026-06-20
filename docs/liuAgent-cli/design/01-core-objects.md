# 核心对象

核心对象描述 liuAgent CLI 运行时的基础数据模型。它们不属于某一个 UI，CLI、Web、Desktop 都应该消费同一组对象。

## AgentConfig

Agent 的静态配置。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `agent_id` | ID | 是 | Agent 唯一标识。 |
| `model` | string | 是 | 默认使用的模型名称。 |
| `workspace` | AbsolutePath | 是 | 允许读写和执行的工作区根目录。 |
| `tool_policy` | string | 是 | 工具权限策略 ID。 |
| `enabled_tools` | string[] | 是 | 当前 Agent 可见的工具名列表。 |
| `event_mode` | `pty` \| `event` | 是 | 交互模式。长期主线是 `event`。 |

## Session

一次连续对话和运行上下文。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `session_id` | ID | 是 | 会话 ID。 |
| `agent_id` | ID | 是 | 关联的 Agent。 |
| `created_at` | Timestamp | 是 | 创建时间。 |
| `updated_at` | Timestamp | 是 | 最近更新时间。 |
| `messages` | Message[] | 是 | 对话消息。 |
| `runs` | Run[] | 是 | 本会话内的执行记录。 |
| `run_state` | RunState | 是 | 当前运行状态；完整可恢复状态使用 `SessionState`。 |

## Run

一次用户输入触发的一段执行过程。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `run_id` | ID | 是 | 执行 ID。 |
| `session_id` | ID | 是 | 所属会话。 |
| `input_message_id` | ID | 是 | 触发本次执行的用户消息。 |
| `status` | RunStatus | 是 | 必须使用 `07-runtime-schema.md` 中的完整枚举：`queued`、`running`、`waiting_model`、`waiting_tool`、`waiting_approval`、`waiting_user`、`completed`、`failed`、`cancelled`。 |
| `steps` | Step[] | 是 | 模型输出、工具调用、权限确认等步骤。 |
| `started_at` | Timestamp | 是 | 开始时间。 |
| `ended_at` | Timestamp | 否 | 结束时间。 |

## Message

对话上下文中的消息，不等同于事件。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `message_id` | ID | 是 | 消息 ID。 |
| `role` | `system` \| `user` \| `assistant` \| `tool` | 是 | 消息来源。 |
| `content` | string | 是 | 文本内容。 |
| `tool_call_id` | ID | 否 | 工具消息关联的调用 ID。 |
| `created_at` | Timestamp | 是 | 创建时间。 |

## Step

Run 内的可审计步骤。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `step_id` | ID | 是 | 步骤 ID。 |
| `type` | StepType | 是 | 必须使用 `07-runtime-schema.md` 中的 `StepType`。 |
| `status` | StepStatus | 是 | `pending`、`running`、`done`、`failed`、`cancelled`。 |
| `payload` | StepPayload | 是 | 与步骤类型对应的数据；必须由 `type` 决定，不能接收任意 object。 |
| `created_at` | Timestamp | 是 | 创建时间。 |

## RunState

当前会话的可恢复状态。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `status` | RunStatus | 是 | 当前状态。 |
| `run_id` | ID | 是 | 当前执行 ID；与 `07-runtime-schema.md` 的 `RunState.run_id` 保持一致。 |
| `waiting_for` | WaitingFor | 否 | 当前等待对象：`model`、`tool`、`approval`、`user`、`adapter_action`。 |
| `pending_request_id` | ID | 否 | 等待中的权限请求 ID，仅用于 `waiting_for=approval`。 |
| `pending_tool_call_ids` | ID[] | 否 | 等待中的工具调用 ID，用于 `waiting_for=tool`。 |
| `pending_tool_batch_id` | ID | 否 | 等待中的工具批次 ID，用于批量工具聚合。 |
| `pending_adapter_action_id` | ID | 否 | 等待中的 Adapter 外部动作 ID，例如 `open_url_id`。 |
| `last_error` | ToolError \| ErrorPayload | 否 | 最近一次错误。 |

`pending_request_id` 不能混用来保存工具调用或 Adapter 动作。等待工具时使用 `pending_tool_call_ids` / `pending_tool_batch_id`，等待打开链接等外部动作时使用 `pending_adapter_action_id`。
