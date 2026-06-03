# Web-Admin 管理台详细拆解

## 概述

`web-admin/` 是整个平台的管理台，包含 **FastAPI 后端**（`api/`）和 **Vue3 前端**（`frontend/`）两部分。

---

## 一、后端 `web-admin/api/`

### 1.1 根目录文件

| 文件 | 说明 |
|---|---|
| `server.py` | **入口文件**。一行代码：`from core.server import *`，将应用创建逻辑委托给 `core/server.py` |
| `pyproject.toml` | Python 项目配置。依赖：FastAPI、Uvicorn、PyJWT、FastMCP、lark-oapi、psycopg、Redis、structlog 等 |
| `uv.lock` | uv 包管理器的依赖锁定文件，确保环境一致性 |
| `.env` / `.env.example` | 环境变量配置。包含数据库连接串、Redis地址、JWT密钥、飞书应用凭证等 |
| `init_admin.py` | **管理员初始化脚本**。首次部署时创建超级管理员账号 |
| `system-policy.md` | 系统策略文档，定义安全检查、访问控制等规则 |
| `agent_loop.py.bak` | Agent 循环逻辑的备份文件（历史遗留） |

### 1.2 `core/` — 核心模块

| 文件 | 说明 |
|---|---|
| `__init__.py` | 包初始化，导出核心模块 |
| `server.py` | **FastAPI 应用工厂**。创建 app 实例、注册所有路由、挂载 MCP 端点、配置 CORS、异常处理 |
| `config.py` | **运行配置 (Settings dataclass)**。从环境变量读取数据库URL、Redis URL、JWT密钥、调试模式等 |
| `auth.py` | **JWT 认证模块**。实现 token 生成、验证、刷新；密码哈希（bcrypt）；登录/登出逻辑 |
| `deps.py` | **依赖注入模块**。FastAPI `Depends()` 的集中定义，包括 `get_db`、`get_current_user`、权限校验等 |
| `db_migrations.py` | **数据库迁移执行器**。读取 `sql_migrations/` 目录下的 SQL 文件并按序执行 |
| `data_scope.py` | **数据权限范围**。定义不同角色能看到的数据范围（全部/部门/个人） |
| `ownership.py` | **所有权管理**。资源的创建者、归属项目和团队的关联逻辑 |
| `role_permissions.py` | **角色权限矩阵**。定义 admin/manager/member 等角色的具体权限点 |
| `redis_client.py` | **Redis 客户端封装**。提供连接池管理、缓存读写、分布式锁等 |
| `observability.py` | **可观测性**。结构化日志（structlog）、请求追踪、性能指标采集 |

### 1.3 `core/sql_migrations/` — 数据库迁移

| 文件 | 说明 |
|---|---|
| `0001_initial_schema.sql` | **初始建表**。创建 users、projects、employees、skills、rules、memories、personas 等所有核心表 |
| `0002_project_experience_summary_jobs.sql` | 项目经验总结任务的表结构 |
| `0003_usage_records_enriched.sql` | 使用记录表的字段扩展，增加 prompt 版本追踪 |
| `0004_usage_records_prompt_version.sql` | 使用记录的 prompt 版本字段 |
| `0005_bot_connectors.sql` | 飞书机器人连接器的表结构 |

### 1.4 `models/` — 数据模型

| 文件 | 说明 |
|---|---|
| `__init__.py` | 导出所有模型 |
| `db_models.py` | **SQLAlchemy/Pydantic 数据库模型**。定义 users、projects、employees、skills、rules、memories、personas、bot_connectors、changelog_entries、departments、dictionaries、evolution_records、feedback_upgrades、llm_providers、market_entries、mcp_modules、online_users、roles、skill_resources、usage_records 等 ORM 模型 |
| `requests.py` | **请求体模型**。所有 API 端点的 Pydantic 请求 schema（创建/更新/查询） |
| `responses.py` | **响应体模型**。API 返回数据的 Pydantic schema |

### 1.5 `routers/` — API 路由（28 个模块）

| 文件 | 说明 |
|---|---|
| `__init__.py` | 路由注册入口，统一导出所有 router |
| `agent_templates.py` | **Agent 模板管理**。预定义的 AI 员工能力模板，支持创建、复制、实例化 |
| `bot_connectors.py` | **机器人连接器**。飞书/企微机器人的接入配置，管理 bot token、webhook URL |
| `bot_events.py` | **机器人事件处理**。接收飞书事件回调（消息、审批、打卡等），路由到对应处理器 |
| `changelog_entries.py` | **更新日志**。记录项目/员工的版本变更历史 |
| `departments.py` | **部门管理**。组织架构的 CRUD，层级树管理 |
| `dictionaries.py` | **字典管理**。系统级键值对配置，如状态枚举、类型定义 |
| `employees.py` | **AI 员工管理**（81KB，第二大模块）。员工的创建、配置、能力组合、使用统计、任务追踪 |
| `evolution.py` | **进化引擎**。触发和管理 AI 员工的自动进化，基于反馈和经验调整能力 |
| `feedback_upgrade.py` | **反馈驱动规则升级**。根据用户反馈自动提出规则修改建议，支持审核和合并 |
| `init_auth.py` | **初始化认证**。首次部署时的认证初始化流程 |
| `llm_providers.py` | **LLM 供应商管理**。配置和管理不同的 AI 模型供应商（API key、base URL、模型列表） |
| `market.py` | **市场模块**。AI 员工/技能的发布、发现和交易 |
| `mcp_modules.py` | **MCP 模块管理**。注册和管理 MCP 服务模块的元信息 |
| `mcp_monitor.py` | **MCP 监控**。监控 MCP 服务的健康状态、调用次数、延迟等指标 |
| `memory.py` | **记忆管理**。AI 员工的记忆存储、检索、压缩策略 |
| `metrics.py` | **指标采集**。系统级别的使用指标和性能数据 |
| `online_users.py` | **在线用户**。追踪当前在线的用户和员工 |
| `personas.py` | **人设管理**。AI 员工的人设定义（角色、性格、沟通风格） |
| `roles.py` | **角色管理**。系统角色的权限配置 |
| `rules.py` | **规则管理**。项目的编码规范、架构约束等规则 |
| `skill_resources.py` | **技能资源**。技能所需的文件、图片、模板等资源 |
| `skills.py` | **技能管理**。技能的注册、发现、安装和卸载 |
| `statistics.py` | **统计报表**。项目/员工的使用统计、趋势分析、可视化数据 |
| `usage_records.py` | **使用记录**。API 调用、MCP 请求的详细记录 |
| `users.py` | **用户管理**。系统用户的 CRUD、密码管理 |
| `websocket_test.py` | **WebSocket 测试**。WebSocket 连接的调试工具 |

### 1.6 `services/` — 业务服务层

| 文件 | 说明 |
|---|---|
| `agent_runtime_v2/` | **Agent 运行时 v2**。核心 AI 执行引擎，包含：<br>• `runtime.py` — 运行时主循环，管理 Agent 生命周期<br>• `query_engine.py` — 统一查询引擎，解析和路由查询请求<br>• `tool_execution_runner.py` — 工具执行调度器<br>• `tool_result_normalizer.py` — 工具结果标准化 |
| `project_chat_execution_service.py` | **项目聊天执行服务**。处理项目内的对话和执行请求 |
| `operation_wait_task_service.py` | **操作等待任务服务**。管理异步任务的等待和状态轮询 |
| `tool_executor.py` | **工具执行器**。统一管理所有可用工具的执行 |

### 1.7 `schemas/` — 数据库 Schema

数据库表结构的 SQLAlchemy 定义，与 `models/db_models.py` 配合使用。

### 1.8 `ws/` — WebSocket

WebSocket 连接管理，支持实时推送（对话消息、任务状态更新等）。

### 1.9 `tasks/` — 后台任务

Celery/BackgroundTasks 异步任务定义，如定时清理、统计汇总等。

### 1.10 `db_utils/` — 数据库工具

数据库连接池管理、查询构建器、事务管理辅助函数。

### 1.11 `utils/` — 通用工具

日期处理、字符串工具、文件操作等通用辅助函数。

### 1.12 `tests/` — 测试用例

| 文件 | 说明 |
|---|---|
| `test_agent_runtime_v2.py` | Agent 运行时 v2 的单元测试 |
| `test_project_chat_response_task_tree_guard.py` | 项目聊天响应和任务树守卫测试 |
| `test_statistics_routes.py` | 统计路由的 API 测试 |
| `test_unit.py` | 通用单元测试 |

### 1.13 `mcp/` — 内置 MCP 端点

直接在 FastAPI 中挂载的 MCP 服务端点，包括：
- `/mcp/query` — 统一查询 MCP
- `/mcp/projects/{project_id}` — 项目 MCP
- `/mcp/employees/{employee_id}` — 员工 MCP

### 1.14 `migrations/` — 数据库迁移

Alembic 或自定义迁移脚本的目录。

---

## 二、前端 `web-admin/frontend/`

### 2.1 根目录文件

| 文件 | 说明 |
|---|---|
| `package.json` | npm 包配置。依赖：Vue 3、Element Plus、Pinia、Vue Router、Axios、Vite 等 |
| `vite.config.ts` | **Vite 构建配置**。定义代理规则（API 代理到后端）、别名、插件配置 |
| `index.html` | 入口 HTML 文件 |
| `nginx.conf` | **Nginx 配置**。前端容器内的反向代理配置，处理 SPA 路由和 API 代理 |
| `tsconfig.json` | TypeScript 编译配置 |

### 2.2 `src/` — 源代码

| 目录/文件 | 说明 |
|---|---|
| `main.ts` | **前端入口**。创建 Vue app、挂载 Pinia/Router、注册 Element Plus、启动应用 |
| `App.vue` | 根组件，包含全局布局和路由视图 |
| `router/` | **Vue Router 路由配置**。定义页面路由映射、导航守卫 |
| `stores/` | **Pinia 状态管理**。包含用户信息、项目列表、员工配置等全局状态 |
| `api/` | **API 请求层**。Axios 实例封装，包含所有后端 API 的调用函数（对应 routers/ 的 28 个模块） |
| `views/` | **页面视图组件**。包括：<br>• `projects/` — 项目管理页面（列表、详情、聊天 `ProjectChat.vue`）<br>• `employees/` — 员工管理页面<br>• `system/` — 系统管理页面（统计面板 `StatisticsDashboard.vue` 等）<br>• `login/` — 登录页面 |
| `components/` | **公共组件**。可复用的 UI 组件（表格、表单、对话框等） |
| `layouts/` | **布局组件**。主布局、侧边栏、顶栏等 |
| `utils/` | **工具函数**。日期格式化、请求拦截、权限判断等 |

---

## 三、Docker Compose 编排

| 文件 | 说明 |
|---|---|
| `docker-compose.yml` | **开发环境编排**。hot-reload、调试端口、本地卷挂载 |
| `docker-compose.test.yml` | **测试环境编排**。CI/CD 集成、自动化测试 |
| `docker-compose.prod.yml` | **生产环境编排**。优化镜像、资源限制、健康检查 |
| `docker-compose.base.yml` | **基础服务编排**。PostgreSQL + Redis 的独立部署 |
