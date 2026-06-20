# 运行时 Schema

本文档把前面文档里的概念对象收敛成可落代码的运行时类型。第一版建议用 TypeScript 类型或 Zod schema 表达；如果核心运行时不是 TypeScript，也应保持同等字段和枚举。

## 基础约定

| 名称 | 类型 | 规则 |
| --- | --- | --- |
| `ID` | string | 带前缀的稳定 ID，例如 `sess_`、`run_`、`msg_`、`call_`、`evt_`。 |
| `Timestamp` | string | ISO 8601 UTC 字符串。 |
| `JsonValue` | JSON | 只允许 JSON 可序列化值，不允许函数、Date 实例、Error 实例。 |
| `RelativePath` | string | 相对 workspace 的路径，不允许 `..` 逃逸。 |
| `AbsolutePath` | string | 仅内部使用，不进入模型上下文。 |

## 枚举

### RunStatus

```ts
type RunStatus =
  | "queued"
  | "running"
  | "waiting_model"
  | "waiting_tool"
  | "waiting_approval"
  | "waiting_user"
  | "completed"
  | "failed"
  | "cancelled";
```

### StepType

```ts
type StepType =
  | "user_input"
  | "model_request"
  | "model_output"
  | "tool_call"
  | "permission_request"
  | "permission_decision"
  | "tool_result"
  | "adapter_command"
  | "state_change";
```

### StepStatus

```ts
type StepStatus =
  | "pending"
  | "running"
  | "done"
  | "failed"
  | "cancelled";
```

### StepPayload

`Step.payload` 必须和 `Step.type` 一一对应，不能使用泛 `object` 接收任意结构。

| StepType | Payload 类型 | 最小内容 |
| --- | --- | --- |
| `user_input` | `UserInputStepPayload` | `message_id`、`content`。 |
| `model_request` | `ModelRequestStepPayload` | `request_id`，可保存裁剪后的 `ModelRequest` 快照。 |
| `model_output` | `ModelOutputStepPayload` | `message_id`、`finish_reason`。 |
| `tool_call` | `ToolCallStepPayload` | `tool_call_id`、`name`、`action`。 |
| `permission_request` | `PermissionRequestStepPayload` | `request_id`、`action`、`options`。 |
| `permission_decision` | `PermissionDecisionStepPayload` | `decision_id`、`request_id`、`decision`。 |
| `tool_result` | `ToolResultStepPayload` | `tool_result_id`、`tool_call_id`、`ok`、`summary`、`created_at`。 |
| `adapter_command` | `AdapterCommandStepPayload` | `command_id`、`type`、`idempotency_key`。 |
| `state_change` | `StateChangeStepPayload` | `from`、`to`，等待态必须带 pending 字段。 |

```ts
type UserInputStepPayload = {
  message_id: ID;
  content: string;
};

type ModelRequestStepPayload = {
  request_id: ID;
  model?: string;
};

type ModelOutputStepPayload = {
  message_id: ID;
  finish_reason: ModelResponse["finish_reason"];
};

type ToolCallStepPayload = {
  tool_call_id: ID;
  name: string;
  action: string;
};

type PermissionRequestStepPayload = {
  request_id: ID;
  action: string;
  options: PermissionOption[];
};

type PermissionDecisionStepPayload = {
  decision_id: ID;
  request_id: ID;
  decision: PermissionDecisionValue;
  grant_scope?: GrantScope;
};

type ToolResultStepPayload = {
  tool_result_id: ID;
  tool_call_id: ID;
  ok: boolean;
  summary: string;
  error_code?: string;
  created_at: Timestamp;
};

type AdapterCommandStepPayload = {
  command_id: ID;
  type: AdapterCommandType;
  idempotency_key?: string;
};

type StateChangeStepPayload = StateChangedPayload;

type StepPayload =
  | UserInputStepPayload
  | ModelRequestStepPayload
  | ModelOutputStepPayload
  | ToolCallStepPayload
  | PermissionRequestStepPayload
  | PermissionDecisionStepPayload
  | ToolResultStepPayload
  | AdapterCommandStepPayload
  | StateChangeStepPayload;
```

### ToolCallStatus

```ts
type ToolCallStatus =
  | "created"
  | "validating"
  | "waiting_permission"
  | "executing"
  | "succeeded"
  | "failed"
  | "rejected"
  | "denied"
  | "cancelled";
```

### PermissionDecisionValue

```ts
type PermissionDecisionValue =
  | "approve_once"
  | "approve_run"
  | "approve_session"
  | "approve_workspace"
  | "deny"
  | "revise";
```

### PermissionOption

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `decision` | PermissionDecisionValue | 是 | 无 | Permission Gate。 |
| `label` | string | 是 | 无 | Adapter 展示文案。 |
| `grant_scope` | GrantScope | 条件必填 | 无 | 批准类选项必须填写；拒绝或修改类选项不填写。 |
| `is_default` | boolean | 否 | `false` | Permission Gate。 |

`PermissionOption.grant_scope` 不能超过命中的 `PolicyRule.grant_scope` 中的批准类范围。批准类选项只能使用 `GrantScope`，不能使用 `PolicyGrantScope.never`；`never` 只表示策略不允许生成授权记忆。Adapter 回传 `permission_decision` 时，`decision + grant_scope` 必须匹配某个 `PermissionRequest.options` 项。

### OpenUrlDoneStatus

```ts
type OpenUrlDoneStatus =
  | "opened"
  | "completed"
  | "failed"
  | "cancelled";
```

### WaitingFor

```ts
type WaitingFor =
  | "model"
  | "tool"
  | "approval"
  | "user"
  | "adapter_action";
```

### ToolBatchMode / ToolBatchFailurePolicy

```ts
type ToolBatchMode =
  | "sequential"
  | "parallel";

type ToolBatchFailurePolicy =
  | "fail_fast"
  | "continue_on_error"
  | "model_decides";

type ToolBatchStatus =
  | "created"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";
```

### EventType

```ts
type EventType =
  | "message_delta"
  | "message_completed"
  | "approval_required"
  | "open_url"
  | "tool_started"
  | "tool_result"
  | "state_changed"
  | "error";
```

### AdapterInputType

```ts
type AdapterInputType =
  | "user_message"
  | "permission_decision"
  | "adapter_command"
  | "interrupt"
  | "resume";
```

### AdapterInputPayload

`AdapterInput.payload` 必须由 `AdapterInput.type` 决定。

| AdapterInputType | Payload 类型 | 说明 |
| --- | --- | --- |
| `user_message` | `SubmitTextCommandPayload` | 用户输入文本和附件。 |
| `permission_decision` | `AdapterCommand` | `type` 必须为 `permission_decision`，不能只传裸 payload。 |
| `adapter_command` | `AdapterCommand` | 已标准化的 Adapter 命令。 |
| `interrupt` | `AdapterCommand` | `type` 必须为 `cancel`，不能只传裸 payload。 |
| `resume` | `AdapterCommand` | `type` 必须为 `resume`，不能只传裸 payload。 |

```ts
type AdapterInputPayload =
  | SubmitTextCommandPayload
  | AdapterCommand;
```

除 `type="user_message"` 外，`AdapterInput.payload` 必须是完整 `AdapterCommand`，保留 `command_id`、`event_id`、`idempotency_key` 和命令类型。Core 接收 `permission_decision`、`interrupt`、`resume` 这类状态变化输入时，不能绕过 `CommandReceipt`。

### AdapterKind / AdapterCommandType

```ts
type AdapterKind =
  | "cli"
  | "web"
  | "desktop";

type AdapterCommandType =
  | "submit_text"
  | "permission_decision"
  | "cancel"
  | "resume"
  | "open_url_done";
```

### TransportDirection / TransportKind

```ts
type TransportDirection =
  | "server_to_client"
  | "client_to_server";

type TransportKind =
  | "event"
  | "command"
  | "ack"
  | "hello"
  | "heartbeat"
  | "error";
```

### TransportPayload

`TransportEnvelope.payload` 必须由 `TransportEnvelope.kind` 决定。

| TransportKind | Payload 类型 |
| --- | --- |
| `event` | `AgentEvent` |
| `command` | `CommandFrame` |
| `ack` | `AckFrame` |
| `hello` | `ClientHello` |
| `heartbeat` | `HeartbeatPayload` |
| `error` | `ErrorPayload` |

```ts
type TransportPayload =
  | AgentEvent
  | CommandFrame
  | AckFrame
  | ClientHello
  | HeartbeatPayload
  | ErrorPayload;
```

### GrantScope

`GrantScope` 只表示已经批准或可批准的授权范围。策略层“不允许生成授权记忆”使用 `PolicyGrantScope.never`，不能落入 `PermissionOption`、`PermissionDecision` 或 `PermissionGrant`。

```ts
type GrantScope =
  | "once"
  | "run"
  | "session"
  | "workspace";

type PolicyGrantScope =
  | GrantScope
  | "never";
```

## 核心运行对象

### AgentConfig

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `agent_id` | ID | 是 | 生成或配置 | Agent 配置。 |
| `model` | string | 是 | 无 | Agent 配置。 |
| `workspace` | AbsolutePath | 是 | 无 | Agent 配置。 |
| `tool_policy` | string | 是 | `default` | Agent 配置。 |
| `enabled_tools` | string[] | 是 | `[]` | Agent 配置。 |
| `event_mode` | `pty` \| `event` | 是 | `event` | Agent 配置。 |

### Session

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `session_id` | ID | 是 | 生成 | Core。 |
| `agent_id` | ID | 是 | 无 | AgentConfig。 |
| `created_at` | Timestamp | 是 | 生成 | Core。 |
| `updated_at` | Timestamp | 是 | 生成 | Core。 |
| `messages` | Message[] | 是 | `[]` | Core。 |
| `runs` | Run[] | 是 | `[]` | Core。 |
| `run_state` | RunState | 是 | 无 | Core 状态机；完整可恢复状态使用 `SessionState`。 |

### Message

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `message_id` | ID | 是 | 生成 | Core。 |
| `role` | `system` \| `user` \| `assistant` \| `tool` | 是 | 无 | Core 或模型输出。 |
| `content` | string | 是 | `""` | 用户输入、模型输出或工具 observation。 |
| `tool_call_id` | ID | 否 | 无 | 工具消息关联的调用 ID。 |
| `created_at` | Timestamp | 是 | 生成 | Core。 |

## 模型交互对象

### ModelMessage

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `role` | `system` \| `user` \| `assistant` \| `tool` | 是 | 无 | Core 组装。 |
| `content` | string | 是 | `""` | Message 或 Observation。 |
| `tool_call_id` | ID | 否 | 无 | 工具 observation。 |
| `name` | string | 否 | 无 | 工具名或系统标识。 |

### ModelTool

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `name` | string | 是 | 无 | Tool Registry。 |
| `description` | string | 是 | 无 | ToolDefinition。 |
| `input_schema` | object | 是 | 无 | ToolDefinition。 |
| `action` | string | 是 | 无 | ToolDefinition，传给 Permission Gate 的策略动作名。 |

### ModelRequest

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `request_id` | ID | 是 | 生成 | Model Runtime。 |
| `session_id` | ID | 是 | 无 | Session。 |
| `run_id` | ID | 是 | 无 | Run。 |
| `model` | string | 是 | AgentConfig.model | AgentConfig。 |
| `messages` | ModelMessage[] | 是 | `[]` | Transcript 裁剪后生成。 |
| `tools` | ModelTool[] | 是 | `[]` | Tool Registry。 |
| `temperature` | number | 否 | `0.2` | AgentConfig 或调用参数。 |
| `stream` | boolean | 是 | `true` | Adapter 能力决定。 |

### ModelResponse

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `request_id` | ID | 是 | 无 | ModelRequest。 |
| `message_id` | ID | 是 | 生成 | Model Runtime。 |
| `content` | string | 是 | `""` | 模型输出。 |
| `tool_calls` | ModelToolCall[] | 是 | `[]` | 模型输出。 |
| `finish_reason` | `stop` \| `tool_calls` \| `length` \| `error` | 是 | 无 | 模型输出。 |
| `usage` | object | 否 | 无 | 模型供应商返回。 |

### ModelToolCall

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `tool_call_id` | ID | 是 | 生成或模型返回 | 模型输出。 |
| `name` | string | 是 | 无 | 模型输出。 |
| `arguments` | object | 是 | `{}` | 模型输出解析。 |

模型输出的 `ModelToolCall` 只是原始意图。进入 Tool Runtime 后必须转换为带 `run_id`、`origin_message_id`、`status`、时间字段和权限关联字段的 `ToolCall`。

## 工具运行对象

### ToolCall

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `tool_call_id` | ID | 是 | 生成或继承 | ModelToolCall。 |
| `name` | string | 是 | 无 | ModelToolCall。 |
| `arguments` | object | 是 | `{}` | ModelToolCall。 |
| `run_id` | ID | 是 | 无 | 当前 Run。 |
| `action` | string | 是 | 无 | ToolDefinition.action，传给 Permission Gate 的策略动作名。 |
| `origin_message_id` | ID | 是 | 无 | 模型消息。 |
| `status` | ToolCallStatus | 是 | `created` | Tool Runtime。 |
| `tool_batch_id` | ID | 否 | 无 | ToolBatch。 |
| `index` | number | 否 | 无 | 模型工具调用顺序。 |
| `depends_on` | ID[] | 否 | `[]` | Core 调度器。 |
| `permission_request_id` | ID | 否 | 无 | Permission Gate。 |
| `created_at` | Timestamp | 是 | 生成 | Tool Runtime。 |
| `started_at` | Timestamp | 否 | 无 | Executor。 |
| `ended_at` | Timestamp | 否 | 无 | Executor。 |

### ToolBatch

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `tool_batch_id` | ID | 是 | 生成 | Core 调度器。 |
| `run_id` | ID | 是 | 无 | 当前 Run。 |
| `origin_message_id` | ID | 是 | 无 | 模型消息。 |
| `mode` | ToolBatchMode | 是 | `sequential` | Core 调度器。 |
| `failure_policy` | ToolBatchFailurePolicy | 是 | `fail_fast` | Core 调度器。 |
| `tool_call_ids` | ID[] | 是 | `[]` | Core 调度器。 |
| `status` | ToolBatchStatus | 是 | `created` | Core 调度器。 |
| `created_at` | Timestamp | 是 | 生成 | Core 调度器。 |
| `ended_at` | Timestamp | 否 | 无 | Core 调度器。 |

### ToolResult

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `tool_result_id` | ID | 是 | 生成 | Executor。 |
| `tool_call_id` | ID | 是 | 无 | ToolCall。 |
| `ok` | boolean | 是 | 无 | Executor。 |
| `content` | string | 是 | `""` | 给模型的 observation。 |
| `summary` | string | 是 | `content` 截断摘要或错误摘要 | 给 UI 的摘要；事件流和审计必须可展示。 |
| `data` | object | 否 | 无 | 结构化结果。 |
| `error` | ToolError | 否 | 无 | 失败时填写。 |
| `audit_id` | ID | 否 | 无 | AuditLog。 |
| `created_at` | Timestamp | 是 | 生成 | Executor。 |

### ToolError

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `code` | string | 是 | 无 | Tool Runtime 或 Executor。 |
| `message` | string | 是 | 无 | Tool Runtime 或 Executor。 |
| `retryable` | boolean | 是 | `false` | Tool Runtime 或 Executor。 |
| `details` | object | 否 | 无 | 原始错误细节，不直接给模型。 |

## 权限与审计对象

### RiskLevel

```ts
type RiskLevel =
  | "safe"
  | "medium"
  | "high"
  | "critical";
```

### PermissionRequest

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `request_id` | ID | 是 | 生成 | Permission Gate。 |
| `run_id` | ID | 是 | 无 | 当前 Run。 |
| `action` | string | 是 | 无 | 策略动作名，例如 `command.run`、`url.open`。 |
| `risk` | RiskLevel | 是 | 无 | Policy Engine。 |
| `reason` | string | 是 | 无 | Tool Runtime 或 Adapter。 |
| `scope` | string | 是 | 无 | 影响范围。 |
| `preview` | object | 否 | 无 | 命令、路径、URL 或 diff 预览。 |
| `options` | PermissionOption[] | 是 | 无 | 可选决策。 |

### PermissionDecision

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `decision_id` | ID | 是 | 生成 | Permission Gate。 |
| `request_id` | ID | 是 | 无 | PermissionRequest。 |
| `decision` | PermissionDecisionValue | 是 | 无 | 用户或策略。 |
| `grant_scope` | GrantScope | 否 | 无 | 当 `decision` 为批准类决策时填写，不能超过 `PermissionRequest.options` 和 `PolicyRule.grant_scope` 中的批准类范围。 |
| `decided_by` | `user` \| `policy` | 是 | 无 | Permission Gate。 |
| `client_id` | ID | 否 | 无 | Adapter。 |
| `idempotency_key` | string | 是 | 生成或命令传入 | AdapterCommand 或策略自动决策。 |
| `comment` | string | 否 | 无 | 用户或策略说明。 |
| `created_at` | Timestamp | 是 | 生成 | Permission Gate。 |

### AuditResult

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `executed` | boolean | 是 | 无 | Tool Runtime 或 Adapter。 |
| `ok` | boolean | 是 | 无 | 执行结果。 |
| `tool_call_id` | ID | 否 | 无 | ToolCall。 |
| `tool_result_id` | ID | 条件必填 | 无 | 当 `tool_call_id` 存在且工具已产生结果时必须填写。 |
| `summary` | string | 是 | 无 | 可展示摘要。 |
| `error_code` | string | 否 | 无 | 稳定错误码。 |
| `retryable` | boolean | 否 | 无 | 是否可重试。 |

### AuditLog

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `audit_id` | ID | 是 | 生成 | Audit Logger。 |
| `session_id` | ID | 是 | 无 | Session。 |
| `run_id` | ID | 否 | 无 | Run。 |
| `client_id` | ID | 否 | 无 | Adapter。 |
| `adapter` | AdapterKind | 否 | 无 | Adapter。 |
| `tool_call_id` | ID | 否 | 无 | ToolCall。 |
| `tool_batch_id` | ID | 否 | 无 | ToolBatch。 |
| `request` | PermissionRequest | 否 | 无 | 权限请求快照。 |
| `decision` | PermissionDecision | 否 | 无 | 权限决策快照。 |
| `result` | AuditResult | 否 | 无 | 执行结果摘要。 |
| `created_at` | Timestamp | 是 | 生成 | Audit Logger。 |

### PendingAdapterAction

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `adapter_action_id` | ID | 是 | 生成 | Core。 |
| `run_id` | ID | 是 | 无 | 当前 Run。 |
| `event_id` | ID | 是 | 无 | 触发动作的 AgentEvent。 |
| `type` | `open_url` | 是 | 无 | Core。 |
| `status` | `pending` \| OpenUrlDoneStatus | 是 | `pending` | Core 或 AdapterCommand。 |
| `owner_client_id` | ID | 否 | 无 | 首个接手动作的客户端。 |
| `command_receipt_ids` | ID[] | 是 | `[]` | 指向 `SessionState.processed_commands.receipt_id`，不重复保存回执正文。 |
| `created_at` | Timestamp | 是 | 生成 | Core。 |
| `updated_at` | Timestamp | 是 | 生成 | Core。 |

## RunState

`RunState` 是恢复和 UI 同步的当前状态视图。不同等待阶段必须使用不同 pending 字段，不能把工具调用、权限请求和 Adapter 动作都塞进 `pending_request_id`。

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `run_id` | ID | 是 | 无 | Run 创建。 |
| `status` | RunStatus | 是 | `queued` | Core 状态机。 |
| `waiting_for` | WaitingFor | 否 | 无 | 当前等待对象。 |
| `pending_request_id` | ID | 否 | 无 | 仅用于 `waiting_approval` 的权限请求。 |
| `pending_tool_call_ids` | ID[] | 否 | `[]` | `waiting_tool` 下等待中的工具调用。 |
| `pending_tool_batch_id` | ID | 否 | 无 | `waiting_tool` 下等待聚合的工具批次。 |
| `pending_adapter_action_id` | ID | 否 | 无 | `waiting_user` / `adapter_action` 下等待 Adapter 完成的动作，例如 `open_url_id`。 |
| `last_error` | ToolError \| ErrorPayload | 否 | 无 | 失败状态的稳定错误。 |

字段约束：

- `waiting_for="approval"` 时必须有 `pending_request_id`，且工具和 Adapter pending 字段为空。
- `waiting_for="tool"` 时必须有 `pending_tool_call_ids` 或 `pending_tool_batch_id`，且 `pending_request_id` 为空。
- `waiting_for="adapter_action"` 或 `waiting_for="user"` 且等待外部链接完成时，必须有 `pending_adapter_action_id`，不能复用 `pending_request_id`。
- `completed`、`failed`、`cancelled` 这类终态不得保留任何 pending 字段；`failed` 必须有 `last_error`。

## 状态、存储与恢复对象

### Step

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `step_id` | ID | 是 | 生成 | Core。 |
| `type` | StepType | 是 | 无 | Core。 |
| `status` | StepStatus | 是 | `pending` | Core 状态机。 |
| `payload` | StepPayload | 是 | `{}` | 步骤类型决定。 |
| `created_at` | Timestamp | 是 | 生成 | Core。 |

### Run

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `run_id` | ID | 是 | 生成 | Core。 |
| `session_id` | ID | 是 | 无 | Session。 |
| `input_message_id` | ID | 是 | 无 | 用户消息。 |
| `status` | RunStatus | 是 | `queued` | Core 状态机。 |
| `steps` | Step[] | 是 | `[]` | Core。 |
| `started_at` | Timestamp | 是 | 生成 | Core。 |
| `ended_at` | Timestamp | 否 | 无 | Core。 |

### SessionState

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `session_id` | ID | 是 | 无 | Session。 |
| `run_state` | RunState | 是 | 无 | Core 状态机。 |
| `messages` | Message[] | 是 | `[]` | Transcript replay。 |
| `pending_tool_calls` | ToolCall[] | 是 | `[]` | Tool Runtime。 |
| `pending_tool_batches` | ToolBatch[] | 是 | `[]` | Core 调度器。 |
| `pending_permissions` | PermissionRequest[] | 是 | `[]` | Permission Gate。 |
| `pending_adapter_actions` | PendingAdapterAction[] | 是 | `[]` | Core。 |
| `processed_commands` | CommandReceipt[] | 是 | `[]` | Core 命令入口。 |
| `updated_at` | Timestamp | 是 | 生成 | State Store。 |

### Checkpoint

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `checkpoint_id` | ID | 是 | 生成 | State Store。 |
| `session_id` | ID | 是 | 无 | Session。 |
| `run_id` | ID | 否 | 无 | Run。 |
| `state` | SessionState | 是 | 无 | State Store。 |
| `base_event_seq` | number | 是 | 无 | Transcript。 |
| `transcript_hash` | string | 否 | 无 | State Store。 |
| `reason` | string | 是 | 无 | 创建检查点的原因。 |
| `created_at` | Timestamp | 是 | 生成 | State Store。 |

### Transcript

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `session_id` | ID | 是 | 无 | Session。 |
| `messages` | Message[] | 是 | `[]` | Core。 |
| `events` | AgentEvent[] | 是 | `[]` | Event Bus。 |
| `tool_calls` | ToolCall[] | 是 | `[]` | Tool Runtime。 |
| `tool_results` | ToolResult[] | 是 | `[]` | Executor。 |
| `audit_logs` | AuditLog[] | 是 | `[]` | Audit Logger。 |

## 事件 payload 联合类型

`AgentEvent.payload` 必须由 `type` 决定，禁止让 Adapter 猜字段。

```ts
type AgentEventPayload =
  | MessageDeltaPayload
  | MessageCompletedPayload
  | ApprovalRequiredPayload
  | OpenUrlPayload
  | ToolStartedPayload
  | ToolResultPayload
  | StateChangedPayload
  | ErrorPayload;

type AgentEvent = {
  event_id: ID;
  type: EventType;
  session_id: ID;
  run_id?: ID;
  created_at: Timestamp;
  payload: AgentEventPayload;
};
```

### AgentEvent

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `event_id` | ID | 是 | 事件 ID。 |
| `type` | EventType | 是 | 事件类型。 |
| `session_id` | ID | 是 | 所属会话。 |
| `run_id` | ID | 否 | 所属执行。 |
| `created_at` | Timestamp | 是 | 创建时间。 |
| `payload` | AgentEventPayload | 是 | 由 `type` 决定的载荷。 |

`AgentEvent.type` 和 `payload` 必须一一匹配，例如 `type="open_url"` 只能使用 `OpenUrlPayload`。事件进入 `Transcript.events` 时必须保留 `event_id`、`session_id`、`run_id` 和 `created_at`，不能只保存 payload。

### MessageDeltaPayload

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `message_id` | ID | 是 | 正在输出的模型消息。 |
| `delta` | string | 是 | 本次增量文本。 |

### MessageCompletedPayload

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `message_id` | ID | 是 | 已完成消息。 |
| `content` | string | 是 | 完整文本。 |
| `finish_reason` | string | 是 | 结束原因。 |

### ApprovalRequiredPayload

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `request_id` | ID | 是 | 权限请求 ID。 |
| `title` | string | 是 | 展示标题。 |
| `risk` | RiskLevel | 是 | 风险等级。 |
| `action` | string | 是 | 策略动作名，例如 `command.run`、`url.open`。 |
| `scope` | string | 是 | 影响范围。 |
| `preview` | object | 否 | 命令、路径、URL 或 diff 预览。 |
| `options` | PermissionOption[] | 是 | 可选决策。 |

### OpenUrlPayload

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `open_url_id` | ID | 是 | 打开链接动作 ID。 |
| `url` | string | 是 | 要打开的 URL。 |
| `reason` | string | 是 | 打开原因。 |
| `requires_user_action` | boolean | 是 | 是否需要用户在页面完成操作。 |
| `request_id` | ID | 否 | 关联权限请求。 |
| `return_hint` | string | 否 | 给用户看的返回提示。 |

### ToolStartedPayload

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `tool_call_id` | ID | 是 | 工具调用 ID。 |
| `name` | string | 是 | 工具名。 |
| `started_at` | Timestamp | 是 | 开始时间。 |

### ToolResultPayload

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `tool_result_id` | ID | 是 | 工具结果 ID。 |
| `tool_call_id` | ID | 是 | 工具调用 ID。 |
| `ok` | boolean | 是 | 是否成功。 |
| `summary` | string | 是 | 给 UI 展示的摘要。 |
| `error_code` | string | 否 | 失败时的稳定错误码。 |
| `created_at` | Timestamp | 是 | 结果生成时间。 |

### StateChangedPayload

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `from` | RunStatus | 否 | 原状态。 |
| `to` | RunStatus | 是 | 新状态。 |
| `waiting_for` | WaitingFor | 否 | 等待对象。 |
| `pending_request_id` | ID | 否 | 仅等待权限请求时填写。 |
| `pending_tool_call_ids` | ID[] | 否 | 等待工具调用时填写。 |
| `pending_tool_batch_id` | ID | 否 | 等待工具批次聚合时填写。 |
| `pending_adapter_action_id` | ID | 否 | 等待 Adapter 外部动作时填写。 |
| `last_error` | ToolError \| ErrorPayload | 否 | 进入失败状态时填写，必须和 `RunState.last_error` 一致。 |

## Adapter 与命令对象

### AdapterInput

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `input_id` | ID | 是 | 生成 | Adapter。 |
| `session_id` | ID | 是 | 无 | Session。 |
| `type` | AdapterInputType | 是 | 无 | Adapter。 |
| `payload` | AdapterInputPayload | 是 | 无 | Adapter。 |
| `source` | AdapterKind | 是 | 无 | Adapter。 |

`AdapterInput.type` 和 `payload` 约束：

- `user_message` 可以直接使用 `SubmitTextCommandPayload`，由 Core 生成内部 `AdapterCommand` 或直接创建用户消息。
- `permission_decision` 必须使用完整 `AdapterCommand`，且 `payload.type="permission_decision"`。
- `interrupt` 必须使用完整 `AdapterCommand`，且 `payload.type="cancel"`。
- `resume` 必须使用完整 `AdapterCommand`，且 `payload.type="resume"`。
- `adapter_command` 必须使用完整 `AdapterCommand`，并按 `AdapterCommand.type` 校验 payload。

### AdapterOutput

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `output_id` | ID | 是 | 生成 | Core。 |
| `session_id` | ID | 是 | 无 | Session。 |
| `events` | AgentEvent[] | 是 | `[]` | Core。 |
| `state` | RunState | 是 | 无 | Core。 |

### PermissionDecisionCommandPayload

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `request_id` | ID | 是 | 无 | approval_required。 |
| `decision` | PermissionDecisionValue | 是 | 无 | 用户或 Adapter。 |
| `grant_scope` | GrantScope | 条件必填 | 无 | 批准类决策必须显式填写，并与决策值一一映射。 |
| `idempotency_key` | string | 是 | 无 | AdapterCommand。 |
| `comment` | string | 否 | 无 | 用户或 Adapter。 |

批准类决策值和授权范围必须按以下规则匹配：`approve_once -> once`、`approve_run -> run`、`approve_session -> session`、`approve_workspace -> workspace`。`deny`、`revise` 不得携带 `grant_scope`。

### SubmitTextCommandPayload

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `message_id` | ID | 否 | 生成 | Adapter 或 Core。 |
| `content` | string | 是 | 无 | 用户输入。 |
| `attachments` | object[] | 否 | `[]` | Adapter。 |

### CancelCommandPayload

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `run_id` | ID | 否 | 当前 Run | Adapter。 |
| `reason` | string | 否 | 无 | 用户或 Adapter。 |
| `idempotency_key` | string | 是 | 无 | AdapterCommand。 |

### ResumeCommandPayload

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `run_id` | ID | 否 | 当前 Run | Adapter。 |
| `from_checkpoint_id` | ID | 否 | 无 | Adapter。 |
| `idempotency_key` | string | 是 | 无 | AdapterCommand。 |

### OpenUrlDoneCommandPayload

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `open_url_id` | ID | 是 | 无 | open_url event。 |
| `status` | OpenUrlDoneStatus | 是 | 无 | Adapter。 |
| `idempotency_key` | string | 是 | 无 | AdapterCommand。 |
| `message` | string | 否 | 无 | Adapter。 |
| `error_code` | string | 否 | 无 | Adapter。 |

### AdapterCommand

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `command_id` | ID | 是 | 生成 | Adapter。 |
| `event_id` | ID | 否 | 无 | 对应事件。 |
| `type` | AdapterCommandType | 是 | 无 | Adapter。 |
| `payload` | SubmitTextCommandPayload \| PermissionDecisionCommandPayload \| CancelCommandPayload \| ResumeCommandPayload \| OpenUrlDoneCommandPayload | 是 | 无 | 命令类型决定。 |
| `idempotency_key` | string | 条件必填 | 无 | 状态变化或副作用命令必须填写。 |

`permission_decision`、`cancel`、`resume`、`open_url_done` 的 `payload.idempotency_key` 必须与顶层 `idempotency_key` 一致。

### CommandFrame

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `command_id` | ID | 是 | 生成 | Client。 |
| `event_id` | ID | 否 | 无 | 对应事件。 |
| `type` | AdapterCommandType | 是 | 无 | Client。 |
| `payload` | SubmitTextCommandPayload \| PermissionDecisionCommandPayload \| CancelCommandPayload \| ResumeCommandPayload \| OpenUrlDoneCommandPayload | 是 | 无 | 命令参数。 |
| `idempotency_key` | string | 条件必填 | 无 | 状态变化或副作用命令必须填写；`submit_text` 可选。 |

`CommandFrame` 转成 `AdapterCommand` 时必须保留同一个顶层 `idempotency_key`，并复制到需要幂等的 payload 中。`permission_decision`、`cancel`、`resume`、`open_url_done` 必须有顶层 `idempotency_key`，且必须与 payload 内同名字段一致；`submit_text` 可以没有幂等键，如果提供则同样进入 `CommandReceipt` 去重。

### CommandResult

命令入口处理后的稳定结果。重复命令必须返回第一次 `CommandResult`。

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `ok` | boolean | 是 | 无 | Core。 |
| `status` | `accepted` \| `duplicate` \| `conflict` \| `failed` | 是 | 无 | Core。 |
| `message` | string | 否 | 无 | Core。 |
| `decision_id` | ID | 否 | 无 | Permission Gate。 |
| `adapter_action_id` | ID | 否 | 无 | Core。 |
| `error_code` | string | 否 | 无 | Core。 |

### CommandReceipt

`CommandReceipt` 是幂等和断线恢复的持久记录，不能只保存字符串数组。

只有带顶层 `idempotency_key` 的命令才会创建 `CommandReceipt`。`submit_text` 如果没有提供幂等键，可以直接创建消息而不写回执；如果提供幂等键，则必须写入回执并参与重复提交检测。

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `receipt_id` | ID | 是 | 生成 | Core 命令入口。 |
| `session_id` | ID | 是 | 无 | Session。 |
| `run_id` | ID | 否 | 无 | Run。 |
| `command_id` | ID | 是 | 无 | AdapterCommand 或 CommandFrame。 |
| `type` | AdapterCommandType | 是 | 无 | AdapterCommand 或 CommandFrame。 |
| `idempotency_key` | string | 是 | 无 | AdapterCommand 或 CommandFrame。 |
| `payload_hash` | string | 是 | 无 | 对 canonical JSON payload 做稳定哈希。 |
| `result` | CommandResult | 是 | 无 | Core 命令入口。 |
| `created_at` | Timestamp | 是 | 生成 | Core。 |
| `updated_at` | Timestamp | 是 | 生成 | Core。 |

同一 `session_id + type + idempotency_key` 再次出现时，若 `payload_hash` 一致，返回第一次 `result`；若不一致，返回 `status="conflict"`，并禁止推进状态。

## 传输对象

### TransportEnvelope

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `envelope_id` | ID | 是 | 生成 | Transport。 |
| `session_id` | ID | 是 | 无 | Session。 |
| `run_id` | ID | 否 | 无 | Run。 |
| `direction` | TransportDirection | 是 | 无 | Transport。 |
| `kind` | TransportKind | 是 | 无 | Transport。 |
| `seq` | number | 是 | 无 | Session 内单调递增。 |
| `payload` | TransportPayload | 是 | 无 | 由 `kind` 决定。 |
| `created_at` | Timestamp | 是 | 生成 | Transport。 |

`kind="event"` 时 `payload` 必须是完整 `AgentEvent`；`kind="command"` 时 `payload` 必须是 `CommandFrame`。客户端按 `seq` 有序处理，发现断号必须走恢复接口，不能猜测状态。

### ClientHello

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `client_id` | ID | 是 | 生成 | Client。 |
| `adapter` | AdapterKind | 是 | 无 | Client。 |
| `protocol_version` | string | 是 | 无 | Client。 |
| `last_seen_seq` | number | 否 | 无 | Client。 |
| `capabilities` | string[] | 是 | `[]` | Client。 |

### AckFrame

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `client_id` | ID | 是 | 无 | Client。 |
| `ack_seq` | number | 是 | 无 | Client。 |
| `received_event_ids` | ID[] | 否 | 无 | Client。 |

### HeartbeatPayload

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `client_id` | ID | 否 | 无 | Client。 |
| `last_seen_seq` | number | 否 | 无 | Client。 |
| `sent_at` | Timestamp | 是 | 生成 | Transport。 |

## 安全策略对象

### SecurityContext

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `session_id` | ID | 是 | 无 | Session。 |
| `run_id` | ID | 否 | 无 | Run。 |
| `client_id` | ID | 否 | 无 | Adapter。 |
| `adapter` | AdapterKind | 是 | 无 | Adapter。 |
| `workspace_root` | AbsolutePath | 否 | 无 | Runtime。 |
| `user_id` | ID | 否 | 无 | Auth。 |
| `policy_profile` | string | 是 | `default` | Policy Engine。 |

### PolicyRule

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `rule_id` | ID | 是 | 无 | Policy Config。 |
| `action` | string | 是 | 无 | Policy Config。 |
| `risk` | RiskLevel | 是 | 无 | Policy Config。 |
| `match` | object | 是 | `{}` | Policy Config，必须使用结构化匹配条件。 |
| `decision` | `allow` \| `ask` \| `deny` | 是 | 无 | Policy Config。 |
| `grant_scope` | PolicyGrantScope[] | 是 | `[]` | Policy Config。 |
| `audit_required` | boolean | 是 | `true` | Policy Config。 |

### PermissionGrant

| 字段 | 类型 | 必填 | 默认值 | 来源 |
| --- | --- | --- | --- | --- |
| `grant_id` | ID | 是 | 生成 | Permission Gate。 |
| `request_id` | ID | 是 | 无 | PermissionRequest。 |
| `action` | string | 是 | 无 | PermissionRequest。 |
| `scope` | GrantScope | 是 | 无 | PermissionDecision。 |
| `constraints` | object | 是 | `{}` | Permission Gate。 |
| `granted_by` | `user` \| `policy` | 是 | 无 | Permission Gate。 |
| `expires_at` | Timestamp | 否 | 无 | Permission Gate。 |
| `created_at` | Timestamp | 是 | 生成 | Permission Gate。 |

只有批准类 `PermissionDecision` 可以生成 `PermissionGrant`。`deny`、`revise` 或策略命中 `PolicyGrantScope.never` 时不得生成持久授权；批准类决策的 `PermissionGrant.scope` 必须等于 `PermissionDecision.grant_scope`，且不能是 `never`。

### ErrorPayload

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `code` | string | 是 | 稳定错误码。 |
| `message` | string | 是 | 可展示错误说明。 |
| `retryable` | boolean | 是 | 是否可重试。 |
| `details` | object | 否 | 调试信息，不直接给模型。 |
