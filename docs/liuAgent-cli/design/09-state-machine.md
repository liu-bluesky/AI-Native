# 状态机

状态机约束 Core、Tool Runtime、Permission Gate 和 Adapter 的协作边界。任何实现都不应该靠布尔字段猜当前流程。

## Run 状态机

```text
queued
  -> running
  -> waiting_model
  -> running
  -> waiting_tool
  -> running
  -> waiting_approval
  -> running
  -> waiting_user
  -> completed

running -> failed
running -> cancelled
waiting_* -> cancelled
```

## Run 状态定义

| 状态 | 含义 | 允许进入方式 | 允许退出方式 |
| --- | --- | --- | --- |
| `queued` | Run 已创建但未开始 | 用户输入创建 Run | `running`、`cancelled` |
| `running` | Core 正在推进流程 | 调度器启动或等待结束 | `waiting_model`、`waiting_tool`、`waiting_approval`、`waiting_user`、`completed`、`failed`、`cancelled` |
| `waiting_model` | 已向模型发请求，等待响应 | 创建 ModelRequest | `running`、`failed`、`cancelled` |
| `waiting_tool` | 工具调用正在执行 | Tool Runtime 接受调用 | `running`、`failed`、`cancelled` |
| `waiting_approval` | 等待用户或策略决策 | Permission Gate 产生请求 | `running`、`cancelled` |
| `waiting_user` | 等待普通用户输入 | Core 发起继续确认或外部操作等待 | `running`、`cancelled` |
| `completed` | Run 成功结束 | 模型给出最终答案 | 终态 |
| `failed` | Run 失败 | 不可恢复错误 | 终态或人工 resume |
| `cancelled` | Run 被取消 | 用户中断或系统取消 | 终态 |

## open_url 状态流

`open_url` 是 Adapter 动作，不是工具结果。它通常用于 OAuth、外部网页确认、浏览器授权等流程。

```text
running
  -> waiting_approval
  -> running
  -> waiting_user
  -> running
```

规则：

1. 如果链接动作需要授权，先进入 `waiting_approval`，产生 `approval_required`。
2. 用户批准后，Core 发出 `open_url` 事件。
3. 若 `requires_user_action=true`，Run 进入 `waiting_user`，`pending_adapter_action_id` 记录 `open_url_id`。
4. Adapter 回传 `open_url_done.status=completed` 后，Run 回到 `running`。
5. `open_url_done.status=failed` 时，Run 进入 `failed`，并记录可展示错误。
6. `open_url_done.status=cancelled` 时，Run 进入 `cancelled` 或保持 `waiting_user` 等待用户重新选择；由具体动作策略决定。

`open_url_done.status=opened` 只能更新展示状态，不能让 Run 从 `waiting_user` 恢复为 `running`。

## 工具调用状态机

```text
created
  -> validating
  -> waiting_permission
  -> executing
  -> succeeded

validating -> rejected
waiting_permission -> denied
executing -> failed
executing -> cancelled
```

| 状态 | 含义 | 必须记录 |
| --- | --- | --- |
| `created` | 模型产生 ToolCall | `tool_call_id`、`name`、`arguments`、`action` |
| `validating` | 校验工具名和 schema | schema 校验结果 |
| `waiting_permission` | 需要权限确认 | `PermissionRequest` |
| `executing` | 执行器运行中 | started event、audit trail |
| `succeeded` | 工具成功 | `ToolResult.tool_result_id`、`ToolResult.ok=true` |
| `failed` | 工具执行失败 | `ToolError` |
| `rejected` | schema 或策略直接拒绝 | `ToolError` |
| `denied` | 用户或策略拒绝 | `PermissionDecision` |
| `cancelled` | 用户中断或系统取消 | cancel reason |

## 多工具调用调度

模型一次返回多个 `ModelToolCall` 时，Core 必须先创建一个 `ToolBatch`，再把每个意图转换成 `ToolCall`。不要让 Adapter 自己决定并发或顺序。

调度模式：

- `sequential`：按 `index` 顺序执行；任一工具失败时按 `failure_policy` 处理。
- `parallel`：无依赖工具可并发执行；所有终态结果汇总后再回到模型。

失败策略：

- `fail_fast`：第一个 `failed`、`rejected`、`denied` 使整个批次失败，未开始的工具标记为 `cancelled`。
- `continue_on_error`：继续执行剩余工具，把成功和失败结果都作为 observation 返回给模型。
- `model_decides`：高风险或语义相关工具失败后暂停，把部分结果交给模型判断下一步。

不变量：

- 同一 `ToolBatch` 内每个 `ToolCall` 必须有稳定 `index`。
- 有 `depends_on` 的工具不能早于依赖工具成功执行。
- `waiting_tool` 可以同时等待多个 pending `tool_call_id`，但必须能从 `ToolBatch` 聚合出批次状态。
- 批次结束后才能把完整 observation 交回模型；除非工具定义显式允许流式 observation。

## 权限请求状态机

```text
created
  -> presented
  -> decided
  -> consumed

presented -> expired
presented -> cancelled
```

| 状态 | 含义 | 说明 |
| --- | --- | --- |
| `created` | Permission Gate 创建请求 | 尚未展示。 |
| `presented` | Adapter 已展示给用户 | CLI/Web/Desktop 可用不同 UI。 |
| `decided` | 已收到用户或策略决策 | 记录 `PermissionDecision`。 |
| `consumed` | 决策已被 Tool Runtime 消费 | 允许继续或拒绝执行。 |
| `expired` | 请求过期 | 默认拒绝。 |
| `cancelled` | Run 被取消 | 不再执行。 |

## Adapter 命令处理

Adapter 只能通过 `AdapterInput` 或 `AdapterCommand` 回传用户动作。Core 接收后必须校验：

1. `session_id` 是否匹配当前 Session。
2. `event_id` 或 `request_id` 是否仍处于 pending。
3. command 类型是否允许作用于当前状态。
4. 是否会导致权限越级。

## 恢复规则

恢复时不允许无条件重放副作用动作。

| 恢复状态 | 默认策略 |
| --- | --- |
| `waiting_approval` | 恢复审批 UI，等待用户重新决策或继续原决策。 |
| `waiting_tool` | 检查工具是否有幂等结果；没有则标记为 `failed` 并要求重新发起。 |
| `waiting_user` | 如果等待 `open_url_done`，恢复链接完成 UI；不能仅凭链接已打开自动继续。 |
| `waiting_model` | 可以重新请求模型，但必须保留原 request 记录。 |
| `running` | 先按 checkpoint 后事件重放重建状态，再按未完成副作用判定：存在 pending 权限、工具批次或 Adapter 动作时进入对应 `waiting_*`；不存在 pending 且上一事件为终态时保持终态；仍无法证明可继续时进入 `failed` 并要求显式 resume。 |
| `completed` | 只读展示，不再推进。 |
| `failed` | 允许用户显式 resume，生成新 Run 或从 checkpoint 继续。 |

## 状态写入要求

每次状态变化必须同时写入：

- `SessionState.run_state`
- `Transcript` 的 `state_changed` event
- 如涉及权限或副作用，写入 `AuditLog`

状态变化事件示例：

```json
{
  "event_id": "evt_state_001",
  "type": "state_changed",
  "session_id": "sess_001",
  "run_id": "run_001",
  "created_at": "2026-06-20T07:00:00Z",
  "payload": {
    "from": "waiting_approval",
    "to": "running",
    "waiting_for": null,
    "pending_request_id": null,
    "pending_tool_call_ids": [],
    "pending_tool_batch_id": null,
    "pending_adapter_action_id": null
  }
}
```

## 不变量

- 同一时间一个 Run 只能有一个主状态。
- `waiting_approval` 必须有 `pending_request_id`。
- `waiting_tool` 必须至少有一个 pending `tool_call_id` 或 pending `tool_batch_id`。
- `waiting_user` 若等待外部链接完成，`pending_adapter_action_id` 必须记录 `open_url_id`。
- `pending_request_id` 只表示权限请求；不能复用为工具调用 ID、工具批次 ID 或 Adapter 动作 ID。
- 同一状态下只能保留与 `waiting_for` 匹配的 pending 字段，其他 pending 字段必须为空或省略。
- `completed` 后不能再追加工具调用。
- `failed` 必须有 `last_error`。
- `cancelled` 必须有取消来源：`user`、`system` 或 `timeout`。
