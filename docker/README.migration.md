# 服务器迁移清单

目标：把一台旧服务器上的 Docker 部署迁移到新服务器，同时保留：

- PostgreSQL 业务数据
- 上传后的技能包与技能元数据
- API 运行时文件

## 0. 迁移前提

新服务器需要具备：

- Docker
- Docker Compose
- 能访问镜像仓库
- 已准备好 `docker/compose.prod.yml`
- 已准备好 `docker/.env.prod`

如果你的容器名或卷名不是默认值，也可以在执行脚本前覆盖：

```bash
export POSTGRES_CONTAINER=ai-employee-postgres
export SKILL_VOLUME=ai_employee_mcp_skills_knowledge_prod
export API_DATA_VOLUME=ai_employee_api_data_prod
```

建议在新服务器先执行一次配置检查：

```bash
cd /path/to/ai-employee
docker compose --env-file docker/.env.prod -f docker/compose.prod.yml config
```

## 1. 旧服务器备份

进入项目目录：

```bash
cd /path/to/ai-employee/docker
```

### 1.1 备份数据库

```bash
./deploy.sh backup-db
```

默认产物：

- `docker/backup/ai_employee.sql`

### 1.2 备份技能目录卷

```bash
./deploy.sh backup-skill-volume
```

默认产物：

- `docker/backup/mcp-skills-knowledge/`

### 1.3 备份 API 运行时数据卷

```bash
./deploy.sh backup-api-data-volume
```

默认产物：

- `docker/backup/api-data/`

### 1.4 打包备份目录

```bash
tar -czf docker-backup-$(date +%Y%m%d-%H%M%S).tar.gz backup
```

把这个压缩包传到新服务器。

## 2. 新服务器准备

进入项目目录：

```bash
cd /path/to/ai-employee/docker
cp .env.prod.example .env.prod
```

至少修改：

- `API_IMAGE`
- `FRONTEND_IMAGE`
- `DB_PASSWORD`
- `HOST_API_PORT`
- `HOST_FRONTEND_PORT`

拉起空白服务：

```bash
./deploy.sh pull
./deploy.sh up
```

说明：

- 这一步是为了先创建 PostgreSQL、API 数据卷、技能卷
- 如果数据库是全新卷，PostgreSQL 会先初始化

## 3. 新服务器恢复

把备份包放到 `docker/` 下并解压：

```bash
tar -xzf docker-backup-*.tar.gz
```

### 3.1 恢复技能卷

```bash
./deploy.sh restore-skill-volume
```

### 3.2 恢复 API 数据卷

```bash
./deploy.sh restore-api-data-volume
```

### 3.3 恢复数据库

```bash
./deploy.sh restore-db backup/ai_employee.sql
```

## 4. 启动并校验

重新部署：

```bash
./deploy.sh deploy
./deploy.sh ps
```

看日志：

```bash
./deploy.sh logs api
./deploy.sh logs frontend
```

## 5. 重点校验项

- 前端页面能打开
- API `/api/health` 或核心页面接口正常
- 技能列表存在
- 随机导出一个已上传技能 zip，确认包内容完整
- 员工已绑定技能仍可正常调用
- PostgreSQL 中的 `skills`、`skill_bindings`、`employees`、`rules` 数据量正常

## 6. 回滚思路

如果新服务器恢复失败：

- 不删除旧服务器运行中的容器和卷
- 先回到旧服务器继续提供服务
- 修复新服务器环境或恢复流程后再重新迁移

如果新服务器已经启动但数据不完整：

- 停止新服务：`docker compose --env-file .env.prod -f compose.prod.yml down`
- 删除错误恢复产生的卷或容器
- 重新创建空白环境后再恢复

## 7. 特别说明

- 上传技能不是靠镜像迁移，而是靠 PostgreSQL + `mcp-skills/knowledge` 卷共同迁移。
- 仅恢复数据库，不恢复技能卷，会导致技能记录存在但包目录缺失。
- 仅恢复技能卷，不恢复数据库，会导致技能包在磁盘上，但平台里没有对应技能元数据。
