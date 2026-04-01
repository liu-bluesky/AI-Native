# 统一查询 MCP 升级前后对比

> 日期：2026-04-01  
> 范围：`/mcp/query/sse` 与 `/mcp/query/mcp`

## 1. 一句话区别

- 升级前：统一查询入口，重点是“查什么、读什么、怎么发起协作”。
- 升级后：统一智能体能力入口，重点是“先理解任务，再聚合上下文，再判断策略，再沉淀工作状态”。

## 2. 接入方式是否变化

- 没变：
  - SSE：`/mcp/query/sse?key=...`
  - HTTP：`/mcp/query/mcp?key=...`
- 结论：
  - 客户端接入方式保持兼容。
  - 这次升级没有推翻原入口，只是在同一路径上补能力。

## 3. 能力对比

### 3.1 升级前

- 基础查询：
  - `search_ids`
  - `get_content`
  - `get_manual_content`
- 项目执行代理：
  - `save_project_memory`
  - `list_project_members`
  - `get_project_runtime_context`
  - `list_project_proxy_tools`
  - `invoke_project_skill_tool`
  - `execute_project_collaboration`
- 资源：
  - `query://usage-guide`

特点：

- 偏查询与聚合。
- 能回答“有哪些项目/员工/规则”。
- 能读取项目或员工手册。
- 能从统一入口代理项目协作。
- 还不能很好回答“这件事下一步该怎么做”。

### 3.2 升级后

在保留原能力的基础上，新增 4 组能力。

#### A. 任务理解与上下文编排

- `analyze_task`
- `resolve_relevant_context`
- `generate_execution_plan`

作用：

- 先结构化理解用户任务。
- 自动聚合相关成员、规则、工具。
- 输出执行步骤骨架，而不是只返回查询结果。

#### B. 风险与策略判断

- `classify_command_risk`
- `check_workspace_scope`
- `resolve_execution_mode`
- `check_operation_policy`

作用：

- 判断命令和路径风险。
- 判断应走 local connector 还是项目工具。
- 在执行前给出允许、拦截或需确认的结论。

#### C. 工作记忆与恢复

- `save_work_facts`
- `append_session_event`
- `resume_work_session`
- `summarize_checkpoint`

作用：

- 从“记住对话”升级为“记住工作轨迹”。
- 支持长任务恢复、阶段检查点、会话续跑。
- 轨迹会双写到项目记忆和独立 `work_session_store`。
- 后台可通过 `GET /api/work-sessions`、`GET /api/work-sessions/{session_id}` 和 `/work-sessions` 页面查看。

#### D. 客户端画像与交付输出

- `query://client-profile/claude-code`
- `query://client-profile/codex`
- `query://client-profile/generic-cli`
- `build_delivery_report`
- `generate_release_note_entry`

作用：

- 给不同 CLI 提供接入建议。
- 让统一入口能直接产出交付报告和更新日志条目。

## 4. 使用链路对比

### 升级前推荐链路

```text
search_ids
-> get_manual_content
-> execute_project_collaboration
```

### 升级后推荐链路

```text
query://usage-guide
-> analyze_task
-> search_ids
-> get_manual_content
-> resolve_relevant_context
-> generate_execution_plan
-> execute_project_collaboration / 手动编排
-> save_project_memory / save_work_facts
```

区别：

- 升级前更像查询跳板。
- 升级后更像外部 CLI 的能力增强层。

## 5. 服务端是否需要新增大模型

- 当前这次升级：不需要。
- 当前实现主要基于：
  - 项目运行时数据
  - 规则与手册
  - 已有 store
  - 确定性逻辑
  - 统一入口编排

结论：

- 现在的 MCP 服务层本身不要求新增服务端 LLM。
- 但要产生完整“智能体效果”，仍然需要外部模型或 CLI 来消费这些工具和资源。

## 6. 验证层面对比

### 升级前

- 主要是能力实现存在。
- 对真实挂载入口的验证不完整。

### 升级后

已补齐：

- `tools/call`
- `tools/list`
- `resources/list`
- `resources/read`
- 真实 `/mcp/query/mcp`
- 真实 `POST /mcp/query/sse`
- 标准项目链路
- 项目协作链路
- 记忆链路

已确认：

- `POST /mcp/query/mcp` 和 `POST /mcp/query/sse` 需要 `Accept: application/json, text/event-stream`
- SSE bridge 可以直接承载同一套 JSON-RPC body

## 7. 页面与字段层面对比

### 升级前

- 统一查询 MCP 的工作记忆主要停留在项目记忆文本层。
- 后台没有独立的工作轨迹查看入口。
- `Phase / Step / changed_files / verification / risks / next_steps` 这类字段没有稳定查看面板。

### 升级后

- `save_work_facts`、`append_session_event` 可附带：
  - `session_id`
  - `phase`
  - `step`
  - `status`
  - `goal`
  - `changed_files`
  - `verification`
  - `risks`
  - `next_steps`
- `resume_work_session`、`summarize_checkpoint` 会优先读取独立 `work_session_store`，不足时再回退项目记忆。
- 后台设置中心已新增“工作轨迹”菜单，页面路由为 `/work-sessions`。
- 页面当前可直接查看：
  - `session_id`
  - `phase`
  - `step`
  - `status`
  - `goal`
  - `changed_files`
  - `verification`
  - `risks`
  - `next_steps`
  - `timeline`

## 8. 当前版本的实际定位

当前版本不是：

- 新 CLI
- 新终端壳
- 新模型服务

当前版本是：

- 面向外部 CLI/Agent 的 MCP 能力层
- 稳定入口仍是 `/mcp/query/sse`
- 重点增强任务理解、策略判断、工作记忆和交付输出

## 9. 后续如果继续升级

优先级建议：

- 做仓外真实 API Key 联调
- 验证外部 CLI 是否按 `query://usage-guide -> search_ids -> get_manual_content` 顺序消费
- 独立 `work_session_store` 如需继续演进，可再升级为完整 transcript event store
- 观察是否真的需要把部分能力升级为服务端 LLM 推理

## 10. 一句话总结

升级前是“统一查询 MCP”，升级后是“统一智能体能力 MCP”。
