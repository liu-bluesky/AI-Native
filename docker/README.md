# Docker 使用说明

补充学习材料：

- `README.quick.md`：最短命令速查，适合日常直接照着执行。
- `README.learn.md`：面向日常使用的通俗解读，适合复习 `docker/` 目录里每个文件的作用和常见命令。
- `README.deploy-test.md`：按“本地打包 -> 备份 -> 上传 -> 服务器恢复 -> 验收”顺序整理的一次性实操清单，适合首次完整测试。
- `../web-admin/api/core/sql_migrations/`：PostgreSQL 正式 schema migration 目录；`docker/init/` 只负责首次建库 bootstrap。

## 目录说明

- `docker-compose.yml`：本地一键启动编排（`postgres` + `redis` + `api` + `frontend`）
- `.env`：本地 Docker 配置
- `.env.example`：Docker 配置模板
- `Dockerfile.api`：后端 API 镜像构建
- `Dockerfile.frontend`：前端镜像构建
- `nginx.conf`：前端 Nginx 反向代理配置
- `compose.prod.yml`：服务器镜像部署模板
- `.env.prod.example`：服务器镜像部署环境变量模板
- `deploy.sh`：生产部署、卷备份恢复、数据库备份恢复脚本
- `init/`：PostgreSQL 初始化脚本目录（首次建库时自动执行）

隔离说明：

- Compose 项目名固定为 `ai_employee`（见 `name: ai_employee`）
- PostgreSQL 数据卷固定为 `ai_employee_pgdata`
- 这样可避免与其他目录名同为 `docker` 的项目发生卷/网络命名冲突

## 前置条件

- 已安装 Docker Desktop（或 Docker Engine + Docker Compose）

## 快速启动

```bash
cd /Users/liulantian/self/ai设计规范/docker
docker compose up -d
```

## 服务器部署（镜像方式）

生产环境有两种常见方式：

- 仓库拉取模式：服务器自己从镜像仓库 `pull`
- 离线导入模式：本地先 `docker save`，再把 tar 上传到服务器 `docker load`

两种方式都使用 `compose.prod.yml` 和 `.env.prod`，差别只在于镜像来源，以及最终是执行 `deploy` 还是 `up`。

### 方式 A：服务器直接拉镜像仓库

```bash
cd /path/to/ai-employee/docker
cp .env.prod.example .env.prod
chmod +x deploy.sh
docker compose --env-file .env.prod -f compose.prod.yml pull
docker compose --env-file .env.prod -f compose.prod.yml up -d
```

`compose.prod.yml` 的特点：

- `api` / `frontend` 使用 `image:`，不依赖服务器本地源码构建
- PostgreSQL、API 运行时数据、技能知识目录都走 Docker volume
- `mcp-skills/knowledge` 单独持久化，避免上传技能跟着容器一起丢失

生产环境至少要改：

- `API_IMAGE`
- `FRONTEND_IMAGE`
- `DB_PASSWORD`
- `HOST_API_PORT`
- `HOST_FRONTEND_PORT`

也可以直接用脚本：

```bash
cd /path/to/ai-employee/docker
cp .env.prod.example .env.prod
chmod +x deploy.sh
./deploy.sh deploy
```

如需复用到不同环境，可额外覆盖：

```bash
POSTGRES_CONTAINER=ai-employee-postgres \
SKILL_VOLUME=ai_employee_mcp_skills_knowledge_prod \
API_DATA_VOLUME=ai_employee_api_data_prod \
./deploy.sh backup-skill-volume
```

### 方式 B：上传镜像 tar 到服务器离线部署

适用场景：

- 服务器不方便登录镜像仓库
- 你已经在本地执行过 `docker save`
- 你准备把 `ai_employee-api:latest`、`ai_employee-frontend:latest` 这类本地镜像直接带到服务器

先把这些文件上传到服务器项目根目录，例如：

- `ai_employee-api_latest.tar`
- `ai_employee-frontend_latest.tar`
- `ai_employee-docker-deploy-files.tar.gz`

然后执行：

```bash
cd /path/to/ai-employee
mkdir -p docker
tar -xzf ai_employee-docker-deploy-files.tar.gz -C docker
docker load -i ai_employee-api_latest.tar
docker load -i ai_employee-frontend_latest.tar

cd docker
cp .env.prod.example .env.prod
chmod +x deploy.sh
```

把 `.env.prod` 至少改成：

```env
API_IMAGE=ai_employee-api:latest
FRONTEND_IMAGE=ai_employee-frontend:latest
DB_PASSWORD=replace-with-a-strong-password
HOST_API_PORT=8000
HOST_FRONTEND_PORT=3000
```

然后启动：

```bash
./deploy.sh up
./deploy.sh ps
```

这里要特别注意：

- 离线导入模式不要直接执行 `./deploy.sh deploy`
- `deploy` 会先做 `pull`，如果 `.env.prod` 里还是默认占位值 `your-registry/...`，会直接报镜像不存在
- 离线模式应先 `docker load`，再把 `API_IMAGE` / `FRONTEND_IMAGE` 改为本机已有 tag，最后执行 `./deploy.sh up`

如果服务器连 Docker Hub 也拉不了，还要额外把基础镜像一起导入：

- `postgres:17`
- `redis:7-alpine`

查看状态：

```bash
docker compose ps
```

查看日志：

```bash
docker compose logs -f
```

## 访问地址

- 前端：`http://localhost:3000`
- API：`http://localhost:8000`
- PostgreSQL：`localhost:5432`
- Redis：仅在 Compose 内网暴露，默认不映射宿主机端口，避免与已有本地 Redis 冲突

## 常用命令

只启动基础依赖：

```bash
docker compose up -d postgres redis
```

重启单个服务：

```bash
docker compose restart api
docker compose restart frontend
docker compose restart postgres
```

停止服务（保留数据卷）：

```bash
docker compose down
```

停止并清空数据库卷（危险）：

```bash
docker compose down -v
```

## 初始化 SQL

把 `.sql` 文件放到 `docker/init/`，例如：

`docker/init/001_init.sql`

注意：仅在 PostgreSQL 数据卷首次初始化时执行。已初始化后新增 SQL 不会自动回放。

正式 schema 变更请改：

- `web-admin/api/core/sql_migrations/*.sql`

并执行：

```bash
cd /Users/liulantian/self/ai设计规范/web-admin/api
python scripts/migrate_db.py
```

## 环境变量

先复制模板：

```bash
cp docker/.env.example docker/.env
```

再编辑 `docker/.env`：

- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`
- `DB_PORT`
- `REDIS_DB`
- `CORE_STORE_BACKEND`（`postgres` 或 `json`）
- `USAGE_STORE_BACKEND`（`postgres` 或 `sqlite`）
- `AUTO_RUN_DB_MIGRATIONS`（`true` 或 `false`）

改完后建议重建：

```bash
docker compose down
docker compose up -d --build
```

## 注意事项

- 存储后端可通过环境变量切换：
- `CORE_STORE_BACKEND=postgres|json`
- `USAGE_STORE_BACKEND=postgres|sqlite`
- `AUTO_RUN_DB_MIGRATIONS=true|false`
- `api` 服务容器内部统一使用 `DATABASE_URL` 连接 PostgreSQL；`DB_*` 变量只用于 Compose 拼接数据库连接和初始化 Postgres 容器。
- `api` 服务容器内部统一连接 `redis:6379`；默认不暴露宿主机 Redis 端口，因此不会和现有 `ai-redis` 或本机 Redis 抢占 `6379`。
- 正式导出依赖 `FFmpeg`；`docker/Dockerfile.api` 已内置安装，修改镜像后需执行 `docker compose up -d --build` 让 API 容器生效。
- `api` 服务默认会把宿主机 `~/.ai-native/web-admin-api` 挂载到容器内 `/root/.ai-native/web-admin-api`。这样素材库上传文件、旁白/BGM、正式导出产物会和本地开发使用同一份数据目录，避免容器里找不到宿主机已有素材文件。
- `compose.prod.yml` 默认改用 Docker volume 持久化 `/root/.ai-native/web-admin-api` 和 `/app/mcp-skills/knowledge`；前者保存 API 运行时文件，后者保存技能元数据与技能包目录。
- PostgreSQL migration 是否自动补跑由 `AUTO_RUN_DB_MIGRATIONS` 控制；为 `true` 时会在 API 启动和 Postgres store 建连时自动补跑；需要手动补跑时使用 `python scripts/migrate_db.py`。
- `web-admin/api` 本地开发默认值已调整为 PostgreSQL：
- 默认后端：`CORE_STORE_BACKEND=postgres`、`USAGE_STORE_BACKEND=postgres`
- 默认连接：`postgresql://admin:changeme@127.0.0.1:5432/ai_employee`
- `restart: unless-stopped` 会导致 Docker 重启后自动拉起服务；若不希望自动启动，可手动改为 `restart: "no"` 并重建容器。

## 上传技能如何迁移

先说结论：上传技能不是靠镜像迁移，而是靠持久化数据迁移。

当前上传技能分成两部分：

- 技能元数据：`skills` / `skill_bindings`，默认随 PostgreSQL 迁移
- 技能包文件本体：保存在 `mcp-skills/knowledge/skill-packages/`，需要单独持久化或备份

如果你使用 `compose.prod.yml`：

- PostgreSQL 在卷 `ai_employee_pgdata_prod`
- API 运行时数据在卷 `ai_employee_api_data_prod`
- 技能知识目录在卷 `ai_employee_mcp_skills_knowledge_prod`

这样容器重建后，上传的技能不会丢。

### 备份技能卷

```bash
cd /path/to/ai-employee/docker
mkdir -p backup/mcp-skills-knowledge
docker run --rm \
  -v ai_employee_mcp_skills_knowledge_prod:/from \
  -v "$(pwd)/backup/mcp-skills-knowledge:/to" \
  alpine sh -c 'cp -a /from/. /to/'
```

### 恢复技能卷

```bash
cd /path/to/ai-employee/docker
docker run --rm \
  -v ai_employee_mcp_skills_knowledge_prod:/to \
  -v "$(pwd)/backup/mcp-skills-knowledge:/from" \
  alpine sh -c 'cp -a /from/. /to/'
```

### 备份 PostgreSQL

```bash
docker exec ai-employee-postgres pg_dump -U ${DB_USER:-admin} ${DB_NAME:-ai_employee} > backup/ai_employee.sql
```

### 恢复 PostgreSQL

```bash
cat backup/ai_employee.sql | docker exec -i ai-employee-postgres psql -U ${DB_USER:-admin} -d ${DB_NAME:-ai_employee}
```

### 从旧开发容器导出已上传技能

如果你之前已经在旧容器里上传过技能，但还没有做卷持久化，可以先导出旧容器里的技能目录：

```bash
docker cp ai-employee-api:/app/mcp-skills/knowledge ./backup/mcp-skills-knowledge-from-container
```

再把其中内容恢复到 `ai_employee_mcp_skills_knowledge_prod` 卷。

## Usage 数据迁移（SQLite -> PostgreSQL）

```bash
cd /Users/liulantian/self/ai设计规范/web-admin/api
python scripts/migrate_usage_to_pg.py \
  --sqlite-path ~/.ai-native/web-admin-api/usage.db \
  --database-url postgresql://admin:changeme@localhost:5432/ai_employee
```

说明：`web-admin/api/data/` 已废弃，API 本地运行时数据默认改为 `~/.ai-native/web-admin-api/`，也可通过 `API_DATA_DIR` 覆盖。

## Core 数据迁移（JSON/SQLite -> PostgreSQL）

```bash
cd /Users/liulantian/self/ai设计规范/web-admin/api
python scripts/migrate_core_to_pg.py \
  --database-url postgresql://admin:changeme@localhost:5432/ai_employee
```
