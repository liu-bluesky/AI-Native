# Test Docker 首次部署验证

这套配置用于在本机启动一套隔离的测试 Docker 环境，验证“首次部署 -> 创建超级管理员 -> 登录可用”的流程。

## 文件

- `docker-compose.test.yml`：隔离的测试编排，项目名 `ai_employee_test`
- `.env.test`：测试端口、测试数据库和初始化账号参数

## 与默认本地栈的隔离

测试栈不会复用默认 `docker-compose.yml` 的容器名和数据卷：

- 前端：http://localhost:3100
- API：http://localhost:8100
- PostgreSQL：localhost:55432
- PostgreSQL volume：`ai_employee_test_pgdata`
- API runtime volume：`ai_employee_test_api_data`

默认本地栈仍然是：前端 3000、API 8000、PostgreSQL 5432、volume `ai_employee_pgdata`。

## 启动测试栈

```bash
cd /Volumes/苹果1_5T/self/ai-employee/docker
docker compose --env-file .env.test -f docker-compose.test.yml up -d --build
```

## 首次初始化超级管理员

测试账号来自 `.env.test`：

- 用户名：`admin`
- 密码：`test123456`
- 显示名：`测试超级管理员`

执行：

```bash
cd /Volumes/苹果1_5T/self/ai-employee/docker
set -a && . ./.env.test && set +a
curl -sS -X POST "http://localhost:${HOST_API_PORT}/api/init/setup" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"${INIT_ADMIN_USERNAME}\",\"display_name\":\"${INIT_ADMIN_DISPLAY_NAME}\",\"password\":\"${INIT_ADMIN_PASSWORD}\"}"
```

如果接口返回 `Already initialized`，说明当前测试卷里已经有用户；需要重新测试“首次部署”时，请先清空测试卷，见下方“重置测试栈”。

## 验证

```bash
cd /Volumes/苹果1_5T/self/ai-employee/docker
set -a && . ./.env.test && set +a

docker compose --env-file .env.test -f docker-compose.test.yml ps
curl -sS -i "http://localhost:${HOST_API_PORT}/api/init/status" | sed -n '1,12p'
curl -sS -I "http://localhost:${HOST_FRONTEND_PORT}" | sed -n '1,12p'
curl -sS -X POST "http://localhost:${HOST_API_PORT}/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"${INIT_ADMIN_USERNAME}\",\"password\":\"${INIT_ADMIN_PASSWORD}\"}" | python3 -m json.tool
```

期望结果：

- `postgres`、`redis` 为 healthy
- `api`、`frontend` 为 Up
- `/api/init/status` 返回 `initialized: true`
- 前端返回 HTTP 200
- `/api/auth/login` 返回 token 和用户信息

## 查看日志

```bash
cd /Volumes/苹果1_5T/self/ai-employee/docker
docker compose --env-file .env.test -f docker-compose.test.yml logs --tail=100 api
docker compose --env-file .env.test -f docker-compose.test.yml logs --tail=100 frontend
```

## 停止测试栈（保留数据）

```bash
cd /Volumes/苹果1_5T/self/ai-employee/docker
docker compose --env-file .env.test -f docker-compose.test.yml down
```

## 重置测试栈（删除测试数据卷，危险）

只会删除测试栈 volume：`ai_employee_test_pgdata` 和 `ai_employee_test_api_data`。
不会删除默认本地栈的 `ai_employee_pgdata`。

```bash
cd /Volumes/苹果1_5T/self/ai-employee/docker
docker compose --env-file .env.test -f docker-compose.test.yml down -v
docker compose --env-file .env.test -f docker-compose.test.yml up -d --build
```
