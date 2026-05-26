# AI 智能体开发工作流重构方案 v2

> 版本：v2
> 日期：2026-05-26
> 目标：把当前 AI 对话从“聊天循环 + 工具调用”升级为“可持续执行、可恢复、可验证的 Agent Runtime”。

## 1. 结论

当前 AI 对话已经具备模型对话、工具调用、项目宿主命令执行、后台 operation task、前端 Live Execution 展示等基础能力，但整体仍是“模型聊天循环”而不是“任务执行运行时”。

这会导致典型问题：

- 工具已经执行完成，但模型没有继续推进。
- 后台任务完成后，恢复依赖前端拼 prompt 重新发起请求。
- 工具结果只作为 message 追加，没有成为可审计的运行状态。
- 模型空输出、短输出或没有 tool call 时，任务容易被错误结束。

重构的核心不是增加兜底文案，而是新增一层后端 `AgentTaskRuntime`：

```text
用户目标
-> 创建 TaskRun
-> 规划 / 决策
-> 解析工具调用
-> 权限判断
-> 执行工具
-> 结构化记录 Observation
-> 再次决策
-> 后台任务恢复
-> 验证完成
-> 交付总结
```

最终目标是让 AI 对话具备 Codex / Claude Code 类开发型智能体工作流：能执行命令、读取结果、继续推进、恢复长任务，并且以证据判断完成。

## 2. 当前现状

关键实现位置：

- `web-admin/api/services/agent_orchestrator.py`
- `web-admin/api/services/tool_executor.py`
- `web-admin/api/services/operation_wait_task_service.py`
- `web-admin/api/routers/projects.py`
- `web-admin/frontend/src/views/projects/ProjectChat.vue`

当前链路：

```text
前端发送用户消息
-> AgentOrchestrator.run()
-> 调用模型流式接口
-> 收集 tool_calls
-> ToolExecutor 执行工具
-> project_host_run_command 执行命令或创建后台任务
-> 工具结果 append 到 OpenAI 风格 tool message
-> 再次请求模型
-> 没有 tool call 时 done
```

这套结构能处理简单问答和单轮工具调用，但不适合开发型任务。开发型任务需要的是持续任务循环，而不是“模型自然决定是否继续”。

## 3. 当前核心问题

### 3.1 编排器职责过重

`AgentOrchestrator.run()` 同时承担：

- LLM 流式输出解析
- tool call 聚合
- 工具执行
- `project_host_run_command` 特判
- Lark / 飞书工作流自动补跑
- 后台 operation task 等待
- 用户授权等待
- 前端事件转换
- 完成判定
- 对话历史写入
- 任务树审计

结果是任何一种状态分支都可能影响最终完成语义，也很难为“后台恢复”“空输出不完成”“命令结果继续推理”建立统一规则。

### 3.2 后台任务与主执行上下文割裂

当前后台任务恢复链路里，前端承担了续跑职责：

```text
后端发出 background_task_pending
-> 前端监听 operation task 完成
-> 前端构造 buildOperationResumeUserPrompt()
-> 前端再次调用 sendProjectChatRequest()
```

这意味着“继续执行”不是后端运行时能力，而是 UI 层补出来的。页面断开、会话切换、消息匹配失败时，任务就不能稳定恢复。

### 3.3 工具结果不是一等状态

工具结果目前主要进入 `messages`，缺少结构化运行记录：

- 执行过哪些工具
- 参数是什么
- stdout / stderr / exit_code 是什么
- 是否产生后台任务
- 是否需要用户授权
- 最近一次工具结果是否支持完成结论
- 是否已经验证

因此模型是否继续推进，过度依赖下一轮自然语言输出。

### 3.4 完成判定过弱

当前“模型没有新 tool call”容易被当成完成。开发型智能体必须区分：

- `done`：目标已达成，并有证据。
- `blocked`：无法继续，并有阻塞证据。
- `waiting_user`：需要用户授权或补充输入。
- `failed`：运行时或工具失败，且无法自动恢复。
- `continue`：刚获得工具结果，还应继续决策。

不能因为模型返回空内容、短句、没有 tool call，就结束任务。

## 4. 目标架构

新增后端运行时目录：

```text
web-admin/api/services/agent_runtime/
  __init__.py
  runtime.py
  task_run.py
  state_store.py
  query_engine.py
  llm_step.py
  tool_call_collector.py
  tool_execution_runner.py
  tool_result_normalizer.py
  tool_pool.py
  permission_policy.py
  operation_resume.py
  memory_compaction.py
  event_stream.py
  completion_policy.py
  errors.py
```

高层调用关系：

```text
ProjectChat API / WebSocket
-> AgentTaskRuntime.start_or_resume()
   -> TaskRunStore.load_or_create()
   -> DynamicToolPool.resolve()
   -> QueryEngine.loop()
      -> LLMStep.call_model()
      -> ToolCallCollector.collect()
      -> PermissionPolicy.check()
      -> ToolExecutionRunner.execute()
      -> ToolResultNormalizer.normalize()
      -> TaskRunStore.append_event()
      -> CompletionPolicy.evaluate()
   -> EventStream.emit()
```

核心边界：

- `AgentTaskRuntime` 负责任务生命周期。
- `QueryEngine` 负责模型和工具的循环。
- `ToolExecutor` 继续保留为底层工具适配器。
- `operation_wait_task_service` 只负责后台任务监控，不再驱动 prompt 续跑。
- `ProjectChat.vue` 只展示运行状态，不再决定是否自动继续。

## 5. Claude / Codex 类 12 个模块

### 5.1 QueryEngine / Execution Loop

职责：

- 驱动模型推理、工具调用、观察结果、再次推理的循环。
- 控制最大轮次、最大工具调用数、超时和取消。
- 保证工具执行结果一定进入下一轮决策或完成策略。

输入：

- `TaskRun`
- 当前消息上下文
- 可用工具池
- 运行预算

输出：

- `TaskRunEvent`
- `AssistantDelta`
- `CompletionDecision`

建议接口：

```python
class QueryEngine:
    async def run(self, task_run: TaskRun, *, resume_event: TaskRunEvent | None = None) -> TaskRun:
        ...
```

### 5.2 Session / Transcript State

职责：

- 保存完整会话轨迹，不只保存聊天文本。
- 记录模型输入、模型输出、tool call、tool result、状态切换、恢复点。
- 支撑审计、恢复、compact 和问题复盘。

最小内容：

- `messages`
- `events`
- `tool_calls`
- `tool_results`
- `pending_operations`
- `checkpoints`
- `compact_summary`

### 5.3 Planner / Task State

职责：

- 将用户目标转成可执行阶段。
- 维护当前 `phase`、计划步骤、完成项、阻塞点、验证项。
- 与项目任务树对齐，但不把任务树当作唯一运行状态。

推荐阶段：

```text
created
-> planning
-> executing
-> waiting_user
-> waiting_background
-> verifying
-> summarizing
-> completed
```

### 5.4 Dynamic Tool Pool

职责：

- 根据项目、员工、技能、MCP、权限、宿主环境动态决定可用工具。
- 把 CLI、脚本、HTTP API、MCP tool、浏览器工具统一成 runtime tool 描述。
- 在暴露给模型前过滤不可用或不允许的工具。

工具来源：

- 内置工具，例如 `project_host_run_command`
- 项目技能工具
- MCP 工具
- CLI 插件
- 浏览器工具
- 文件读写工具

输出结构：

```json
{
  "name": "project_host_run_command",
  "kind": "shell",
  "description": "Run a command in project host",
  "input_schema": {},
  "risk_level": "medium",
  "requires_approval": false,
  "capabilities": ["shell", "project-workspace"],
  "source": "builtin"
}
```

### 5.5 Permission / Policy Engine

职责：

- 在工具暴露前和调用前进行风险判断。
- 处理文件写入、shell、网络、删除、部署、凭证等敏感操作。
- 给出允许、需确认、拒绝和原因。

建议决策：

```text
allow
confirm
deny
defer
```

输入：

- `TaskRun`
- `ToolDescriptor`
- `ToolCall`
- 项目 workspace
- 用户权限

输出：

```json
{
  "decision": "confirm",
  "risk_level": "high",
  "reason": "Command may modify files outside project workspace",
  "required_user_action": "approve_tool_call"
}
```

### 5.6 Tool Executor / Adapter Layer

职责：

- 执行具体工具。
- 保持对现有 `ToolExecutor` 的兼容。
- 将 shell、MCP、CLI、插件、HTTP API、浏览器动作适配到统一调用入口。

建议接口：

```python
class ToolExecutionRunner:
    async def execute(self, task_run: TaskRun, tool_call: RuntimeToolCall) -> RawToolResult:
        ...
```

适配器类型：

- `ShellCommandAdapter`
- `McpToolAdapter`
- `SkillToolAdapter`
- `CliPluginAdapter`
- `BrowserToolAdapter`
- `HttpApiAdapter`

### 5.7 Observation / Tool Result Normalizer

职责：

- 把不同工具的原始结果转成统一 Observation。
- 提取 stdout、stderr、exit_code、错误、后台任务 ID、授权链接、摘要。
- 标记结果是否可恢复、是否需要继续、是否构成阻塞。

统一状态：

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

### 5.8 Resume / Background Job Coordinator

职责：

- 后台 operation task 完成后恢复同一个 `TaskRun`。
- 将后台结果作为 Observation 注入运行时。
- 不依赖前端重新发起普通聊天请求。

目标流程：

```text
operation task completed
-> operation metadata 找到 run_id
-> AgentTaskRuntime.resume(run_id, operation_result)
-> TaskRun append background_result event
-> QueryEngine 继续
-> EventStream 推送后续事件
```

### 5.9 Memory / Context / Compaction

职责：

- 控制长任务上下文。
- 将历史工具结果、关键决策、已完成步骤压缩成 checkpoint。
- 将稳定结论写入项目记忆或工作事实。

最小策略：

- 最近 N 轮保留完整消息。
- 较早工具结果压缩成 `compact_summary`。
- 重要事件保留结构化索引。
- 任务完成后写入工作事实和任务树验证结果。

### 5.10 MCP / Plugin / Skills Extension Layer

职责：

- 将 MCP、插件、技能、CLI 能力统一抽象成 runtime tool / resource / command。
- 插件不是 CLI 本身；CLI 只是插件的一种执行入口。

关系：

```text
AI Runtime
-> Plugin / Skill / MCP Tool
   -> CLI command
   -> Python script
   -> HTTP API
   -> MCP server
   -> Browser automation
```

插件 manifest 最小字段：

```json
{
  "id": "jx-crmcli",
  "name": "JX CRM CLI",
  "version": "1.0.0",
  "tools": [
    {
      "name": "crm.auth.login",
      "entry": "jx crmcli auth login",
      "kind": "cli",
      "risk_level": "medium"
    }
  ],
  "permissions": ["shell", "network"],
  "resources": [],
  "prompts": []
}
```

### 5.11 Event Stream / UI Bridge

职责：

- 将运行时事件推给前端。
- 前端只展示状态、日志、等待动作和最终结果。
- 前端不再构造恢复 prompt，不再决定任务是否继续。

前端职责：

- 展示 `TaskRun.status`
- 展示工具执行日志
- 展示授权 / 确认请求
- 发送用户补充输入或审批结果
- 订阅后台继续事件

### 5.12 Completion / Verification Policy

职责：

- 统一判断是否完成、继续、等待、阻塞、失败。
- 防止模型空输出或早停导致任务静默结束。
- 对开发任务要求验证证据。

决策：

```text
continue
retry_model
request_user
wait_background
verify
complete
fail
block
```

禁止完成场景：

- 模型空输出。
- 工具刚执行完但没有解释结果。
- 模型只给下一步命令，而该命令可以由工具执行。
- 最近工具失败但没有诊断。
- 开发型任务没有验证证据。

## 6. 核心数据模型

### 6.1 TaskRun

```json
{
  "run_id": "run_xxx",
  "project_id": "proj-d16591a6",
  "chat_session_id": "chat-session-xxx",
  "conversation_id": "optional",
  "user_id": "admin",
  "user_goal": "安装这个 jx crmcli",
  "task_type": "development",
  "status": "running",
  "phase": "executing",
  "model": "gpt-...",
  "messages": [],
  "events": [],
  "plan": [],
  "current_step_id": "",
  "tool_calls": [],
  "tool_results": [],
  "pending_operations": [],
  "pending_user_actions": [],
  "blockers": [],
  "verification": [],
  "compact_summary": "",
  "budgets": {
    "max_model_steps": 20,
    "max_tool_calls": 30,
    "max_runtime_seconds": 1800
  },
  "created_at": "",
  "updated_at": "",
  "completed_at": ""
}
```

### 6.2 RuntimeToolCall

```json
{
  "call_id": "call_xxx",
  "step_id": "step_xxx",
  "tool_name": "project_host_run_command",
  "tool_kind": "shell",
  "source": "model",
  "args": {
    "command": "curl -L http://cloud.jxycrm.com/tools/manifest.json",
    "cwd": "/Volumes/苹果1_5T/self/ai-employee"
  },
  "risk": {
    "level": "medium",
    "requires_approval": false
  },
  "created_at": ""
}
```

### 6.3 ToolObservation

```json
{
  "event_type": "tool_observation",
  "observation_id": "obs_xxx",
  "run_id": "run_xxx",
  "call_id": "call_xxx",
  "tool_name": "project_host_run_command",
  "status": "succeeded",
  "stdout": "",
  "stderr": "",
  "exit_code": 0,
  "error": "",
  "summary": "",
  "artifacts": [],
  "operation": {
    "operation_id": "",
    "status": "",
    "resume_token": ""
  },
  "requires_model_continuation": true,
  "requires_user_action": false,
  "created_at": ""
}
```

### 6.4 PendingOperation

```json
{
  "operation_id": "op_xxx",
  "run_id": "run_xxx",
  "call_id": "call_xxx",
  "kind": "host_command",
  "status": "running",
  "resume_strategy": "runtime",
  "metadata": {
    "project_id": "proj-d16591a6",
    "chat_session_id": "chat-session-xxx",
    "original_goal": "安装这个 jx crmcli"
  },
  "created_at": "",
  "updated_at": ""
}
```

## 7. TaskRun 状态机

状态定义：

```text
created
running
waiting_user
waiting_background
verifying
completed
failed
blocked
cancelled
```

阶段定义：

```text
intake
planning
executing
observing
resuming
verifying
summarizing
done
```

状态流：

```text
created
-> running
   -> waiting_user
   -> waiting_background
   -> verifying
   -> failed
   -> blocked
   -> completed
   -> cancelled
```

关键规则：

- `waiting_background` 必须有 `pending_operations`。
- `waiting_user` 必须有 `pending_user_actions`。
- `completed` 必须有最终 assistant message 和验证证据。
- `failed` 必须有错误来源和最近观察结果。
- `blocked` 必须说明缺少什么输入、权限或环境。

## 8. Event Stream 协议

运行时向前端推送统一事件：

```json
{
  "type": "agent_runtime_event",
  "run_id": "run_xxx",
  "chat_session_id": "chat-session-xxx",
  "event": "tool_result",
  "status": "running",
  "phase": "observing",
  "payload": {},
  "created_at": ""
}
```

推荐事件类型：

```text
run_started
plan_updated
assistant_delta
assistant_message
tool_call_started
tool_call_output
tool_call_finished
tool_observation
policy_check
user_action_required
background_task_started
background_task_progress
background_task_finished
run_resumed
verification_started
verification_finished
run_completed
run_failed
run_blocked
run_cancelled
```

前端兼容策略：

- 旧事件仍可暂时保留。
- 新事件统一挂在 `agent_runtime_event` 下。
- Live Execution 从事件流读取，不再基于前端构造的 resume prompt 判断。

## 9. 后台恢复协议

### 9.1 创建后台任务时写入 metadata

`project_host_run_command` 若创建 operation task，必须写入：

```json
{
  "run_id": "run_xxx",
  "call_id": "call_xxx",
  "project_id": "proj-d16591a6",
  "chat_session_id": "chat-session-xxx",
  "resume_strategy": "agent_runtime",
  "original_goal": "",
  "created_by": "AgentTaskRuntime"
}
```

### 9.2 后台任务完成后恢复

```text
operation_wait_task_service detects completed
-> publish operation_completed event
-> OperationResumeCoordinator loads TaskRun
-> append background observation
-> QueryEngine.run(task_run, resume_event=...)
-> stream follow-up events
```

### 9.3 前端变化

删除或降级这些职责：

- 不再用 `buildOperationResumeUserPrompt()` 作为主恢复机制。
- 不再由前端调用 `sendProjectChatRequest()` 触发自动续跑。
- 前端只发送用户显式补充、授权确认或取消。

## 10. 工具协议

### 10.1 工具描述

```json
{
  "name": "crm.auth.login",
  "display_name": "CRM 登录",
  "kind": "cli",
  "source": "plugin",
  "description": "Login to CRM CLI",
  "input_schema": {},
  "output_schema": {},
  "risk_level": "medium",
  "requires_approval": false,
  "supports_background": true,
  "workspace_required": true
}
```

### 10.2 工具执行请求

```json
{
  "run_id": "run_xxx",
  "call_id": "call_xxx",
  "tool_name": "crm.auth.login",
  "args": {},
  "policy_context": {
    "project_id": "proj-d16591a6",
    "workspace_path": "/Volumes/苹果1_5T/self/ai-employee"
  }
}
```

### 10.3 工具执行响应

```json
{
  "ok": true,
  "status": "succeeded",
  "stdout": "",
  "stderr": "",
  "exit_code": 0,
  "data": {},
  "artifacts": [],
  "background_task": null,
  "user_action": null,
  "error": ""
}
```

## 11. 当前代码迁移映射

| 当前模块 | 当前职责 | v2 后职责 |
| --- | --- | --- |
| `agent_orchestrator.py` | 聊天、工具、恢复、完成判定混合编排 | 保留兼容入口，委托 `AgentTaskRuntime` |
| `tool_executor.py` | 执行工具并返回结果 | 作为 adapter 底座，被 `ToolExecutionRunner` 调用 |
| `operation_wait_task_service.py` | 后台任务等待与状态更新 | 增加 runtime resume hook，不负责拼 prompt |
| `projects.py` | 项目聊天 API / WebSocket | 创建或恢复 `TaskRun`，转发 runtime events |
| `ProjectChat.vue` | 展示 + 自动续跑控制 | 状态视图，只展示和提交用户动作 |
| 任务树 MCP | 项目级规划和审计 | 与 `TaskRun.plan/current_step/verification` 同步 |

## 12. 持久化设计

优先使用数据库持久化；第一阶段可用 JSON 字段降低迁移成本。

建议表：

```text
agent_task_runs
- run_id primary key
- project_id
- chat_session_id
- user_id
- user_goal
- task_type
- status
- phase
- compact_summary
- budgets_json
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
- policy_json
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

第一阶段如不建表，可先落在现有会话 / operation metadata 的 JSON 字段，但接口形态要按上述模型设计，避免后续再改协议。

## 13. CompletionPolicy 详细规则

输入：

- `TaskRun`
- 最近模型输出
- 最近工具观察
- 当前计划状态
- 验证结果
- 运行预算

输出：

```json
{
  "decision": "continue",
  "reason": "Tool result was produced and requires model continuation",
  "next_phase": "executing"
}
```

完成必须满足：

- 用户目标已经被明确回应。
- 最近工具结果不与完成结论冲突。
- 开发型任务存在验证证据。
- 没有未处理的 `pending_operations`。
- 没有未处理的 `pending_user_actions`。

继续条件：

- 刚产生工具结果，且 `requires_model_continuation=true`。
- 模型输出下一步命令，而该命令可以通过工具执行。
- 模型空输出但最近状态不是最终态。
- 工具失败后仍存在可执行诊断路径。

暂停条件：

- 需要用户授权。
- 需要用户确认高风险操作。
- 需要验证码、登录、外部人工动作。

失败条件：

- 工具反复失败并达到重试上限。
- 模型连续空输出达到上限。
- 运行预算耗尽且无法生成有效总结。

## 14. 阶段实施计划

### 阶段一：拆出运行时骨架，不改变外部行为

目标：

- 降低 `AgentOrchestrator` 耦合。
- 建立新模块边界。
- 保持现有 API 和前端行为基本不变。

新增文件：

```text
web-admin/api/services/agent_runtime/
  __init__.py
  task_run.py
  tool_call_collector.py
  tool_execution_runner.py
  tool_result_normalizer.py
  completion_policy.py
```

改动文件：

- `web-admin/api/services/agent_orchestrator.py`
- `web-admin/api/services/tool_executor.py`
- `web-admin/api/tests/test_agent_orchestrator_runtime.py`

验收：

- 现有 `test_agent_orchestrator_runtime.py` 通过。
- `project_host_run_command` 特判集中到策略 / runner。
- 空模型输出不被直接当成完成。

### 阶段二：引入 TaskRun 和结构化事件

目标：

- 每个任务都有 `run_id`。
- 工具结果写入 `TaskRun.tool_results/events`。
- 前端收到统一 runtime event。

新增文件：

```text
web-admin/api/services/agent_runtime/state_store.py
web-admin/api/services/agent_runtime/event_stream.py
web-admin/api/services/agent_runtime/query_engine.py
```

验收：

- 命令执行完成后，TaskRun 有 tool observation。
- done 事件包含验证摘要。
- 模型空输出会进入 retry / diagnostic，而不是静默结束。

### 阶段三：后端接管后台任务恢复

目标：

- operation task 绑定 `run_id`。
- 后台完成后由后端恢复同一个 TaskRun。
- 前端不再拼恢复 prompt。

改动文件：

- `web-admin/api/services/operation_wait_task_service.py`
- `web-admin/api/routers/projects.py`
- `web-admin/frontend/src/views/projects/ProjectChat.vue`

验收：

- 页面不断开时，后台任务完成后自动继续。
- 页面断开后再打开，能看到 TaskRun 状态并继续。
- 前端不再调用普通聊天接口模拟恢复。

### 阶段四：动态工具池、权限和插件层

目标：

- 统一 MCP / Skill / Plugin / CLI 工具描述。
- 工具暴露前做权限过滤。
- 高风险动作进入用户确认。

新增文件：

```text
web-admin/api/services/agent_runtime/tool_pool.py
web-admin/api/services/agent_runtime/permission_policy.py
web-admin/api/services/agent_runtime/plugin_registry.py
```

验收：

- CLI 插件能作为 tool 暴露。
- 不可用工具不会进入模型工具列表。
- 高风险命令需要确认。

### 阶段五：开发型智能体协议和项目任务树打通

目标：

- 支持计划、执行、验证、交付四段式任务。
- 与项目任务树、工作事实、记忆闭环。

验收：

- 用户提出“安装 / 修复 / 执行 / 部署”时，AI 能主动执行可用工具。
- 每次工具结果后继续判断下一步。
- 交付输出包含改动、验证、风险。

## 15. 测试计划

### 15.1 单元测试

- `ToolCallCollector` 能解析流式 tool call。
- `ToolResultNormalizer` 能统一 shell / MCP / background 结果。
- `CompletionPolicy` 能识别空输出、工具后继续、验证完成。
- `PermissionPolicy` 能区分 allow / confirm / deny。

### 15.2 集成测试

场景一：连续命令执行。

```text
模型调用 command A
-> 工具成功
-> 模型基于结果调用 command B
-> 工具成功
-> 模型总结
```

断言：

- 至少两个 tool observations。
- 最终 `run_completed` 有正文。
- 正文引用关键工具结果。

场景二：空模型输出不完成。

```text
工具成功
-> 下一轮模型返回空
```

断言：

- 不直接 `completed`。
- `CompletionPolicy` 给出 `retry_model` 或 `fail`。
- 事件里有诊断原因。

场景三：后台任务恢复。

```text
工具返回 background_running
-> operation task succeeded
-> runtime resume
-> 模型继续总结或执行下一步
```

断言：

- 恢复同一个 `run_id`。
- 前端不发送普通 resume prompt。
- 最终结果基于原始目标。

场景四：用户授权等待。

```text
工具返回 waiting_user
-> 用户确认 / 授权
-> runtime resume
```

断言：

- 状态为 `waiting_user`。
- 用户动作后恢复同一 TaskRun。
- 不重复创建新任务。

### 15.3 端到端测试

- 在项目聊天里触发 CLI 安装类任务。
- Live Execution 展示工具执行过程。
- 后台任务完成后自动继续。
- 最终消息包含验证结果和剩余风险。

## 16. 不建议的修法

以下做法不能解决根因：

- 给空内容加一段兜底文案。
- 靠 prompt 要求模型“不要停”。
- 前端监听后台完成后拼自然语言 prompt 再发一次。
- 在 `AgentOrchestrator.run()` 里继续堆更多特判。
- 只把 CLI 安装成插件，却没有 TaskRun 和恢复机制。

这些方式只能缓解单点，不会让 AI 对话成为稳定的任务执行型智能体。

## 17. 验收标准

v2 重构完成后，必须满足：

- AI 对话执行命令后，会读取结果并继续判断下一步。
- 工具结果有结构化 Observation，可审计。
- 后台 operation task 完成后，后端恢复同一个 TaskRun。
- 前端只展示状态，不负责构造恢复 prompt。
- 模型空输出不会导致任务静默完成。
- 开发型任务完成必须有验证证据。
- MCP / Skill / Plugin / CLI 能力统一进入动态工具池。
- 高风险工具调用经过权限策略判断。
- 任务结束时能写入项目任务树验证结果和工作事实。

## 18. 推荐优先级

第一优先级：

```text
TaskRun
QueryEngine
ToolResultNormalizer
CompletionPolicy
OperationResumeCoordinator
```

第二优先级：

```text
DynamicToolPool
PermissionPolicy
EventStream
StateStore
```

第三优先级：

```text
PluginRegistry
MemoryCompaction
项目任务树深度联动
前端 Live Execution 体验优化
```

原因：

- 当前最痛的问题是“执行后不会稳定继续”和“后台任务恢复断裂”。
- 这两个问题必须由运行时状态机解决。
- 插件和 CLI 接入只是能力来源，不是任务连续性的根因。

## 19. 一句话原则

AI 对话要像 Codex 一样执行任务，关键不是让模型“更愿意继续”，而是让后端 runtime 拥有任务状态、工具观察、恢复机制和完成策略。
