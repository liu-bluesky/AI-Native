# 目录结构与模块边界

> 更新日期：2026-06-04

## 顶级目录

```text
ai-employee/
├── web-admin/                 # Web 管理台：FastAPI API + Vue 前端
├── mcp-skills/                # 独立技能 MCP 服务与系统技能包知识库
├── mcp-rules/                 # 独立规则 MCP 服务
├── mcp-memory/                # 独立记忆 MCP 服务
├── mcp-persona/               # 独立人设 MCP 服务
├── mcp-evolution/             # 独立进化引擎 MCP 服务
├── mcp-sync/                  # 独立同步 MCP 服务
├── docker/                    # Docker Compose、镜像构建和发布文档
├── remote-docker-deploy/      # 远程 Docker 发布、数据同步与回滚脚本
├── docs/                      # 产品、架构、专项方案与历史设计文档
├── rules/                     # 仓库级 Markdown 规则
├── agents/                    # 仓库级专用 Agent 角色说明
├── skills/                    # 本地/宿主技能目录，当前主要承载飞书技能体系
├── assets/                    # 静态资源
├── feishu-archive-upload/     # 飞书归档上传相关资产
├── codeDocs/                  # 当前代码文档
├── .ai-employee/              # 本地 query-mcp、requirement、技能副本和运行状态
├── AGENTS.md                  # Codex/Agent 接入当前项目的强制规则
├── CLAUDE.md                  # Claude Code 入口说明
├── HERMES.md                  # Hermes 入口说明
├── README.md                  # 项目主说明
├── lark-cli.md                # 飞书 CLI 使用说明
├── skills-lock.json           # 技能版本锁定
├── 工作流.md                  # 工作流说明
├── AI开发教程.md              # AI 开发教程
└── LICENSE                    # 许可证
```

## 根目录关键文件

| 路径 | 说明 |
|---|---|
| `AGENTS.md` | 当前项目内 Agent 的最高优先级项目入口规则。要求读取统一查询 MCP 资源、初始化 `.ai-employee/`、维护 requirement、任务树和工作事实。 |
| `README.md` | 项目总览，说明 MCP-first 定位、核心功能、Web-Admin、任务树与工作流。 |
| `CLAUDE.md` / `HERMES.md` | 不同宿主 Agent 的使用约定。 |
| `skills-lock.json` | 锁定宿主技能版本，当前包含大量 `lark-*` 技能。 |
| `lark-cli.md` | 飞书 CLI 命令、认证和技能使用说明。 |
| `rules/*.md` | 仓库级规则，包括 `architecture.md`、`backend.md`、`frontend.md`、`homepage-ui.md`、`mcp-service.md`、`query-mcp-prompt-sync.md`、`ui-design.md`。 |
| `agents/*.md` | 专用角色提示文档：后端、前端、MCP 架构、安全审计。 |

## `web-admin/`

详见 [web-admin.md](./web-admin.md)。

```text
web-admin/
├── api/
│   ├── server.py              # API 入口，转发到 core.server
│   ├── pyproject.toml         # 后端依赖与 pytest 配置
│   ├── core/                  # 配置、认证、依赖、迁移、权限、Redis、可观测性
│   ├── core/sql_migrations/   # PostgreSQL SQL 迁移
│   ├── routers/               # FastAPI 路由模块
│   ├── services/              # 业务服务、动态 MCP、Agent Runtime、连接器、后台任务
│   ├── stores/                # JSON/PostgreSQL store 实现与工厂
│   ├── models/                # 请求、响应、数据库模型
│   ├── scripts/               # 启停、迁移、初始化、修复脚本
│   └── tests/                 # pytest 测试
└── frontend/
    ├── package.json           # 前端依赖与 npm scripts
    ├── vite.config.js         # Vite 配置
    ├── index.html             # SPA 入口
    └── src/
        ├── main.js            # Vue 应用入口
        ├── App.vue
        ├── router/            # Vue Router
        ├── views/             # 页面
        ├── components/        # 复用组件
        ├── modules/           # 项目聊天、任务树反馈等局部模块
        ├── utils/             # API、权限、认证、工作区、日期等工具
        ├── api/               # 前端 API 封装
        └── styles/            # UI 设计样式
```

## 独立 MCP 服务

详见 [mcp-services.md](./mcp-services.md)。

每个根目录 MCP 服务基本都有：

- `server.py`：FastMCP 服务入口。
- `store.py`：本地存储/知识库访问。
- `pyproject.toml`：服务依赖。
- `knowledge/`：对应服务的本地知识库或数据目录。

| 目录 | 服务名 | 主要职责 |
|---|---|---|
| `mcp-skills/` | `skills-service` | 技能查询、安装、卸载、技能资源。 |
| `mcp-rules/` | `rules-service` | 规则查询、提交、演化、反馈统计。 |
| `mcp-memory/` | `memory-service` | 记忆保存、召回、压缩、身份信号。 |
| `mcp-persona/` | `persona-service` | 人设、语气、风格、快照、漂移评估。 |
| `mcp-evolution/` | `evolution-engine` | 使用模式分析、候选规则、自动进化、报告。 |
| `mcp-sync/` | `sync-service` | 更新推送、状态同步、Agent 通知。 |

## `docker/`

详见 [deploy-and-config.md](./deploy-and-config.md)。

```text
docker/
├── docker-compose.yml         # 本地/开发 Compose
├── docker-compose.test.yml    # 测试 Compose
├── compose.prod.yml           # 生产 Compose
├── Dockerfile.api             # Python 3.12 + FastAPI API 镜像
├── Dockerfile.frontend        # Node 20 build + Nginx runtime
├── nginx.conf                 # 前端容器 Nginx 与 /api/ 反代
├── deploy.sh / deploy.ps1     # 部署脚本
├── build-publish-images.sh    # 镜像构建发布脚本
├── init/001_usage_schema.sql  # 初始化 SQL
├── backup/                    # 本地备份样例
├── dist/                      # 镜像归档产物目录
└── README*.md / 部署.md       # 部署、发布、迁移、测试说明
```

## `remote-docker-deploy/`

远程发布工具集，当前不是单一 `deploy.sh` 结构，而是 Python 编排器加三个阶段脚本：

| 文件 | 说明 |
|---|---|
| `remote_docker_deploy.py` | 主编排器，支持 `package`、`upload`、`remote`、`rollback` 等阶段。 |
| `package_deploy_artifacts.sh` | 本地构建并打包离线镜像 tar，或 remote-build 源码包。 |
| `upload_deploy_artifacts.sh` | 上传产物到远程服务器，不执行部署。 |
| `update_remote_stack.sh` | 在远端做预检查、备份、`docker load/build`、`deploy.sh up`，默认带 `--update-db`。 |
| `sync_postgres_data.py` | 将本地 PostgreSQL 业务表同步到远端。 |
| `sync_resource_visibility.py` | 同步员工、规则、技能的可见范围。 |
| `.remote-deploy.prod.json` | `prod` profile 的非敏感配置。 |

## `docs/`

`docs/` 是产品和技术方案库，和 `codeDocs/` 的职责不同。当前主要结构：

```text
docs/
├── README.md
├── 开发经验.md
├── 总结文档.md
├── 00-项目总览/
├── 10-平台架构设计/
├── 20-产品应用设计/
├── 30-专项功能方案/
├── 40-数据存储升级/
├── 反馈驱动规则升级模块/
└── update/
```

其中 `30-专项功能方案/` 保存大量当前功能演进方案，例如统一查询 MCP、任务树闭环、Agent Runtime、项目素材、短片工作室、飞书机器人等。

## `.ai-employee/`

这是当前工作区的本地运行状态与技能副本目录，不能把其他子目录的同名目录当成当前根目录状态。

| 路径 | 说明 |
|---|---|
| `.ai-employee/skills/query-mcp-workflow/` | 本地统一查询 MCP 工作流技能副本。 |
| `.ai-employee/query-mcp/active-sessions/` | 每个 CLI 会话的 canonical 本地状态。 |
| `.ai-employee/query-mcp/active/<project_id>.json` | 历史遗留项目级指针，只读恢复使用，禁止新写，不能代表当前窗口。 |
| `.ai-employee/query-mcp/session-history/` | 项目 + 会话历史状态。 |
| `.ai-employee/requirements/<project_id>/` | 每个需求的本地 requirement 对象。 |
| `.ai-employee/operation-wait-tasks/` | 操作等待任务状态。 |
| `.ai-employee/cli-toolchain/` | CLI 插件/工具链根目录。 |

## 需要避免的旧文档误差

- 前端入口是 `src/main.js`，不是 `main.ts`。
- Vite 配置是 `vite.config.js`，不是 `vite.config.ts`。
- 后端当前没有 `schemas/`、`ws/`、`tasks/`、`db_utils/` 这些顶层目录。
- `docker/` 下没有 `docker-compose.prod.yml` 或 `docker-compose.base.yml`，生产编排是 `compose.prod.yml`。
- `remote-docker-deploy/` 没有 `deploy.sh`、`Dockerfile`、`docker-compose.yml`，远程部署由 Python 编排器和阶段脚本完成。
