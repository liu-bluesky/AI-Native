# 状态与存储

状态与存储负责让会话可以恢复、回放和审计。它不只保存聊天文本，还要保存事件、工具调用、权限决策和关键状态变化。

## SessionState

当前会话状态。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `session_id` | ID | 是 | 会话 ID。 |
| `run_state` | RunState | 是 | 当前运行状态。 |
| `messages` | Message[] | 是 | 当前上下文消息。 |
| `pending_tool_calls` | ToolCall[] | 是 | 等待执行或等待结果的工具调用。 |
| `pending_tool_batches` | ToolBatch[] | 是 | 等待执行或等待聚合结果的工具批次。 |
| `pending_permissions` | PermissionRequest[] | 是 | 等待用户决策的权限请求。 |
| `pending_adapter_actions` | PendingAdapterAction[] | 是 | 等待 Adapter 完成的外部动作，例如 `open_url`。 |
| `processed_commands` | CommandReceipt[] | 是 | 已处理命令的幂等回执，用于重复提交返回第一次结果。 |
| `updated_at` | Timestamp | 是 | 最近更新时间。 |

## PendingAdapterAction

等待 Adapter 完成的外部动作。它不是工具调用，也不是权限请求。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `adapter_action_id` | ID | 是 | 外部动作 ID，例如 `open_url_id`。 |
| `run_id` | ID | 是 | 所属 Run。 |
| `event_id` | ID | 是 | 触发动作的事件 ID。 |
| `type` | `open_url` | 是 | 动作类型。 |
| `status` | `pending` \| `opened` \| `completed` \| `failed` \| `cancelled` | 是 | 当前动作状态。 |
| `owner_client_id` | ID | 否 | 首个接手动作的客户端。 |
| `command_receipt_ids` | ID[] | 是 | 指向 `SessionState.processed_commands.receipt_id`，不重复保存回执正文。 |
| `created_at` | Timestamp | 是 | 创建时间。 |
| `updated_at` | Timestamp | 是 | 最近更新时间。 |

`RunState.pending_adapter_action_id` 必须指向 `pending_adapter_actions.adapter_action_id`。如果动作已 `completed` 且对应 `open_url_done` 事件已经应用，可以从 pending 列表移除；如果只看到 `opened`，不能自动继续 Run。

## CommandReceipt

命令幂等记录。它保存第一次命令的 payload 哈希和处理结果，不能退化成只保存 `idempotency_key` 字符串。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `receipt_id` | ID | 是 | 回执 ID。 |
| `session_id` | ID | 是 | 会话 ID。 |
| `run_id` | ID | 否 | 所属 Run。 |
| `command_id` | ID | 是 | AdapterCommand 或 CommandFrame ID。 |
| `type` | AdapterCommandType | 是 | 命令类型。 |
| `idempotency_key` | string | 是 | 幂等键。 |
| `payload_hash` | string | 是 | canonical JSON payload 的稳定哈希。 |
| `result` | CommandResult | 是 | 第一次处理结果。 |
| `created_at` | Timestamp | 是 | 创建时间。 |
| `updated_at` | Timestamp | 是 | 最近更新时间。 |

## Checkpoint

可恢复检查点。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `checkpoint_id` | ID | 是 | 检查点 ID。 |
| `session_id` | ID | 是 | 会话 ID。 |
| `run_id` | ID | 否 | 所属执行。 |
| `state` | SessionState | 是 | 状态快照。 |
| `base_event_seq` | number | 是 | 创建检查点时已经应用到的最大事件序号。 |
| `transcript_hash` | string | 否 | 创建检查点时 transcript 前缀哈希。 |
| `reason` | string | 是 | 创建原因，例如 `before_tool_call`、`waiting_approval`。 |
| `created_at` | Timestamp | 是 | 创建时间。 |

## Transcript

完整运行记录。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `session_id` | ID | 是 | 会话 ID。 |
| `messages` | Message[] | 是 | 对话消息。 |
| `events` | AgentEvent[] | 是 | 事件记录。 |
| `tool_calls` | ToolCall[] | 是 | 工具调用记录。 |
| `tool_results` | ToolResult[] | 是 | 工具结果记录。 |
| `audit_logs` | AuditLog[] | 是 | 审计记录。 |

## 建议文件布局

```text
.liuagent/
  sessions/
    <session_id>/
      state.json
      transcript.jsonl
      checkpoints/
        <checkpoint_id>.json
      audit.jsonl
```

## 存储边界

- `state.json` 保存当前可恢复状态，可以被覆盖。
- `transcript.jsonl` 保存追加式运行记录，不应静默重写历史。
- `audit.jsonl` 保存权限和高风险动作记录，应追加写入。
- checkpoint 只保存关键节点，不需要每个 token 都落盘。

## 恢复策略

恢复时按以下顺序处理，唯一权威顺序是事件序号 `seq`：

1. 读取最近 checkpoint，得到 `base_event_seq` 和状态快照。
2. 从 `transcript.jsonl` 读取 `seq > base_event_seq` 的事件。
3. 按序 replay 事件，重建 `SessionState`。
4. 读取 `state.json` 作为最终校准；如果和 replay 结果冲突，以事件 replay 为准，并重写 `state.json`。
5. 检查 `pending_permissions`，有则恢复到等待用户确认。
6. 检查 `pending_adapter_actions`，例如未完成的 `open_url`，恢复为等待用户完成外部动作。
7. 检查 `pending_tool_batches` 和 `pending_tool_calls`，默认不自动重放高风险工具。

## Checkpoint / replay 合并规则

合并时不能同时相信 checkpoint 和最新 state。规则如下：

- `transcript.jsonl` 是追加事实源，不能静默改写。
- `checkpoint` 是性能优化，只能作为 replay 起点。
- `state.json` 是缓存视图，可被 replay 结果覆盖。
- 如果 checkpoint 的 `transcript_hash` 与 transcript 前缀不一致，该 checkpoint 失效，必须回退到更早 checkpoint 或从头 replay。
- replay 遇到重复 `event_id` 时保留第一次，后续重复事件只记录诊断日志。
- replay 遇到重复 `session_id + type + idempotency_key` 的命令时，必须查找 canonical 的 `processed_commands`；payload 哈希一致则返回第一次 `CommandResult`，不一致则返回幂等冲突。
- replay 后若发现工具已产生终态 `ToolResult`，不得再次执行该 `tool_call_id`。
- replay 后若发现 `pending_adapter_actions` 已有相同 `adapter_action_id` 的终态命令，必须复用第一次结果；相同幂等键但 payload 哈希不一致时标记为冲突，不能继续推进。
