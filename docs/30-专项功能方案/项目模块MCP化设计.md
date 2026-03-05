# 项目模块 MCP 化设计（Project-as-MCP）

## 1. 背景与目标

当前系统已支持：
- 记忆带 `project_name` 维度。
- 反馈工单/候选按 `project_id` 隔离。
- 员工技能可通过本地脚本代理执行（无需技能服务单独远程调用）。

但项目仍不是一等实体，导致：
- 项目成员关系分散在员工配置外。
- 项目上下文缺少统一 MCP 接入面。
- 接入方需要围绕员工单元初始化，项目级复用不直观。

目标：将项目升级为一等模块，并提供独立 MCP 入口，实现“项目引入员工后即可复用记忆、反馈、技能、规则”。

## 2. 设计原则

- 项目是一等实体：项目信息、成员关系、配置可独立管理。
- 项目是主入口：接入方优先连接项目 MCP，而非员工 MCP。
- 员工保留为能力载体：技能与规则归属于员工，但由项目进行编排。
- 本地优先：技能与规则优先本地调用，不强依赖员工 MCP 二次转发。
- 兼容优先：员工 MCP 保持可用，作为兼容路径。

## 3. 数据模型（v1）

### 3.1 Project

- `id`: 项目 ID（唯一）
- `name`: 项目显示名
- `description`: 描述
- `mcp_enabled`: 是否暴露项目 MCP
- `feedback_upgrade_enabled`: 项目反馈升级开关
- `created_at` / `updated_at`

### 3.2 ProjectMember

- `project_id`
- `employee_id`
- `role`（默认 `member`）
- `enabled`（默认 `true`）
- `joined_at`

## 4. API 设计（v1）

新增路由前缀：`/api/projects`

- `GET /api/projects`：项目列表
- `POST /api/projects`：创建项目
- `GET /api/projects/{project_id}`：项目详情
- `PUT|PATCH /api/projects/{project_id}`：更新项目
- `DELETE /api/projects/{project_id}`：删除项目
- `GET /api/projects/{project_id}/members`：成员列表
- `POST /api/projects/{project_id}/members`：添加成员
- `DELETE /api/projects/{project_id}/members/{employee_id}`：移除成员

## 5. MCP 设计（v1）

新增动态 MCP 入口：`/mcp/projects/{project_id}`

### 5.1 Resource

- `project://{project_id}/profile`
- `project://{project_id}/members`

### 5.2 Tools

- `get_project_profile()`
- `list_project_members()`
- `get_project_runtime_context()`
- `recall_project_memory(query="", employee_id="", project_name="")`
- `submit_project_feedback_bug(employee_id, title, symptom, expected, ...)`
- `query_project_rules(keyword="", employee_id="")`
- `list_project_proxy_tools()`
- `invoke_project_skill_tool(tool_name, employee_id, args/args_json, timeout_sec)`

说明：
- `recall_project_memory` 默认使用项目 `name` 作为 `project_name` 过滤。
- 技能执行通过本地脚本代理直接调用，不依赖员工 MCP 转发。
- 反馈工单以 `project_id` 入库，员工仅作为归属人。

## 6. 兼容策略

- 保留现有 `/mcp/employees/{employee_id}`。
- 不修改既有员工能力语义，仅新增项目编排层。
- 前端与接入方可逐步从员工 MCP 切换至项目 MCP。

## 7. 落地范围（本次）

- 新增 Project Store（JSON + PostgreSQL）。
- 新增 `deps.project_store`。
- 新增项目请求模型与 API 路由。
- 新增项目 MCP 动态代理并挂载。
- 补充最小文档说明。

## 8. 后续增强（v2+）

- 项目级技能/规则覆盖（override）与优先级策略。
- 项目级 API Key 与统计维度（替代 employee_id 统计耦合）。
- 项目级记忆策略（共享记忆池 + 员工私有记忆混合检索）。
- 项目模板与一键初始化（项目 + 成员 + 技能包 + 规则域）。
