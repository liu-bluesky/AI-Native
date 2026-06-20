# 权限审计

权限审计负责回答三件事：动作能不能执行、用户是否确认过、事后能不能追溯。

## RiskLevel

| 等级 | 含义 | 默认策略 |
| --- | --- | --- |
| `safe` | 只读、低影响 | 可自动执行。 |
| `medium` | 写 workspace 或运行只读命令 | 可配置是否确认。 |
| `high` | 删除、覆盖、安装依赖、网络写入 | 必须确认。 |
| `critical` | 部署、发消息、外传凭据、系统目录写入 | 默认禁止或强确认。 |

## PermissionRequest

权限请求由 Tool Runtime 或 Adapter 发起，由 Permission Gate 评估。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `request_id` | ID | 是 | 权限请求 ID。 |
| `run_id` | ID | 是 | 所属执行。 |
| `action` | string | 是 | 策略动作名，例如 `command.run`、`url.open`；工具名只记录在 `preview` 或关联的 `ToolCall` 中。 |
| `risk` | RiskLevel | 是 | 风险等级。 |
| `reason` | string | 是 | 为什么需要执行。 |
| `scope` | string | 是 | 影响范围。 |
| `preview` | object | 否 | 命令、路径、URL、diff 等预览信息。 |
| `options` | PermissionOption[] | 是 | 结构化可选决策；批准类选项必须携带对应 `grant_scope`。 |

## PermissionDecision

用户或策略给出的决策。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `decision_id` | ID | 是 | 决策 ID。 |
| `request_id` | ID | 是 | 对应权限请求。 |
| `decision` | PermissionDecisionValue | 是 | `approve_once`、`approve_run`、`approve_session`、`approve_workspace`、`deny`、`revise`。 |
| `grant_scope` | GrantScope | 否 | 批准类决策的授权范围；必须和批准决策值一一映射。 |
| `decided_by` | `user` \| `policy` | 是 | 决策来源。 |
| `client_id` | ID | 否 | 做出决策的客户端实例。 |
| `idempotency_key` | string | 是 | 跨端重复提交时的幂等键。 |
| `comment` | string | 否 | 用户或策略说明。 |
| `created_at` | Timestamp | 是 | 决策时间。 |

Adapter 回传审批结果时，最终必须落成 `PermissionDecision`。Web 按钮可以显示“允许/拒绝”，但协议值必须使用 `approve_once`、`approve_run`、`approve_session`、`approve_workspace`、`deny`、`revise`。

用户或 Adapter 产生的决策必须携带幂等键，避免多端重复点击生成多条有效决策。纯策略自动决策如果没有客户端命令来源，也必须由 Permission Gate 基于 `request_id + decision + grant_scope + policy_version` 生成确定性幂等键。

`PermissionDecision.decision + grant_scope` 必须匹配 `PermissionRequest.options` 中的一个结构化选项，且不能超过命中的 `PolicyRule.grant_scope` 中的批准类范围。批准类选项和决策只能使用 `GrantScope`：`once`、`run`、`session`、`workspace`，不能使用策略层的 `PolicyGrantScope.never`；拒绝或修改类决策不写 `grant_scope`。

批准类决策值和授权范围固定映射：`approve_once -> once`、`approve_run -> run`、`approve_session -> session`、`approve_workspace -> workspace`。

## AuditLog

审计日志记录不可只保存在 UI 层。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `audit_id` | ID | 是 | 审计记录 ID。 |
| `session_id` | ID | 是 | 所属会话。 |
| `run_id` | ID | 否 | 所属执行。 |
| `client_id` | ID | 否 | 发起或确认动作的客户端实例。 |
| `adapter` | AdapterKind | 否 | 发起或确认动作的适配器。 |
| `tool_call_id` | ID | 否 | 关联工具调用。 |
| `tool_batch_id` | ID | 否 | 关联工具批次。 |
| `request` | PermissionRequest | 否 | 权限请求快照。 |
| `decision` | PermissionDecision | 否 | 权限决策快照。 |
| `result` | AuditResult | 否 | 执行结果摘要。 |
| `created_at` | Timestamp | 是 | 记录时间。 |

## AuditResult

审计结果必须能同时表达“授权成功但执行失败”的情况。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `executed` | boolean | 是 | 是否真的进入执行器。 |
| `ok` | boolean | 是 | 动作最终是否成功。 |
| `tool_call_id` | ID | 否 | 对应工具调用。 |
| `tool_result_id` | ID | 条件必填 | 当 `tool_call_id` 存在且工具已产生结果时必须填写。 |
| `summary` | string | 是 | 可展示摘要，不包含敏感内容。 |
| `error_code` | string | 否 | 失败时的稳定错误码。 |
| `retryable` | boolean | 否 | 失败是否可重试。 |

链路要求：

- `PermissionRequest.request_id` 必须能追到 `PermissionDecision.request_id`。
- `PermissionDecision.decision_id` 必须能追到 `AuditLog.decision`。
- `ToolCall.permission_request_id` 必须能追到 `AuditLog.request.request_id`。
- `ToolResult.audit_id` 必须能追到 `AuditLog.audit_id`。
- `AuditLog.result.tool_result_id` 必须能追到 `ToolResult.tool_result_id`。
- 如果授权通过但执行失败，`AuditLog.result.ok=false`，不能只记录授权成功。

## 必须审计的动作

- 写文件、覆盖文件、删除文件。
- 执行本地命令。
- 安装依赖、启动服务、部署。
- 打开外部链接并要求用户授权。
- 网络写入、发送消息、提交表单。
- 读取或可能外传本地凭据。
