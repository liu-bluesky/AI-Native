# 打包与更新服务器测试清单

这份文档只做一件事：让你按顺序完整测试一次

- 本地打包后端镜像
- 本地打包前端镜像
- 导出数据库和运行时数据
- 上传到服务器
- 在服务器恢复并启动
- 做最基本验收

适用场景：

- 你本地已经改完代码，准备发到服务器
- 服务器优先使用离线镜像 tar 部署
- 你希望连数据库、技能和 API 运行时文件一起迁移

如果你只是更新代码，不迁移旧数据，可以跳过“第 3 步备份旧数据”和“第 6 步恢复旧数据”。

## 0. 先记住两个原则

1. 离线部署时，用 `./deploy.sh up`，不要直接用 `./deploy.sh deploy`
2. 不要只备份数据库，还要备份技能卷和 API 数据卷

原因：

- `deploy` 会先执行 `pull`
- 离线模式里镜像已经通过 `docker load` 导入，没必要再拉
- 业务数据不只在 PostgreSQL，还在 Docker volume 里

## 1. 准备条件

本地机器需要：

- Docker
- 能进入项目目录 `/Users/liulantian/self/ai-employee/docker`

服务器需要：

- Docker
- Docker Compose
- 能接收你上传的 tar 和 `docker/` 目录

## 2. 本地打包镜像

进入目录：

```bash
cd /Users/liulantian/self/ai-employee/docker
```

构建后端镜像：

```bash
docker build -f Dockerfile.api -t ai_employee-api:latest ..
```

构建前端镜像：

```bash
docker build -f Dockerfile.frontend -t ai_employee-frontend:latest ..
```

导出后端镜像 tar：

```bash
docker save -o ../ai_employee-api_latest.tar ai_employee-api:latest
```

导出前端镜像 tar：

```bash
docker save -o ../ai_employee-frontend_latest.tar ai_employee-frontend:latest
```

可选检查：

```bash
docker images | grep ai_employee
ls -lh ../ai_employee-api_latest.tar ../ai_employee-frontend_latest.tar
```

## 3. 本地备份数据

如果你这次是“更新已有服务器”而不是“纯新装”，先备份。

先准备生产环境配置文件：

```bash
cd /Users/liulantian/self/ai-employee/docker
cp .env.prod.example .env.prod
chmod +x deploy.sh
```

如果 `.env.prod` 里数据库用户名、库名和线上不一致，先改对，再备份。

备份数据库：

```bash
./deploy.sh backup-db
```

备份技能卷：

```bash
./deploy.sh backup-skill-volume
```

备份 API 运行时数据卷：

```bash
./deploy.sh backup-api-data-volume
```

把备份目录打包：

```bash
tar -czf docker-backup-$(date +%Y%m%d-%H%M%S).tar.gz backup
```

正常情况下会得到：

- `../ai_employee-api_latest.tar`
- `../ai_employee-frontend_latest.tar`
- `docker/docker-backup-时间戳.tar.gz`

## 4. 准备要上传到服务器的文件

建议上传这些内容：

- `ai_employee-api_latest.tar`
- `ai_employee-frontend_latest.tar`
- `docker/docker-backup-时间戳.tar.gz`
- 整个 `docker/` 目录

如果你不方便直接上传整个 `docker/` 目录，至少保证服务器上有这些文件：

- `docker/compose.prod.yml`
- `docker/.env.prod.example`
- `docker/deploy.sh`
- `docker/init/`

## 5. 服务器导入镜像并准备配置

假设你把文件传到了服务器的 `/path/to/ai-employee`。

先进入项目根目录：

```bash
cd /path/to/ai-employee
```

导入后端镜像：

```bash
docker load -i ai_employee-api_latest.tar
```

导入前端镜像：

```bash
docker load -i ai_employee-frontend_latest.tar
```

进入 `docker/` 目录并准备配置：

```bash
cd docker
cp .env.prod.example .env.prod
chmod +x deploy.sh
```

编辑 `.env.prod`，至少改这几个值：

```env
API_IMAGE=ai_employee-api:latest
FRONTEND_IMAGE=ai_employee-frontend:latest
DB_PASSWORD=你的强密码
HOST_API_PORT=8000
HOST_FRONTEND_PORT=3000
```

如果数据库用户名、数据库名不是默认值，也一起改：

```env
DB_USER=admin
DB_NAME=ai_employee
DB_PORT=5432
```

启动空白服务，先把卷创建出来：

```bash
./deploy.sh up
./deploy.sh ps
```

## 6. 服务器恢复旧数据

如果这次是全新服务器但要恢复旧数据，继续做这一步。

如果只是上线新代码，不迁移旧数据，这一步可以跳过。

在服务器 `docker/` 目录下解压备份：

```bash
tar -xzf docker-backup-*.tar.gz
```

恢复技能卷：

```bash
./deploy.sh restore-skill-volume
```

恢复 API 数据卷：

```bash
./deploy.sh restore-api-data-volume
```

恢复数据库：

```bash
./deploy.sh restore-db backup/ai_employee.sql
```

恢复完成后，重新拉起服务：

```bash
./deploy.sh up
./deploy.sh ps
```

## 7. 验收步骤

先看容器状态：

```bash
./deploy.sh ps
```

看后端日志：

```bash
./deploy.sh logs api
```

看前端日志：

```bash
./deploy.sh logs frontend
```

再做这些实际检查：

- 浏览器打开前端首页
- 检查核心页面能正常加载数据
- 检查接口健康状态，例如 `/api/health`
- 检查原有技能列表是否还在
- 随机做一次导出，确认产物正常

## 8. 这次测试里最容易犯的错

错误 1：
离线部署时执行了 `./deploy.sh deploy`

结果：
脚本先 `pull`，可能报镜像不存在

正确做法：

```bash
./deploy.sh up
```

错误 2：
只导出了数据库，没有导出卷

结果：

- 技能包文件丢失
- API 运行时文件丢失

正确做法：
数据库、技能卷、API 数据卷一起备份

错误 3：
`.env.prod` 里的镜像名没改成本机已导入的 tag

正确做法：

```env
API_IMAGE=ai_employee-api:latest
FRONTEND_IMAGE=ai_employee-frontend:latest
```

错误 4：
恢复数据前没有先 `./deploy.sh up`

结果：
卷可能还没创建，恢复会失败

正确做法：
先启动一次空白服务，让 PostgreSQL 和卷先创建出来

## 9. 你实际测试时的最短执行顺序

如果你想只看最短命令顺序，就按这个走。

本地：

```bash
cd /Users/liulantian/self/ai-employee/docker
docker build -f Dockerfile.api -t ai_employee-api:latest ..
docker build -f Dockerfile.frontend -t ai_employee-frontend:latest ..
docker save -o ../ai_employee-api_latest.tar ai_employee-api:latest
docker save -o ../ai_employee-frontend_latest.tar ai_employee-frontend:latest

cp .env.prod.example .env.prod
chmod +x deploy.sh
./deploy.sh backup-db
./deploy.sh backup-skill-volume
./deploy.sh backup-api-data-volume
tar -czf docker-backup-$(date +%Y%m%d-%H%M%S).tar.gz backup
```

服务器：

```bash
cd /path/to/ai-employee
docker load -i ai_employee-api_latest.tar
docker load -i ai_employee-frontend_latest.tar

cd docker
cp .env.prod.example .env.prod
chmod +x deploy.sh
./deploy.sh up
tar -xzf docker-backup-*.tar.gz
./deploy.sh restore-skill-volume
./deploy.sh restore-api-data-volume
./deploy.sh restore-db backup/ai_employee.sql
./deploy.sh up
./deploy.sh ps
```

如果你这次只是更新代码，不恢复旧数据，服务器侧最短命令会变成：

```bash
cd /path/to/ai-employee
docker load -i ai_employee-api_latest.tar
docker load -i ai_employee-frontend_latest.tar

cd docker
cp .env.prod.example .env.prod
chmod +x deploy.sh
./deploy.sh up
./deploy.sh ps
```
