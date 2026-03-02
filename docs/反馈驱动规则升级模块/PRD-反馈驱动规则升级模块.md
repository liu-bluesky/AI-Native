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

## 2.2 非目标

- 不做“零审核全自动发布高风险规则”。
- 不改造现有所有规则模型字段（先最小增量）。
- 不引入复杂分布式基础设施（先基于当前 JSON/SQLite 架构）。

## 3. 参考与优化点

参考 `rule-porter-mcp`：

- 可复用“经验沉淀”的结构化输入思路（title/scenario/symptom/solution）。
- 可复用“跨项目通用规则提取”的方法论。

在本项目新增优化：

- 增加“深层反思”标准输出（直接原因、根因、证据链）。
- 增加“候选升级 + 人工审核 + 版本发布 + 回滚”治理链路。
- 增加“独立模块启用控制”，避免影响未启用员工。

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

## 6. 核心流程

1. 用户提交反馈（手动）
2. 系统聚合上下文（会话、工具调用、命中规则）
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

## 8. 数据模型（最小集）

## 8.1 feedback_bug

- `id`
- `employee_id`
- `session_id`
- `rule_id`
- `title`
- `symptom`
- `expected`
- `severity`
- `reporter`
- `status`（new/analyzing/pending_review/closed）
- `created_at`

## 8.2 feedback_analysis

- `feedback_id`
- `bug_type`
- `direct_cause`
- `root_cause`
- `evidence_refs`（会话片段、tool_call、rule_id）
- `confidence`
- `generated_at`

## 8.3 rule_upgrade_candidate

- `id`
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
- `candidate_id`
- `reviewer`
- `action`（approve/edit/reject）
- `comment`
- `edited_content`
- `created_at`

## 9. API 草案（网关）

- `POST /api/feedback/bugs`
- `GET /api/feedback/bugs`
- `GET /api/feedback/bugs/{id}`
- `POST /api/feedback/bugs/{id}/analyze`
- `GET /api/feedback/candidates?status=pending`
- `POST /api/feedback/candidates/{id}/review`
- `POST /api/feedback/candidates/{id}/publish`
- `POST /api/feedback/candidates/{id}/rollback`

## 10. 审核与风控

- 低风险：可配置自动通过，但默认仍需人工抽检。
- 中风险：必须人工审核。
- 高风险：必须双人审核或管理员审核。
- 任意风险：发布后 24h 内触发异常阈值可自动回滚。

## 11. 指标定义

- 反馈处理时效（提交到首次审核）
- 候选通过率（approved / total）
- 发布后回归率（发布后新增同类 bug 占比）
- 规则采纳率（规则命中后未被纠正的比例）
- 回滚率（rollback / published）

## 12. 上线计划（建议）

- `Phase 1` 文档与数据模型落地（本 PRD + 接口冻结）
- `Phase 2` 后端 MVP（反馈入库、分析、候选、审核）
- `Phase 3` 前端 MVP（反馈录入、审核台、规则版本记录）
- `Phase 4` 小范围灰度（指定 1-2 个员工）
- `Phase 5` 全量发布与治理机制固化

## 13. 验收标准

- 可以在员工维度手动启用/停用模块。
- 至少 1 条反馈可走完“提交 -> 反思 -> 候选 -> 审核 -> 发布”闭环。
- 审核日志完整可追溯。
- 发布后可执行回滚并恢复旧规则版本。

