# 测试夹具

测试夹具用于证明 CLI、Web、Desktop 消费同一套 Agent Core、事件、权限和状态结构。这里定义的是验收样例，不绑定具体测试框架。

## Fixture 目录建议

```text
fixtures/
  events/
    approval-required.json
    open-url.json
    tool-call-success.json
    tool-call-failed.json
  sessions/
    waiting-approval-state.json
    interrupted-run-state.json
  transcripts/
    simple-file-read.jsonl
    command-approval-denied.jsonl
  replays/
    web-approval-flow.json
    desktop-open-url-flow.json
    pty-bridge-flow.json
```

正式实现时，文档里的样例应迁移为仓库内可执行 fixture，并纳入回归测试。

## EventFixture

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `fixture_id` | ID | 是 | 样例 ID。 |
| `title` | string | 是 | 样例名称。 |
| `input` | AgentEvent[] | 是 | 输入事件序列。 |
| `expected_adapter_outputs` | object | 是 | 各端期望展示或动作。 |
| `expected_commands` | AdapterCommand[] | 否 | 用户交互后应产生的命令。 |

示例：

```json
{
  "fixture_id": "fixture_approval_required",
  "title": "写文件前请求授权",
  "input": [
    {
      "event_id": "evt_001",
      "type": "approval_required",
      "session_id": "sess_001",
      "run_id": "run_001",
      "created_at": "2026-06-20T07:00:00Z",
      "payload": {
        "request_id": "perm_001",
        "title": "允许写入文件？",
        "risk": "medium",
        "action": "file.write",
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
  ],
  "expected_adapter_outputs": {
    "cli": "显示确认问题和可选项",
    "web": "显示审批按钮和文件路径预览",
    "desktop": "显示原生确认弹窗并保留审计入口"
  }
}
```

## ReplayCase

ReplayCase 用于验证事件回放和恢复。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `case_id` | ID | 是 | 回放用例 ID。 |
| `initial_state` | SessionState | 是 | 初始状态。 |
| `events` | AgentEvent[] | 是 | 待回放事件。 |
| `commands` | AdapterCommand[] | 否 | 回放中注入的用户命令。 |
| `expected_final_state` | object | 是 | 期望最终状态摘要。 |

## 必测流程

| 用例 | 目的 | 验收点 |
| --- | --- | --- |
| 流式消息输出 | 验证 `message_delta` 一致消费 | CLI 连续打印，Web 合并消息，Desktop 不重复通知。 |
| 工具成功 | 验证 `tool_started` + `tool_result` | 三端都能展示同一个工具调用 ID 和摘要。 |
| 工具失败 | 验证错误 payload | 三端都展示失败原因，状态进入 `failed` 或可恢复状态。 |
| 审批通过 | 验证 `approval_required` 到 `PermissionDecision` | 只产生一个有效决策并写入审计。 |
| 审批拒绝 | 验证拒绝后的状态 | 工具不执行，模型收到拒绝 observation。 |
| 打开链接 | 验证 `open_url` | CLI 打印链接，Web 新窗口，Desktop 系统浏览器。 |
| 断线恢复 | 验证 `last_seen_seq` | 缺失事件可回放，当前状态可校准。 |
| PTY 桥接 | 验证 CLI 快速复刻 | 可显示终端文本，但权限仍来自结构化事件。 |

## 多端一致性矩阵

| 事件 | CLI | Web | Desktop | 必须一致的字段 |
| --- | --- | --- | --- | --- |
| `message_delta` | 流式打印 | 追加文本 | 更新窗口内容 | `message_id`、`delta` 顺序 |
| `approval_required` | 终端确认 | 按钮确认 | 原生弹窗 | `request_id`、`risk`、`options` |
| `open_url` | 打印链接 | 打开窗口 | 系统浏览器 | `open_url_id`、`url`、`reason` |
| `tool_started` | 状态行 | 时间线节点 | 任务进度 | `tool_call_id`、`name` |
| `tool_result` | 摘要输出 | 结果面板 | 结果通知 | `tool_result_id`、`tool_call_id`、`ok`、`summary`、`created_at` |
| `state_changed` | 状态提示 | 状态条 | 状态同步 | `from`、`to`、`waiting_for` |

## 验收规则

- 每个事件 fixture 至少被 CLI、Web、Desktop 三个 Adapter 消费一次。
- 每个权限 fixture 必须验证审计日志。
- 每个恢复 fixture 必须验证 `SessionState` 与 Transcript 可对齐。
- PTY fixture 只能验证终端复刻，不作为业务状态一致性的唯一证据。
- 所有 fixture 必须使用固定 ID，避免快照测试不稳定。

## 最小回归集

第一版实现至少准备这些 fixture：

1. `message_delta` 两段流式输出。
2. `approval_required` + `approve_once`。
3. `approval_required` + `deny`。
4. `open_url` 授权链接。
5. `tool_started` + `tool_result.ok=true`。
6. `tool_started` + `tool_result.ok=false`。
7. `state_changed.to=waiting_approval` 断线恢复。
8. `pty_bridge` 文本透传但权限事件仍结构化。
9. `PermissionRequest.action=command.run` 能命中对应 `PolicyRule.action=command.run`。
10. `AuditLog` 使用 `request/decision/result` 快照结构，而不是扁平 `action/risk/result_summary`。
11. `ToolCall.action` 来自 `ToolDefinition.action`，并进入 `PermissionRequest.action`。
12. `ToolResult.tool_result_id` 能被 `AuditResult.tool_result_id` 追踪。
13. `permission_decision` 命令携带与决策值一致的 `grant_scope`。

## 失败样例

需要保留失败 fixture，避免实现只覆盖成功路径：

- Web 重复点击审批按钮，系统只接受第一次有效决策。
- Web 和 Desktop 同时提交同一个 `request_id` 的审批命令，若 `idempotency_key` 不同但请求已决策，第二个命令必须返回已决策冲突。
- Desktop 断线后重新提交旧 `command_id`，系统返回幂等结果。
- Desktop 重复提交同一个 `open_url_done.idempotency_key`，系统必须返回第一次处理结果。
- Desktop 重复提交同一个 `open_url_done.idempotency_key` 但 payload 不一致，系统必须返回幂等冲突。
- CLI 在等待审批时被中断，恢复后仍显示同一个 `request_id`。
- `state_changed.to=waiting_user` 把 `open_url_id` 写入 `pending_request_id` 时，schema 校验必须失败。
- `state_changed.to=waiting_tool` 没有 `pending_tool_call_ids` 且没有 `pending_tool_batch_id` 时，schema 校验必须失败。
- `state_changed.to=waiting_approval` 同时带有 `pending_request_id` 和 `pending_adapter_action_id` 时，schema 校验必须失败。
- `RunState` 使用 `current_run_id` 而不是 canonical `run_id` 时，schema 校验必须失败。
- `PermissionRequest.action=run_command` 但策略只定义 `command.run` 时，策略匹配测试必须失败并提示动作名未规范化。
- `ToolResult` 缺少 `created_at` 时，schema 校验必须失败。
- `ToolResult` 缺少 `tool_result_id` 时，schema 校验必须失败。
- `ToolResult` 缺少 `summary` 时，schema 校验必须失败；实现可由 `content` 截断生成，但落库和事件前必须存在。
- `tool_result` 事件 payload 缺少 `tool_result_id`，或与 `ToolResult.tool_result_id` 不一致时，schema 校验必须失败。
- `AuditLog.result` 有 `tool_call_id` 且工具已产生结果，但缺少 `tool_result_id` 时，schema 校验必须失败。
- `ToolCall` 缺少 `action` 时，Permission Gate 不能用工具名猜测策略动作，必须失败。
- `permission_decision.decision=approve_session` 但 `grant_scope` 缺失或不是 `session` 时，schema 校验必须失败。
- `permission_decision.decision=approve_once` 但 `grant_scope` 不是 `once` 时，schema 校验必须失败。
- `permission_decision.decision=approve_run` 但 `grant_scope` 不是 `run` 时，schema 校验必须失败。
- `permission_decision.decision=approve_workspace` 但 `grant_scope` 不是 `workspace` 时，schema 校验必须失败。
- `permission_decision` 的 `decision + grant_scope` 无法匹配 `PermissionRequest.options` 中任一结构化选项时，schema 校验必须失败。
- `PermissionRequest.options` 使用字符串数组而不是结构化 `PermissionOption[]` 时，schema 校验必须失败。
- 批准类 `PermissionOption.grant_scope=never` 时，schema 校验必须失败。
- `PolicyRule.grant_scope=["never"]` 时，Permission Gate 不能生成批准类 `PermissionOption` 或 `PermissionGrant`，否则 schema 校验必须失败。
- `cancel` 或 `resume` 命令 payload 缺少与顶层一致的 `idempotency_key` 时，schema 校验必须失败。
- `cancel`、`resume`、`permission_decision` 或 `open_url_done` 的顶层 `idempotency_key` 与 payload 内 `idempotency_key` 不一致时，schema 校验必须失败。
- `AdapterCommand` 缺少 `command_id` 时，schema 校验必须失败。
- `submit_text` 命令 payload 缺少 `content` 时，schema 校验必须失败。
- `AdapterInput.type=user_message` 但 payload 不是 `SubmitTextCommandPayload` 时，schema 校验必须失败。
- `AdapterInput.type=permission_decision`、`interrupt` 或 `resume` 但 payload 不是完整 `AdapterCommand` 时，schema 校验必须失败。
- `TransportEnvelope.kind=event` 但 payload 不是完整 `AgentEvent`，例如缺少 `session_id`、`created_at` 或内层 payload 时，schema 校验必须失败。
- `Step.type=tool_result` 但 payload 缺少 `tool_result_id` 时，schema 校验必须失败。
- `Step.type=tool_result` 但 payload 缺少 `summary` 或 `created_at` 时，schema 校验必须失败。
- `TransportEnvelope.kind=heartbeat` 但 payload 不是 `HeartbeatPayload` 时，schema 校验必须失败。
- 重复命令只有 `idempotency_key` 记录、没有 `CommandReceipt.payload_hash` 和第一次 `CommandResult` 时，恢复测试必须失败。
- `PendingAdapterAction` 直接内嵌 `CommandReceipt[]` 而不是引用 `command_receipt_ids` 时，schema 校验必须失败，避免两份 canonical 状态。
- 相同 `session_id + type + idempotency_key` 但 payload 哈希不同的命令必须返回幂等冲突。
- `AuditLog` 只写扁平 `action/risk/result_summary` 而没有 `request/decision/result` 快照时，schema 校验必须失败。
- PTY 文本显示“是否允许”，但缺少结构化 `approval_required`，测试必须失败。
