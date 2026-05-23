# AI 员工工厂 Docker 极简部署（知乎版）

> 这一版只讲一件事：直接给你可用的 `compose.prod.yml`，你改几个参数，执行一条命令就能跑。

如果你嫌之前那版太复杂，这一页就是按“像 Dify 一样，文档里直接给文件内容”的思路重写的。

## 1. 先说结论

你真正要准备的东西只有 3 个：

- `compose.prod.yml`
- `.env.prod`
- `init/001_usage_schema.sql`

然后执行：

```bash
docker compose --env-file .env.prod -f compose.prod.yml up -d
```

普通用户先不用看 `deploy.sh`、`deploy.ps1`、`README.publish.md`。

## 2. 先确认 Docker 可用

```bash
docker --version
docker compose version
```

能看到版本号就继续。

## 3. 建目录

```bash
mkdir -p ai-employee-docker/init
cd ai-employee-docker
```

## 4. 直接创建 `compose.prod.yml`

把下面内容保存成 `compose.prod.yml`：

```yaml
name: ${COMPOSE_PROJECT_NAME:-ai_employee_prod}

services:
  postgres:
    image: ${POSTGRES_IMAGE:-postgres:17}
    container_name: ${POSTGRES_CONTAINER_NAME:-ai-employee-postgres}
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${DB_USER:-admin}
      POSTGRES_PASSWORD: ${DB_PASSWORD:-changeme}
      POSTGRES_DB: ${DB_NAME:-ai_employee}
    ports:
      - "${DB_PORT:-5432}:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init:/docker-entrypoint-initdb.d
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER:-admin} -d ${DB_NAME:-ai_employee}"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: ${REDIS_IMAGE:-redis:7-alpine}
    container_name: ai-employee-redis
    restart: unless-stopped
    command: ["redis-server", "--save", "", "--appendonly", "no"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  api:
    image: ${API_IMAGE:?set API_IMAGE in .env.prod}
    container_name: ai-employee-api
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      CORE_STORE_BACKEND: ${CORE_STORE_BACKEND:-postgres}
      USAGE_STORE_BACKEND: ${USAGE_STORE_BACKEND:-postgres}
      AUTO_RUN_DB_MIGRATIONS: ${AUTO_RUN_DB_MIGRATIONS:-true}
      DATABASE_URL: postgresql://${DB_USER:-admin}:${DB_PASSWORD:-changeme}@postgres:5432/${DB_NAME:-ai_employee}
      REDIS_HOST: redis
      REDIS_PORT: 6379
      REDIS_DB: ${REDIS_DB:-0}
      API_HOST: 0.0.0.0
      API_PORT: 8000
      API_RELOAD: "false"
    ports:
      - "${HOST_API_PORT:-8000}:8000"
    volumes:
      - api_data:/root/.ai-native/web-admin-api
      - mcp_skills_knowledge:/app/mcp-skills/knowledge

  frontend:
    image: ${FRONTEND_IMAGE:?set FRONTEND_IMAGE in .env.prod}
    container_name: ai-employee-frontend
    restart: unless-stopped
    depends_on:
      api:
        condition: service_started
    ports:
      - "${HOST_FRONTEND_PORT:-3000}:80"

volumes:
  pgdata:
    name: ai_employee_pgdata_prod
  api_data:
    name: ai_employee_api_data_prod
  mcp_skills_knowledge:
    name: ai_employee_mcp_skills_knowledge_prod
```

## 5. 直接创建 `.env.prod`

把下面内容保存成 `.env.prod`：

```env
API_IMAGE=docker.io/lantianliu/ai-employee:api-1.0.1
FRONTEND_IMAGE=docker.io/lantianliu/ai-employee:frontend-1.0.1
POSTGRES_IMAGE=docker.io/lantianliu/ai-employee:postgres-17
REDIS_IMAGE=docker.io/lantianliu/ai-employee:redis-7-alpine

HOST_API_PORT=8000
HOST_FRONTEND_PORT=3000
DB_PORT=5432

DB_USER=admin
DB_PASSWORD=change-this-password-before-production
DB_NAME=ai_employee

REDIS_DB=0

CORE_STORE_BACKEND=postgres
USAGE_STORE_BACKEND=postgres
AUTO_RUN_DB_MIGRATIONS=true
```

你至少改这 3 个值：

```env
API_IMAGE=docker.io/lantianliu/ai-employee:api-1.0.1
FRONTEND_IMAGE=docker.io/lantianliu/ai-employee:frontend-1.0.1
DB_PASSWORD=换成你自己的强密码
```

如果端口冲突，再改：

```env
HOST_FRONTEND_PORT=3001
HOST_API_PORT=8001
DB_PORT=15432
```

## 6. 创建初始化 SQL

再创建一个文件：`init/001_usage_schema.sql`

内容如下：

```sql
-- Legacy bootstrap SQL for first-time PostgreSQL container initialization only.
-- Canonical schema migrations now live under web-admin/api/core/sql_migrations/.

CREATE TABLE IF NOT EXISTS api_keys (
    key TEXT PRIMARY KEY,
    developer_name TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_records (
    id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    api_key TEXT NOT NULL DEFAULT '',
    developer_name TEXT NOT NULL DEFAULT 'anonymous',
    event_type TEXT NOT NULL,
    tool_name TEXT NOT NULL DEFAULT '',
    client_ip TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_usage_employee ON usage_records(employee_id);
CREATE INDEX IF NOT EXISTS idx_usage_created ON usage_records(created_at);
```

这一步不要省。

因为 `compose.prod.yml` 里挂了这行：

```yaml
- ./init:/docker-entrypoint-initdb.d
```

第一次启动 PostgreSQL 时，会用这个目录做初始化。

## 7. 直接启动

最核心的一条命令就是：

```bash
docker compose --env-file .env.prod -f compose.prod.yml up -d
```

如果你想先拉镜像，也可以：

```bash
docker compose --env-file .env.prod -f compose.prod.yml pull
docker compose --env-file .env.prod -f compose.prod.yml up -d
```

## 8. 看服务有没有起来

```bash
docker compose --env-file .env.prod -f compose.prod.yml ps
```

正常会看到这 4 个服务：

- `postgres`
- `redis`
- `api`
- `frontend`

## 9. 打开系统

默认地址：

- 前端：`http://localhost:3000`
- API：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`

如果你改过端口，就把这里的端口替换掉。

## 10. 首次使用

第一次打开前端后，按页面提示初始化超级管理员即可。

如果你想检查后端是否已经初始化成功，可以执行：

```bash
curl http://localhost:8000/api/init/status
```

如果返回里有：

```json
{"initialized":true}
```

说明已经可以正常使用。

## 11. 升级也很简单

以后升级，只改 `.env.prod` 里的镜像版本：

```env
API_IMAGE=docker.io/lantianliu/ai-employee:api-1.0.2
FRONTEND_IMAGE=docker.io/lantianliu/ai-employee:frontend-1.0.2
```

然后重新执行：

```bash
docker compose --env-file .env.prod -f compose.prod.yml up -d
```

## 12. 停止服务

```bash
docker compose --env-file .env.prod -f compose.prod.yml down
```

这条命令只会停容器，不会删数据库数据卷。

## 13. 常见问题

### 1）镜像拉不下来

先试：

```bash
docker login
```

然后再执行启动命令。

### 2）端口被占用

改 `.env.prod`：

```env
HOST_FRONTEND_PORT=3001
HOST_API_PORT=8001
DB_PORT=15432
```

### 3）我到底要不要看脚本

不用。

这页就是给“不想看脚本、只想把服务跑起来”的用户准备的。
