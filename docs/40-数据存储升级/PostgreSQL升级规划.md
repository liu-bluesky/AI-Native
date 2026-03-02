# PostgreSQL 升级规划（执行版）

> 目的：将当前项目从“JSON/SQLite 混合存储”升级为“PostgreSQL 为主存储”，并通过阶段化迁移降低风险，避免后续开发遗漏关键步骤。

## 当前进展（2026-03-02）

- [x] Docker PostgreSQL 服务可启动并健康检查通过
- [x] 新增 `web-admin/api/usage_store_pg.py`（PostgreSQL 实现）
- [x] `deps.py` 增加 `USAGE_STORE_BACKEND` 切换（sqlite/postgres）
- [x] 新增迁移脚本 `web-admin/api/scripts/migrate_usage_to_pg.py`
- [x] 新增初始化脚本 `docker/init/001_usage_schema.sql`
- [x] 新增 `web-admin/api/stores_pg.py`（skills/rules/memory/persona/evolution/sync PG 适配器）
- [x] `web-admin/api/stores.py` 增加 `CORE_STORE_BACKEND` 切换（json/postgres）
- [x] 新增 `web-admin/api/user_store_pg.py` 与 `web-admin/api/employee_store_pg.py`
- [x] `deps.py` 增加 `CORE_STORE_BACKEND` 下 user/employee 存储切换
- [x] 新增迁移脚本 `web-admin/api/scripts/migrate_core_to_pg.py`
- [ ] API 容器构建验证（受 Docker Hub 网络超时影响待完成）
- [x] 执行 JSON/SQLite -> PostgreSQL 实际数据迁移并对账（2026-03-02：users=1, employees=2, skills=1, rules=6, api_keys=2, usage_records=164）

## 1. 背景与现状

当前存储形态：

- `web-admin/api/usage_store.py` 使用 SQLite（`usage.db`）。
- `mcp-memory/store.py` 使用 SQLite（`memories.db`）。
- `mcp-skills` / `mcp-rules` / `mcp-persona` / `mcp-evolution` / `mcp-sync` 主要使用 JSON 文件存储。
- `web-admin/api/stores.py` 通过 importlib 桥接各服务 Store，支持 `CORE_STORE_BACKEND=json|postgres`。

存在问题：

- 多存储介质并存，统计与进化数据链路割裂。
- 并发扩展能力受限，跨服务一致性和审计追踪成本高。
- 新功能（反馈驱动升级、大规模并发）缺乏统一数据底座。

## 2. 升级目标

目标分层：

1. **阶段目标**：先把高价值、写频繁的数据迁到 PostgreSQL（Usage、Evolution）。
2. **中期目标**：将规则、员工、人设、技能元数据迁到 PostgreSQL，JSON 仅作为导入导出格式。
3. **长期目标**：形成统一事件与审计体系，支持反馈闭环、版本治理、横向扩展。

非目标（本轮不做）：

- 一次性全量替换所有 Store。
- 引入分布式数据库或复杂分片方案。
- 立即改造全部 MCP 服务为异步 ORM。

## 3. 原则

- **增量迁移**：双写/灰度，不做一次性切换。
- **可回滚**：每个阶段都有明确回退开关。
- **向后兼容**：现有 API 行为不变，优先替换底层实现。
- **可观测**：迁移期间对比新旧数据一致性。
- **安全优先**：迁移与回滚均保留审计日志。

## 4. 目标架构（本项目）

- 主库：PostgreSQL 17
- 连接池：PgBouncer（下一阶段引入）
- 缓存：Redis（下一阶段引入）
- 应用层：
- `web-admin/api` 通过统一 Repository 层读写 PostgreSQL
- `mcp-*` 服务逐步从 JSON/SQLite Store 迁到 PG Store
- 保留 JSON 导入导出能力（用于技能包、规则交换）

## 5. 数据域迁移优先级

P0（先迁）：

- `usage_records` / `api_keys`（当前 SQLite usage.db）
- `evolution candidates/events/usage_logs`（当前 JSON）

P1（第二批）：

- `employees`（当前 JSON）
- `rules`（当前 JSON，含版本/置信度/使用统计）

P2（第三批）：

- `skills` / `personas` / `sync events`
- `memory`（SQLite -> PostgreSQL，需评估检索性能）

## 6. 阶段计划（必须按序）

## Phase 0：设计冻结

交付：

- 表结构设计（DDL）
- 索引设计
- 迁移脚本框架
- 环境变量规范（`DATABASE_URL` 等）

验收：

- 评审通过并冻结 schema v1
- 所有负责人确认阶段边界

## Phase 1：基础设施就绪

任务：

- docker-compose 增加 PostgreSQL 初始化 SQL（`docker/init/*.sql`）
- 新增数据库接入模块（连接管理、健康检查）
- 为 API 增加 `DATABASE_URL` 配置入口

验收：

- 本地/测试环境可稳定连通 PostgreSQL
- 健康检查接口可返回 DB 状态

## Phase 2：Usage 域迁移（第一落地）

任务：

- 新建 `usage_store_pg.py`（与现有接口兼容）
- 增加 feature flag：`USAGE_STORE_BACKEND=sqlite|postgres`
- 编写一次性迁移脚本：`usage.db -> PostgreSQL`
- 迁移后校验总量、一致性（按 employee/day 比较）

验收：

- `create_key/list_keys/validate_key/record_event/get_stats` 全部通过回归
- 线上灰度无明显性能退化

## Phase 3：Evolution 域迁移

任务：

- candidates/events/usage_logs 改为 PostgreSQL 表
- 审核流（approve/edit/reject）全链路接 PG
- 保留 JSON 只读回溯工具（迁移后下线写入）

验收：

- evolution 报表与候选审核页面正常
- 迁移前后核心指标偏差 < 1%

## Phase 4：Rules / Employees 域迁移

任务：

- 规则、员工主数据迁移 PG
- 新旧存储双写一段时间
- 完成切流并关闭 JSON 主写

验收：

- 规则查询、绑定、统计、版本变更功能全通过
- 员工创建/编辑/详情无行为变化

## Phase 5：收尾与治理

任务：

- 清理废弃存储路径与脚本
- 完整补齐运维手册（备份、恢复、巡检）
- 增加容量与性能压测基线

验收：

- 文档齐全
- 数据备份恢复演练通过

## 7. 表结构建议（v1 草案）

建议先建核心表：

- `api_keys`
- `usage_records`
- `evolution_candidates`
- `evolution_events`
- `employees`
- `rules`
- `rule_changelog`

索引建议：

- `usage_records(employee_id, created_at desc)`
- `usage_records(event_type, created_at desc)`
- `evolution_candidates(employee_id, status, created_at desc)`
- `rules(domain, updated_at desc)`

## 8. 配置规范（统一）

新增环境变量：

- `DATABASE_URL=postgresql://user:pass@host:5432/dbname`
- `DB_POOL_MIN=5`
- `DB_POOL_MAX=30`
- `CORE_STORE_BACKEND=postgres`
- `USAGE_STORE_BACKEND=postgres`

约束：

- 不再在业务代码中硬编码 sqlite 路径。
- 配置缺失时必须启动失败（fail fast）。

## 9. 风险与回滚

主要风险：

- 双写期间数据不一致
- 迁移脚本中断导致部分数据缺失
- 统计口径差异导致报表波动

回滚策略：

- 每个域独立 feature flag，可快速切回旧 Store
- 切流前做快照备份
- 回滚时保留 PG 增量日志，后续可重放

## 10. 验收指标（硬性）

- API 错误率无显著上升（与迁移前基线相比）
- 关键接口 P95 延迟不劣化超过 20%
- 数据一致性校验通过（关键表 100% 对齐）
- 迁移/回滚 SOP 至少演练 1 次

## 11. 待办清单（防遗忘）

- [ ] 冻结 schema v1 与命名规范
- [x] 产出 usage 域 PG Store 与 feature flag
- [x] 完成 usage 迁移脚本与对账脚本
- [x] 产出 core 域 PG Store（skills/rules/memory/persona/evolution/sync + user/employee）
- [x] 完成 core 迁移脚本（JSON/SQLite -> PostgreSQL）
- [ ] 灰度 1 个员工 + 1 个团队
- [ ] 完成 evolution 域迁移设计评审
- [ ] 完成 rules/employees 域迁移设计评审
- [ ] 补齐运维与故障回滚文档

## 12. 文档维护规则

- 本文档为迁移主文档，任何阶段变更必须先更新文档再开发。
- 每完成一个阶段，必须更新“阶段状态”和“遗留问题”。
- 未在本文档记录的迁移动作，禁止直接上线。
