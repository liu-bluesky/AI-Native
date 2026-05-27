# AI 智能体开发工作流升级方案 v3

> 版本：v3
> 日期：2026-05-27
> 目标：把 ai-employee 的项目对话升级为 Claude Code / Codex CLI 同级效果的开发型 Agent Runtime。

## 1. 升级目标

本方案不是做对比说明，而是定义 ai-employee 下一版必须达到的运行时效果。

目标效果：

- 用户提出开发、排查、安装、部署、修复类任务后，系统创建一个可恢复的 `TaskRun`。
- 模型每次工具调用、工具结果、后台任务、用户授权、完成判定都写入结构化事件。
- 工具结果不会只作为聊天文本存在，而是成为运行时的 `Observation`。
- 模型不能因为空输出、短输出、没有 tool call 就结束任务。
- 后台任务完成后，后端恢复同一个 `TaskRun`，而不是前端拼一段 prompt 再发起新聊天。
- 首次进入项目目录时有 trust directory 边界，未信任目录不得加载项目本地配置、hooks、插件、执行策略。
- 每次敏感工具调用都经过权限管线，支持 `AllowOnce`、`AllowSession`、`AllowAlways`、`Deny`。
- 长任务中断后可以从 transcript、TaskRun、任务树、工作轨迹恢复，不依赖模型记忆。
- 开发型任务完成必须有验证证据，未验证不能进入 completed。
- 新工作流必须在独立目录和独立入口中并行开发，旧工作流保持可用；未完成验证和切流前，不得删除或重写旧链路。

一句话目标：

```text
任务目标、执行状态、权限决定、工具观察和完成判定必须外置为强状态；
模型只负责推理，不能独自决定任务是否已经完成。
```

## 2. 现状结论

当前 ai-employee 已有以下基础：

- 项目聊天和流式模型输出。
- `AgentOrchestrator.run()` 中的 tool call 聚合和工具执行。
- `ToolExecutor` 执行 MCP / 项目工具 / 宿主命令。
- 项目任务树 MCP，可记录任务节点和验证结果。
- `start_work_session`、`save_work_facts`、`append_session_event`、`resume_work_session` 等工作轨迹工具。
- `classify_command_risk`、`check_operation_policy` 可判断风险、工作区范围和是否需要确认。
- 前端 Live Execution 展示后台任务、授权、终端等状态。

但当前系统还不是 Claude/Codex 同级的 Agent Runtime：

- 没有一个权威 `TaskRun` 对象负责整轮任务生命周期。
- 工具结果主要 append 到 OpenAI 风格 `tool` message，没有独立事件日志和 observation store。
- 完成判定仍可能走到“模型没有 tool call -> completed”的弱路径。
- 后台 operation task 的自动继续仍有前端拼恢复 prompt 的痕迹。
- 权限检查是可调用能力，不是每个工具调用的强制拦截管线。
- 没有完整的 trust directory 首启边界。
- 没有 session 级 permission rule，例如 AllowOnce / AllowSession / Persisted allow。
- 任务树偏项目审计，不是执行循环的唯一权威状态。

因此 v3 要做的是一次运行时升级，而不是继续在 prompt 或前端上补兜底。

## 3. 强制设计原则

### 3.1 任务不靠模型记住

所有任务状态必须保存在运行时：

- `user_goal`
- `plan`
- `current_step`
- `tool_calls`
- `observations`
- `pending_operations`
- `pending_user_actions`
- `permission_decisions`
- `verification`
- `completion_decision`

模型上下文只是运行时状态的投影。上下文压缩、页面刷新、模型空输出都不能让任务目标丢失。

### 3.2 工具结果必须进入下一轮决策

任何工具调用结束后，必须生成 `ToolObservation`，并由 `CompletionPolicy` 决定下一步：

```text
tool result
-> normalize observation
-> append event
-> evaluate completion policy
-> continue / wait / ask / verify / complete / fail
```

不能把工具结果追加到 messages 后就交给模型自然发挥。

### 3.3 完成必须过门禁

`completed` 不是模型自然语言说“完成了”，而是运行时状态满足完成条件：

- 用户原始目标被覆盖。
- 没有 pending background operation。
- 没有 pending user action。
- 最近工具结果不与完成结论冲突。
- 开发型任务有验证证据。
- 任务树当前节点已写入验证结果。
- CompletionPolicy 返回 `complete`。

否则只能是 `continue`、`waiting_user`、`waiting_background`、`blocked`、`failed`。

### 3.4 权限是工具执行前的强制管线

权限不允许只作为模型可选工具或提示词要求存在。每次工具执行前必须调用：

```text
ToolCall
-> PermissionPolicy.evaluate()
-> allow / ask / deny
-> PermissionDecision persisted
-> execute or wait_user or block
```

用户的 AllowOnce / AllowSession / AllowAlways 只改变权限上下文，不绕过安全检查。

### 3.5 前端只展示状态，不驱动任务继续

前端可以提交用户输入、审批结果、取消动作，但不能负责：

- 拼恢复 prompt。
- 判断后台完成后是否继续。
- 判断任务是否完成。
- 构造模型下一轮输入。

这些全部归后端 `AgentTaskRuntime`。

### 3.6 新旧工作流隔离

升级开发必须采用旁路并行策略：

- 新 runtime 放在独立目录，不直接覆盖旧 `AgentOrchestrator` 主链。
- 旧工作流继续作为默认可用路径和 fallback。
- 新入口通过开关、灰度或显式路由启用。
- 旧链路只允许接入最小适配层，不允许在开发期大规模改写。
- 删除旧工作流必须等新工作流完成端到端验证、灰度切流、回滚预案和数据迁移确认。

禁止做法：

- 在旧 `AgentOrchestrator.run()` 中直接重写主循环。
- 为了接入新 runtime 删除旧 tool execution / background resume 逻辑。
- 在没有开关和回滚路径时替换项目聊天 API。
- 新旧状态混写到同一套不可区分字段，导致无法回滚。

## 4. 目标运行时架构

新增后端运行时目录必须与旧工作流隔离。推荐使用 `agent_runtime_v2/` 或 `agent_runtime_next/`，开发完成并切流稳定后再评估是否重命名为 `agent_runtime/`。

```text
web-admin/api/services/agent_runtime_v2/
  __init__.py
  runtime.py
  task_run.py
  state_store.py
  event_log.py
  query_engine.py
  llm_step.py
  tool_call_collector.py
  tool_execution_runner.py
  tool_result_normalizer.py
  tool_pool.py
  permission_policy.py
  permission_store.py
  trust_policy.py
  operation_resume.py
  completion_policy.py
  verification_policy.py
  memory_compaction.py
  transcript_store.py
  event_stream.py
  errors.py
```

旧目录 / 旧模块保留：

```text
web-admin/api/services/agent_orchestrator.py
web-admin/api/services/tool_executor.py
web-admin/api/services/operation_wait_task_service.py
```

旧模块在开发期只做三类改动：

- 增加 feature flag 分流。
- 增加向新 runtime 转发的薄适配层。
- 增加兼容事件或状态读取，不改变旧默认行为。

主链路：

```text
ProjectChat API / WebSocket
-> AgentTaskRuntime.start_or_resume()
   -> TrustPolicy.ensure_workspace_trusted()
   -> TaskRunStore.load_or_create()
   -> TranscriptStore.record_user_message_before_llm()
   -> DynamicToolPool.resolve()
   -> QueryEngine.loop()
      -> LLMStep.call_model()
      -> ToolCallCollector.collect()
      -> PermissionPolicy.evaluate()
      -> ToolExecutionRunner.execute()
      -> ToolResultNormalizer.normalize()
      -> TaskRunStore.append_event()
      -> CompletionPolicy.evaluate()
   -> EventStream.emit()
   -> WorkSession / TaskTree sync
```

核心边界：

| 模块 | 职责 |
| --- | --- |
| `AgentTaskRuntime` | 任务生命周期入口，创建、恢复、取消、收尾 |
| `TaskRunStore` | 读写权威任务状态 |
| `TranscriptStore` | 事件化 transcript，支持 resume 和 compact |
| `QueryEngine` | 模型与工具循环 |
| `DynamicToolPool` | 汇总内置工具、MCP、技能、插件、CLI、浏览器工具 |
| `PermissionPolicy` | 工具执行前强制权限判断 |
| `TrustPolicy` | 首次目录信任、项目本地配置加载边界 |
| `ToolExecutionRunner` | 统一执行工具 |
| `ToolResultNormalizer` | 原始结果转 observation |
| `OperationResumeCoordinator` | 后台任务完成后恢复同一个 TaskRun |
| `CompletionPolicy` | 强制完成门禁 |
| `VerificationPolicy` | 开发型任务验证要求 |
| `EventStream` | 统一推送运行时事件 |

## 5. TaskRun：防遗忘的权威状态

`TaskRun` 是整轮任务的唯一权威状态。任务树、聊天消息、工作事实都是它的同步视图。

最小模型：

```json
{
  "run_id": "run_xxx",
  "project_id": "proj-d16591a6",
  "chat_session_id": "chat-session-xxx",
  "work_session_id": "ws_xxx",
  "user_id": "admin",
  "workspace_path": "/Volumes/苹果1_5T/self/ai-employee",
  "workspace_trust": {
    "trusted": true,
    "trusted_at": "",
    "source": "user"
  },
  "user_goal": "修复并验证项目问题",
  "task_type": "development",
  "status": "running",
  "phase": "executing",
  "plan": [],
  "current_step_id": "",
  "messages": [],
  "events": [],
  "tool_calls": [],
  "observations": [],
  "permission_decisions": [],
  "pending_operations": [],
  "pending_user_actions": [],
  "blockers": [],
  "verification": [],
  "completion": {
    "decision": "",
    "reason": "",
    "evidence": []
  },
  "compact_summary": "",
  "budgets": {
    "max_model_steps": 20,
    "max_tool_calls": 40,
    "max_runtime_seconds": 1800
  },
  "created_at": "",
  "updated_at": "",
  "completed_at": ""
}
```

状态机：

```text
created
-> planning
-> running
   -> waiting_user
   -> waiting_background
   -> verifying
   -> blocked
   -> failed
   -> completed
   -> cancelled
```

硬规则：

- `waiting_user` 必须存在 `pending_user_actions`。
- `waiting_background` 必须存在 `pending_operations`。
- `completed` 必须存在 `completion.evidence`。
- `failed` 必须存在最近失败 observation。
- `blocked` 必须说明缺少什么权限、输入、环境或外部动作。

## 6. QueryEngine：持续执行循环

`QueryEngine` 的目标是让任务持续推进，而不是让模型单轮回答。

接口：

```python
class QueryEngine:
    async def run(
        self,
        task_run: TaskRun,
        *,
        resume_event: TaskRunEvent | None = None,
    ) -> TaskRun:
        ...
```

循环规则：

```text
while budget remains:
    build model context from TaskRun
    call model
    collect assistant output and tool calls
    if tool calls:
        for each tool call:
            permission decision
            execute or wait/deny
            normalize observation
            append event
        decision = CompletionPolicy.evaluate()
        if decision == continue:
            continue
    else:
        decision = CompletionPolicy.evaluate()
    route decision
```

必须支持：

- 多轮工具调用。
- 工具结果后继续决策。
- 模型空输出 retry。
- 模型早停拦截。
- 权限等待。
- 后台等待。
- 预算耗尽后的明确 failed / blocked，而不是静默完成。

`AgentOrchestrator.run()` 在升级后只保留兼容入口，不再直接拥有完成判定。

## 7. TranscriptStore：可恢复事件日志

必须把 transcript 从“聊天文本”升级为事件化日志。

关键要求：

- 用户消息被接受后，必须在调用模型前写入 transcript。
- 模型输出、tool call、tool result、权限决定、后台恢复、compact 边界都写入事件。
- resume 时根据事件链重建 `TaskRun`、messages、file history、permission context、task state。
- compact 不能删除恢复所需的结构化事件。

事件类型：

```text
user_message_accepted
assistant_delta
assistant_message
tool_call_created
permission_requested
permission_decided
tool_execution_started
tool_observation
background_operation_started
background_operation_finished
task_plan_updated
verification_recorded
compact_boundary
completion_decision
run_completed
run_failed
run_blocked
```

写入顺序要求：

```text
accept user message
-> persist user_message_accepted
-> call model
```

这样进程在模型返回前被杀，也可以恢复到“用户消息已接收”的状态。

## 8. ToolObservation：工具结果一等状态

工具执行响应必须规范化为 `ToolObservation`。

```json
{
  "observation_id": "obs_xxx",
  "run_id": "run_xxx",
  "call_id": "call_xxx",
  "tool_name": "project_host_run_command",
  "tool_kind": "shell",
  "status": "succeeded",
  "stdout": "",
  "stderr": "",
  "exit_code": 0,
  "data": {},
  "artifacts": [],
  "summary": "",
  "background_operation": null,
  "user_action": null,
  "requires_model_continuation": true,
  "supports_completion_evidence": true,
  "created_at": ""
}
```

状态枚举：

```text
succeeded
failed
blocked
waiting_user
background_running
timeout
cancelled
policy_denied
```

`requires_model_continuation=true` 时，CompletionPolicy 默认不能 complete，必须让 QueryEngine 继续一轮模型决策。

## 9. CompletionPolicy：完成门禁

CompletionPolicy 是防止任务遗忘和早停的核心。

输入：

- 当前 `TaskRun`
- 最近 assistant message
- 最近 tool observation
- 当前计划状态
- pending operations
- pending user actions
- verification
- budgets

输出：

```json
{
  "decision": "continue",
  "reason": "tool observation requires model continuation",
  "next_phase": "executing",
  "evidence": []
}
```

决策枚举：

```text
continue
retry_model
request_user
wait_background
verify
complete
fail
block
cancel
```

禁止完成：

- 模型空输出。
- 模型只有“下一步你可以运行 xxx”，但工具仍可执行。
- 最近工具结果刚产生且未进入下一轮解释。
- 最近工具失败但没有诊断或阻塞说明。
- 存在 `pending_operations`。
- 存在 `pending_user_actions`。
- 开发型任务没有验证证据。
- 任务树当前节点未写入验证结果。
- 运行时没有覆盖用户原始目标。

允许完成：

- 用户目标有明确回应。
- 关键工具结果已被解释。
- 没有 pending 项。
- 验证证据存在。
- 任务树和工作事实同步成功或记录了同步失败风险。

## 10. VerificationPolicy：开发任务验证

开发型任务必须验证。

验证证据类型：

- 测试命令输出。
- 构建命令输出。
- lint / typecheck 输出。
- 运行服务和接口探测结果。
- 页面截图或浏览器验证结果。
- 人工明确确认。
- 无法验证时的阻塞原因和最小复现说明。

规则：

- 代码修改后没有任何验证，不允许 completed。
- 如果验证命令失败，必须继续修复或转为 failed / blocked。
- 如果验证无法执行，必须说明缺少什么环境或权限。
- 验证结果必须写入 `TaskRun.verification` 和任务树节点。

## 11. PermissionPolicy：Claude/Codex 同级权限模型

### 11.1 权限决策

每次工具调用前必须产生 `PermissionDecision`：

```json
{
  "decision_id": "perm_xxx",
  "run_id": "run_xxx",
  "call_id": "call_xxx",
  "tool_name": "project_host_run_command",
  "input": {},
  "behavior": "ask",
  "risk_level": "high",
  "reason": "write outside workspace",
  "matched_rule": null,
  "created_at": ""
}
```

`behavior`：

```text
allow
ask
deny
```

### 11.2 用户授权选项

用户确认弹窗必须支持：

```text
AllowOnce
AllowSession
AllowAlways
Deny
DenyWithFeedback
```

含义：

| 选项 | 生效范围 | 持久化 |
| --- | --- | --- |
| `AllowOnce` | 当前 tool call | 不持久化 |
| `AllowSession` | 当前 chat_session / run session 的匹配规则 | 写入 session permission context |
| `AllowAlways` | 当前项目或用户配置的匹配规则 | 写入持久配置 |
| `Deny` | 当前 tool call | 写入 decision event |
| `DenyWithFeedback` | 当前 tool call + 用户反馈 | 写入 decision event，并进入模型下一轮 |

### 11.3 PermissionRule

```json
{
  "rule_id": "rule_xxx",
  "scope": "session",
  "behavior": "allow",
  "tool_name": "project_host_run_command",
  "matcher": {
    "command_prefix": ["npm", "run", "build"],
    "cwd_within_workspace": true
  },
  "created_by": "admin",
  "created_at": "",
  "expires_at": ""
}
```

规则 scope：

```text
once
session
project
user
policy
```

安全限制：

- destructive 命令不得建议持久 `AllowAlways`。
- 任意脚本解释器裸前缀不得建议持久允许，例如 `python`、`python3`、`node`。
- 带 shell 重定向、变量展开、通配符、命令替换的命令不得生成宽泛 prefix rule。
- 系统路径、凭证路径、`.ssh`、`.env`、`.git` 等敏感路径必须有 bypass-immune safety check。
- deny rule 优先级高于 allow rule。

### 11.4 与现有工具衔接

现有 `classify_command_risk`、`check_workspace_scope`、`check_operation_policy` 保留，但升级为 `PermissionPolicy` 的内部步骤：

```text
PermissionPolicy.evaluate()
-> classify command risk
-> check workspace scope
-> check sandbox mode
-> check trust state
-> match permission rules
-> ask / allow / deny
```

## 12. TrustPolicy：首次目录信任

### 12.1 目标

实现类似：

```text
Do you trust the contents of this directory?
Working with untrusted contents comes with higher risk of prompt injection.
Trusting the directory allows project-local config, hooks, plugins, and exec policies to load.

1. Yes, continue
2. No, quit / continue restricted
```

### 12.2 信任边界

未信任目录时禁止：

- 加载项目本地 agent 配置。
- 加载项目本地 hooks。
- 自动安装或运行项目插件。
- 应用项目本地 exec policies。
- 执行项目本地脚本建议的自动授权。
- 读取可能触发外部命令的辅助配置。

未信任目录时允许：

- 只读查看普通文件。
- 明确用户单次授权的安全命令。
- 显示信任确认。

### 12.3 持久化

```json
{
  "workspace_path": "/Volumes/苹果1_5T/self/ai-employee",
  "git_root": "/Volumes/苹果1_5T/self/ai-employee",
  "trusted": true,
  "trusted_by": "admin",
  "trusted_at": "",
  "source": "project"
}
```

信任记录位置：

- 项目级：`.ai-employee/trust/workspaces.json`
- 用户级：用户配置目录
- 会话级：仅当前进程内存

要求：

- home 目录等过宽路径默认只允许 session trust，不建议持久 trust。
- 工作区变更后必须重新检查 trust。
- trust 状态必须进入 `TaskRun.workspace_trust`。

## 13. 后台任务恢复

后台任务必须绑定 `run_id`。

创建后台任务 metadata：

```json
{
  "operation_id": "op_xxx",
  "run_id": "run_xxx",
  "call_id": "call_xxx",
  "project_id": "proj-d16591a6",
  "chat_session_id": "chat-session-xxx",
  "work_session_id": "ws_xxx",
  "resume_strategy": "agent_runtime",
  "original_goal": "",
  "created_by": "AgentTaskRuntime"
}
```

恢复流程：

```text
operation_wait_task_service detects completion
-> OperationResumeCoordinator.load(run_id)
-> append background_operation_finished event
-> create ToolObservation
-> QueryEngine.run(task_run, resume_event=...)
-> CompletionPolicy.evaluate()
-> EventStream.push()
```

验收要求：

- 页面不断开时，后台完成后自动继续。
- 页面断开后，重新打开能看到同一个 TaskRun 的状态。
- 不再由前端调用普通聊天接口模拟恢复。
- 恢复后模型上下文包含原始目标、后台结果、当前计划。

## 14. DynamicToolPool：统一工具池

工具来源：

- 内置工具：命令、文件、浏览器、终端。
- MCP 工具：项目 MCP、统一查询 MCP、外部 MCP。
- Skill 工具：项目技能和员工技能。
- Plugin 工具：本地插件和系统插件。
- CLI 工具：作为 plugin/skill 的执行入口。

工具描述：

```json
{
  "name": "project_host_run_command",
  "display_name": "项目命令",
  "kind": "shell",
  "source": "builtin",
  "input_schema": {},
  "risk_level": "medium",
  "requires_permission": true,
  "supports_background": true,
  "requires_workspace_trust": true,
  "capabilities": ["shell", "workspace-write"]
}
```

规则：

- 未通过 trust 的项目本地工具不进入工具池。
- 当前用户无权限的工具不进入工具池。
- 当前 sandbox 不允许的工具不进入工具池。
- 高风险工具可以进入工具池，但执行前必须 ask。

## 15. EventStream：前端展示协议

统一事件：

```json
{
  "type": "agent_runtime_event",
  "run_id": "run_xxx",
  "chat_session_id": "chat-session-xxx",
  "event": "tool_observation",
  "status": "running",
  "phase": "observing",
  "payload": {},
  "created_at": ""
}
```

推荐事件：

```text
run_started
workspace_trust_required
workspace_trust_decided
plan_updated
assistant_delta
assistant_message
tool_call_started
permission_required
permission_decided
tool_observation
background_task_started
background_task_progress
background_task_finished
run_resumed
verification_started
verification_finished
completion_decision
run_completed
run_failed
run_blocked
run_cancelled
```

前端职责：

- 展示运行状态。
- 展示工具日志。
- 展示权限弹窗和 trust 弹窗。
- 提交用户审批结果。
- 提交用户补充输入。
- 订阅同一个 `run_id` 的后续事件。

前端不再负责：

- 拼恢复 prompt。
- 判断任务是否完成。
- 判断后台完成后是否继续。
- 修改执行状态机。

## 16. 与任务树和工作轨迹打通

`TaskRun` 是权威执行状态，任务树是项目视图。

同步规则：

- `TaskRun.plan` 创建后同步到项目任务树。
- `TaskRun.current_step_id` 更新后同步当前任务树节点。
- 每个步骤完成时，必须写任务树 verification。
- `TaskRun.verification` 写入工作事实。
- `TaskRun.completed` 后归档任务树。
- 如果任务树同步失败，TaskRun 不丢失，只在最终交付里标记同步风险。

工作事实写入：

```text
run_started -> start_work_session
step_completed -> append_session_event
verification_finished -> save_work_facts
run_completed -> build_delivery_report / save_project_memory
```

## 17. 持久化方案

第一阶段可以 JSON store，接口按数据库模型设计。

建议表：

```text
agent_task_runs
- run_id primary key
- project_id
- chat_session_id
- work_session_id
- user_id
- workspace_path
- user_goal
- task_type
- status
- phase
- compact_summary
- budgets_json
- workspace_trust_json
- created_at
- updated_at
- completed_at

agent_task_events
- event_id primary key
- run_id
- event_type
- phase
- status
- payload_json
- created_at

agent_tool_calls
- call_id primary key
- run_id
- tool_name
- tool_kind
- args_json
- status
- created_at
- updated_at

agent_tool_observations
- observation_id primary key
- run_id
- call_id
- tool_name
- status
- stdout
- stderr
- exit_code
- summary
- payload_json
- created_at

agent_permission_decisions
- decision_id primary key
- run_id
- call_id
- tool_name
- behavior
- risk_level
- reason
- matched_rule_json
- created_at

agent_permission_rules
- rule_id primary key
- scope
- project_id
- user_id
- chat_session_id
- behavior
- tool_name
- matcher_json
- expires_at
- created_at

agent_pending_operations
- operation_id primary key
- run_id
- call_id
- kind
- status
- metadata_json
- created_at
- updated_at
```

## 18. 实施阶段

### 阶段 0：独立目录和运行时开关

目标：

- 创建独立 `agent_runtime_v2/` 目录。
- 加 `agent_runtime_enabled` 开关。
- 保留旧 `AgentOrchestrator` 行为作为 fallback。
- 新入口创建 `TaskRun`，但可先不改变外部 API。

改动：

- `web-admin/api/services/agent_runtime_v2/`
- `web-admin/api/services/runtime/orchestrator_factory.py`
- `web-admin/api/routers/projects.py`

旧 `web-admin/api/services/agent_orchestrator.py` 不作为阶段 0 改动对象。新 runtime 通过工厂开关进入，旧工作流继续作为默认 fallback。

验收：

- 旧工作流默认路径不变。
- 开关关闭时行为不变。
- 开关开启时每条开发型消息生成 `run_id`。
- `run_started` 事件能到前端。
- 任意新 runtime 异常可以回退旧工作流。

### 阶段 1：TaskRun + TranscriptStore

目标：

- 用户消息 accepted 后先持久化。
- 工具调用和工具结果写入事件日志。
- 支持从 `run_id` 读取完整状态。

新增：

```text
task_run.py
state_store.py
event_log.py
transcript_store.py
```

验收：

- 进程在模型返回前中断，resume 能看到用户消息已接收。
- 工具执行后能查到 `ToolObservation`。
- 事件日志能重建 TaskRun 当前状态。

### 阶段 2：QueryEngine + CompletionPolicy

目标：

- 工具结果后必须继续决策。
- 空输出不完成。
- 未验证不完成。

新增：

```text
query_engine.py
llm_step.py
tool_call_collector.py
completion_policy.py
verification_policy.py
```

验收：

- 模型返回空内容时进入 retry / fail，不进入 completed。
- 模型只给下一步命令且工具可执行时，继续工具调用。
- 代码修改任务无验证时不能 completed。
- CompletionPolicy 每次决策都有 event。

当前落地状态（2026-05-27）：

- 已创建独立 `agent_runtime_v2/` 包。
- 已实现 `QueryEngine`、`LLMStep`、`ToolCallCollector`、`ToolExecutionRunner`、`CompletionPolicy`、`VerificationPolicy`。
- 仅在 `assistant_workflow.agent_runtime_mode == "query_engine"` 时进入新 QueryEngine；默认仍走旧工作流。
- 工具结果会生成 `ToolObservation` 并写入事件；空模型输出不会 completed。

### 阶段 3：PermissionPolicy + TrustPolicy

目标：

- 首次目录信任。
- 工具执行前统一权限管线。
- 支持 AllowOnce / AllowSession / AllowAlways / Deny。

新增：

```text
permission_policy.py
permission_store.py
trust_policy.py
```

前端新增：

- Trust directory dialog。
- Permission request dialog。
- Session permission rule 展示和撤销入口。

验收：

- 未信任目录时，不加载项目本地 hooks/plugin/exec policy。
- 高风险命令执行前产生 `permission_required`。
- AllowOnce 只允许当前 call。
- AllowSession 对同会话匹配命令生效。
- AllowAlways 持久化后新会话可复用。
- Deny 后工具不执行，模型收到拒绝观察。

当前落地状态（2026-05-27）：

- 已实现 `PermissionPolicy`、`PermissionStore`、`TrustPolicy`。
- `ToolExecutionRunner` 已在执行前强制调用 `PermissionPolicy.evaluate()`。
- `ask` / `deny` 不会下发到底层 `ToolExecutor`，而是生成 `blocked` ToolObservation，并写入 `permission_decision` / `tool_observation_created` 事件。
- QueryEngine 收到权限阻断后会进入 `waiting_user` 或 `blocked`，不会绕过权限继续执行。
- 已新增 `PermissionActionService` 和项目 API，可写入 `AllowOnce` / `AllowSession` / `AllowAlways` / `Deny` 规则，并记录 `permission_action_applied` 事件。
- `AllowOnce` 按 `run_id + call_id` 精确匹配；`AllowSession` / `Deny` 按同一 `chat_session_id` 和命令精确匹配；`AllowAlways` 以项目 + 用户持久规则复用。
- 已新增 workspace trust API；ProjectChat 已有最小入口可提交“信任工作区”。
- ProjectChat 已能从 `agent_runtime.observations[*].permission_decision` 生成权限操作卡，并提交“允许一次 / 本会话允许 / 始终允许 / 拒绝”。
- 已接入 `OperationResumeCoordinator`：用户保存 allow 规则后，后端会在同一个 `run_id` 上复跑原始待授权 tool call，并写入 `operation_resume_started` / `operation_resume_completed` 事件。
- `OperationResumeCoordinator` 已支持可选的 QueryEngine continuation：当调用方提供 `llm_service/tools/provider/model` 时，会把原始消息、待授权 tool call 和恢复后的 tool result 组回同一条消息链，再继续模型推理。
- `AgentTaskRuntime` 已在 `TaskRun.metadata.resume_context` 持久化恢复所需的模型、工具、工作区、本地连接器和执行参数。
- permission action API 已能从 `resume_context` 重建 `ToolExecutor` 和 LLM runtime；用户 Allow 后会优先在同一个 `TaskRun` 上自动继续 QueryEngine，缺少上下文或模型服务不可恢复时退回仅恢复工具调用。
- permission action 结果已通过项目聊天实时通道广播；同一会话的已打开页面可收到 `agent_runtime_permission_action_result` 并更新授权卡状态。
- QueryEngine continuation 内部逐事件实时推送仍是后续扩展；当前先推送最终恢复结果和 continuation 摘要。

### 阶段 4：OperationResumeCoordinator

目标：

- 后台任务完成后由后端恢复同一个 TaskRun。
- 前端不再拼恢复 prompt。

新增：

```text
operation_resume.py
```

改动：

- `operation_wait_task_service.py`
- `projects.py`
- `ProjectChat.vue`

验收：

- 后台任务完成自动继续同一个 `run_id`。
- 页面断开后恢复仍能继续。
- operation metadata 包含 `run_id/call_id/resume_strategy`。

当前落地状态（2026-05-27）：

- 已新增 `operation_resume.py`，实现 `OperationResumeCoordinator.resume_permission_action()`。
- permission action API 保存 allow 规则后会调用 coordinator，使用 run 事件中记录的原始 `tool_call` 在同一个 `TaskRun` 上恢复执行。
- 恢复过程写入 `operation_resume_started`、`tool_observation_created`、`operation_resume_completed`，如果触发 continuation，还会写入 `operation_resume_continuation_started` / `operation_resume_continuation_completed`。
- `AgentTaskRuntime` 会把初始 messages 写入 transcript；恢复器可用这些 messages 重建“assistant tool_call -> tool result -> 继续模型”的上下文，避免前端拼恢复 prompt。
- permission action API 恢复工具时会复用 `TaskRun.metadata.employee_id`，避免恢复阶段丢失员工/项目工具上下文。
- ProjectChat 已能在权限操作卡上展示“已恢复执行”；当后端返回 continuation 时，展示“已保存授权并继续运行”和续跑结果摘要。
- ProjectChat 已监听 `agent_runtime_permission_action_result`，即使授权动作来自另一个打开页面，也能更新当前权限操作卡。
- 已有测试覆盖 AllowOnce 恢复原工具调用，以及高风险命令授权后继续 QueryEngine 的消息链重建。
- 已补齐后台等待任务恢复链路：`ToolExecutionRunner` 会把 `run_id/call_id/tool_name` 注入工具参数，`ToolExecutor` 创建 `operation_wait_task` 时写入 `metadata.agent_runtime_v2`，后台任务成功后 ProjectChat websocket 后端直接调用 `AgentRuntimeResumeService.resume_background_operation()`，不再依赖前端拼恢复 prompt。
- QueryEngine 已识别 `operation_wait_task` / `cli_plugin_login_task` 的 queued / running / waiting_user_action 状态，并把同一个 `TaskRun` 暂停为 `waiting_user`，等待后台任务完成后恢复。
- 后台恢复过程会写入 `background_operation_resume_started`、`tool_observation_created`、`background_operation_continuation_started` / `completed`、`background_operation_resume_completed`，并通过 `agent_runtime_operation_resume_result` 实时事件更新已打开页面。
- 已新增 `AgentRuntimeResumeService`，permission action 和后台任务恢复共用同一套 `resume_context`、`ToolExecutor`、LLM runtime 重建逻辑。
- 已有测试覆盖后台任务 pending 后暂停、后台任务成功后恢复同一个 `TaskRun` 并继续 QueryEngine。

### 阶段 5：DynamicToolPool + 插件化工具

目标：

- MCP / Skill / Plugin / CLI / 浏览器能力统一进入工具池。
- 工具池受 trust、权限、sandbox、用户角色约束。

新增：

```text
dynamic_tool_pool.py
plugin_registry.py
```

验收：

- 未授权工具不会暴露给模型。
- 项目插件只有在 trust 后加载。
- CLI 工具作为 plugin/skill tool 执行，不再散落在 prompt 里。

当前落地状态（2026-05-27）：

- 已新增 `agent_runtime_v2/plugin_registry.py`，把 runtime tools 归一为独立 `RuntimeToolEntry`，并对 MCP / Skill / Plugin / CLI / 浏览器 / 本地连接器 / 内置工具做来源分类。
- `agent_runtime_v2/dynamic_tool_pool.py` 已改为基于 `PluginRegistry` 生成有效工具池、OpenAI tools、工具 allow-list 和审计摘要，不再直接依赖旧 `runtime.tool_registry` 的来源推断与摘要结构。
- `AgentTaskRuntime.metadata.resume_context` 已保存 `tool_pool` 摘要和规范化 `tools`，便于恢复、审计和前端展示。
- QueryEngine 模式已通过 `DynamicToolPool.names()` 生成 `ToolExecutor.allowed_tool_names`，避免恢复阶段暴露原始工具池外的工具。
- 已新增 `agent_runtime_v2/browser_tool_loader.py`，把全局浏览器 request/action 工具按 `browser-tools` 插件注入工具池；未连接浏览器 bridge 或目录未 trust 时不会暴露给模型。
- `PluginRegistry` 已读取本地技能包 `manifest.json`，在工具摘要中携带 `plugin_name`、`version`、`installed`、`available`、`load_status`、`requires_trust`、`trusted`。
- `default_plugin_registry_context()` 已读取 `.ai-employee/cli-plugin-market/install-state.json` 的安装收据，作为 CLI 插件真实安装状态的离线来源，不依赖网络查询。
- 项目本地 skill / plugin / cli / browser / local connector 工具已纳入 trust 后加载策略：未 trust 的工作区只保留无需 trust 的工具，受限工具不会进入 OpenAI tools 和 `ToolExecutor.allowed_tool_names`。
- CLI 插件安装回执已记录 `locked_version` / `lock_source`，插件市场接口已透出健康状态、依赖检查项、缺失依赖和锁定版本，市场页面可直接展示插件健康状态与版本锁定信息。
- 仍需继续增强更细粒度角色策略、依赖修复动作和运行时事件历史回放；当前阶段已完成工具池安全加载与插件健康反馈的核心闭环。

### 阶段 5.1：EventStream 实时反馈

目标：

- QueryEngine、工具执行、后台恢复、权限动作的运行时事件都能进入统一前端事件协议。
- 打开的 ProjectChat 页面能看到持续执行过程，而不是只看到最终 done。

当前落地状态（2026-05-27）：

- 已新增 `agent_runtime_v2/event_stream.py`，定义 `agent_runtime_event` 公共 payload。
- `RuntimeEventLog` 已支持内存订阅，ProjectChat websocket 已建立队列桥，把 `event_log.append()` 产生的运行时事件实时推送到当前请求。
- permission action 和后台任务恢复结果已分别通过 `agent_runtime_permission_action_result`、`agent_runtime_operation_resume_result` 广播到项目聊天实时通道。
- ProjectChat 前端已处理 `agent_runtime_event`，将 `llm_step_completed`、`tool_call_started`、`permission_decision`、`tool_observation_created`、`completion_decision` 等事件写入过程面板和运行状态卡片。
- 后续可继续补 SSE 订阅端点和跨页面历史回放；当前打开的 ProjectChat 页面已经能看到 QueryEngine 的实时执行过程。

### 阶段 6：任务树、工作事实、交付闭环

目标：

- TaskRun 与项目任务树、工作事实、记忆闭环。
- 最终交付包含证据、风险、验证。

验收：

- 每个完成节点都有 verification_result。
- `run_completed` 后任务树归档。
- `save_work_facts` 能恢复关键步骤。
- 交付报告能追溯 `run_id` 和 evidence。

### 阶段 7：灰度切流和旧工作流下线

目标：

- 新 runtime 通过端到端验证后再逐步切流。
- 旧工作流在灰度期继续保留为 fallback。
- 所有数据迁移、运行指标和回滚路径确认后，才允许删除旧链路。

切流步骤：

```text
1. 开发环境启用 agent_runtime_v2
2. 内部项目灰度启用
3. 指定用户 / 指定项目启用
4. 默认启用新 runtime，旧工作流作为 fallback
5. 保留观察期
6. 冻结旧工作流
7. 删除旧工作流和兼容适配层
```

删除旧工作流前必须满足：

- 新 runtime 覆盖旧工作流全部核心能力。
- 历史聊天、任务树、后台 operation、权限记录均可读取或迁移。
- 线上连续观察期无阻断级问题。
- 有明确回滚方案或归档备份。
- 删除清单经过人工确认。

## 19. 测试矩阵

### 19.1 防遗忘测试

场景：

```text
用户要求修复问题
-> 模型执行命令 A
-> 工具返回成功
-> 模型空输出
```

断言：

- 不出现 `run_completed`。
- CompletionPolicy 返回 `retry_model` 或 `continue`。
- TaskRun 仍保留原始目标。

### 19.2 工具后继续测试

场景：

```text
tool A succeeded
-> observation.requires_model_continuation=true
```

断言：

- QueryEngine 继续下一轮。
- 最终回答引用 tool A 结果。

### 19.3 后台恢复测试

场景：

```text
tool returns background_running
-> operation completes after page disconnect
-> user reopens page
```

断言：

- 同一个 `run_id` 恢复。
- 后端继续 QueryEngine。
- 前端没有发送 resume prompt。

### 19.4 权限测试

场景：

```text
rm -rf build/
```

断言：

- PermissionPolicy 返回 ask。
- 用户 AllowOnce 后仅当前 call 执行。
- 再次执行仍需确认。

场景：

```text
npm run build
```

断言：

- 用户 AllowSession 后同会话匹配命令自动允许。
- 新会话不自动允许，除非选择 AllowAlways。

### 19.5 Trust directory 测试

场景：

```text
首次打开未信任项目
```

断言：

- 显示 trust dialog。
- 用户拒绝时不加载项目本地 hooks/plugin/exec policy。
- 用户信任后 trust 状态写入配置。

### 19.6 验证门禁测试

场景：

```text
代码文件已修改
-> 模型直接总结完成
```

断言：

- CompletionPolicy 返回 `verify`。
- 无验证证据不得 completed。

## 20. 不再接受的修法

以下做法不能达到 Claude/Codex 同级效果：

- 靠 prompt 要求模型“不要忘记任务”。
- 在最终回复里提醒“请继续执行”。
- 前端拼恢复 prompt 再发一次普通聊天。
- 在 `AgentOrchestrator.run()` 里继续堆 if/else 特判。
- 工具结果只写入 messages，不写 observation。
- 权限只做风险提示，不作为执行前强制 gate。
- 只做任务树 UI，不建立 TaskRun 权威状态。

## 21. 总体验收标准

v3 完成后必须满足：

- 任意开发型任务都有 `run_id`。
- 新 runtime 位于独立目录，旧工作流在切流完成前保持可用。
- 新旧入口有 feature flag 或灰度开关，可以快速回退。
- 用户消息 accepted 后先持久化再调用模型。
- 工具调用、工具结果、权限决定、后台恢复都有结构化事件。
- 工具结果后 QueryEngine 必须继续或由 CompletionPolicy 明确拦截。
- 空输出不会导致 completed。
- 后台任务完成后恢复同一个 TaskRun。
- 首次项目目录有 trust boundary。
- 工具执行前有 PermissionPolicy gate。
- 支持 AllowOnce / AllowSession / AllowAlways / Deny。
- 开发型任务无验证不得 completed。
- 最终交付能追溯工具证据、验证证据、任务树节点和工作事实。

## 22. 优先级

第一优先级，决定是否真的防遗忘：

```text
TaskRun
TranscriptStore
QueryEngine
ToolObservation
CompletionPolicy
```

第二优先级，决定是否像 Claude/Codex 一样安全可控：

```text
TrustPolicy
PermissionPolicy
PermissionStore
AllowOnce / AllowSession / AllowAlways
```

第三优先级，决定长任务是否稳定：

```text
OperationResumeCoordinator
MemoryCompaction
TaskTree sync
WorkSession sync
```

第四优先级，决定扩展能力：

```text
DynamicToolPool
PluginRegistry
Skill/MCP/CLI adapters
Frontend runtime inspector
```

第五优先级，决定能否安全替换旧工作流：

```text
Feature flag rollout
Compatibility adapter
Fallback to old workflow
Migration / archive scripts
Old workflow deletion checklist
```

## 23. 最终原则

要达到 Claude/Codex 同级效果，关键不是“模型更聪明”，而是：

```text
运行时拥有任务状态；
权限系统拥有执行开关；
完成策略拥有最终裁决；
前端只展示和提交用户动作；
模型不能绕过 TaskRun、PermissionPolicy 和 CompletionPolicy。
```
