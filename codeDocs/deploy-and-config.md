# 部署、配置与规则体系

> 更新日期：2026-06-04

## 一、Docker 部署体系

当前 Docker 配置集中在 `docker/`。

### 主要文件

| 文件 | 说明 |
|---|---|
| `docker/docker-compose.yml` | 本地/开发整套服务：PostgreSQL 17、Redis 7、API、Frontend。 |
| `docker/docker-compose.test.yml` | 测试环境编排。 |
| `docker/compose.prod.yml` | 生产编排，使用外部传入的 `API_IMAGE` 和 `FRONTEND_IMAGE`。 |
| `docker/Dockerfile.api` | API 镜像。基于 `python:3.12-slim`，安装 `ffmpeg`，复制 API 和 6 个根目录 MCP 服务。 |
| `docker/Dockerfile.frontend` | 前端镜像。Node 20 构建，Nginx 运行。 |
| `docker/nginx.conf` | Nginx 配置，`/api/` 反代到 `api:8000`，其余走 SPA fallback。 |
| `docker/deploy.sh` / `docker/deploy.ps1` | 本地/服务器部署脚本。 |
| `docker/build-publish-images.sh` | 构建和发布镜像。 |
| `docker/init/001_usage_schema.sql` | 初始化使用记录 schema。 |
| `docker/README*.md` / `docker/部署.md` | 快速开始、生产发布、迁移、测试等说明。 |

### 本地 Compose 服务

`docker/docker-compose.yml` 当前服务：

| 服务 | 镜像/构建 | 说明 |
|---|---|---|
| `postgres` | `postgres:17` | 主数据库，映射 `${DB_PORT:-5432}:5432`，使用 `docker/init` 初始化。 |
| `redis` | `redis:7-alpine` | 缓存和实时/后台能力依赖。 |
| `api` | `docker/Dockerfile.api` | FastAPI API，端口 `8000`。 |
| `frontend` | `docker/Dockerfile.frontend` | Nginx + Vue dist，端口 `3000:80`。 |

本地启动：

```bash
cd docker
cp .env.example .env
docker compose up -d --build
```

默认访问：

- 前端：`http://localhost:3000`
- API：`http://localhost:8000`

### 生产 Compose

`docker/compose.prod.yml` 不在远端直接 build，而是要求传入镜像：

```env
API_IMAGE=ai_employee-api:latest
FRONTEND_IMAGE=ai_employee-frontend:latest
DB_PASSWORD=replace-with-a-strong-password
HOST_API_PORT=8000
HOST_FRONTEND_PORT=3000
```

生产卷：

- `ai_employee_pgdata_prod`
- `ai_employee_api_data_prod`
- `ai_employee_cli_toolchain_prod`
- `ai_employee_mcp_skills_knowledge_prod`

## 二、本地 API 配置

本地直跑 API 读取：

- `web-admin/api/.env`
- `web-admin/api/.env.local`
- 真实环境变量，优先级最高。

关键变量：

| 变量 | 说明 |
|---|---|
| `API_HOST` / `API_PORT` / `API_RELOAD` | Uvicorn 监听和 reload。 |
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

本地直跑：

```bash
cd web-admin/api
cp .env.example .env
uv sync
uv run python init_admin.py
uv run python server.py
```

前端直跑：

```bash
cd web-admin/frontend
npm install
npm run dev
```

## 三、远程 Docker 发布

远程发布工具在 `remote-docker-deploy/`。默认流程支持离线镜像 tar、registry 拉取、remote-build 和回滚。

### 主命令

```bash
python3 remote-docker-deploy/remote_docker_deploy.py \
  --profile prod \
  --remote-deploy-password '你的服务器密码'
```

默认目标由 profile 读取，`README.md` 记录的默认值包括：

- Host: `64.81.113.174`
- User: `root`
- Remote dir: `/www/aiEmployee/docker`
- Compose file: `compose.prod.yml`
- Env file: `.env.prod`
- Delivery mode: `offline`

### 三阶段脚本

| 脚本 | 说明 |
|---|---|
| `package_deploy_artifacts.sh` | 本地构建 API/Frontend 镜像并 `docker save`，或 remote-build 模式下打源码包。 |
| `upload_deploy_artifacts.sh` | 上传产物到远端，不执行远程部署。 |
| `update_remote_stack.sh` | 远端预检查、部署锁、备份、`docker load/build`、执行 `deploy.sh up`。默认带 `--update-db`。 |

分步发布：

```bash
./remote-docker-deploy/package_deploy_artifacts.sh --profile prod
./remote-docker-deploy/upload_deploy_artifacts.sh --profile prod --remote-deploy-password '你的服务器密码'
./remote-docker-deploy/update_remote_stack.sh --profile prod --remote-deploy-password '你的服务器密码'
```

不执行数据库迁移：

```bash
DEPLOY_UPDATE_DB=false ./remote-docker-deploy/update_remote_stack.sh \
  --profile prod \
  --remote-deploy-password '你的服务器密码'
```

### 发布模式

| 模式 | 说明 |
|---|---|
| `offline` | 本地构建镜像并保存为 tar，上传后远端 `docker load`。默认模式。 |
| `registry` | 使用镜像仓库。 |
| `remote-build` | 上传源码到服务器，远端重新 `docker build`。 |

### 回滚

```bash
python3 remote-docker-deploy/remote_docker_deploy.py \
  --profile prod \
  --remote-deploy-password '你的服务器密码' \
  --action rollback \
  --rollback-from backup/auto-deploy-20260326-120000
```

回滚会校验备份、备份当前线上状态、停止 API/Frontend、恢复技能卷/API 数据卷/数据库，然后重新拉起服务。

## 四、数据同步脚本

### 同步资源可见范围

```bash
python3 remote-docker-deploy/sync_resource_visibility.py \
  --profile prod \
  --remote-deploy-password '你的服务器密码'
```

用途：把本地员工、规则、技能的 `created_by`、`share_scope`、`shared_with_usernames` 同步到远程 PostgreSQL。

常用参数：

- `--source auto|docker-postgres|json`
- `--all-users`
- `--dry-run`

### 同步 PostgreSQL 业务数据

```bash
python3 remote-docker-deploy/sync_postgres_data.py \
  --profile prod \
  --remote-deploy-password '你的服务器密码'
```

用途：从本地 `ai-employee-postgres` 同步 public schema 下的业务表到远程 PostgreSQL，默认跳过 `schema_migrations`，执行前会备份远程库。

## 五、规则体系

仓库级 Markdown 规则位于 `rules/`：

| 文件 | 说明 |
|---|---|
| `architecture.md` | 架构规则。 |
| `backend.md` | 后端规则。 |
| `frontend.md` | 前端规则。 |
| `homepage-ui.md` | 官网/首页 UI 规则。 |
| `mcp-service.md` | MCP 服务规则。 |
| `query-mcp-prompt-sync.md` | 统一查询 MCP prompt/技能同步规则。 |
| `ui-design.md` | 项目 UI 设计规则。 |

这些规则和 Web-Admin 中的项目规则、员工规则不是同一层：

- `rules/` 是仓库内静态规则文档。
- `mcp-rules/` 是独立规则 MCP 服务。
- Web-Admin 项目/员工规则通过后端 store、项目 MCP 和员工 MCP 暴露。
- 反馈驱动规则升级由 `feedback_upgrade.py`、`feedback_service.py`、进化页面和候选评审共同承载。

## 六、技能体系

技能来源主要有三类：

| 来源 | 说明 |
|---|---|
| `mcp-skills/knowledge/skill-packages/` | 系统技能包知识库，例如 `query-mcp-workflow`、`db-query`、`vue`、`refactor` 等。 |
| `.ai-employee/skills/query-mcp-workflow/` | 当前项目本地同步的统一查询 MCP 工作流技能副本。 |
| `skills/` + `skills-lock.json` | 宿主技能目录和版本锁，当前主要包含大量飞书 `lark-*` 技能。 |

处理项目任务时，统一查询 MCP 入口会优先使用项目手册、项目规则、员工手册、项目技能代理和本地 requirement 状态；只有项目能力无法覆盖时，再使用通用代码能力补足。

## 七、发布前检查

发布或改配置前建议核对：

- `docker/.env` 或 `.env.prod` 是否包含正确数据库密码和镜像名。
- API 是否能读取目标 `DATABASE_URL`。
- `AUTO_RUN_DB_MIGRATIONS` 是否符合本次发布策略。
- 生产远程发布是否需要 `--update-db`。
- `mcp-skills/knowledge` 是否需要持久化或随镜像更新。
- `CLI_PLUGIN_TOOLCHAIN_ROOT` 是否挂载持久卷。
- 前端构建是否通过 `npm run build`。
- 后端测试是否至少覆盖当前改动风险点。
