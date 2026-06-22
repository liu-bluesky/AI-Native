# 规划机制

规划机制描述 Agent 在执行前如何评估需求清晰度、生成计划、获取确认，以及执行中如何维持连续推进与暂停判断。它不等同于状态机（`09-state-machine.md`），而是状态机的前置决策层。

## 职责边界

| 模块 | 负责 | 不负责 |
| --- | --- | --- |
| 规划机制 | 清晰度评估、计划生成、确认门、阻塞记录 | 工具执行、权限审批、事件输出 |
| `09-state-machine.md` | Run/工具调用/权限请求状态转移 | 是否需要先规划 |
| `13-agent-orchestration.md` | 提示词规则、策略引擎、运行时生命周期 | 计划对象的结构与存储 |
| `04-permission-audit.md` | 高风险动作拦截与审计 | 需求清晰度判断 |

---

## 触发条件

每次用户输入进入 Agent 后，规划机制先于工具执行运行。

```text
User Input
  -> ClarityAssessment       ← 规划机制入口
  -> 清晰度 >= 阈值 且为查询型？
       是 -> 直接回答，不生成 TaskTree
       否 -> PlanSummary + 等待 PlanDecision
            -> PlanDecision.approved == true -> 进入执行
            -> PlanDecision.approved == false -> 返回修改
```

**需求分类**

| 类型 | 判断依据 | 规划行为 |
| --- | --- | --- |
| 查询/解释 | 无写入、无修改、无状态变更 | 清晰度 ≥ 3 直接回答 |
| 实现/修改/部署 | 涉及文件写入、命令执行、外部服务、状态变更 | 必须先输出 PlanSummary 并等待确认 |
| 模糊需求 | 清晰度 < 3 或存在两种以上合理理解 | 输出理解摘要 + 可能误解点 + 等待确认 |

---

## ClarityAssessment

对用户输入进行清晰度评估。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `score` | int (1–5) | 是 | 整体清晰度评分；阈值为 3，低于此值必须先澄清。 |
| `goal_clear` | bool | 是 | 目标是否明确。 |
| `target_clear` | bool | 是 | 操作对象（文件、模块、服务）是否明确。 |
| `scope_clear` | bool | 是 | 影响范围是否明确。 |
| `expected_result_clear` | bool | 是 | 预期结果是否明确。 |
| `ambiguities` | string[] | 否 | 存在歧义的点；低于阈值时必填。 |
| `interpretation` | string | 是 | Agent 当前对需求的理解摘要，供用户核对。 |

**评分规则**

- 四个维度各 1 分，加上整体判断凑整到 1–5。
- 全部明确且无歧义 → 5；三个明确 → 3–4；两个或以下明确 → 1–2。
- 阈值 3/5：score ≥ 3 且为查询型可直接回答；score ≥ 3 且为实现型必须生成 PlanSummary；score < 3 必须先输出澄清请求。

---

## TaskNode

任务树的单个节点。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `node_id` | ID | 是 | 节点 ID。 |
| `title` | string | 是 | 节点标题，一句话描述要做什么。 |
| `type` | `goal` \| `task` \| `step` | 是 | `goal` 是根节点，`task` 是子任务，`step` 是原子操作步骤。 |
| `status` | TaskNodeStatus | 是 | 见下方枚举。 |
| `parent_id` | ID | 否 | 父节点 ID；根节点为空。 |
| `children` | ID[] | 否 | 子节点 ID 列表。 |
| `tool_hint` | string | 否 | 预期使用的工具名，辅助权限预检。 |
| `is_destructive` | bool | 是 | 是否为不可逆操作；为 true 时必须在执行前单独确认。 |
| `verification_result` | string | 否 | 完成后的验证结论；完成节点必填。 |

**TaskNodeStatus 枚举**

| 值 | 说明 |
| --- | --- |
| `pending` | 尚未开始。 |
| `running` | 正在执行。 |
| `done` | 已完成并通过验证。 |
| `failed` | 执行失败。 |
| `blocked` | 遇到阻塞，等待处理。 |
| `skipped` | 已跳过（条件不满足或用户取消）。 |

---

## TaskTree

层级任务树，由 PlanSummary 生成，贯穿整个执行过程。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `tree_id` | ID | 是 | 树 ID。 |
| `root_goal` | string | 是 | 用户原始需求摘要。 |
| `nodes` | TaskNode[] | 是 | 所有节点，按 `node_id` 索引。 |
| `current_node_id` | ID | 是 | 当前正在执行的节点 ID。 |
| `created_at` | Timestamp | 是 | 树创建时间。 |
| `session_id` | ID | 是 | 所属会话 ID。 |

---

## PlanSummary

在获取用户确认前向用户展示的计划摘要。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `summary_id` | ID | 是 | 摘要 ID。 |
| `interpretation` | string | 是 | Agent 对需求的完整理解陈述。 |
| `task_tree` | TaskTree | 是 | 层级任务树预览。 |
| `destructive_steps` | TaskNode[] | 是 | 所有 `is_destructive=true` 的节点列表；必须单独列出。 |
| `estimated_tools` | string[] | 否 | 预计使用的工具列表。 |
| `risk_summary` | string | 否 | 风险点摘要，例如"将覆盖生产配置文件"。 |

---

## PlanDecision

用户对 PlanSummary 的确认结果。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `decision_id` | ID | 是 | 决策 ID。 |
| `summary_id` | ID | 是 | 对应的 PlanSummary ID。 |
| `approved` | bool | 是 | 是否批准执行。 |
| `modifications` | string | 否 | 用户要求的修改说明；`approved=false` 时必填。 |
| `decided_at` | Timestamp | 是 | 决策时间。 |

同一轮已取得 `approved=true` 后，后续步骤无需再次确认，除非遇到下方所列阻塞条件。

---

## 执行阶段约束

确认后进入连续执行，规划机制转为**监控模式**：跟踪当前节点状态、检测阻塞条件、维护 TaskTree 推进。

**只有以下情况才暂停执行并等待用户响应**

| 暂停条件 | 说明 |
| --- | --- |
| 破坏性/不可逆操作 | `is_destructive=true` 的节点，即使已总体确认，也必须在执行前单独说明对象、范围和可恢复性后再执行。 |
| 权限或环境阻塞 | 工具执行失败、缺少凭据、环境不可达，无法自行恢复。 |
| 需求范围变化 | 执行中发现实际范围与 PlanSummary 描述有实质偏差。 |
| 业务决策点 | 需要用户做不可推断的业务选择（例如选择部署目标）。 |
| 验证无法推进 | 完成后无法验证结果，且验证是任务完成条件。 |

阶段间的进度更新（节点状态变更、工作事实记录）在内部完成，不向用户请求确认。

---

## BlockerRecord

遇到阻塞时记录的对象。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `blocker_id` | ID | 是 | 阻塞 ID。 |
| `node_id` | ID | 是 | 发生阻塞的节点。 |
| `type` | BlockerType | 是 | 见下方枚举。 |
| `reason` | string | 是 | 阻塞原因描述。 |
| `recovery_condition` | string | 是 | 明确说明需要用户做什么才能继续。 |
| `created_at` | Timestamp | 是 | 记录时间。 |

**BlockerType 枚举**

| 值 | 说明 |
| --- | --- |
| `destructive_op` | 不可逆操作需要单独确认。 |
| `permission_denied` | 工具执行被权限策略拒绝。 |
| `env_unreachable` | 环境不可达（命令失败、服务宕机）。 |
| `scope_changed` | 实际范围与计划偏差。 |
| `business_decision` | 需要用户做业务选择。 |
| `verification_failed` | 完成验证步骤失败。 |

---

## 节点完成验证

每个 TaskNode 完成时必须写入 `verification_result`，不能以"自然语言进度"替代完成状态。

```text
执行节点
  -> 执行工具
  -> 观察结果
  -> 验证通过？
       是 -> node.status = "done", node.verification_result = "<验证结论>"
       否 -> node.status = "failed" 或 "blocked" + BlockerRecord
```

---

## 与其他模块的接驳

| 接驳点 | 说明 |
| --- | --- |
| `09-state-machine.md` | PlanDecision 产生后，Run 的状态从 `waiting_user` 转为 `running`；`BlockerRecord` 对应 `waiting_user` 或 `failed` 状态。 |
| `13-agent-orchestration.md` | 策略引擎读取 `ClarityAssessment.score` 和需求分类，决定走规划分支还是直接回答分支。 |
| `04-permission-audit.md` | `is_destructive=true` 的 TaskNode 在执行前触发 `PermissionRequest`；BlockerType `permission_denied` 对应 `PermissionDecision.denied`。 |
| `06-state-storage.md` | `TaskTree` 和 `BlockerRecord` 需要持久化进 `SessionState`，支持中断恢复。 |
