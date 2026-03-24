# Docker 目录通俗解读

这份文档不是给 Docker 老手看的，是给以后回头复习时快速找感觉用的。

一句话先记住：

`docker/` 目录就是这套项目的"容器启动控制台"。它负责把前端、后端、PostgreSQL、Redis 组装成一套能跑起来的环境。

## 1. 这个目录里每个文件是干嘛的

### `docker-compose.yml`

这是总开关，也是最重要的文件。

你可以把它理解成一张"开机清单"：

- 要启动哪些服务
- 每个服务叫什么
- 它们之间怎么连
- 哪些端口对外开放
- 要不要先等数据库或 Redis 好了再启动后端

当前这份配置里主要有 4 个服务：

- `postgres`：数据库
- `redis`：缓存 / 会话存储
- `api`：后端服务
- `frontend`：前端页面

平时你执行：

```bash
docker compose up -d --build
```

本质上就是按这个文件的内容来启动。

### `.env`

这是当前机器真正生效的 Docker 配置。

它主要放：

- 数据库用户名
- 数据库密码
- 数据库名
- 数据库端口
- Redis 逻辑库编号
- 后端使用哪种存储后端

简单理解：

- `docker-compose.yml` 写的是"结构"
- `.env` 写的是"这次启动要用什么参数"

### `.env.example`

这是 `.env` 的模板。

新机器上通常这样开始：

```bash
cp docker/.env.example docker/.env
```

然后再改 `docker/.env`。

它的作用不是直接运行，而是提醒你有哪些配置项能写。

### `Dockerfile.api`

这是"后端镜像说明书"。

Docker 不知道怎么做后端镜像，就按这个文件一步步做：

1. 先选基础环境，这里是 `python:3.12-slim`
2. 安装系统依赖，这里包括 `ffmpeg`
3. 拷贝后端代码
4. 安装 Python 依赖
5. 最后用 `uvicorn` 启动 API

所以如果后端要支持正式导出、FFmpeg 渲染，这个文件就很关键。

### `Dockerfile.frontend`

这是"前端镜像说明书"。

它大致做两段事：

1. 用 Node 把前端代码编译成 `dist`
2. 用 Nginx 把编译好的静态文件跑起来

通俗理解：

- 前端源码不能直接给浏览器
- 要先打包
- 打包完再交给 Nginx 对外提供页面

### `nginx.conf`

这是前端容器里的 Nginx 配置。

它做两件事：

1. 访问网页时，返回前端页面
2. 访问 `/api/` 时，转发给后端 `api:8000`

所以浏览器打开 `http://localhost:3000` 时：

- 页面本身来自前端容器
- 接口请求会被转发给后端容器

### `README.md`

这是 Docker 的正式使用说明。

它适合查：

- 启动命令
- 重建命令
- 停止命令
- 环境变量怎么配
- 端口是多少

这份 `README.learn.md` 更偏解释，`README.md` 更偏操作手册。

### `init/001_usage_schema.sql`

这是数据库初始化 SQL。

它的作用是：

- 当 PostgreSQL 第一次创建时
- 自动执行这里面的 SQL
- 把一些基础表结构准备好

重点注意：

它只在数据库第一次初始化时自动执行。

如果数据库卷已经存在，再往 `init/` 里加 SQL，通常不会自动重新跑。

现在要把它理解成：

- `docker/init/`：第一次建库时的 bootstrap
- `web-admin/api/core/sql_migrations/`：正式、长期维护的 schema 变更入口

以后如果要改 PostgreSQL 表结构，优先新增 migration，不要再把 `docker/init/` 当成唯一来源。

### `init/.gitkeep`

这个文件没有业务作用。

它只是为了让 Git 保留空目录。

## 2. 这些文件是怎么一起工作的

假设你执行：

```bash
cd /Users/liulantian/self/ai设计规范/docker
docker compose up -d --build
```

大致流程是这样：

1. Docker Compose 读取 `docker-compose.yml`
2. 按 `.env` 里的参数把变量填进去
3. 创建或启动 `postgres`
4. 创建或启动 `redis`
5. 用 `Dockerfile.api` 构建后端镜像，然后启动 `api`
6. 用 `Dockerfile.frontend` 构建前端镜像，然后启动 `frontend`
7. 前端容器按 `nginx.conf` 把 `/api/` 请求转发到后端

所以这不是一堆零散文件，而是一整套配合关系。

## 3. 你最常碰到的几个命令，实际在干嘛

### `docker compose up -d --build`

意思是：

- 按当前配置启动整套服务
- 如果镜像需要更新，就重新构建
- 后台运行

适合：

- 第一次启动
- 改了 Dockerfile
- 改了后端或前端代码，想让容器里的版本也更新

### `docker compose up -d --build api`

意思是：

- 只重建并启动 `api` 服务

通常适合：

- 只改了后端
- 只需要让后端拿到新的 FFmpeg、Python 依赖或代码

如果 `api` 依赖的 `postgres`、`redis` 没起来，Compose 也会顺带把它们拉起来。

### `docker compose ps`

这是看当前服务状态。

你可以把它当成：

"现在这套环境里，哪些容器活着，哪些没起来。"

### `docker compose logs -f api`

这是看后端日志。

适合排查：

- API 为什么启动失败
- 端口是不是冲突
- FFmpeg 有没有报错
- 数据库或 Redis 有没有连上

### `docker compose down`

这是停掉这套服务，但通常保留数据库数据卷。

适合：

- 临时停掉环境
- 准备重新拉起

### `docker compose down -v`

这个危险。

它除了停服务，还会把数据卷删掉。

通俗讲：

- 容器删了可以重建
- 数据卷删了，数据库数据可能就没了

不是非常确定时，不要乱用。

## 4. 你最容易混淆的几个概念

### 服务名 vs 容器名

以当前项目为例：

- 服务名：`api`
- 容器名：`ai-employee-api`

什么时候用哪个：

- `docker compose up -d api`
  这里写的是服务名
- `docker logs ai-employee-api`
  这里常用容器名

### 镜像 vs 容器

可以这样记：

- 镜像：安装包 / 模板
- 容器：真正跑起来的实例

所以你改了 `Dockerfile.api` 后，要重新 build。
否则旧容器还是用旧镜像。

### 端口映射

例如：

- `3000:80`
  表示你访问本机 `3000`，实际进的是容器里的 `80`
- `8000:8000`
  表示你访问本机 `8000`，实际进的是 API 容器里的 `8000`

如果本机已经有别的程序占了 `8000`，这里就会冲突。

## 5. 当前这套 Docker 配置，对你最重要的现实意义

### 对正式导出

现在后端镜像里已经装了 `ffmpeg`。

意思是：

- 如果请求命中的是 Docker 里的 `api`
- 正式导出时就能在容器内调用 FFmpeg

所以你不一定非得在宿主机安装 FFmpeg。

### 对 Redis

当前 Compose 已经补了 `redis` 服务。

而且默认不映射宿主机 `6379` 端口。

这样做的好处是：

- 容器里的 `api` 还能正常用 Redis
- 不会和你机器上已有的 Redis 或别的 Redis 容器抢端口

### 对数据库

当前 Compose 里的后端默认连的是同一套 Compose 内部的 `postgres` 服务，不会随便连你机器上别的数据库容器。

## 6. 遇到问题先看哪里

### 后端起不来

先看：

- `docker-compose.yml`
- `Dockerfile.api`
- `docker compose logs -f api`

### 前端页面打不开

先看：

- `Dockerfile.frontend`
- `nginx.conf`
- `docker compose logs -f frontend`

### 数据库问题

先看：

- `.env`
- `docker-compose.yml`
- `docker compose logs -f postgres`

### Redis 问题

先看：

- `docker-compose.yml`
- `docker compose logs -f redis`

## 7. 最后给自己留一个记忆口诀

可以这样记：

- `docker-compose.yml`：总调度
- `.env`：当前参数
- `Dockerfile.api`：后端怎么做出来
- `Dockerfile.frontend`：前端怎么做出来
- `nginx.conf`：前端怎么转发接口
- `init/*.sql`：数据库第一次启动时顺手初始化
- `README.md`：操作手册
- `README.learn.md`：通俗解释

如果以后忘了，就先从这句开始想。
