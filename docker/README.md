# Docker 使用说明

## 目录说明

- `docker-compose.yml`：本地一键启动编排（`postgres` + `api` + `frontend`）
- `.env`：数据库环境变量
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

## 常用命令

只启动数据库：

```bash
docker compose up -d postgres
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

## 环境变量

编辑 `docker/.env`：

- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`
- `DB_PORT`
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
- `web-admin/api` 本地开发默认值已调整为 PostgreSQL：
- 默认后端：`CORE_STORE_BACKEND=postgres`、`USAGE_STORE_BACKEND=postgres`
- 默认连接：`postgresql://admin:changeme@127.0.0.1:5432/ai_employee`
- `restart: unless-stopped` 会导致 Docker 重启后自动拉起服务；若不希望自动启动，可手动改为 `restart: "no"` 并重建容器。

## Usage 数据迁移（SQLite -> PostgreSQL）

```bash
cd /Users/liulantian/self/ai设计规范/web-admin/api
python scripts/migrate_usage_to_pg.py \
  --sqlite-path ./data/usage.db \
  --database-url postgresql://admin:changeme@localhost:5432/ai_employee
```

## Core 数据迁移（JSON/SQLite -> PostgreSQL）

```bash
cd /Users/liulantian/self/ai设计规范/web-admin/api
python scripts/migrate_core_to_pg.py \
  --database-url postgresql://admin:changeme@localhost:5432/ai_employee
```
