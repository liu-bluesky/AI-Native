# Remote Docker Deploy

通过 SSH 自动更新远程 Linux 服务器上的 Docker 部署。

默认目标：

- Host: `64.81.113.174`
- Port: `22`
- User: `root`
- Remote dir: `/www/aiEmployee/docker`
- Compose file: `compose.prod.yml`
- Env file: `.env.prod`
- Delivery mode: `offline`
- Action: `deploy`

默认流程：

1. 本地构建 `linux/amd64` 的 API / Frontend 镜像
2. 本地 `docker save` 成 tar
3. 上传 tar 到远程 `docker/` 目录
4. 远程做预检查并加部署锁
5. 远程备份数据库、技能卷、API 数据卷
6. 远程 `docker load`
7. 默认以 `AUTO_RUN_DB_MIGRATIONS=false` 执行 `./deploy.sh up`
8. 执行 `./deploy.sh ps`

说明：

- 默认走离线发布，不再依赖远程 `pull` 本地标签镜像
- 如果本机拉不到 Docker 基础镜像，可以改用 `remote-build`：上传源码到服务器再构建
- 默认不更新数据库 migration
- 只有显式传 `--update-db`，才会在本次部署时开启数据库 migration
- 默认 profile 是 `default`
- 支持多 profile 配置
- 支持一键回滚到指定备份目录

推荐用法：

```bash
export REMOTE_DEPLOY_PASSWORD='你的服务器密码'
python3 remote-docker-deploy/remote_docker_deploy.py
```

保存生产环境配置到 `prod` profile：

```bash
python3 remote-docker-deploy/remote_docker_deploy.py \
  --profile prod \
  --host 64.81.113.174 \
  --user root \
  --remote-dir /www/aiEmployee/docker \
  --delivery-mode offline \
  --save
```

之后直接用 `prod` profile 发布：

```bash
export REMOTE_DEPLOY_PASSWORD='你的服务器密码'
python3 remote-docker-deploy/remote_docker_deploy.py --profile prod
```

如果你要改回仓库拉取模式：

```bash
python3 remote-docker-deploy/remote_docker_deploy.py \
  --profile prod \
  --delivery-mode registry
```

如果你要改成“上传源码到远程再构建”的模式：

```bash
export REMOTE_DEPLOY_PASSWORD='你的服务器密码'
python3 remote-docker-deploy/remote_docker_deploy.py \
  --profile prod \
  --delivery-mode remote-build
```

这个模式会：

1. 本地打包项目源码
2. 上传到远程项目根目录
3. 远程重新 `docker build`
4. 备份数据库、技能卷、API 数据卷
5. 默认以 `AUTO_RUN_DB_MIGRATIONS=false` 执行 `./deploy.sh up`

如果这次部署需要顺带更新数据库 migration：

```bash
export REMOTE_DEPLOY_PASSWORD='你的服务器密码'
python3 remote-docker-deploy/remote_docker_deploy.py --update-db
```

保存非敏感配置：

```bash
python3 remote-docker-deploy/remote_docker_deploy.py --save
```

只拉起不重新 pull：

```bash
python3 remote-docker-deploy/remote_docker_deploy.py --action up
```

回滚到某次备份：

```bash
export REMOTE_DEPLOY_PASSWORD='你的服务器密码'
python3 remote-docker-deploy/remote_docker_deploy.py \
  --action rollback \
  --rollback-from backup/auto-deploy-20260326-120000
```

回滚时会做这些事：

1. 先校验目标备份目录存在
2. 默认先把当前线上数据再备份一次
3. 拉起依赖并停止 `api` / `frontend`
4. 恢复技能卷、API 数据卷、数据库
5. 最后重新 `up`

支持：

- `--profile`
- `--delivery-mode offline|registry|remote-build`
- `--platform`
- `--api-image`
- `--frontend-image`
- `--artifact-dir`
- `--password`
- `--password-env`
- `--ssh-key`
- `--action rollback`
- `--rollback-from`
- `--healthcheck-url`
- `--update-db`
- `--skip-backup`
- `--dry-run`

配置文件默认保存在当前目录：

- `remote-docker-deploy/.remote-deploy.json`
- `remote-docker-deploy/.remote-deploy.prod.json`
- `remote-docker-deploy/.remote-deploy-{api_key}.json`
- `remote-docker-deploy/.remote-deploy-{employee_id}.json`

离线模式的默认本地参数：

- Platform: `linux/amd64`
- API image: `ai_employee-api:latest`
- Frontend image: `ai_employee-frontend:latest`
- Artifact dir: `/tmp/remote-docker-deploy`

`remote-build` 模式会自动跳过这些目录：

- `.git`
- `docker/backup`
- `web-admin/frontend/node_modules`
- `web-admin/frontend/dist`
- `__pycache__`
- `*.pyc`

## 同步资源权限到远程库

如果你本地已经把员工 / 规则 / 技能改成了新的可见范围，但远程 PostgreSQL 里还是旧值，可以直接同步：

```bash
export REMOTE_DEPLOY_PASSWORD='你的服务器密码'
python3 remote-docker-deploy/sync_resource_visibility.py
```

默认行为：

1. 优先从本地 Docker 容器 `ai-employee-postgres` 读取 `employees / rules / skills`
2. 如果本地容器不可用，则回退到本地 JSON 文件源
3. 先备份远程数据库
4. 把本地 `created_by / share_scope / shared_with_usernames` 同步到远程 PostgreSQL

如果你只是想强制把本地读到的这三类资源全部同步为“所有人可见”：

```bash
export REMOTE_DEPLOY_PASSWORD='你的服务器密码'
python3 remote-docker-deploy/sync_resource_visibility.py --all-users
```

常用参数：

- `--source auto|docker-postgres|json`
- `--local-postgres-container ai-employee-postgres`
- `--api-data-dir /path/to/web-admin-api`
- `--profile prod`
- `--dry-run`
