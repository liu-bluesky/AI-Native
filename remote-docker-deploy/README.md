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
python3 remote-docker-deploy/remote_docker_deploy.py \
  --profile prod \
  --remote-deploy-password '你的服务器密码'
```

如果你要把发布拆成 3 步，直接用这 3 个脚本：

```bash
# 第 1 步：只在本地构建并打包产物，生成离线镜像 tar 或 remote-build 源码包
./remote-docker-deploy/package_deploy_artifacts.sh --profile prod
# 第 2 步：只把第 1 步产物上传到服务器，不执行远程部署
./remote-docker-deploy/upload_deploy_artifacts.sh --profile prod --remote-deploy-password '你的服务器密码'
# 第 3 步：只在服务器执行备份、加载产物并更新远程栈；默认会带上 --update-db
./remote-docker-deploy/update_remote_stack.sh --profile prod --remote-deploy-password '你的服务器密码'
```

这 3 个脚本分别做：

1. `package_deploy_artifacts.sh`
   本地构建镜像并打包离线 tar；如果是 `remote-build`，则改为打源码包。
2. `upload_deploy_artifacts.sh`
   把上一步产物上传到服务器，但还不执行远程更新。
3. `update_remote_stack.sh`
   只在服务器上执行备份、`docker load` / `docker build`、`deploy.sh up`，默认带 `--update-db`。

如果这次不想跑数据库 migration：

```bash
DEPLOY_UPDATE_DB=false ./remote-docker-deploy/update_remote_stack.sh \
  --profile prod \
  --remote-deploy-password '你的服务器密码'
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
python3 remote-docker-deploy/remote_docker_deploy.py \
  --profile prod \
  --remote-deploy-password '你的服务器密码'
```

如果你要改回仓库拉取模式：

```bash
python3 remote-docker-deploy/remote_docker_deploy.py \
  --profile prod \
  --delivery-mode registry
```

如果你要改成“上传源码到远程再构建”的模式：

```bash
python3 remote-docker-deploy/remote_docker_deploy.py \
  --profile prod \
  --delivery-mode remote-build \
  --remote-deploy-password '你的服务器密码'
```

这个模式会：

1. 本地打包项目源码
2. 上传到远程项目根目录
3. 远程重新 `docker build`
4. 备份数据库、技能卷、API 数据卷
5. 默认以 `AUTO_RUN_DB_MIGRATIONS=false` 执行 `./deploy.sh up`

如果这次部署需要顺带更新数据库 migration：

```bash
python3 remote-docker-deploy/remote_docker_deploy.py \
  --profile prod \
  --remote-deploy-password '你的服务器密码' \
  --update-db
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
python3 remote-docker-deploy/remote_docker_deploy.py \
  --profile prod \
  --remote-deploy-password '你的服务器密码' \
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
- `--stage all|package|upload|remote`
- `--delivery-mode offline|registry|remote-build`
- `--platform`
- `--api-image`
- `--frontend-image`
- `--artifact-dir`
- `--password`
- `--remote-deploy-password`
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
python3 remote-docker-deploy/sync_resource_visibility.py \
  --profile prod \
  --remote-deploy-password '你的服务器密码'
```

默认行为：

1. 优先从本地 Docker 容器 `ai-employee-postgres` 读取 `employees / rules / skills`
2. 如果本地容器不可用，则回退到本地 JSON 文件源
3. 先备份远程数据库
4. 把本地 `created_by / share_scope / shared_with_usernames` 同步到远程 PostgreSQL

如果你只是想强制把本地读到的这三类资源全部同步为“所有人可见”：

```bash
python3 remote-docker-deploy/sync_resource_visibility.py \
  --profile prod \
  --remote-deploy-password '你的服务器密码' \
  --all-users
```

常用参数：

- `--source auto|docker-postgres|json`
- `--local-postgres-container ai-employee-postgres`
- `--api-data-dir /path/to/web-admin-api`
- `--profile prod`
- `--dry-run`

## 同步本地 PostgreSQL 业务数据到远程库

如果你的代码已经发布了，但远程 PostgreSQL 里的业务数据还是旧的，可以用这个脚本把本地 `ai-employee-postgres` 的公共表同步到远程 PostgreSQL。

典型场景：

- 本地已经有最新员工、项目、规则、技能、记忆、项目聊天等数据
- 远程代码和 schema 已更新，但远程库里还是旧数据
- 你不想手工给每张表导 SQL

基础用法：

```bash
python3 remote-docker-deploy/sync_postgres_data.py \
  --profile prod \
  --remote-deploy-password '你的服务器密码'
```

默认行为：

1. 从本地容器 `ai-employee-postgres` 读取 public schema 下的所有业务表
2. 默认跳过 `schema_migrations`
3. 生成 UPSERT SQL，上传到远程服务器
4. 先备份远程数据库
5. 在远程 `ai-employee-postgres` 里执行同步 SQL

如果你只想同步部分表：

```bash
python3 remote-docker-deploy/sync_postgres_data.py \
  --profile prod \
  --remote-deploy-password '你的服务器密码' \
  --tables users,employees,projects,project_user_members,rules,skills,skill_bindings
```

如果你希望远程表先清空，再完全按本地数据重建：

```bash
python3 remote-docker-deploy/sync_postgres_data.py \
  --profile prod \
  --remote-deploy-password '你的服务器密码' \
  --tables users,employees,projects,project_user_members,rules,skills,skill_bindings \
  --replace
```

常用参数：

- `--tables`
- `--exclude-tables`
- `--replace`
- `--local-postgres-container ai-employee-postgres`
- `--local-db-user admin`
- `--local-db-name ai_employee`
- `--remote-postgres-container ai-employee-postgres`
- `--remote-db-user admin`
- `--remote-db-name ai_employee`
- `--dry-run`

注意：

- 默认是 UPSERT，不会删除远程多出来的旧行；如果你要远程结果严格等于本地，请显式加 `--replace`
- 这个脚本同步的是 PostgreSQL 表数据，不负责 Docker volume 里的文件资产
- 运行前建议先完成代码发布和 schema migration，避免表结构不一致
