# Docker 使用说明

补充学习材料：

- `README.quick.md`：最短命令速查，适合日常直接照着执行。
- `README.learn.md`：面向日常使用的通俗解读，适合复习 `docker/` 目录里每个文件的作用和常见命令。
- `../web-admin/api/core/sql_migrations/`：PostgreSQL 正式 schema migration 目录；`docker/init/` 只负责首次建库 bootstrap。

## 目录说明

- `docker-compose.yml`：本地一键启动编排（`postgres` + `redis` + `api` + `frontend`）
- `.env`：本地 Docker 配置
- `.env.example`：Docker 配置模板
- `Dockerfile.api`：后端 API 镜像构建
- `Dockerfile.frontend`：前端镜像构建
- `nginx.conf`：前端 Nginx 反向代理配置
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

改完后建议重建：

```bash
docker compose down
docker compose up -d --build
```

## 注意事项

- 存储后端可通过环境变量切换：
- `CORE_STORE_BACKEND=postgres|json`
- `USAGE_STORE_BACKEND=postgres|sqlite`
- `api` 服务容器内部统一使用 `DATABASE_URL` 连接 PostgreSQL；`DB_*` 变量只用于 Compose 拼接数据库连接和初始化 Postgres 容器。
- `api` 服务容器内部统一连接 `redis:6379`；默认不暴露宿主机 Redis 端口，因此不会和现有 `ai-redis` 或本机 Redis 抢占 `6379`。
- 正式导出依赖 `FFmpeg`；`docker/Dockerfile.api` 已内置安装，修改镜像后需执行 `docker compose up -d --build` 让 API 容器生效。
- `api` 服务默认会把宿主机 `~/.ai-native/web-admin-api` 挂载到容器内 `/root/.ai-native/web-admin-api`。这样素材库上传文件、旁白/BGM、正式导出产物会和本地开发使用同一份数据目录，避免容器里找不到宿主机已有素材文件。
- PostgreSQL migration 会在 API 启动和 Postgres store 建连时自动补跑；需要手动补跑时使用 `python scripts/migrate_db.py`。
- `web-admin/api` 本地开发默认值已调整为 PostgreSQL：
- 默认后端：`CORE_STORE_BACKEND=postgres`、`USAGE_STORE_BACKEND=postgres`
- 默认连接：`postgresql://admin:changeme@127.0.0.1:5432/ai_employee`
- `restart: unless-stopped` 会导致 Docker 重启后自动拉起服务；若不希望自动启动，可手动改为 `restart: "no"` 并重建容器。

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
