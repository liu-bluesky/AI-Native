# 智能体编排

用户刚才问的“规则提示词、固定流程、状态机、生命周期控制行为”，专业上可以统一叫：

- `Agent Orchestration`：智能体编排。
- `Agent Runtime Lifecycle`：智能体运行时生命周期。

更准确地说，`Agent Orchestration` 是总称，描述如何把模型、工具、权限、状态、事件、任务计划和用户交互组织成一个可运行系统。`Agent Runtime Lifecycle` 是它在运行时的具体流程，描述一次用户请求从进入系统到完成交付之间经历哪些阶段。

## 它不只是提示词

这类能力不能只靠“写一段规则提示词”完成。

提示词可以告诉模型应该如何判断，但提示词本身不保证执行顺序、权限拦截、状态一致性和审计可追踪。真正稳定的 Agent 系统通常要同时具备这些层：

| 层级 | 专业术语 | 作用 |
| --- | --- | --- |
| 语义判断层 | `Prompt Policy` | 告诉模型如何理解需求、拆任务、判断追加内容和解释工具结果。 |
| 流程编排层 | `Workflow` | 固定入口顺序，例如解析需求、绑定上下文、生成计划、执行工具、验证结果。 |
| 状态控制层 | `State Machine` | 限制合法状态转移，例如不能从等待审批直接跳到已完成。 |
| 策略执行层 | `Policy Engine` | 对命令、文件、链接、授权、部署等动作做允许、拒绝或要求确认。 |
| 安全护栏层 | `Guardrails` | 限制模型和工具越界，例如禁止泄露凭据、禁止未授权删除。 |
| 事件记录层 | `Event Sourcing` | 把模型输出、工具调用、审批决定和状态变化记录为可回放事件。 |
| 运行监督层 | `Runtime Supervisor` | 监控运行过程，处理取消、超时、失败、恢复和用户追加输入。 |

所以它的专业表达不是“写规则提示词”，而是：

```text
Agent Orchestration
  = Prompt Policy
  + Workflow
  + State Machine
  + Policy Engine
  + Event Sourcing
  + Runtime Supervisor
```

## 在 liuAgent CLI 中的位置

liuAgent CLI 应该把智能体运行过程设计成一条明确生命周期：

```text
User Input
  -> Requirement Parsing
  -> Context Binding
  -> Planning
  -> Policy Check
  -> Tool Execution
  -> Observation
  -> Verification
  -> Delivery
```

对应到中文：

- `Requirement Parsing`：解析用户需求，判断是新需求、追加内容、修复还是澄清。
- `Context Binding`：绑定项目、会话、文件、工具和历史上下文。
- `Planning`：生成可执行计划或更新已有计划。
- `Policy Check`：检查是否需要用户授权、是否越权、是否有风险。
- `Tool Execution`：调用文件、命令、浏览器、MCP、桌面 Runner 等工具。
- `Observation`：把工具结果转成模型可继续推理的观察信息。
- `Verification`：验证改动是否满足目标。
- `Delivery`：输出交付结论，并记录事件、状态和审计信息。

## 追加内容如何处理

用户在解决问题过程中突然追加内容，本质上属于 `Runtime Input Event`，也就是运行时输入事件。Runtime Supervisor 需要判断它属于哪一类：

| 类型 | 含义 | 处理方式 |
| --- | --- | --- |
| `clarification` | 用户补充解释原需求，没有改变目标 | 合并到当前需求上下文，继续执行。 |
| `scope_addition` | 用户增加同一目标下的新子任务 | 更新当前计划，追加任务节点。 |
| `scope_change` | 用户改变目标或关键约束 | 暂停当前执行，重新确认并重新规划。 |
| `new_requirement` | 用户提出另一个独立需求 | 新建 requirement、task tree 或 run。 |
| `correction` | 用户指出当前理解或执行有误 | 回滚到最近安全状态，修正计划。 |
| `cancel` | 用户要求停止 | 取消当前 run，记录已完成和未完成状态。 |

这一步不应该完全交给模型自由发挥。推荐做法是让模型先输出结构化分类，再由运行时代码决定是否继续、暂停、重规划或新开任务。

示例结构：

```json
{
  "input_type": "scope_addition",
  "affects_current_goal": true,
  "requires_confirmation": false,
  "plan_action": "append_task_node",
  "reason": "用户追加的是当前 liuAgent CLI 设计文档的同一主题内容"
}
```

## 开发方式

在代码实现里，不同规则应该放在不同层，不要全部塞进一个长提示词。

| 规则类型 | 推荐实现 |
| --- | --- |
| 需求分类、意图理解 | Prompt Policy + 结构化输出 schema |
| 固定入口顺序 | Workflow 代码 |
| 状态是否合法 | State Machine |
| 文件、命令、链接、授权是否可执行 | Policy Engine |
| 用户确认、拒绝、允许一次 | Permission Gate |
| 过程恢复、回放、审计 | Event Log / Event Sourcing |
| CLI、Web、Desktop 一致交互 | AgentEvent + Adapter |

Prompt 负责“判断和解释”，代码负责“约束和执行”。这样 Web、Desktop、CLI 才能复用同一个 Agent Core，而不是各自复制一套交互逻辑。

## 与已有设计文档的关系

- `03-event-protocol.md` 负责描述事件如何在 Core 和 Adapter 之间传递。
- `04-permission-audit.md` 负责描述权限请求和审计记录。
- `09-state-machine.md` 负责描述运行时状态转移。
- `11-security-policy.md` 负责描述策略规则和授权范围。
- 本文负责解释这些机制合在一起的专业命名和分层关系。

## 结论

这类设计在专业上叫 `Agent Orchestration`，中文可以叫“智能体编排”。

落到 liuAgent CLI 的运行时设计里，应拆成：

```text
Agent Runtime Lifecycle
+ Workflow
+ State Machine
+ Policy Engine
+ Prompt Policy
+ Event Sourcing
```

规则提示词只是其中一层。要让 CLI、Web、Desktop 复用同一套能力，核心应该做成事件驱动的 Agent Core，再由不同 Adapter 渲染成终端交互、网页按钮或桌面弹窗。
