# 统一查询 MCP 升级规划

> 日期：2026-04-01
> 状态：规划中
> 起点入口：`/mcp/query/sse`

## 1. 背景

当前系统已经具备统一查询 MCP 入口：

- SSE：`/mcp/query/sse?key=...`
- HTTP：`/mcp/query/mcp?key=...`

现状不是“没有 MCP”，而是 MCP 已经能工作，但当前定位仍偏向：

- 查询入口
- 聚合入口
- 项目协作代理入口

这套能力适合“找到项目、读取手册、发起协作”，但还没有进一步演进成“给 Claude / Codex / Gemini 这类 CLI 持续增强能力的智能体服务层”。

这次升级的目标不是做另一个 Claude Code / Codex CLI，而是把现有统一查询 MCP 继续往上抬一层，做成：

- 现有 CLI 的智能体能力增强层
- 面向项目上下文的 Agent Capability Gateway
- 模型的项目级操作系统，而不是另一个终端壳

## 2. 现有基线

当前 `/mcp/query/sse` 已经有明确实现基础：

- 挂载入口：`web-admin/api/core/server.py`
- 运行时装配：`web-admin/api/services/dynamic_mcp_runtime.py`
- 代理应用：`web-admin/api/services/dynamic_mcp_proxy_apps.py`
- 统一查询工具与 `query://usage-guide`：`web-admin/api/services/dynamic_mcp_apps_query.py`
- 前端接入说明弹窗：`web-admin/frontend/src/components/UnifiedMcpAccessDialog.vue`
- 联调文档：`docs/30-专项功能方案/统一查询MCP联调示例.md`

当前 `query://usage-guide` 已定义的推荐链路是：

1. 先读 `query://usage-guide`
2. 调 `search_ids(keyword="<用户原始问题>")`
3. 调 `get_manual_content(project_id=...)`
4. 需要执行时再调 `execute_project_collaboration(...)`

这说明现有统一查询 MCP 已具备一个很清晰的事实：

- 当前是 `query-first`
- 执行是补充能力，不是主能力
- 兼容已有项目 MCP 和员工 MCP

这个方向是对的，不需要推翻，只需要继续升级。

## 3. 当前能力与缺口

### 3.1 已有优势

- 已有统一入口，CLI 接入成本低。
- 已有项目、员工、规则、手册、记忆等核心上下文。
- 已有 `execute_project_collaboration`，说明系统不是纯查询，而是具备编排基础。
- 已有 `save_project_memory`，说明系统已经能沉淀会话结果。
- 已有前端生成 SSE 配置与接入提示词，说明产品层已经准备好对外接入。

### 3.2 当前缺口

当前入口对 CLI 来说仍然偏底层。它能“查”和“调”，但还不够“理解任务”和“组织执行”。

主要缺口：

- 缺少任务理解层：没有直接帮 CLI 做任务拆解、约束提取、执行计划生成。
- 缺少上下文编排层：CLI 仍要自己决定先查什么、补什么、怎么合并。
- 缺少策略判断层：缺少对命令风险、操作权限、执行方式的统一判定工具。
- 缺少会话恢复层：缺少面向长任务的恢复、续跑、检查点摘要能力。
- 缺少结果沉淀层：缺少面向 patch、PR、发布说明、阶段汇报的结构化输出能力。
- 缺少客户端适配层：还没有针对不同 CLI 的能力画像和推荐调用模式。

## 4. 升级定位

统一查询 MCP 后续不应停留在“统一内容查询”。

更合适的定位是：

> 从 Unified Query MCP 升级为 Agent Capability Gateway。

这个 Gateway 不负责替代外部 CLI，而是负责把当前系统最有价值的能力稳定暴露给外部 CLI：

- 项目上下文
- 规则与约束
- 任务理解
- 协作编排
- 权限判断
- 记忆沉淀
- 会话恢复
- 交付摘要

目标架构应是：

- CLI = Thin Client
- `/mcp/query/sse` = Stable Entry
- MCP Runtime = Thick Capability Layer

## 5. 明确不做什么

本轮升级的非目标必须明确：

- 不做一个新的终端 UI。
- 不重做 Claude Code / Codex 的命令行体验。
- 不把主要精力花在 shell 包装、终端皮肤、快捷键交互上。
- 不把统一查询 MCP 变成“万能聊天接口”。
- 不破坏当前 `search_ids -> get_manual_content -> execute_project_collaboration` 的兼容链路。

## 6. 目标能力分层

建议以 `/mcp/query/sse` 为稳定入口，在同一个统一入口下逐步补齐以下能力层。

### 6.1 接入层

保持现有入口不变：

- `GET /mcp/query/sse?key=...`
- `POST /mcp/query/mcp?key=...`

原则：

- 路径不改
- 鉴权模式不改
- 现有客户端配置尽量不改

### 6.2 上下文层

保留并强化现有能力：

- `search_ids`
- `get_content`
- `get_manual_content`
- `save_project_memory`

补充方向：

- 增加更明确的上下文聚合工具，而不是让 CLI 自己多次拼装。
- 增加“与当前任务最相关”的上下文解析能力，而不是只做 ID 查找。

建议新增工具：

- `resolve_relevant_context`
- `resolve_project_operating_context`
- `resolve_rules_for_task`

### 6.3 任务理解层

这是最值得新增的一层，目标是给 CLI 提供“理解任务”的能力，而不是只给数据。

建议新增工具：

- `analyze_task`
- `extract_constraints`
- `generate_execution_plan`
- `classify_task_type`

期望效果：

- CLI 收到用户原始请求后，可以先把任务结构化。
- 再决定查哪些项目、规则、员工、工具。
- 不再每次都靠模型自己从零猜工作流。

### 6.4 协作编排层

当前已有：

- `execute_project_collaboration`

后续可增强为：

- `plan_project_collaboration`
- `select_best_actors`
- `explain_collaboration_decision`

重点不是把协作做复杂，而是把“为什么由谁来做、为什么单人还是多人”说清楚，并让外部 CLI 可以复用这套判断。

### 6.5 策略与权限层

如果目标是增强外部 CLI，权限与风险不能只靠提示词。

建议新增工具：

- `check_operation_policy`
- `classify_command_risk`
- `check_workspace_scope`
- `explain_block_reason`

这层主要解决：

- 当前操作是否允许
- 是直接执行还是需要确认
- 是本地执行还是应转交系统代理
- 为什么被拒绝或降级

### 6.6 记忆与恢复层

CLI 一旦进入长任务，就需要“断点续跑”和“阶段恢复”。

建议新增工具：

- `save_work_facts`
- `resume_work_session`
- `get_recent_decisions`
- `summarize_checkpoint`

这层比简单保存对话更重要，因为它面对的是“工作状态”而不是“聊天记录”。

### 6.7 交付输出层

当前系统有项目协作和代码能力，但缺少“帮 CLI 形成交付结果”的统一能力。

建议新增工具：

- `summarize_patch_for_pr`
- `generate_release_note_entry`
- `build_delivery_report`
- `build_verification_checklist`

这层能直接提升外部 CLI 的最终交付质量。

## 7. 推荐升级路径

### 阶段 1：保持 `/mcp/query/sse` 不变，先补高层能力工具

目标：

- 不改接入方式
- 不改现有客户端配置
- 在统一查询 MCP 上增加任务理解和上下文编排能力

本阶段建议优先新增：

- `analyze_task`
- `extract_constraints`
- `generate_execution_plan`
- `resolve_relevant_context`

产出效果：

- 现有 CLI 接上 `/mcp/query/sse` 后，第一步不再只是查 ID。
- 可以先拿到“任务结构化理解结果”。

### 阶段 2：补齐策略判断与执行建议

目标：

- 让统一查询 MCP 不只回答“能查什么”
- 还回答“下一步应该怎么安全执行”

本阶段建议优先新增：

- `check_operation_policy`
- `classify_command_risk`
- `explain_block_reason`

产出效果：

- 外部 CLI 在调用 shell、写文件、触发协作前，可以先问后端策略层。
- 权限边界从“提示词建议”升级为“后端可判定能力”。

### 阶段 3：补齐长任务恢复与工作记忆

目标：

- 支持长链路任务
- 支持跨会话恢复
- 支持阶段性检查点

本阶段建议优先新增：

- `save_work_facts`
- `resume_work_session`
- `summarize_checkpoint`

产出效果：

- 外部 CLI 遇到中断、压缩上下文、切换模型时，仍能恢复任务状态。

### 阶段 4：形成客户端适配画像

目标：

- 让同一个 `/mcp/query/sse` 对不同 CLI 有更高适配度

建议增加资源或模板：

- `query://client-profile/claude-code`
- `query://client-profile/codex`
- `query://client-profile/generic-cli`

这些资源不需要改变核心协议，只需要告诉不同客户端：

- 推荐先读哪些资源
- 推荐优先调用哪些工具
- 哪些能力适合自动调用
- 哪些能力适合用户确认后调用

## 8. 建议的标准调用链路

升级后建议把统一查询 MCP 的标准链路，从“查询链路”升级为“理解 + 查询 + 编排 + 沉淀”链路：

1. 读取 `query://usage-guide`
2. 调 `analyze_task(raw_request)`
3. 调 `search_ids(keyword="<用户原始问题>")`
4. 调 `get_manual_content(project_id=...)`
5. 调 `resolve_relevant_context(...)`
6. 调 `generate_execution_plan(...)`
7. 执行 `execute_project_collaboration(...)` 或手动编排
8. 调 `save_project_memory(...)` 或 `save_work_facts(...)`

这样升级后，`/mcp/query/sse` 仍然是同一个入口，但语义从“统一查询”变成“统一智能体能力入口”。

## 9. 对现有实现的落地建议

### 9.1 后端

优先在现有 `dynamic_mcp_apps_query.py` 上做增量升级，而不是另起一套完全独立服务。

原因：

- 当前 `query://usage-guide`、`search_ids`、`get_content` 已经在这里聚合。
- 统一入口的定位已经稳定。
- 兼容成本最低。

建议演进方式：

- 第一阶段先在统一查询 MCP 中增加高层 agent tools。
- 第二阶段再考虑把部分能力拆成更清晰的内部 service。
- 对外仍然继续通过 `/mcp/query/sse` 暴露。

### 9.2 前端

`UnifiedMcpAccessDialog.vue` 当前已经把 `/mcp/query/sse` 作为首选接入方式暴露给用户。

建议后续同步升级：

- 接入说明从“统一查询入口”升级为“统一智能体能力入口”。
- 在弹窗中增加推荐调用链路说明。
- 增加“推荐给 Claude / Codex 的提示词模板”。
- 在项目页或设置页里补充“客户端适配建议”。

### 9.3 文档

文档层建议保留三层结构：

- 联调文档：告诉别人怎么连
- 设计文档：告诉别人为什么这么做
- 升级规划：告诉别人下一步怎么演进

当前对应关系建议为：

- `统一查询MCP联调示例.md`：接入
- `项目模块MCP化设计.md`：现有架构基础
- 本文：后续升级路线

## 10. 推荐优先级

如果按投入产出比排序，最值得先做的是：

1. `analyze_task`
2. `resolve_relevant_context`
3. `generate_execution_plan`
4. `check_operation_policy`
5. `resume_work_session`

原因很直接：

- 这几项最能让外部 CLI 变聪明。
- 它们提升的是任务理解、执行质量和恢复能力。
- 这比继续打磨 CLI 外壳更有复用价值。

## 11. 结论

当前系统不需要去正面重做一个 Claude Code / Codex。

更合理的路径是：

- 保持 `/mcp/query/sse` 作为稳定接入入口
- 把统一查询 MCP 从查询入口升级为 Agent Capability Gateway
- 让 Claude / Codex / 其他 CLI 继续负责交互与执行
- 让当前系统负责上下文、规则、编排、策略、记忆和恢复

一句话总结：

> 不做另一个 CLI，做让现有 CLI 更强的 MCP 服务层。
