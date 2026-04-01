# 统一查询 MCP 开发实施骨架

> 日期：2026-04-01
> 目标入口：`/mcp/query/sse`
> 当前状态：Phase 1 - Phase 4 最小可用版已完成，Phase 3 结构化轨迹增强已完成

## 1. 目标

本轮目标不是重做 CLI，而是把统一查询 MCP 从“聚合查询入口”升级为“高层智能体能力入口”。

实施顺序必须遵守：

1. 先补高层分析能力
2. 再补策略判断能力
3. 再补会话恢复能力
4. 最后补客户端画像和更强交付能力

## 2. 总体阶段

### Phase 0：文档与骨架

- 输出升级规划文档
- 输出 Claude CLI 借鉴映射文档
- 输出实施骨架文档
- 固定开发顺序与优先级

状态：

- 已完成

### Phase 1：高层智能体工具

目标：

- 让 `/mcp/query/sse` 先具备任务理解、相关上下文聚合、执行步骤骨架生成能力

第一批工具：

- `analyze_task`
- `resolve_relevant_context`
- `generate_execution_plan`

本阶段原则：

- 先做最小可用版本
- 优先复用现有 `execute_project_collaboration`、项目规则检索、成员检索、工具检索能力
- 先允许确定性规则实现
- 不把第一版强绑定到新增模型配置

状态：

- 开发中（第一批工具已落地）

### Phase 2：策略与权限判断

目标：

- 让外部 CLI 在执行前先问后端“能不能做、该怎么做”

候选工具：

- `check_operation_policy`
- `classify_command_risk`
- `check_workspace_scope`
- `resolve_execution_mode`

依赖：

- Phase 1 工具先稳定

状态：

- 已完成（最小可用版）

### Phase 3：工作轨迹与恢复

目标：

- 把当前系统从“记住结论”升级为“记住任务执行轨迹”

候选工具：

- `save_work_facts`
- `append_session_event`
- `resume_work_session`
- `summarize_checkpoint`

依赖：

- 统一事件模型
- 会话恢复策略

状态：

- 已完成（结构化轨迹增强版）

当前增强点：

- `save_work_facts` 支持附带 `session_id / phase / step / status / goal / changed_files / verification / risks / next_steps`
- `append_session_event` 支持附带同一套结构化轨迹字段
- 已新增独立 `work_session_store`，轨迹保存从“仅项目记忆”升级为“独立 store + 项目记忆双写”
- `resume_work_session` 不再只返回原始记忆列表，还会聚合输出 `phases / steps / changed_files / verification / risks / next_steps / latest_status / timeline`
- `summarize_checkpoint` 可直接输出按阶段恢复开发现场所需的结构化检查点
- 已新增后台查看入口 `/work-sessions`，可按 session 查看阶段、步骤、验证、风险与时间线

当前边界：

- 当前独立轨迹 store 已能承载工作事件，但仍是轻量事件模型，不是完整 transcript replay 系统
- 已能满足阶段恢复、长任务续跑和交接摘要
- 还不等同于全过程审计与完整会话重放

### Phase 4：客户端画像与交付增强

目标：

- 面向 Claude / Codex / 通用 CLI 输出更清晰的接入建议

候选能力：

- `query://client-profile/claude-code`
- `query://client-profile/codex`
- `build_delivery_report`
- `generate_release_note_entry`

状态：

- 已完成（最小可用版）

## 3. Phase 1 实施步骤

### Step 1：补文档与接入口径

- 补实施骨架文档
- 更新统一 MCP 索引
- 保持 `/mcp/query/sse` 为稳定入口

状态：

- 已完成

### Step 2：在 `dynamic_mcp_apps_query.py` 增加高层工具

新增：

- `analyze_task`
- `resolve_relevant_context`
- `generate_execution_plan`

实现要求：

- 不破坏现有 `search_ids -> get_manual_content -> execute_project_collaboration` 链路
- 尽量复用现有项目协作编排逻辑
- 返回结构化 JSON，不返回散文型文本

状态：

- 已完成（最小可用版）

### Step 3：更新 usage-guide 与接入提示词

目标：

- 让新接入方知道先做任务分析，再做查询和规划

涉及：

- `query://usage-guide`
- `UnifiedMcpAccessDialog.vue`

状态：

- 已完成

### Step 4：做最小验证

验证点：

- 新工具是否能在 query MCP 中暴露
- 返回结构是否稳定
- 旧工具链路是否不受影响
- Python 语法是否通过

状态：

- 已完成（最小验证）

## 4. 第一批交付边界

第一批只交付：

- 高层分析工具
- 结构化结果
- 现有项目协作能力的复用

第一批不做：

- 新审批流
- 新会话事件存储模型
- 新客户端 profile 资源
- 强依赖 LLM 的复杂推理链

## 5. 当前开发优先级

按顺序执行：

1. `analyze_task`
2. `resolve_relevant_context`
3. `generate_execution_plan`
4. 更新 `query://usage-guide`
5. 更新接入提示词
6. 做最小验证

## 6. 一句话原则

先把统一查询 MCP 做成“会分析、会聚合、会给步骤”的入口，再继续做“会判断、会恢复、会交付”的入口。
