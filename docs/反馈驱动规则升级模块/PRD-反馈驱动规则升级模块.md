# PRD：反馈驱动规则升级模块（独立可选）

## 1. 背景

当前系统已有规则、员工、进化、审核能力，但“用户手动反馈 bug -> AI 反思 -> 规则升级 -> 人工审核发布”尚未形成完整闭环。  
同时，进化数据来源与使用行为数据存在分离，导致自动升级价值受限。

本 PRD 的目标是将该能力设计为独立模块，可手动选择接入。

## 2. 目标与非目标

## 2.1 目标

- 支持用户提交结构化反馈，作为规则升级的主要输入。
- AI 输出“深层原因分析 + 规则升级候选”，进入人工审核队列。
- 审核通过后再发布规则新版本，保留回滚能力。
- 模块可按项目/员工手动开启，默认关闭。
- 强制项目边界：仅处理并存储“当前项目”中的反馈与 AI 反思结果，禁止跨项目混入。

## 2.2 非目标

- 不做“零审核全自动发布高风险规则”。
- 不改造现有所有规则模型字段（先最小增量）。
- 不引入复杂分布式基础设施（先基于当前 JSON/SQLite/PostgreSQL 架构）。

## 3. 参考与优化点

参考 `rule-porter-mcp`：

- 可复用“经验沉淀”的结构化输入思路（title/scenario/symptom/solution）。
- 可复用“跨项目通用规则提取”的方法论。

在本项目新增优化：

- 增加“深层反思”标准输出（直接原因、根因、证据链）。
- 增加“候选升级 + 人工审核 + 版本发布 + 回滚”治理链路。
- 增加“独立模块启用控制”，避免影响未启用员工。
- 增加“项目隔离约束”，确保反馈与反思数据只归属当前项目。

## 4. 角色与权限

- 反馈提交者（Developer）：提交 bug 反馈，查看处理结果。
- 审核者（Reviewer）：审核规则升级候选（approve/edit/reject）。
- 发布者（Maintainer）：执行规则发布/回滚。
- 管理员（Admin）：启停模块、配置风控阈值。

## 5. 模块化接入设计

## 5.1 配置维度

- 全局开关：`feedback_upgrade.enabled_global`
- 项目开关：`feedback_upgrade.enabled_projects[]`
- 员工开关：`employee.feedback_upgrade_enabled`

判定原则：全局开启且项目开启且员工开启时生效。

## 5.2 接入点

- 员工创建/编辑页增加“反馈驱动升级模块”开关（手动选择添加）。
- 演化页面新增“反馈工单”和“候选审核”入口。
- 规则详情页新增“版本变更记录 + 来源反馈”视图。

## 5.3 项目边界与数据归属（关键）

- 所有反馈链路实体必须携带 `project_id`。
- `feedback_analysis` 与 `rule_upgrade_candidate` 必须继承同一 `project_id`，不可变更。
- 上下文聚合只允许读取当前项目内数据：会话、工具调用、规则命中、使用日志。
- 禁止跨项目查询或写入；后端必须按 `project_id` 做硬过滤（而非仅前端过滤）。
- 若请求中 `project_id` 与当前登录上下文不匹配，返回 `403`。

## 6. 核心流程

1. 用户在当前项目提交反馈（手动）
2. 系统聚合当前项目上下文（会话、工具调用、命中规则）
3. AI 生成反思报告（含证据链）
4. AI 生成规则升级候选（不直接上线）
5. 审核者执行 approve/edit/reject
6. 通过后生成规则新版本并灰度发布
7. 持续监控指标，异常回滚

## 7. 功能需求（FR）

- `FR-1` 反馈提交：支持标题、现象、期望、严重级别、关联规则/会话。
- `FR-2` 反思分析：输出 bug_type、direct_cause、root_cause、evidence_refs、confidence。
- `FR-3` 候选生成：输出目标规则、改前改后 diff、风险级别、预期收益。
- `FR-4` 审核流：支持 approve/edit/reject，编辑后再次确认。
- `FR-5` 发布流：审核通过后才可发布新版本。
- `FR-6` 回滚流：支持按规则版本回滚。
- `FR-7` 审计：每个动作记录操作人、时间、变更前后内容。
- `FR-8` 策略：按风险域设置不同阈值与审批要求。
- `FR-9` 项目隔离：反馈、反思、候选、审核数据必须按 `project_id` 强隔离。
- `FR-10` 端到端可视化：前端必须提供反馈录入、分析详情、候选审核、版本追踪页面。

## 8. 数据模型（最小集）

## 8.1 feedback_bug

- `id`
- `project_id`（必填）
- `employee_id`
- `session_id`
- `rule_id`
- `title`
- `symptom`
- `expected`
- `severity`
- `reporter`
- `status`（new/analyzing/pending_review/closed）
- `source_context`（JSON，记录当前项目会话/命中规则快照）
- `created_at`

## 8.2 feedback_analysis

- `id`
- `project_id`（必填）
- `feedback_id`
- `bug_type`
- `direct_cause`
- `root_cause`
- `evidence_refs`（会话片段、tool_call、rule_id）
- `confidence`
- `model_name`
- `reflection_output`（JSON，AI 标准化反思原文）
- `generated_at`

## 8.3 rule_upgrade_candidate

- `id`
- `project_id`（必填）
- `feedback_id`
- `employee_id`
- `target_rule_id`
- `old_rule_content`
- `proposed_rule_content`
- `risk_level`
- `confidence`
- `status`（pending/approved/rejected/published/rolled_back）
- `created_at`
- `updated_at`

## 8.4 review_decision

- `id`
- `project_id`（必填）
- `candidate_id`
- `reviewer`
- `action`（approve/edit/reject）
- `comment`
- `edited_content`
- `created_at`

## 9. API 草案（网关）

采用项目级路径，确保后端天然具备隔离边界。

- `POST /api/projects/{project_id}/feedback/bugs`
- `GET /api/projects/{project_id}/feedback/bugs`
- `GET /api/projects/{project_id}/feedback/bugs/{id}`
- `POST /api/projects/{project_id}/feedback/bugs/{id}/analyze`
- `GET /api/projects/{project_id}/feedback/candidates?status=pending`
- `POST /api/projects/{project_id}/feedback/candidates/{id}/review`
- `POST /api/projects/{project_id}/feedback/candidates/{id}/publish`
- `POST /api/projects/{project_id}/feedback/candidates/{id}/rollback`
- `PATCH /api/projects/{project_id}/feedback/config`

## 10. 前端设计（菜单与功能）

## 10.1 菜单与导航

- 员工列表页操作列新增 `反馈` 按钮，路由到 `反馈工单页`。
- 演化模块内增加二级导航：`反馈工单`、`候选审核`、`规则版本记录`。
- 员工编辑页新增模块开关：`反馈驱动升级模块`。

## 10.2 页面清单

- `反馈工单列表页`：筛选 `status/severity/rule_id/time`，支持查看当前项目数据。
- `反馈提交弹窗/页面`：填写标题、现象、期望、严重级别、关联会话、关联规则。
- `反馈详情页`：显示反馈正文、AI 反思结果、证据链、候选规则。
- `候选审核页`：approve/edit/reject，编辑后强制二次确认。
- `规则详情页`：新增版本变更记录、来源反馈链路。

## 10.3 前端状态约束

- 页面切换项目后必须清空旧项目缓存。
- 所有请求必须携带当前项目上下文（路径参数 `project_id`）。
- 跨项目数据返回时前端不做兜底修正，直接报错并提示权限问题。

## 11. 后端设计（接口与分层）

## 11.1 路由与服务分层

- 新增路由：`web-admin/api/routers/feedback_upgrade.py`
- 服务层建议拆分：`feedback_service.py`、`analysis_service.py`、`candidate_service.py`
- 存储层新增对应 Store：`feedback_bug_store`、`feedback_analysis_store`、`feedback_candidate_store`

## 11.2 后端核心校验

- 请求进入路由后先校验 `project_id` 与用户可访问项目集合。
- 所有查询语句必须包含 `project_id` 条件。
- 发布与回滚动作必须校验候选状态机合法（禁止越级状态迁移）。

## 11.3 异步任务

- `analyze` 接口写入任务队列（或任务表），异步调用 AI 执行反思。
- 任务结果写回 `feedback_analysis`，并触发候选生成。
- 若 AI 失败，反馈状态转 `analyze_failed`，并记录错误原因用于重试。

## 12. 审核与风控

- 低风险：可配置自动通过，但默认仍需人工抽检。
- 中风险：必须人工审核。
- 高风险：必须双人审核或管理员审核。
- 任意风险：发布后 24h 内触发异常阈值可自动回滚。

## 13. 指标定义

- 反馈处理时效（提交到首次审核）
- 候选通过率（approved / total）
- 发布后回归率（发布后新增同类 bug 占比）
- 规则采纳率（规则命中后未被纠正的比例）
- 回滚率（rollback / published）
- 项目隔离错误率（跨项目访问被拦截次数 / 总请求数）

## 14. 上线计划（建议）

- `Phase 1` 文档与数据模型落地（本 PRD + 接口冻结）
- `Phase 2` 后端 MVP（反馈入库、分析、候选、审核）
- `Phase 3` 前端 MVP（反馈录入、审核台、规则版本记录）
- `Phase 4` 小范围灰度（指定 1-2 个员工）
- `Phase 5` 全量发布与治理机制固化

## 15. 验收标准

- 可以在员工维度手动启用/停用模块。
- 至少 1 条反馈可走完“提交 -> 反思 -> 候选 -> 审核 -> 发布”闭环。
- 审核日志完整可追溯。
- 发布后可执行回滚并恢复旧规则版本。
- 反馈与反思数据可按 `project_id` 查询，且无法跨项目访问。
- 前端存在可用菜单入口与完整页面链路（反馈录入、审核、版本追踪）。
