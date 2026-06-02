# AI 对话框计划驱动执行工作流升级计划

> 日期：2026-06-01  
> 项目：`proj-d16591a6`  
> 状态：设计阶段  
> 范围：AI 对话框、assistant_workflow、Agent Runtime v2、工具/命令执行事件、前端执行过程 UI  

## 1. 背景

当前 AI 对话框已经具备任务类型识别、项目上下文注入、工具调用、任务树、工作轨迹和 Agent Runtime v2 等能力，但用户侧感知仍偏“聊天机器人”。

用户期望的工作方式是：

```text
获取用户提问内容
-> 理解需求：判断是普通提问，还是要求执行任务
-> 执行型需求生成计划
-> 按计划生成对应命令或工具动作
-> 开始执行
-> 前端 UI 展示当前执行了哪些命令、工具和结果
-> 任务执行结束后给出反馈
```

这个方向是正确的。它的关键不是增加一个模型，而是把现有“模型自行调工具”的过程升级为“计划驱动、过程可见、结果可验证”的执行系统。

## 2. 当前工作流现状

当前实际链路更接近：

```text
用户消息
-> assistant_workflow 粗分类
-> 选择模型、员工、项目上下文和工具
-> 模型在对话循环里决定是否调用工具
-> 工具返回结果
-> 模型继续生成或结束
-> 前端展示部分过程和最终回复
```

已有能力：

- `assistant_workflow_state_service.py` 能识别 `query`、`coding`、`automation`、`docs`、`bugfix` 等任务类型。
- `projects.py` 会组装项目、员工、工具、任务树和运行时上下文。
- `agent_orchestrator.py` 与 `agent_runtime_v2/` 支持模型工具调用循环。
- `ProjectChat.vue` 已有执行过程容器，并已开始展示工具、命令、输出摘要。
- 统一查询 MCP 和任务树具备需求分析、上下文聚合、执行计划、状态回写能力。

当前不足：

| 环节 | 现状 | 问题 |
| --- | --- | --- |
| 意图判断 | 主要靠关键词和上下文 | 普通提问与执行任务的边界不够稳定 |
| 计划生成 | 部分任务有任务树/计划 | 并非每个执行型需求都先形成可见计划 |
| 命令生成 | 模型在工具调用时临时生成 | 缺少独立的 command plan 和执行前审计 |
| 执行展示 | 前端已有过程容器 | 工具/命令/验证之间还没有稳定关联 |
| 验证收口 | 有 done、audit、guard | 缺少强制 verification 阶段和证据展示 |

## 3. 目标

把 AI 对话框升级为计划驱动的执行入口。

目标链路：

```text
User Input
-> Intent Router
-> Task Understanding
-> Execution Plan
-> Command / Tool Plan
-> Step Executor
-> Live Execution Timeline
-> Verification
-> Final Report
```

用户侧看到的是：

```text
深度思考
- 正在理解需求
- 判定为执行型任务

执行计划
- 1. 检查当前环境
- 2. 执行安装命令
- 3. 验证版本

执行过程
- 命令：node -v
- cwd：...
- exit：0
- 输出：...

验证结果
- 已执行 node -v
- 结果符合预期

最终反馈
- 完成了什么
- 有哪些文件/环境变化
- 后续建议
```

## 4. 核心设计原则

### 4.1 普通提问不进入执行链路

普通提问应直接回答或工具增强回答，不生成命令计划。

示例：

- “AIGC 是我们现在做的东西吗？”
- “解释一下这个模块”
- “这个方案有什么风险？”

流程：

```text
intent=query
-> direct_answer / tool_augmented
-> final answer
```

### 4.2 执行型需求必须先计划

凡是会改变项目状态、系统状态、外部系统状态，或需要多步操作的需求，都必须先生成计划。

示例：

- “帮我安装 Node 24”
- “把这个功能改掉”
- “部署一下”
- “帮我发消息”
- “生成素材并保存到项目”

流程：

```text
intent=execution
-> task_understanding
-> execution_plan
-> command_plan / tool_plan
-> execution
-> verification
-> final_report
```

### 4.3 命令不是直接执行，而是作为计划步骤执行

命令或工具动作必须绑定到计划节点。

建议结构：

```json
{
  "step_id": "step-001",
  "title": "检查 Node 当前版本",
  "action_type": "command",
  "command": "node -v",
  "cwd": "/path/to/workspace",
  "risk_level": "low",
  "requires_confirmation": false,
  "expected_result": "输出当前 Node 版本",
  "verification": "exit_code == 0"
}
```

### 4.4 前端展示的是可审计摘要，不展示原始思维链

“深度思考”不等于暴露模型内部推理全文。

前端应展示：

- 需求理解摘要
- 任务分类
- 执行计划
- 正在执行的步骤
- 命令和工具参数
- 输出摘要
- 验证证据

不展示：

- 模型原始 chain-of-thought
- 敏感凭据
- 过长 stdout/stderr 全量内容

## 5. 后端事件协议升级

建议统一事件类型：

```text
thinking_started
thinking_summary
intent_classified
plan_created
step_started
command_planned
command_started
command_output
command_finished
tool_started
tool_finished
verification_started
verification_finished
final_report
blocked
failed
done
```

### 5.1 thinking_summary

```json
{
  "type": "thinking_summary",
  "request_id": "req-xxx",
  "summary": "用户要求执行环境安装任务，需要先检查当前版本，再下载并配置。",
  "intent": "execution",
  "confidence": 0.86
}
```

### 5.2 plan_created

```json
{
  "type": "plan_created",
  "request_id": "req-xxx",
  "plan_id": "plan-xxx",
  "steps": [
    {
      "step_id": "step-001",
      "title": "检查当前环境",
      "status": "pending"
    },
    {
      "step_id": "step-002",
      "title": "执行安装",
      "status": "pending"
    },
    {
      "step_id": "step-003",
      "title": "验证结果",
      "status": "pending"
    }
  ]
}
```

### 5.3 command_started

```json
{
  "type": "command_started",
  "request_id": "req-xxx",
  "plan_id": "plan-xxx",
  "step_id": "step-001",
  "command": "node -v",
  "cwd": "/path/to/workspace",
  "sandbox": "workspace-write",
  "risk_level": "low"
}
```

### 5.4 command_finished

```json
{
  "type": "command_finished",
  "request_id": "req-xxx",
  "plan_id": "plan-xxx",
  "step_id": "step-001",
  "exit_code": 0,
  "stdout_preview": "v24.0.0",
  "stderr_preview": "",
  "duration_ms": 180
}
```

### 5.5 verification_finished

```json
{
  "type": "verification_finished",
  "request_id": "req-xxx",
  "plan_id": "plan-xxx",
  "status": "passed",
  "evidence": [
    "node -v 输出 v24.0.0",
    "npm -v 正常返回"
  ]
}
```

## 6. 模块改造方案

### 6.1 Intent Router

职责：

- 判断用户输入是普通提问、执行任务、写入任务、高风险任务还是需要澄清。
- 输出结构化 intent。

建议输出：

```json
{
  "intent": "execution",
  "task_type": "environment_setup",
  "clarity_score": 4,
  "requires_plan": true,
  "requires_confirmation": false,
  "risk_level": "medium"
}
```

落点：

- 扩展 `assistant_workflow_state_service.py`
- 将当前关键词识别升级为“规则 + 模型结构化分类 + 风险策略”的组合。

### 6.2 Plan Generator

职责：

- 为执行型需求生成步骤计划。
- 每一步要有输入、动作、预期输出和验证方法。

落点：

- 优先复用统一查询 MCP 的 `analyze_task`、`resolve_relevant_context`、`generate_execution_plan`。
- 对项目聊天入口补一个轻量 `execution_plan` 状态。
- 长任务同步生成任务树，短任务可生成内存计划。

### 6.3 Command / Tool Planner

职责：

- 将计划步骤转换为命令或工具动作。
- 标记风险等级、权限需求、执行环境。

输出示例：

```json
{
  "step_id": "step-002",
  "action_type": "tool",
  "tool_name": "project_host_run_command",
  "arguments": {
    "command": "npm install",
    "cwd": "/workspace/web-admin/frontend"
  },
  "risk_level": "medium",
  "requires_confirmation": true
}
```

落点：

- `agent_orchestrator.py`
- `agent_runtime_v2/query_engine.py`
- `tool_executor.py`
- `project_host_command_service.py`

### 6.4 Step Executor

职责：

- 按计划逐步执行。
- 每步开始、完成、失败、阻塞都发事件。
- 失败不能覆盖历史 attempt，要产生新的 attempt 记录。

状态：

```text
pending
running
waiting_user
blocked
failed
verifying
completed
```

### 6.5 Frontend Timeline

职责：

- 把后端事件渲染成执行时间线。
- 用户能看见当前 AI 正在做什么。

组件结构：

```text
ExecutionTrace
├── ThinkingBlock
├── PlanBlock
├── StepCard
│   ├── CommandBlock
│   ├── ToolArgsBlock
│   ├── OutputPreview
│   └── VerificationEvidence
└── FinalReportBlock
```

当前已完成的基础：

- `ProjectChat.vue` 已有 `message-process-shell`
- 已开始展示深度思考步骤
- 已开始展示工具/命令卡片
- 已开始展示 `command`、`cwd`、`exit`、输出摘要

后续需要：

- 独立抽出 `ExecutionTrace.vue`
- 支持计划节点和命令节点一一对应
- 支持折叠/展开
- 支持简洁模式/详细模式
- 支持复制命令和查看完整输出

## 7. 前端展示规范

### 7.1 默认展示层级

默认展开：

- 深度思考摘要
- 当前执行步骤
- 正在执行的命令
- 阻塞/失败/待确认项
- 最终反馈

默认折叠：

- 过长 stdout
- 过长 stderr
- 完整工具参数
- 中间模型事件

### 7.2 命令卡片字段

每个命令卡片至少展示：

```text
标题
状态
cwd
command
exit code
stdout 摘要
stderr 摘要
耗时
风险等级
是否需要授权
```

### 7.3 视觉状态

| 状态 | 展示 |
| --- | --- |
| running | 蓝色进行中 |
| waiting_user | 黄色待处理 |
| completed | 绿色已完成 |
| failed | 红色失败 |
| blocked | 红色阻塞 |
| verifying | 蓝色验证中 |

## 8. 分阶段实施计划

### Phase 1：过程可见化

目标：

- 前端清楚展示深度思考、工具、命令、输出摘要。
- 不大改后端协议，先消费已有事件。

任务：

- 保留并强化 `ProjectChat.vue` 的执行过程卡片。
- 工具操作不再隐藏。
- 命令类工具展示 `command/cwd/exit/output`。
- 响应开始时显示“深度思考”步骤。

状态：

- 已开始实现。

### Phase 2：计划事件标准化

目标：

- 后端在执行前明确生成 `plan_created`。
- 每个工具/命令绑定 `step_id`。

任务：

- 扩展 `assistant_workflow_state_service.py` 的 intent 输出。
- 在项目聊天入口生成 execution plan。
- 给 `tool_start/tool_result` 增加 `plan_id/step_id`。
- 前端按计划节点聚合展示。

### Phase 3：命令计划与风险确认

目标：

- 命令执行前形成 command plan。
- 高风险命令必须可见、可确认、可拒绝。

任务：

- 增加 `command_planned` 事件。
- 接入 `classify_command_risk` / `check_operation_policy`。
- 前端展示风险等级和确认按钮。
- 执行历史记录 attempt。

### Phase 4：验证与交付报告

目标：

- 每个执行型任务必须有验证阶段。
- 最终反馈不只是自然语言总结，而是交付报告。

任务：

- 增加 `verification_started/verification_finished`。
- 完成时生成 `final_report`。
- 交付报告展示完成项、验证证据、失败/阻塞原因、后续建议。
- 与任务树 `complete_task_node_with_verification` 对齐。

### Phase 5：组件化与长期维护

目标：

- 把执行过程 UI 从 `ProjectChat.vue` 中拆出，降低维护成本。

任务：

- 新建 `ExecutionTrace.vue`
- 新建 `ExecutionStepCard.vue`
- 新建 `CommandOutputBlock.vue`
- 抽出事件归一化工具
- 补前端单元测试和快照测试

## 9. 验收标准

### 9.1 普通提问

输入：

```text
AIGC 是我们现在做的东西吗？
```

期望：

- 不生成命令计划。
- 可直接回答。
- 不展示无意义执行步骤。

### 9.2 简单命令型任务

输入：

```text
帮我检查当前 Node 版本
```

期望：

- 展示深度思考。
- 展示执行计划。
- 展示命令 `node -v`。
- 展示 cwd、exit code、stdout 摘要。
- 最终反馈说明当前版本。

### 9.3 多步执行任务

输入：

```text
帮我安装 Node 24 并验证
```

期望：

- 先生成计划。
- 每一步有状态。
- 下载、安装、验证分别是独立步骤。
- 失败时展示失败步骤和错误输出。
- 成功时展示验证证据。

### 9.4 高风险任务

输入：

```text
清空这个目录重新部署
```

期望：

- 标记高风险。
- 展示影响范围。
- 请求用户确认。
- 未确认前不得执行删除或覆盖。

## 10. 风险与约束

### 10.1 不展示原始思维链

只能展示结构化思考摘要和计划，不展示模型内部推理全文。

### 10.2 不让前端猜业务状态

前端可以兼容旧事件，但长期应以标准事件协议为准。

### 10.3 不把所有提问都变成任务

普通咨询必须保持轻量，否则用户会觉得系统反应慢。

### 10.4 不绕过权限策略

命令计划可见不代表自动执行。高风险命令、外部写入、删除、部署必须确认。

## 11. 建议优先级

优先做：

1. 执行型 intent 分类标准化
2. `plan_created` 事件
3. `tool_start/tool_result` 绑定 `step_id`
4. 前端计划时间线
5. verification 事件

暂缓做：

1. 完整 DAG 调度
2. 多 Agent 并发计划拆分
3. 完整输出日志持久化 UI
4. 可视化流程编辑器

## 12. 最终目标

升级完成后，AI 对话框不再只是“输入问题、等待回复”的聊天界面，而是一个可观察的 AI 执行控制台。

用户能清楚看到：

- AI 怎么理解需求
- 为什么要执行这些步骤
- 当前执行到哪一步
- 实际执行了哪些命令
- 每条命令结果是什么
- 是否验证通过
- 最终交付是否可信

这才是当前系统从普通 AIGC 对话升级为 AI Agent 工作流产品的关键。
