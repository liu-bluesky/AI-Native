# AI 员工工厂：发布 Docker 镜像与一键部署

这份文档面向“把当前项目打包成镜像发布到 Docker Hub / 私有镜像仓库，让别人只用 Docker 就能部署”的场景。

当前项目拆成两个业务镜像：

- API 镜像：后端 FastAPI + MCP 代理入口
- Frontend 镜像：前端 Vue 静态资源 + Nginx 反向代理

运行时依赖使用官方镜像：

- PostgreSQL：`postgres:17`
- Redis：`redis:7-alpine`

## 一、发布者：构建并推送镜像

先进入项目 Docker 目录：

```bash
cd /Volumes/苹果1_5T/self/ai-employee/docker
chmod +x build-publish-images.sh
```

登录 Docker Hub，或你的私有镜像仓库：

```bash
docker login
```

设置镜像命名。

如果发布到 Docker Hub，`IMAGE_NAMESPACE` 通常是你的 Docker Hub 用户名或组织名：

```bash
export IMAGE_NAMESPACE=你的DockerHub用户名
export IMAGE_TAG=1.0.0
```

构建并推送多架构镜像：

```bash
./build-publish-images.sh build-push
```

默认会推送：

```text
docker.io/${IMAGE_NAMESPACE}/ai-employee-api:${IMAGE_TAG}
docker.io/${IMAGE_NAMESPACE}/ai-employee-frontend:${IMAGE_TAG}
```

例如：

```bash
IMAGE_NAMESPACE=myname IMAGE_TAG=1.0.0 ./build-publish-images.sh build-push
```

会发布：

```text
docker.io/myname/ai-employee-api:1.0.0
docker.io/myname/ai-employee-frontend:1.0.0
```

如果你只想先在本机生成单架构镜像，不推送：

```bash
IMAGE_NAMESPACE=myname IMAGE_TAG=dev PLATFORMS=linux/amd64 LOAD=true ./build-publish-images.sh build
```

如果你使用私有仓库，可以直接指定完整镜像名：

```bash
API_IMAGE=registry.example.com/team/ai-employee-api:1.0.0 \
FRONTEND_IMAGE=registry.example.com/team/ai-employee-frontend:1.0.0 \
./build-publish-images.sh build-push
```

## 二、部署者：只用 Docker Compose 部署

部署机器需要安装：

- Docker
- Docker Compose v2

部署者只需要拿到以下文件：

- `compose.prod.yml`
- `.env.prod.example`
- `deploy.sh`
- `init/` 目录

可以新建一个目录，例如：

```bash
mkdir -p ai-employee-docker/docker
cd ai-employee-docker/docker
```

把上面文件放进这个目录后，复制环境变量模板：

```bash
cp .env.prod.example .env.prod
```

编辑 `.env.prod`：

```env
API_IMAGE=docker.io/你的DockerHub用户名/ai-employee-api:1.0.0
FRONTEND_IMAGE=docker.io/你的DockerHub用户名/ai-employee-frontend:1.0.0

HOST_FRONTEND_PORT=3000
HOST_API_PORT=8000

DB_USER=admin
DB_PASSWORD=请改成强密码
DB_NAME=ai_employee
DB_PORT=5432

CORE_STORE_BACKEND=postgres
USAGE_STORE_BACKEND=postgres
AUTO_RUN_DB_MIGRATIONS=true
```

启动：

```bash
chmod +x deploy.sh
docker compose --env-file .env.prod -f compose.prod.yml pull
docker compose --env-file .env.prod -f compose.prod.yml up -d
```

也可以用脚本：

```bash
chmod +x deploy.sh
./deploy.sh deploy
```

查看状态：

```bash
./deploy.sh ps
```

查看日志：

```bash
./deploy.sh logs api
./deploy.sh logs frontend
```

访问：

```text
前端：http://服务器IP:3000
API：http://服务器IP:8000
API 文档：http://服务器IP:8000/docs
```

首次部署后，打开前端页面，根据页面提示创建超级管理员账号。

也可以用 API 初始化超级管理员：

```bash
curl -X POST 'http://服务器IP:8000/api/init/setup' \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","display_name":"超级管理员","password":"请改成强密码"}'
```

注意：首次初始化只允许创建内置用户名 `admin`。如果已经初始化过，再调用会返回 `Already initialized`。

验证初始化状态：

```bash
curl 'http://服务器IP:8000/api/init/status'
```

期望看到：

```json
{"initialized":true,"setup_required":false,"enable_user_register":true}
```

## 三、停止、升级、备份

停止服务，但保留数据：

```bash
docker compose --env-file .env.prod -f compose.prod.yml down
```

升级镜像：

```bash
# 修改 .env.prod 里的 API_IMAGE / FRONTEND_IMAGE tag 后执行
docker compose --env-file .env.prod -f compose.prod.yml pull
docker compose --env-file .env.prod -f compose.prod.yml up -d
```

备份数据库：

```bash
./deploy.sh backup-db ./backup/ai_employee.sql
```

恢复数据库：

```bash
./deploy.sh restore-db ./backup/ai_employee.sql
```

备份 API 运行时数据：

```bash
./deploy.sh backup-api-data-volume ./backup/api-data
```

备份上传技能知识库：

```bash
./deploy.sh backup-skill-volume ./backup/mcp-skills-knowledge
```

危险：删除容器和数据卷，会清空数据库和运行时数据：

```bash
docker compose --env-file .env.prod -f compose.prod.yml down -v
```

## 四、发布文件清单

建议随镜像一起发布这些文件：

```text
docker/compose.prod.yml
docker/.env.prod.example
docker/deploy.sh
docker/init/
docker/README.publish.md
```

镜像本身不保存数据库、上传文件、运行时技能等数据。这些数据通过 Docker volume 持久化：

```text
ai_employee_pgdata_prod
ai_employee_api_data_prod
ai_employee_mcp_skills_knowledge_prod
```

## 五、常见问题

### 1. `pull access denied` 或 `repository does not exist`

检查 `.env.prod` 里的：

```env
API_IMAGE=
FRONTEND_IMAGE=
```

确认镜像名、tag、仓库权限正确。如果是私有仓库，先执行：

```bash
docker login registry.example.com
```

### 2. 页面能打开，但 API 请求失败

检查：

```bash
docker compose --env-file .env.prod -f compose.prod.yml ps
docker compose --env-file .env.prod -f compose.prod.yml logs -f api
```

确认 API 容器正常运行，且前端 Nginx 能通过 Compose 内网访问 `api:8000`。

### 3. 首次初始化接口返回 `Already initialized`

说明数据卷里已经有用户。生产环境不要随便清空数据卷。如果只是测试环境，可以执行：

```bash
docker compose --env-file .env.prod -f compose.prod.yml down -v
```

然后重新启动。
