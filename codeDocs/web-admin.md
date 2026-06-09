# Web-Admin 管理台

> 更新日期：2026-06-04

`web-admin/` 是平台的配置、运营、调试和可视化入口，由 FastAPI 后端和 Vue 3 前端组成。平台主能力仍按 MCP-first 设计，Web 管理台负责把项目、员工、技能、规则、记忆、任务树、运行时和系统配置可视化。

## 后端总览

```text
web-admin/api/
├── server.py                 # 入口：from core.server import *
├── pyproject.toml            # FastAPI、FastMCP、psycopg、Redis、PyJWT 等依赖
├── core/
├── core/sql_migrations/
├── routers/
├── services/
├── stores/
├── models/
├── scripts/
└── tests/
```

### 应用入口

`web-admin/api/server.py` 只导出 `core.server`。实际应用工厂在 `web-admin/api/core/server.py`：

- 创建 `FastAPI(title="AI Employee Factory", version="0.1.0")`。
- 配置 CORS。
- 启动生命周期任务：
  - 自动执行 PostgreSQL 迁移。
  - `StudioExportBackgroundService`。
  - `ProjectExperienceSummaryBackgroundService`。
  - 飞书机器人长连接 supervisor。
  - 项目聊天实时订阅。
  - 全局助手任务调度器。
- 注册 28 个路由模块。
- 挂载 5 个动态 MCP proxy。
- 为 MCP 客户端探测 OAuth/OIDC well-known 路径返回 204，避免无意义 404。

### `core/`

| 文件 | 说明 |
|---|---|
| `server.py` | FastAPI 应用工厂、路由注册、MCP 挂载、生命周期任务。 |
| `config.py` | 环境变量统一入口。读取 `web-admin/api/.env`、`.env.local` 和真实环境变量。 |
| `auth.py` | JWT、密码哈希、登录认证。 |
| `deps.py` | Store 和权限依赖注入。 |
| `db_migrations.py` | 执行 `core/sql_migrations/` 下的 SQL 迁移。 |
| `data_scope.py` | 数据范围规则。 |
| `ownership.py` | 资源所有权和共享范围。 |
| `role_permissions.py` | 角色权限矩阵。 |
| `redis_client.py` | Redis 客户端封装。 |
| `observability.py` | 结构化日志与观测支持。 |

### SQL 迁移

当前 SQL 迁移位于 `web-admin/api/core/sql_migrations/`：

- `0001_initial_schema.sql`
- `0002_project_experience_summary_jobs.sql`
- `0003_usage_records_enriched.sql`
- `0004_usage_records_prompt_version.sql`
- `0005_bot_connectors.sql`

当 `AUTO_RUN_DB_MIGRATIONS=true` 且 store 使用 PostgreSQL 时，API 启动会自动执行迁移。

## 注册路由

`core/server.py` 当前实际注册这些路由模块：

| 模块 | 主要职责 |
|---|---|
| `init_auth.py` | 首次初始化、初始化状态。 |
| `market.py` | 市场页和插件/资源发现。 |
| `agent_templates.py` | Agent 模板。 |
| `bot_events.py` | 机器人事件入口。 |
| `bot_connectors.py` | 飞书等机器人连接器配置。 |
| `changelog_entries.py` | 更新日志。 |
| `departments.py` | 部门。 |
| `system_config.py` | 系统配置。 |
| `projects.py` | 项目、项目聊天、项目素材、任务树相关接口。 |
| `employees.py` | AI 员工管理、员工详情、员工使用。 |
| `skill_resources.py` | 技能资源。 |
| `skills.py` | 技能管理。 |
| `rules.py` | 规则管理。 |
| `llm_providers.py` | LLM Provider 与模型配置。 |
| `memory.py` | 记忆管理。 |
| `personas.py` | 人设管理。 |
| `evolution.py` | 进化报告、候选规则、反馈演进。 |
| `sync.py` | 同步状态。 |
| `usage.py` | API Key 与使用记录。 |
| `feedback_upgrade.py` | 反馈驱动规则升级。 |
| `users.py` | 用户。 |
| `roles.py` | 角色。 |
| `mcp_modules.py` | MCP 模块元信息。 |
| `mcp_monitor.py` | MCP 监控。 |
| `dictionaries.py` | 字典。 |
| `online_users.py` | 在线用户。 |
| `statistics.py` | 统计看板。 |
| `work_sessions.py` | 工作会话与轨迹。 |

注意：`routers/metrics.py` 文件存在，但当前 `core/server.py` 未注册它。

## 动态 MCP 挂载

Web-Admin API 内部挂载的 MCP proxy：

| 路径 | 来源 |
|---|---|
| `/mcp/query` | `query_mcp_proxy_app` |
| `/mcp/projects/{project_id}` | `project_mcp_proxy_app` |
| `/mcp/employees/{employee_id}` | `employee_mcp_proxy_app` |
| `/mcp/skills/{skill_id}` | `skill_mcp_proxy_app` |
| `/mcp/rules/{rule_id}` | `rule_mcp_proxy_app` |

相关实现集中在 `web-admin/api/services/mcp/`，包括：

- `dynamic_mcp_runtime.py`
- `dynamic_mcp_apps_query.py`
- `dynamic_mcp_apps_project.py`
- `dynamic_mcp_apps_employee.py`
- `dynamic_mcp_skill_executor.py`
- `dynamic_mcp_skill_proxies.py`
- `dynamic_mcp_context.py`
- `dynamic_mcp_collaboration.py`
- `query_mcp_project_state.py`
- `project_mcp_presence.py`

## 业务服务层

`web-admin/api/services/` 当前按职责分组：

| 目录/文件 | 说明 |
|---|---|
| `assistant/` | 全局助手、能力路由、工作流状态和策略。 |
| `chat/` | 项目聊天执行、实时订阅、任务树、工作流状态归档。 |
| `mcp/` | 动态 MCP 工具、资源、代理、审计和项目状态。 |
| `agent_runtime/` | Agent Runtime v2，详见内部 `README.md`。 |
| `runtime/` | 运行时解析、工具注册、provider resolver、prompt assembler。 |
| `connectors/` | 本地连接器、项目主机命令/终端、机器人连接器安装。 |
| `plugins/` | CLI 插件市场、安装任务、profile。 |
| `feishu/` | 飞书机器人、长连接 supervisor、定时提醒、归档写入。 |
| `projects/` | 项目声音库、项目经验总结。 |
| `providers/` | LLM provider、系统语音服务。 |
| `skills/` | 技能导入、技能资源、员工模板、Vett 注册表。 |
| `catalogs/` | 字典、模型类型、聊天参数、外部技能/规则 catalog。 |
| `task_tree_guard/` | 任务树健康、演化和守卫逻辑。 |
| `studio_export_service.py` | 短片工作室导出后台任务。 |
| `operation_wait_task_service.py` | 操作等待任务。 |
| `tool_executor.py` | 通用工具执行器。 |
| `feedback_service.py` | 反馈服务。 |

## Store 层

`web-admin/api/stores/` 同时保留 JSON 和 PostgreSQL 实现：

```text
stores/
├── factory.py
├── mcp_bridge.py
├── json/
└── postgres/
```

典型 store 包括 `project_store`、`employee_store`、`rule_store`、`work_session_store`、`project_chat_store`、`project_material_store`、`local_connector_store`、`llm_provider_store` 等。`core.config` 通过 `CORE_STORE_BACKEND`、`USAGE_STORE_BACKEND` 决定后端存储。

## 后端配置

`core/config.py` 当前关键环境变量：

| 变量 | 默认值/说明 |
|---|---|
| `API_HOST` | 默认 `0.0.0.0` |
| `API_PORT` | 默认 `8000` |
| `API_RELOAD` | 默认 `true` |
| `AUTO_RUN_DB_MIGRATIONS` | 默认 `true` |
| `CORE_STORE_BACKEND` | 默认 `postgres` |
| `USAGE_STORE_BACKEND` | 默认 `postgres` |
| `DATABASE_URL` | 优先使用；缺失时由 `DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME` 拼接；仍缺失则回退本地开发库。 |
| `API_DATA_DIR` | 默认 `~/.ai-native/web-admin-api` |
| `CLI_PLUGIN_TOOLCHAIN_ROOT` | 默认项目根 `.ai-employee/cli-toolchain` |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` | Redis 连接配置。 |
| `STUDIO_EXPORT_WORKER_ENABLED` | 控制导出和经验总结后台 worker。 |
| `FEISHU_BOT_LONG_CONNECTION_WORKER_ENABLED` | 控制飞书长连接 worker。 |

## 前端总览

```text
web-admin/frontend/
├── package.json
├── vite.config.js
├── index.html
├── public/
└── src/
    ├── main.js
    ├── App.vue
    ├── router/index.js
    ├── views/
    ├── components/
    ├── modules/
    ├── utils/
    ├── api/
    └── styles/
```

### 前端依赖

当前 `package.json` 依赖：

- Vue 3、Vue Router 4
- Element Plus、Element Plus Icons
- Axios
- ECharts
- marked
- mammoth、pdfjs-dist、xlsx
- Vite 5 和 `@vitejs/plugin-vue`

### 主要路由

公共路由：

- `/loading`
- `/init`
- `/intro`
- `/market`
- `/updates`
- `/login`
- `/register`

主应用挂载在 `Layout.vue` 下，核心页面包括：

- 工作台：`/workbench`、`/tasks`、`/settings-center`、`/desktop/background`
- AI 对话：`/ai/chat`
- AI 对话设置中心：`/ai/chat/settings/...`
- 用户权限：`/users`、`/departments`、`/roles`、`/user/settings`
- 项目：`/projects`、`/projects/:id`
- 素材创作工作台：`/materials`、`/materials/studio`、`/materials/voices`、`/materials/works`
- 系统：`/system/config`、`/system/bot-connectors`、`/statistics`、`/online-users`、`/mcp-monitor`、`/dictionaries`
- 员工：`/employees`、`/employees/create`、`/employees/:id`
- 技能：`/skills`、`/skill-resources`
- 规则：`/rules`
- 记忆与同步：`/memory/:id`、`/sync/:id`
- 反馈与进化：`/feedback/:id`、`/feedback/:id/batch-analyze`、`/evolution/:id`、`/review/:id`
- LLM：`/llm/providers`
- 使用记录：`/usage/keys`

### 重要前端模块

| 路径 | 说明 |
|---|---|
| `src/views/projects/ProjectChat.vue` | 项目对话和任务树可视化的核心页面。 |
| `src/modules/project-chat/` | 项目聊天设置、常量、高风险规则、任务树状态 hook。 |
| `src/modules/task-tree-feedback/` | 任务树反馈 banner、问题列表和健康状态。 |
| `src/components/AiChatDialog.vue` | AI 对话框。 |
| `src/components/GlobalAiAssistant.vue` | 全局助手。 |
| `src/components/UnifiedMcpAccessDialog.vue` | 统一 MCP 接入弹窗。 |
| `src/components/WorkSessionDetailPanel.vue` | 工作会话详情。 |
| `src/components/project-workspace/` | 项目工作区 UI 组件。 |
| `src/components/studio/` | 短片工作室时间线、预览和菜单组件。 |
| `src/utils/api.js` | Axios/API 基础封装。 |
| `src/utils/auth.js` / `auth-storage.js` | 登录和 token 存储。 |
| `src/utils/permissions.js` | 前端权限判断。 |
| `src/utils/ws-chat.js` | 聊天实时连接。 |
| `src/utils/project-materials.js` | 项目素材工具。 |

## 本地启动

后端：

```bash
cd web-admin/api
uv sync
uv run python init_admin.py
uv run python server.py
```

或使用项目脚本：

```bash
web-admin/api/scripts/start_api_with_runner.sh
```

前端：

```bash
cd web-admin/frontend
npm install
npm run dev
```

Docker 整套启动见 [deploy-and-config.md](./deploy-and-config.md)。
