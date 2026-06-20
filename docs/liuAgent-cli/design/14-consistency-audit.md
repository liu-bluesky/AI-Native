# 一致性审查

本文档用于记录 `docs/liuAgent-cli` 设计文档的一致性检查规则。核心目标不是再新增概念，而是把后续审查固定成三个方向：

- 检测数据结构是否出现不同阶段对不上。
- 检测是否还缺少其他实现细节。
- 检测是否存在逻辑 bug 风险。

## 审查范围

审查对象覆盖 `design/` 目录里的核心对象、工具系统、事件协议、权限审计、适配器协议、状态存储、运行时 schema、工具契约、状态机、传输协议、安全策略、测试夹具和智能体编排。

重点链路：

```text
User Input
  -> Run / Step
  -> ModelRequest / ModelResponse
  -> ToolCall / ToolBatch
  -> PermissionRequest / PermissionDecision
  -> ToolResult
  -> AgentEvent
  -> TransportEnvelope / AdapterCommand
  -> SessionState / Transcript / AuditLog
```

每次修改设计文档后，都必须沿这条链路检查字段、状态、ID、权限、事件、恢复和审计是否仍然对齐。

## 三类审查维度

### 1. 不同阶段数据结构是否对不上

检查同一个对象在生命周期不同阶段是否字段、状态、ID 关联和语义一致。

检查项：

- 同一个 ID 是否贯穿上下游，例如 `run_id`、`step_id`、`tool_call_id`、`tool_batch_id`、`request_id`、`event_id`。
- 同一个状态枚举是否只有一个 canonical 来源，例如 `RunStatus`、`ToolCallStatus`、`PermissionDecisionValue`、`OpenUrlDoneStatus`。
- `ModelToolCall` 进入 Tool Runtime 后，是否补齐 `run_id`、`origin_message_id`、`status`、时间字段和权限关联字段。
- `ToolResult` 是否能通过 `tool_call_id` 追到 `ToolCall`，通过 `audit_id` 追到 `AuditLog`。
- `AgentEvent.payload`、`AdapterCommand.payload`、runtime schema 是否使用同一组字段。
- `SessionState.pending_tool_calls`、`SessionState.pending_permissions` 是否能恢复当前等待对象。
- `Transcript`、checkpoint、`SessionState` replay 后是否能得到同一个运行状态。

判定规则：

- 字段名不一致，属于结构不一致。
- 同一概念出现多套 ID，属于结构不一致。
- 状态值在多个文档重复定义，属于结构不一致。
- 事件 payload 和 runtime schema 对不上，属于结构不一致。
- 存储快照无法恢复到事件流对应状态，属于结构不一致。

修复原则：

- 先确定 canonical 定义，再改引用文档。
- canonical schema 优先放在 `07-runtime-schema.md`。
- 状态转移优先放在 `09-state-machine.md`。
- 跨端通信字段优先放在 `03-event-protocol.md`、`05-adapter-protocol.md`、`10-transport-protocol.md`。

### 2. 是否还缺少其他细节

检查设计是否已经足够落代码、写测试、做跨端适配。

检查项：

- 字段表是否写清楚类型、必填、默认值、来源和用途。
- 状态机是否写清楚进入条件、退出条件、失败路径和恢复路径。
- 权限和审计是否写清楚谁发起、谁决策、谁执行、失败如何记录。
- Web、CLI、Desktop 是否有同一协议下的不同展示方式，而不是各自实现业务逻辑。
- 是否给出幂等、断线恢复、并发、取消、超时、重复提交等边界规则。
- 是否说明哪些对象进入 `SessionState`、`Transcript`、`AuditLog`。
- 是否说明哪些字段面向模型，哪些字段面向 UI，哪些字段只用于审计。
- 是否能直接转成 TypeScript、Zod、JSON Schema 和契约测试。

判定规则：

- 只写“需要处理”，但没有字段、状态或边界条件，属于细节缺口。
- 只写“后续补充”，但没有补充位置和约束，属于细节缺口。
- 只写“由实现决定”，但会影响跨端一致性，属于细节缺口。
- 有权限动作但没有审计字段，属于细节缺口。
- 有恢复流程但没有 replay 规则，属于细节缺口。

修复原则：

- 每个对象补齐字段表。
- 每个状态补齐进入条件、退出条件和失败出口。
- 每个副作用动作补齐权限等级、审批请求、执行结果和审计记录。
- 每个跨端交互补齐 `AgentEvent` 和 `AdapterCommand` 的结构。
- 每个恢复场景补齐 replay、幂等键和冲突处理。

### 3. 是否存在逻辑 bug 风险

检查设计在真实运行时是否会导致重复执行、越权、状态卡死、恢复错误或跨端不一致。

重点风险：

- 重复审批：多个客户端对同一 `request_id` 同时提交决策。
- 重复执行工具：断线恢复后再次执行已经成功的 `tool_call_id`。
- 状态卡死：`waiting_approval`、`waiting_tool`、`waiting_user` 没有可恢复出口。
- 权限绕过：Adapter 或 Runner 直接执行本机动作，没有经过 Permission Gate。
- 审计断链：授权成功但执行失败时，只记录了决策，没有记录失败结果。
- 并发错序：多个 `ToolCall` 同时执行时，结果顺序和模型原始调用不一致。
- replay 冲突：`state.json`、checkpoint、transcript replay 互相矛盾。
- 协议污染：UI 文案值进入协议层，例如把按钮文案当成 `decision`。
- 错误吞掉：工具失败后没有生成 `ToolResult.ok=false`，导致模型和 UI 都不知道失败原因。
- 跨端分叉：CLI、Web、Desktop 对同一事件走不同业务逻辑。

判定规则：

- 同一用户动作可能产生两次副作用，属于逻辑 bug 风险。
- 同一状态没有明确终态，属于逻辑 bug 风险。
- 权限动作可以绕过 Core，属于逻辑 bug 风险。
- 审计无法追到失败原因，属于逻辑 bug 风险。
- replay 后和当前状态冲突但继续执行，属于逻辑 bug 风险。

修复原则：

- 所有用户决策必须有 `idempotency_key`。
- 同一个 `request_id` 只能产生一个有效 `PermissionDecision`。
- 已有终态 `ToolResult` 的 `tool_call_id` 不得再次执行。
- 所有等待状态都必须有恢复、取消、失败或超时出口。
- 所有副作用动作必须经过 Permission Gate。
- 授权通过但执行失败时，`AuditLog.result.ok=false` 必须写入。
- 多工具调用必须使用 `ToolBatch` 和稳定 `index` 保持顺序。

## 当前对齐结论

当前设计应收敛到以下 canonical 入口：

- 运行时枚举以 `07-runtime-schema.md` 为准。
- 工具调用生命周期以 `02-tool-system.md` 和 `09-state-machine.md` 为准。
- 权限请求、权限决策和审计链路以 `04-permission-audit.md` 和 `11-security-policy.md` 为准。
- Core 与 Adapter 的事件和命令以 `03-event-protocol.md`、`05-adapter-protocol.md`、`10-transport-protocol.md` 为准。
- 状态恢复和 replay 以 `06-state-storage.md` 和 `12-test-fixtures.md` 为准。
- 智能体生命周期和规则执行分层以 `13-agent-orchestration.md` 为准。

## 后续审查记录格式

后续每次发现问题，按下面格式追加：

```md
### YYYY-MM-DD 问题标题

类型：结构不一致 / 细节缺口 / 逻辑 bug 风险

涉及文档：

- `design/xx.md`

问题：

- ...

修复：

- ...

验证：

- ...
```

审查结论必须写回本文档，不能只停留在口头判断。

### 2026-06-20 pending 字段和幂等键对齐

类型：结构不一致 / 细节缺口 / 逻辑 bug 风险

涉及文档：

- `design/01-core-objects.md`
- `design/03-event-protocol.md`
- `design/04-permission-audit.md`
- `design/05-adapter-protocol.md`
- `design/06-state-storage.md`
- `design/07-runtime-schema.md`
- `design/09-state-machine.md`
- `design/10-transport-protocol.md`
- `design/12-test-fixtures.md`

问题：

- `RunState` 原先容易把权限请求、工具调用和 Adapter 动作都混到 `pending_request_id`，导致 `waiting_approval`、`waiting_tool`、`waiting_user` 在恢复时无法可靠区分。
- `open_url_done` 的幂等键在事件协议、Adapter 协议和传输协议中位置不完全一致，容易出现顶层命令和 payload 互相覆盖。
- `PermissionDecision.idempotency_key` 原先不是必填，多端重复点击审批按钮时可能生成多条有效决策。
- 状态存储只写了 `pending_adapter_actions` 是对象数组，没有定义可恢复字段，断线后无法稳定判断 `open_url` 是已打开、已完成还是需要继续等待。
- 测试夹具缺少 pending 字段错配、重复审批、重复 `open_url_done` 和幂等冲突的失败样例。

修复：

- `RunState` 拆成 `pending_request_id`、`pending_tool_call_ids`、`pending_tool_batch_id`、`pending_adapter_action_id`，并规定 `pending_request_id` 只表示权限请求。
- `StateChangedPayload` 和事件示例同步补齐 pending 字段约束，禁止把 `open_url_id` 写入 `pending_request_id`。
- `AdapterCommand` 与 `CommandFrame` 明确以顶层 `idempotency_key` 为 canonical；直接 Adapter 输入如带 `payload.idempotency_key`，必须与顶层一致。
- `PermissionDecision.idempotency_key` 改为必填；策略自动决策也必须生成确定性幂等键。
- `PendingAdapterAction` 补齐 `adapter_action_id`、`status`、`owner_client_id` 和命令幂等记录字段，并补充 replay 冲突规则。
- `12-test-fixtures.md` 增加重复审批、重复 `open_url_done`、payload 冲突和 pending 字段错配失败样例。

验证：

- `rg -n "pending_request_id|pending_tool_call_ids|pending_tool_batch_id|pending_adapter_action_id|WaitingFor|idempotency_key|open_url_done" docs/liuAgent-cli/design -g '*.md'`
- `sed -n` 回读 `04-permission-audit.md`、`05-adapter-protocol.md`、`06-state-storage.md`、`07-runtime-schema.md`、`09-state-machine.md`、`10-transport-protocol.md`、`12-test-fixtures.md`。

### 2026-06-20 schema canonical 和策略动作名对齐

类型：结构不一致 / 细节缺口 / 逻辑 bug 风险

涉及文档：

- `design/01-core-objects.md`
- `design/02-tool-system.md`
- `design/03-event-protocol.md`
- `design/04-permission-audit.md`
- `design/07-runtime-schema.md`
- `design/08-tool-contracts.md`
- `design/09-state-machine.md`
- `design/11-security-policy.md`
- `design/12-test-fixtures.md`

问题：

- `RunState` 在核心对象中使用 `current_run_id`，但 runtime schema 使用 `run_id`。
- 权限动作名同时出现 `run_command` / `open_url` 和 `command.run` / `url.open` 两套写法。
- `07-runtime-schema.md` 缺少 `PermissionRequest`、`PermissionDecision`、`AuditLog`、`PendingAdapterAction`、`AdapterCommand`、`CommandFrame` 等 canonical 对象。
- `ToolResult.created_at` 只在工具契约中出现，工具系统和 runtime schema 未同步。
- `running` 恢复策略写成“由实现决定”，会导致 CLI、Web、Desktop 恢复分叉。
- 安全策略的审计最低字段是扁平结构，和 `AuditLog.request/decision/result` canonical 结构不一致。

修复：

- `RunState` 统一使用 `run_id`。
- 权限策略动作名统一使用 `file.write`、`command.run`、`url.open` 这类 canonical action；工具名只作为工具名，不作为权限 action。
- 在 runtime schema 中补齐权限、审计、Adapter 命令和传输命令对象。
- `ToolResult` 统一补 `created_at`。
- `running` 恢复改成基于 checkpoint + replay + pending 对象的确定性判定。
- 审计最低要求改为 `request/decision/result` 快照结构。
- 测试夹具补充 schema 失败样例和策略动作名匹配样例。

验证：

- `rg -n "current_run_id|run_command|open_url|command.run|url.open|PermissionRequest|AdapterCommand|CommandFrame|ToolResult|AuditLog" docs/liuAgent-cli/design -g '*.md'`
- `sed -n` 回读 `01-core-objects.md`、`04-permission-audit.md`、`07-runtime-schema.md`、`09-state-machine.md`、`11-security-policy.md`、`12-test-fixtures.md`。

### 2026-06-20 runtime schema 覆盖缺口修复

类型：结构不一致 / 细节缺口 / 逻辑 bug 风险

涉及文档：

- `design/01-core-objects.md`
- `design/02-tool-system.md`
- `design/03-event-protocol.md`
- `design/04-permission-audit.md`
- `design/05-adapter-protocol.md`
- `design/06-state-storage.md`
- `design/07-runtime-schema.md`
- `design/08-tool-contracts.md`
- `design/10-transport-protocol.md`

问题：

- `ToolResult.error` 和 `RunState.last_error` 引用了 `ToolError`，但 `07-runtime-schema.md` 没有定义 `ToolError`，导致 canonical schema 无法独立落代码。
- `AgentEvent` 在事件协议中包含 `event_id`、`session_id`、`run_id`、`created_at`，但 runtime schema 的联合类型只定义了 `type/payload`，进入 Transcript 后会丢失溯源字段。
- `AgentConfig`、`Session`、`SessionState`、`Checkpoint`、`Transcript`、`TransportEnvelope`、`ClientHello`、`AckFrame`、`SecurityContext`、`PolicyRule`、`PermissionGrant` 等运行关键对象只散落在分文档，没有在 runtime schema 中形成可生成类型的 canonical 定义。
- 适配器和传输文档中 `AdapterInput.type`、`AdapterCommand.type`、`CommandFrame.type`、`TransportEnvelope.kind` 等字段仍写成泛 `string`，实现时容易接受未定义协议值。
- 核心对象、工具系统、权限审计、适配器协议、状态存储和工具契约中同一批 ID 与时间字段仍写成裸 `string`，和 `ID`、`Timestamp` 基础约定不一致。
- `Session.state` 容易被误解为完整 `SessionState`，但实际只表示当前 `RunState`，和 `SessionState.run_state` 命名不一致。

修复：

- 在 `07-runtime-schema.md` 补齐 `ToolError`、`AgentConfig`、`Session`、`Message`、`Step`、`Run`、`SessionState`、`Checkpoint`、`Transcript`、传输对象和安全策略对象。
- 在 `07-runtime-schema.md` 增加 `AdapterKind`、`AdapterCommandType`、`TransportDirection`、`TransportKind`、`GrantScope` 等基础枚举，减少分文档重复 literal union。
- 将 `AgentEvent` 改为包含 `event_id`、`type`、`session_id`、`run_id`、`created_at`、`payload` 的完整事件对象，并规定 `type` 与 payload 必须一一匹配。
- `03-event-protocol.md` 将 `type`、`created_at`、`payload` 对齐到 `EventType`、`Timestamp`、`AgentEventPayload`。
- `05-adapter-protocol.md` 与 `10-transport-protocol.md` 将命令、传输方向和传输类型字段对齐到 runtime schema 枚举。
- `01-core-objects.md`、`02-tool-system.md`、`03-event-protocol.md`、`04-permission-audit.md`、`05-adapter-protocol.md`、`06-state-storage.md` 和 `08-tool-contracts.md` 将 ID 与时间字段统一为 `ID` / `Timestamp`。
- `Session.state` 改为 `Session.run_state`，并明确完整可恢复状态使用 `SessionState`。

验证：

- `rg -n "ToolError|AgentConfig|Session|SessionState|Checkpoint|Transcript|TransportEnvelope|ClientHello|AckFrame|SecurityContext|PolicyRule|GrantScope|PermissionGrant|AgentEvent" docs/liuAgent-cli/design/07-runtime-schema.md`
- `rg -n "type\\` \\| string|created_at\\` \\| string|current_run_id|由实现决定|result_summary" docs/liuAgent-cli/design -g '*.md'`
- `sed -n` 回读 `01-core-objects.md`、`02-tool-system.md`、`03-event-protocol.md`、`04-permission-audit.md`、`05-adapter-protocol.md`、`06-state-storage.md`、`07-runtime-schema.md`、`08-tool-contracts.md`、`10-transport-protocol.md`。
- 旧字段名扫描只剩 `12-test-fixtures.md` 的失败样例和本文档历史审计记录，表示这些旧写法应被测试拒绝，不是当前 canonical schema。

### 2026-06-20 tool action、result id 和命令 payload 对齐

类型：结构不一致 / 细节缺口 / 逻辑 bug 风险

涉及文档：

- `design/02-tool-system.md`
- `design/04-permission-audit.md`
- `design/05-adapter-protocol.md`
- `design/07-runtime-schema.md`
- `design/08-tool-contracts.md`
- `design/09-state-machine.md`
- `design/10-transport-protocol.md`
- `design/12-test-fixtures.md`

问题：

- `08-tool-contracts.md` 的通用 `ToolCall` 带 `action`，但 `02-tool-system.md` 和 `07-runtime-schema.md` 的 `ToolCall` 没有 `action`，导致 Permission Gate 可能只能从工具名猜策略动作。
- `AuditResult.tool_result_id` 指向工具结果 ID，但 `ToolResult` 没有 `tool_result_id` 字段，审计结果无法稳定追踪到具体工具结果。
- `PermissionDecision` 只有 `decision`，没有承载 `GrantScope`；安全策略定义的 `once/run/session/workspace/never` 无法落到用户决策。
- `AdapterCommand.payload` 和 `CommandFrame.payload` 仍是泛 `object`，只有 `permission_decision` 与 `open_url_done` 写了结构，`submit_text`、`cancel`、`resume` 缺少可校验 payload。
- 测试夹具没有覆盖 `ToolCall.action`、`ToolResult.tool_result_id`、审批 `grant_scope` 和命令 payload 缺失的失败路径。

修复：

- `ToolCall` 补齐 `action`，并规定来自 `ToolDefinition.action`，不能用工具名替代策略动作名。
- `ToolResult` 补齐 `tool_result_id`，让 `AuditResult.tool_result_id` 有稳定追踪目标。
- `PermissionDecision` 和 `PermissionDecisionCommandPayload` 补齐 `grant_scope`，并规定批准类决策值必须和 `GrantScope` 一一映射。
- 在 runtime schema 中补齐 `SubmitTextCommandPayload`、`CancelCommandPayload`、`ResumeCommandPayload`，并把 `AdapterCommand.payload`、`CommandFrame.payload` 改成命令 payload 联合类型。
- `05-adapter-protocol.md` 和 `10-transport-protocol.md` 同步五类命令的 payload 约束和幂等要求；`TransportEnvelope.payload` 对齐 runtime schema 的联合类型。
- `09-state-machine.md` 补充 `ToolCall.created` 必须记录 `action`，`ToolCall.succeeded` 必须记录 `ToolResult.tool_result_id`。
- `12-test-fixtures.md` 增加 `ToolCall.action`、`ToolResult.tool_result_id`、审批 `grant_scope` 和命令 payload 缺失的成功/失败样例。

验证：

- `rg -n "ToolCall|ToolResult|tool_result_id|grant_scope|SubmitTextCommandPayload|CancelCommandPayload|ResumeCommandPayload|PermissionDecisionCommandPayload" docs/liuAgent-cli/design -g '*.md'`
- `sed -n` 回读 `02-tool-system.md`、`04-permission-audit.md`、`05-adapter-protocol.md`、`07-runtime-schema.md`、`08-tool-contracts.md`、`10-transport-protocol.md`、`12-test-fixtures.md`。

### 2026-06-20 PermissionOption 结构化

类型：结构不一致 / 细节缺口 / 逻辑 bug 风险

涉及文档：

- `design/03-event-protocol.md`
- `design/04-permission-audit.md`
- `design/07-runtime-schema.md`
- `design/12-test-fixtures.md`

问题：

- `PermissionRequest.options` 原先是 `PermissionDecisionValue[]`，只能表达按钮决策值，不能表达 `grant_scope`。
- `PermissionDecision.grant_scope` 虽然补齐，但缺少和用户可选项的结构化匹配关系，Adapter 可能回传一个 UI 没展示过或策略不允许的授权范围。
- 事件示例和测试夹具仍使用 `["approve_once", "deny"]` 字符串数组，和 `grant_scope` 校验不闭环。

修复：

- `PermissionOption` 改为结构化对象，包含 `decision`、`label`、批准类必填的 `grant_scope` 和可选 `is_default`。
- `approval_required.options` 示例改为结构化数组，Adapter 回传时必须用 `decision + grant_scope` 匹配其中一项。
- `PermissionDecision` 文档明确 `decision + grant_scope` 必须匹配 `PermissionRequest.options`，且不能超过 `PolicyRule.grant_scope`。
- 测试夹具增加字符串数组 options、grant_scope 不匹配 options 的失败样例。

验证：

- `rg -n "type PermissionOption|PermissionOption|options|grant_scope|approve_once|approve_session" docs/liuAgent-cli/design -g '*.md'`
- `sed -n` 回读 `03-event-protocol.md`、`04-permission-audit.md`、`07-runtime-schema.md`、`12-test-fixtures.md`。

### 2026-06-20 批准决策值和 GrantScope 对齐

类型：结构不一致 / 逻辑 bug 风险

涉及文档：

- `design/04-permission-audit.md`
- `design/05-adapter-protocol.md`
- `design/07-runtime-schema.md`
- `design/10-transport-protocol.md`
- `design/12-test-fixtures.md`

问题：

- `GrantScope` 支持 `once`、`run`、`session`、`workspace`、`never`，但 `PermissionDecisionValue` 只有 `approve_once` 和 `approve_session` 两个批准值。
- 策略允许 `run` 或 `workspace` 授权时，Adapter 没有对应协议值可表达用户选择，容易退化成错误的 session 授权或无法授权。

修复：

- `PermissionDecisionValue` 增加 `approve_run` 和 `approve_workspace`。
- 明确批准类决策值和授权范围固定映射：`approve_once -> once`、`approve_run -> run`、`approve_session -> session`、`approve_workspace -> workspace`。
- `04-permission-audit.md`、`05-adapter-protocol.md`、`10-transport-protocol.md` 同步新决策值和映射规则。
- `12-test-fixtures.md` 增加 `approve_run` / `approve_workspace` 的错误映射失败样例。

验证：

- `rg -n "approve_once|approve_run|approve_session|approve_workspace|GrantScope|grant_scope" docs/liuAgent-cli/design -g '*.md'`
- `sed -n` 回读 `04-permission-audit.md`、`05-adapter-protocol.md`、`07-runtime-schema.md`、`10-transport-protocol.md`、`12-test-fixtures.md`。

### 2026-06-20 payload 联合类型和命令幂等回执收敛

范围：

- `design/01-core-objects.md`
- `design/03-event-protocol.md`
- `design/04-permission-audit.md`
- `design/05-adapter-protocol.md`
- `design/06-state-storage.md`
- `design/07-runtime-schema.md`
- `design/10-transport-protocol.md`
- `design/11-security-policy.md`
- `design/12-test-fixtures.md`
- `PROJECT_DESIGN.md`

问题：

- `Step.payload` 和 `AdapterInput.payload` 仍是泛 `object`，实现可以把任意结构塞进不同阶段，导致 Run 步骤、用户输入、审批、恢复命令在 schema 上对不上。
- `TransportEnvelope.payload` 仍允许尾部 `object`，`heartbeat` 没有稳定结构，客户端可能用无法验证的 payload 推进状态。
- `ToolResult` 已有 `tool_result_id`，但 `tool_result` 事件 payload 没有携带该字段，UI、审计和 replay 只能靠 `tool_call_id` 猜结果。
- 命令幂等只保存 `idempotency_key` 字符串，无法返回第一次处理结果，也无法判断重复命令的 payload 是否被篡改。
- `PendingAdapterAction` 若直接内嵌命令回执，会和 `SessionState.processed_commands` 形成两份 canonical 状态。
- `PermissionGrant` 只写来源为 `PermissionDecision`，没有明确只有批准类决策才能生成 Grant。

修复：

- `07-runtime-schema.md` 增加 `StepPayload`、`AdapterInputPayload`、`TransportPayload`、`HeartbeatPayload`、`CommandResult`、`CommandReceipt`。
- `Step.payload` 改为 `StepPayload`，`AdapterInput.payload` 改为 `AdapterInputPayload`，`TransportEnvelope.payload` 改为 `TransportPayload`。
- `tool_result` 事件 payload 补齐 `tool_result_id`，并要求和 `ToolResult.tool_result_id` 一致。
- `SessionState` 增加 canonical `processed_commands: CommandReceipt[]`；重复命令按 `session_id + type + idempotency_key` 查回执，payload 哈希一致返回第一次 `CommandResult`，不一致返回冲突。
- `PendingAdapterAction` 只保存 `command_receipt_ids` 引用，避免和全局 `processed_commands` 双写。
- `AuditResult.tool_result_id` 改为条件必填：当存在 `tool_call_id` 且工具已产生结果时必须填写。
- `PermissionGrant` 明确只允许由批准类 `PermissionDecision` 生成，`deny`、`revise`、`grant_scope=never` 不得生成持久授权。
- `PROJECT_DESIGN.md` 的 `approval_required.options` 示例从字符串数组改成结构化 `PermissionOption[]`。
- `12-test-fixtures.md` 增加 payload 类型、tool_result_id、CommandReceipt 和 PendingAdapterAction 双写的失败样例。

验证：

- `rg -n 'idempotency_keys|command_receipts|payload\` \| object|AgentEvent \| CommandFrame \| AckFrame \| ClientHello \| ErrorPayload \| object|options": \["approve_once"|PermissionRequest.options.*PermissionDecisionValue|current_run_id|run_command|ToolResultPayload|tool_result_id|StepPayload|AdapterInputPayload|TransportPayload|HeartbeatPayload|CommandReceipt|CommandResult|processed_commands|command_receipt_ids' docs/liuAgent-cli -g '*.md'`
- `sed -n` 回读 `01-core-objects.md`、`03-event-protocol.md`、`05-adapter-protocol.md`、`06-state-storage.md`、`07-runtime-schema.md`、`10-transport-protocol.md`、`12-test-fixtures.md`。

### 2026-06-20 命令入口、事件示例和工具结果必填字段对齐

范围：

- `PROJECT_DESIGN.md`
- `design/02-tool-system.md`
- `design/03-event-protocol.md`
- `design/04-permission-audit.md`
- `design/05-adapter-protocol.md`
- `design/07-runtime-schema.md`
- `design/08-tool-contracts.md`
- `design/10-transport-protocol.md`
- `design/12-test-fixtures.md`

问题：

- `ToolResult.summary` 在工具系统和工具契约中是可选，但 `ToolResultPayload.summary`、`AuditResult.summary` 和 UI 展示都要求有稳定摘要。
- `AdapterInput.type=permission_decision|interrupt|resume` 曾直接映射到裸 command payload，绕过了 `AdapterCommand.command_id`、顶层 `idempotency_key` 和 `CommandReceipt`。
- `CommandFrame.idempotency_key` 一处写成所有命令必填，和 `submit_text` 可不带幂等键的规则冲突。
- `PermissionOption.grant_scope` 允许使用 `never` 时，会出现“批准但禁止授权记忆”的矛盾选项。
- 顶层设计和传输协议里的事件示例缺少 `open_url_id`、`tool_result_id`、payload `created_at` 或完整 `AgentEvent` 字段，和 runtime schema 对不上。
- `open_url_done` 示例说是 `AdapterCommand`，但缺少 `command_id`。

修复：

- `ToolResult.summary` 改为必填；可由 `content` 截断生成，但落库、事件和审计前必须存在。
- 除 `user_message` 外，`AdapterInput.payload` 必须是完整 `AdapterCommand`；`permission_decision`、`interrupt`、`resume` 分别要求 `AdapterCommand.type=permission_decision|cancel|resume`。
- `CommandFrame.idempotency_key` 改为条件必填：`permission_decision`、`cancel`、`resume`、`open_url_done` 必填，`submit_text` 可选；若提供则进入 `CommandReceipt`。
- 明确 `permission_decision`、`cancel`、`resume`、`open_url_done` 顶层幂等键必须和 payload 内同名字段一致。
- 批准类 `PermissionOption.grant_scope` 只能是 `once`、`run`、`session`、`workspace`，不能是 `never`。
- 补齐 `PROJECT_DESIGN.md` 和 `03-event-protocol.md` 中 `open_url`、`tool_result`、`message_delta`、`approval_required`、`tool_started`、`state_changed` 的完整事件字段。
- `10-transport-protocol.md` 的 `TransportEnvelope.kind=event` 示例改为完整 `AgentEvent`。
- `12-test-fixtures.md` 增加 `ToolResult.summary`、完整 `AdapterCommand`、完整 `AgentEvent`、`command_id`、`grant_scope=never` 等失败样例。

验证：

- `rg -n 'summary\` \| string \| 否|tool_result.*\`tool_call_id\`、\`ok\`、\`summary\`|open_url.*\`url\`、\`reason\`|idempotency_key\` \| string \| 是 \| 无 \| Client|AdapterInput.*PermissionDecisionCommandPayload|裸 payload|grant_scope.*never' docs/liuAgent-cli -g '*.md'`
- `rg -n 'kind="event"|完整 AgentEvent|只保存 payload|type \+ payload|open_url_id|tool_result_id|created_at' docs/liuAgent-cli/design docs/liuAgent-cli/PROJECT_DESIGN.md -g '*.md'`
- `sed -n` 回读 `03-event-protocol.md`、`07-runtime-schema.md`、`10-transport-protocol.md`、`12-test-fixtures.md`。

### 2026-06-20 GrantScope 类型边界和状态事件示例对齐

范围：

- `design/04-permission-audit.md`
- `design/07-runtime-schema.md`
- `design/09-state-machine.md`
- `design/11-security-policy.md`
- `design/12-test-fixtures.md`

问题：

- `GrantScope` 同时包含 `never`，但前面已规定批准类 `PermissionOption` 和 `PermissionDecision` 不能使用 `never`，导致同一个类型在策略配置、用户批准和持久 Grant 三个阶段语义不同。
- `PolicyRule.grant_scope` 需要表达“不允许生成授权记忆”，但 `PermissionGrant.scope` 只能表达真实批准范围；两者共用 `GrantScope` 会让实现误把 `never` 写入 Grant。
- `09-state-machine.md` 的 `state_changed` 示例仍是半截事件，只包含 `type + payload`，和 `AgentEvent` 必填 `event_id/session_id/created_at` 的规范不一致。

修复：

- `GrantScope` 收敛为批准类范围：`once`、`run`、`session`、`workspace`。
- 新增 `PolicyGrantScope = GrantScope | "never"`，仅用于 `PolicyRule.grant_scope`。
- 明确 `never` 不能进入 `PermissionOption.grant_scope`、`PermissionDecision.grant_scope` 或 `PermissionGrant.scope`。
- `09-state-machine.md` 的 `state_changed` 示例补齐完整 `AgentEvent` 字段。
- `12-test-fixtures.md` 增加 `PolicyRule.grant_scope=["never"]` 却生成批准选项或 Grant 的失败样例。

验证：

- `rg -n 'GrantScope|PolicyGrantScope|grant_scope|never|PermissionGrant.scope' docs/liuAgent-cli/design/04-permission-audit.md docs/liuAgent-cli/design/07-runtime-schema.md docs/liuAgent-cli/design/11-security-policy.md docs/liuAgent-cli/design/12-test-fixtures.md`
- `rg -n 'state_changed|event_id|session_id|created_at|只包含.*payload|半截事件' docs/liuAgent-cli/design/09-state-machine.md docs/liuAgent-cli/design/14-consistency-audit.md`

### 2026-06-20 顶层 README 工具结构和内置工具清单对齐

范围：

- `README.md`
- `PROJECT_DESIGN.md`
- `design/02-tool-system.md`
- `design/08-tool-contracts.md`

问题：

- 顶层 `README.md` 的工具登记字段仍使用 `schema`，没有列出 canonical `ToolDefinition.input_schema`、`action`、`requires_approval` 和 `scope`。
- 顶层 `README.md` 的工具执行结果示例还是早期 `ok/stdout/stderr/data/error`，和当前 `ToolResult` 必填 `tool_result_id`、`tool_call_id`、`content`、`summary`、`created_at` 不一致。
- `PROJECT_DESIGN.md` 的第一批文件工具漏掉 `write_file`，但 `README.md` 和 `08-tool-contracts.md` 已包含该工具。

修复：

- 顶层 `README.md` 的 Tool Registry 字段同步为 `input_schema`、`action`、`risk`、`requires_approval`、`scope` 和 `execute`。
- 顶层 `README.md` 的 Tool Executor 示例同步为 canonical `ToolResult`。
- `PROJECT_DESIGN.md` 的文件工具清单补齐 `write_file`。

验证：

- `rg -n 'schema|input_schema|ToolResult|stdout|stderr|write_file' docs/liuAgent-cli/README.md docs/liuAgent-cli/PROJECT_DESIGN.md docs/liuAgent-cli/design/02-tool-system.md docs/liuAgent-cli/design/08-tool-contracts.md`

### 2026-06-20 失败状态错误载荷对齐

范围：

- `design/01-core-objects.md`
- `design/07-runtime-schema.md`
- `design/09-state-machine.md`
- `design/12-test-fixtures.md`

问题：

- `RunState.last_error` 允许 `ToolError | ErrorPayload`，但 `StateChangedPayload.last_error` 只允许 `ErrorPayload`。
- 工具失败或策略拒绝进入 `failed` 时通常产生 `ToolError`；如果事件 payload 只接收 `ErrorPayload`，Transcript 和 UI 状态同步会丢失工具错误结构。

修复：

- `StateChangedPayload.last_error` 改为 `ToolError | ErrorPayload`，并明确必须和 `RunState.last_error` 一致。

验证：

- `rg -n 'ToolError|ErrorPayload|last_error|StateChangedPayload|RunState' docs/liuAgent-cli/design/01-core-objects.md docs/liuAgent-cli/design/07-runtime-schema.md docs/liuAgent-cli/design/09-state-machine.md docs/liuAgent-cli/design/12-test-fixtures.md`

### 2026-06-20 ToolResult Step payload 对齐

范围：

- `design/01-core-objects.md`
- `design/07-runtime-schema.md`
- `design/12-test-fixtures.md`

问题：

- `ToolResult`、`ToolResultPayload` 和 `AuditResult` 已要求稳定 `summary`；`ToolResult` 和事件 payload 已要求 `created_at`。
- `ToolResultStepPayload` 只包含 `tool_result_id`、`tool_call_id`、`ok`，导致 Transcript 的 Step 层无法独立展示工具结果摘要，也无法和事件时间对齐。

修复：

- `ToolResultStepPayload` 补齐 `summary`、`error_code?` 和 `created_at`。
- `StepPayload` 表格同步更新最小内容。
- `12-test-fixtures.md` 增加 `Step.type=tool_result` 缺少 `summary` 或 `created_at` 的失败样例。

验证：

- `rg -n 'ToolResultStepPayload|ToolResultPayload|Step.type=tool_result|summary|created_at' docs/liuAgent-cli/design/07-runtime-schema.md docs/liuAgent-cli/design/12-test-fixtures.md`
