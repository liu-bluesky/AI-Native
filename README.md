# AI 员工工厂

AI 员工工厂是一个 MCP-first 的 AI-Native 项目执行与员工管理平台。它把项目、员工、技能、规则、记忆、任务树、工作会话、运行时工具和交付验证统一沉淀为可被外部 AI、IDE、CLI、桌面端和后台服务调用的能力。

当前仓库包含三条主线：

- `web-admin/`：FastAPI 后端、Vue 管理台和 Tauri 桌面端入口。
- `mcp-*`：技能、规则、记忆、人设、进化和同步等独立 MCP 服务。
- `.ai-employee/`：当前工作区的统一查询 MCP 本地状态、需求记录和技能副本。

平台主能力优先通过 MCP tools/resources/prompts、项目 API 和任务树工作流暴露；Web 管理台主要承担配置、运营、调试、观测和人工确认。

## 核心能力

### 项目与员工

- 管理项目、项目成员、项目素材、项目规则、项目经验和任务执行记录。
- 管理 AI 员工的人设、技能、规则、记忆、可见范围和使用统计。
- 支持项目级 MCP、员工级 MCP 和统一查询 MCP，让外部 Agent 围绕项目上下文执行任务。
- 通过工作会话、任务树和验证记录沉淀可恢复、可审计的交付过程。

### 统一查询 MCP

统一查询 MCP 是推荐的聚合入口，挂载在：

```text
/mcp/query
```

它负责：

- 定位项目、员工、规则和技能上下文。
- 读取项目手册、员工手册、规则正文和经验规则。
- 分析任务、生成执行计划、绑定任务树和维护工作会话。
- 维护本地 `.ai-employee/requirements/<project_id>/` 需求对象。
- 同步工作事实、会话事件、检查点和交付报告。

统一查询 MCP 的原则是：显式绑定、本地优先、任务树闭环、验证收尾。

### 技能、规则与记忆

平台内置多类能力服务：

| 目录 | 主要职责 |
|---|---|
| `mcp-skills/` | 技能查询、安装、卸载、资源管理和系统技能包知识库。 |
| `mcp-rules/` | 规则查询、提交、演化和反馈统计。 |
| `mcp-memory/` | 记忆保存、召回、压缩和身份信号。 |
| `mcp-persona/` | 人设、语气、风格、快照和漂移评估。 |
| `mcp-evolution/` | 使用模式分析、候选规则、自动进化和报告。 |
| `mcp-sync/` | 更新推送、状态同步和 Agent 通知。 |

系统技能包位于 `mcp-skills/knowledge/skill-packages/`。当前工作区同步后的统一查询工作流技能位于 `.ai-employee/skills/query-mcp-workflow/`。

### Web 管理台

`web-admin/` 是平台的管理台与 API 网关：

- 后端：FastAPI、Pydantic、FastMCP、PostgreSQL、Redis、PyJWT。
- 前端：Vue 3、Vue Router、Element Plus、Vite、Axios、ECharts。
- 桌面端：Tauri 2，入口位于 `web-admin/frontend/src-tauri/`。

管理台覆盖项目、员工、技能、规则、记忆、人设、模型供应商、系统配置、机器人连接器、MCP 监控、任务树、工作会话、统计看板、反馈升级、短片工作室和桌面本地智能体相关能力。

## 当前执行架构

### 本地智能体与后端系统智能体

当前文档统一使用下面两个术语：

- 桌面本地智能体：运行在用户电脑上的本地 runtime，入口在 Tauri / native bridge，负责本机文件、命令、权限、本地 requirement 和外部 CLI 执行。
- 后端系统智能体：运行在后端 API / Agent Runtime / 项目聊天链路中的旧执行链路，存量代码用于迁移、兼容清理和删除准备。

机器人、项目聊天和桌面端执行的目标链路是：

```text
后端记录/排队
  -> 桌面端本地智能体领取执行
  -> 本机工具和外部 Agent 运行
  -> 回写消息、任务树、工作事实和验证结果
```

如果桌面端接管队列尚未接通，应显式标记为迁移缺口，不应静默回退到旧后端系统对话。

### 任务执行链路

项目执行链路由以下模块组成：

| 模块 | 关键位置 | 说明 |
|---|---|---|
| 工作流状态识别 | `web-admin/api/services/assistant/` | 识别查询、开发、文档、修复、自动化等任务类型，并生成 `assistant_workflow` 状态。 |
| 能力路由 | `assistant_capability_router_service.py`、`runtime/tool_registry.py` | 在本地连接器、项目工具、技能代理和 MCP 能力之间选择执行来源。 |
| 统一查询 MCP | `services/mcp/dynamic_mcp_apps_query.py` | 绑定项目、读取上下文、维护 requirement、任务树和工作事实。 |
| 项目上下文 | 项目 MCP、员工 MCP、规则 MCP、技能 MCP | 聚合项目手册、员工手册、规则、技能、经验和历史记忆。 |
| 任务树闭环 | `services/chat/project_chat_task_tree.py`、query MCP 工具 | 开始节点、完成节点、写入验证结果并归档。 |
| Agent Runtime v2 | `web-admin/api/services/agent_runtime/` | 管理 TaskRun、事件、转录、工具调用、权限、恢复和完成策略。 |
| 桌面本地执行 | `web-admin/frontend/src-tauri/` | 提供本机工作区、命令、权限、外部 Agent 会话和审计事件能力。 |

整体链路：

```text
用户需求
  -> 工作流状态识别
  -> 能力路由
  -> 统一查询 MCP / 项目 MCP 聚合上下文
  -> 任务树与本地 requirement 绑定
  -> Agent Runtime v2 / 桌面本地智能体 / 项目工具执行
  -> 权限、信任、验证和完成策略检查
  -> 工作事实、事件日志、任务树归档和交付报告
```

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3、Vue Router 4、Element Plus、Vite 5、Axios、ECharts、Marked、xlsx |
| 桌面端 | Tauri 2、Rust、native bridge、workspace runner |
| 后端 API | Python 3.10+、FastAPI、Pydantic、Uvicorn、PyJWT、psycopg、Redis、structlog |
| MCP | FastMCP、动态 MCP proxy、独立 MCP 服务 |
| 数据 | PostgreSQL 为主，JSON store 兼容，独立 MCP 服务保留 SQLite/文件知识库 |
| 部署 | Docker Compose、本地直跑、远程 Docker 发布脚本 |
| 本地工作流状态 | `.ai-employee/query-mcp/`、`.ai-employee/requirements/<project_id>/` |

## 快速启动

### 本地后端

```bash
cd web-admin/api
cp .env.example .env
uv sync
uv run python init_admin.py
uv run python server.py
```

如果不用 `uv`，也可以使用可编辑安装：

```bash
cd web-admin/api
pip install -e .
python init_admin.py
python server.py
```

后端默认监听：

```text
http://localhost:8000
```

### 本地前端

```bash
cd web-admin/frontend
npm install
npm run dev
```

前端开发服务器默认通过 Vite 代理访问后端 `8000` 端口。常用前端环境变量：

```env
VITE_API_PROXY_TARGET=http://127.0.0.1:8000
VITE_SHOW_LOCAL_RUNTIME_SETTINGS=true
```

### 桌面端

```bash
cd web-admin/frontend
npm install
npm run tauri:dev
```

桌面端契约检查：

```bash
cd web-admin/frontend
npm run tauri:check
```

Rust 侧检查：

```bash
cd web-admin/frontend/src-tauri
cargo fmt --check
cargo check
```

### Docker 启动

```bash
cd docker
cp .env.example .env
docker compose up -d --build
```

默认访问地址：

```text
前端：http://localhost:3000
API：http://localhost:8000
```

`docker/docker-compose.yml` 会启动 PostgreSQL、Redis、API 和前端容器，并挂载 CLI toolchain：

```text
${HOME}/.ai-employee/cli-toolchain -> /app/.ai-employee/cli-toolchain
```

## 配置

### 后端配置

本地直跑后端读取：

- `web-admin/api/.env`
- `web-admin/api/.env.local`
- 真实环境变量，优先级最高

关键变量：

| 变量 | 说明 |
|---|---|
| `API_HOST` / `API_PORT` / `API_RELOAD` | Uvicorn 监听与 reload。 |
| `API_CORS_ALLOW_ORIGINS` | CORS origin，逗号分隔。 |
| `CORE_STORE_BACKEND` | 核心 store 后端，默认 `postgres`。 |
| `USAGE_STORE_BACKEND` | usage store 后端，默认 `postgres`。 |
| `DATABASE_URL` | PostgreSQL 连接串，应用内部优先使用。 |
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` | `DATABASE_URL` 缺失时的兼容拼接来源。 |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` | Redis 配置。 |
| `API_DATA_DIR` | API 数据目录，默认 `~/.ai-native/web-admin-api`。 |
| `CLI_PLUGIN_TOOLCHAIN_ROOT` | CLI 插件工具链目录，默认项目根 `.ai-employee/cli-toolchain`。 |
| `AUTO_RUN_DB_MIGRATIONS` | API 启动时是否自动执行 SQL 迁移。 |
| `STUDIO_EXPORT_WORKER_ENABLED` | 短片导出和项目经验总结 worker。 |
| `FEISHU_BOT_LONG_CONNECTION_WORKER_ENABLED` | 飞书机器人长连接 worker。 |

### Docker 配置

Docker 配置位于 `docker/.env`，用于 Compose 级别数据库、Redis、镜像和端口设置。

生产编排文件是：

```text
docker/compose.prod.yml
```

生产方式要求传入镜像：

```env
API_IMAGE=ai_employee-api:latest
FRONTEND_IMAGE=ai_employee-frontend:latest
DB_PASSWORD=replace-with-a-strong-password
HOST_API_PORT=8000
HOST_FRONTEND_PORT=3000
```

生产卷包括：

- `ai_employee_pgdata_prod`
- `ai_employee_api_data_prod`
- `ai_employee_cli_toolchain_prod`
- `ai_employee_mcp_skills_knowledge_prod`

## MCP 入口

Web-Admin API 挂载 5 个动态 MCP proxy：

| 路径 | 说明 |
|---|---|
| `/mcp/query` | 统一查询 MCP，聚合项目、员工、规则、任务树和工作轨迹。 |
| `/mcp/projects/{project_id}` | 项目 MCP。 |
| `/mcp/employees/{employee_id}` | 员工 MCP。 |
| `/mcp/skills/{skill_id}` | 技能 MCP。 |
| `/mcp/rules/{rule_id}` | 规则 MCP。 |

相关实现集中在：

```text
web-admin/api/services/mcp/
```

常用文件：

- `dynamic_mcp_runtime.py`
- `dynamic_mcp_apps_query.py`
- `dynamic_mcp_apps_project.py`
- `dynamic_mcp_apps_employee.py`
- `dynamic_mcp_skill_executor.py`
- `dynamic_mcp_skill_proxies.py`
- `dynamic_mcp_context.py`
- `dynamic_mcp_collaboration.py`
- `query_mcp_project_state.py`

## 项目结构

```text
ai-employee/
├── web-admin/                 # Web 管理台：FastAPI API + Vue 前端 + Tauri 桌面端
├── mcp-skills/                # 技能 MCP 服务与系统技能包知识库
├── mcp-rules/                 # 规则 MCP 服务
├── mcp-memory/                # 记忆 MCP 服务
├── mcp-persona/               # 人设 MCP 服务
├── mcp-evolution/             # 进化 MCP 服务
├── mcp-sync/                  # 同步 MCP 服务
├── docker/                    # Docker Compose、镜像构建和发布文档
├── remote-docker-deploy/      # 远程 Docker 发布、数据同步和回滚脚本
├── docs/                      # 产品、架构、专项方案和历史设计文档
├── codeDocs/                  # 当前代码结构文档
├── rules/                     # 仓库级 Markdown 规则
├── agents/                    # 仓库级专用 Agent 角色说明
├── skills/                    # 本地/宿主技能目录
├── assets/                    # 静态资源
├── feishu-archive-upload/     # 飞书归档上传相关资产
├── .ai-employee/              # 本地 query-mcp 状态、requirement 和技能副本
├── AGENTS.md                  # Codex/Agent 接入当前项目的强制规则
├── CLAUDE.md                  # Claude Code 入口说明
├── HERMES.md                  # Hermes 入口说明
├── README.md                  # 项目主说明
└── LICENSE
```

### `web-admin/api/`

```text
web-admin/api/
├── server.py                  # API 入口，转发到 core.server
├── pyproject.toml             # 后端依赖与 pytest 配置
├── core/                      # 配置、认证、依赖、迁移、权限、Redis、可观测性
├── core/sql_migrations/       # PostgreSQL SQL 迁移
├── routers/                   # FastAPI 路由模块
├── services/                  # 业务服务、动态 MCP、Agent Runtime、连接器、后台任务
├── stores/                    # JSON/PostgreSQL store 实现与工厂
├── models/                    # 请求、响应、数据库模型
├── scripts/                   # 启停、迁移、初始化、修复脚本
└── tests/                     # pytest 测试
```

### `web-admin/frontend/`

```text
web-admin/frontend/
├── package.json
├── vite.config.js
├── index.html
├── src/                       # Vue 应用
└── src-tauri/                 # Tauri 桌面端
```

桌面端核心文件：

- `src-tauri/src/main.rs`
- `src-tauri/src/liuagent_core/`
- `src-tauri/tauri.conf.json`
- `src-tauri/check-tauri-shell.mjs`

### `.ai-employee/`

`.ai-employee/` 是当前工作区的本地运行状态目录，不能用其他子目录里的同名目录替代。

| 路径 | 说明 |
|---|---|
| `.ai-employee/skills/query-mcp-workflow/` | 本地统一查询 MCP 工作流技能副本。 |
| `.ai-employee/query-mcp/active-sessions/` | 每个 CLI 会话的 canonical 本地状态。 |
| `.ai-employee/query-mcp/session-history/` | 项目 + 会话历史状态。 |
| `.ai-employee/requirements/<project_id>/` | 每个需求的本地 requirement 对象。 |
| `.ai-employee/operation-wait-tasks/` | 操作等待任务状态。 |
| `.ai-employee/cli-toolchain/` | CLI 插件/工具链根目录。 |

## 远程发布

远程发布工具位于：

```text
remote-docker-deploy/
```

主要脚本：

| 文件 | 说明 |
|---|---|
| `remote_docker_deploy.py` | 主编排器，支持 `package`、`upload`、`remote`、`rollback` 等阶段。 |
| `package_deploy_artifacts.sh` | 本地构建并打包离线镜像 tar，或 remote-build 源码包。 |
| `upload_deploy_artifacts.sh` | 上传产物到远程服务器，不执行部署。 |
| `update_remote_stack.sh` | 远端预检查、备份、`docker load/build` 和服务更新。 |
| `sync_postgres_data.py` | 将本地 PostgreSQL 业务表同步到远端。 |
| `sync_resource_visibility.py` | 同步员工、规则、技能的可见范围。 |

示例：

```bash
python3 remote-docker-deploy/remote_docker_deploy.py --profile prod
```

也可以分阶段执行：

```bash
./remote-docker-deploy/package_deploy_artifacts.sh --profile prod
./remote-docker-deploy/upload_deploy_artifacts.sh --profile prod
./remote-docker-deploy/update_remote_stack.sh --profile prod
```

## 开发约定

- 新能力优先设计为 MCP tool/resource/prompt、项目 API 或可追踪的任务树能力，再考虑管理台页面。
- 涉及项目执行、协作、恢复和交付时，应维护 requirement、工作会话、任务树和验证结果。
- 修改后端代码前阅读 `rules/backend.md`。
- 修改前端代码前阅读 `rules/frontend.md`。
- 修改 MCP 服务前阅读 `rules/mcp-service.md`。
- 涉及跨层架构、权限边界或数据流时阅读 `rules/architecture.md`。
- 当前事实以源码和 `codeDocs/` 为准；历史方案文档只作为背景参考。

## 常用检查

后端：

```bash
cd web-admin/api
uv run pytest
```

前端：

```bash
cd web-admin/frontend
npm run build
npm run test:chat-transport
npm run test:local-liuagent-chat
npm run test:pause-state
```

桌面端：

```bash
cd web-admin/frontend
npm run tauri:check
cd src-tauri
cargo fmt --check
cargo check
```

## 文档入口

- [代码文档索引](codeDocs/README.md)
- [目录结构与模块边界](codeDocs/directory-structure.md)
- [Web-Admin 管理台](codeDocs/web-admin.md)
- [MCP 服务](codeDocs/mcp-services.md)
- [部署、配置与规则体系](codeDocs/deploy-and-config.md)
- [Docker 使用说明](docker/README.md)
- [远程 Docker 发布工具](remote-docker-deploy/README.md)
- [编码规范](rules/)

## License

MIT
