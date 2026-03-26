# Docker 常用命令速查

这份文件只保留最常用、最好记的命令。

先进入目录：

```bash
cd /Users/liulantian/self/ai设计规范/docker
```

## 1. 第一次启动或整套更新

```bash
docker compose up -d --build
```

意思：

- `up`：启动服务
- `-d`：后台运行
- `--build`：先重新构建镜像，再启动

适合：

- 第一次启动
- 改了 `Dockerfile`
- 不确定前后端是不是都要更新

## 2. 只更新后端

```bash
docker compose up -d --build api
```

意思：

- 只重建并启动 `api`
- 如果 `postgres`、`redis` 还没起来，Compose 会顺带拉起依赖

适合：

- 只改了后端代码
- 只改了 Python 依赖

## 3. 只更新前端和后端

```bash
docker compose up -d --no-build --force-recreate api frontend
docker compose up -d --build api frontend
```

意思：

- 只重建并启动 `api` 和 `frontend`
- 不会主动重建 `postgres`、`redis`

适合：

- 你只改了页面和接口
- 想更新业务代码，但不动数据库

## 4. 看服务有没有起来

```bash
docker compose ps
```

重点看：

- `Up`：服务正常运行
- `Exited`：服务已经停了
- `unhealthy`：服务起来了，但健康检查没过

## 5. 看日志排错

看后端：

```bash
docker compose logs -f api
```

看前端：

```bash
docker compose logs -f frontend
```

看数据库：

```bash
docker compose logs -f postgres
```

退出日志查看：

```bash
Ctrl + C
```

## 6. 停掉服务

```bash
docker compose down
```

意思：

- 停掉容器
- 保留数据库数据卷

一般日常停服务，用这个就够了。

## 7. 危险命令

```bash
docker compose down -v
```

这个会连数据库卷一起删。

除非你明确要清空数据，否则不要用。

## 8. 你后面最常用的判断方式

如果只是代码更新：

- 改后端：`docker compose up -d --build api`
- 改前端和后端：`docker compose up -d --build api frontend`
- 不确定改了什么：`docker compose up -d --build`

如果只是看有没有报错：

- 先 `docker compose ps`
- 再 `docker compose logs -f api`

## 9. 服务器上传 tar 后怎么启动

如果你上传到服务器的是镜像 tar，不是仓库地址，最短流程是：

```bash
cd /path/to/ai-employee
docker load -i ai_employee-api_latest.tar
docker load -i ai_employee-frontend_latest.tar

cd docker
cp .env.prod.example .env.prod
chmod +x deploy.sh
```

`.env.prod` 至少改：

```env
API_IMAGE=ai_employee-api:latest
FRONTEND_IMAGE=ai_employee-frontend:latest
DB_PASSWORD=你的密码
```

启动：

```bash
./deploy.sh up
./deploy.sh ps
```

记住：

- `./deploy.sh deploy` 适合服务器自己从仓库拉镜像
- `./deploy.sh up` 适合已经 `docker load` 到本机的离线部署
