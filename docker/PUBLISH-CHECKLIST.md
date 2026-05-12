# AI 员工工厂：公开 Docker 镜像发布清单

生成时间：2026-05-11
项目目录：`/Volumes/苹果1_5T/self/ai-employee`
Docker 目录：`/Volumes/苹果1_5T/self/ai-employee/docker`

## 当前已完成

已在本机完成单架构 arm64 镜像构建，用于验证 Dockerfile 和发布脚本可用：

```text
ai-employee/ai-employee-api:publish-local
ai-employee/ai-employee-frontend:publish-local
```

本机镜像检查结果：

```text
ai-employee/ai-employee-api:publish-local       arm64  约 1.17GB
ai-employee/ai-employee-frontend:publish-local  arm64  约 100MB
```

注意：这两个镜像目前只在本机 Docker 中，还没有推送到公开镜像仓库。

## 发布前必须确定

你需要选择一个公开镜像仓库，并登录：

- Docker Hub：`docker.io/<用户名或组织>/ai-employee-api:<tag>`
- GitHub Container Registry：`ghcr.io/<用户名或组织>/ai-employee-api:<tag>`
- 其他 registry：例如 `registry.example.com/team/ai-employee-api:<tag>`

当前本机 Docker 配置里未发现登录凭据，因此不能直接 push 到公开地址。

## Docker Hub 发布命令

把 `<namespace>` 换成你的 Docker Hub 用户名或组织名，把 `<tag>` 换成版本号：

```bash
cd /Volumes/苹果1_5T/self/ai-employee/docker

docker login

IMAGE_NAMESPACE=<namespace> \
IMAGE_TAG=<tag> \
./build-publish-images.sh build-push
```

示例：

```bash
IMAGE_NAMESPACE=myname IMAGE_TAG=1.0.0 ./build-publish-images.sh build-push
```

发布后公开镜像地址为：

```text
docker.io/myname/ai-employee-api:1.0.0
docker.io/myname/ai-employee-frontend:1.0.0
```

## GHCR 发布命令

先使用 GitHub PAT 登录 GHCR：

```bash
echo '<GitHub PAT>' | docker login ghcr.io -u <github-user> --password-stdin
```

构建并推送：

```bash
cd /Volumes/苹果1_5T/self/ai-employee/docker

REGISTRY=ghcr.io \
IMAGE_NAMESPACE=<github-user-or-org> \
IMAGE_TAG=<tag> \
./build-publish-images.sh build-push
```

发布后镜像地址为：

```text
ghcr.io/<github-user-or-org>/ai-employee-api:<tag>
ghcr.io/<github-user-or-org>/ai-employee-frontend:<tag>
```

如果 GHCR 包默认是 private，需要到 GitHub Packages 页面把包可见性改为 public。

## 用户拉取并启动

用户只需要拿到以下文件：

```text
compose.prod.yml
.env.prod.example
deploy.sh
init/
```

准备目录：

```bash
mkdir -p ai-employee-docker/docker
cd ai-employee-docker/docker
```

复制上述文件后：

```bash
cp .env.prod.example .env.prod
```

修改 `.env.prod`：

```env
API_IMAGE=docker.io/<namespace>/ai-employee-api:<tag>
FRONTEND_IMAGE=docker.io/<namespace>/ai-employee-frontend:<tag>

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
docker compose --env-file .env.prod -f compose.prod.yml pull
docker compose --env-file .env.prod -f compose.prod.yml up -d
```

访问：

```text
前端：http://服务器IP:3000
API：http://服务器IP:8000
API 文档：http://服务器IP:8000/docs
```

首次部署后，打开前端页面创建超级管理员账号；或通过 API：

```bash
curl -X POST 'http://服务器IP:8000/api/init/setup' \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","display_name":"超级管理员","password":"请改成强密码"}'
```

## 本机已验证的发布相关文件

```text
docker/build-publish-images.sh
docker/README.publish.md
docker/compose.prod.yml
docker/.env.prod.example
docker/deploy.sh
docker/init/
```

`docker compose --env-file .env.prod.example -f compose.prod.yml config` 已通过。
