# 完整目录结构 & 文件讲解

## 顶级目录

```
ai-employee/
├── web-admin/                # 🖥️ 管理台 (FastAPI后端 + Vue3前端)
├── mcp-skills/               # 🧩 技能管理 MCP 服务
├── mcp-rules/                # 📋 规则管理 MCP 服务
├── mcp-memory/               # 🧠 记忆管理 MCP 服务
├── mcp-persona/              # 🎭 人设管理 MCP 服务
├── mcp-evolution/            # 🔄 进化引擎 MCP 服务
├── mcp-sync/                 # 🔁 同步 MCP 服务
├── docker/                   # 🐳 Docker Compose 部署配置
├── remote-docker-deploy/     # 🚀 远程 Docker 发布工具
├── docs/                     # 📚 项目文档 (架构设计/PRD/方案)
├── rules/                    # ⚖️ AI 可消费的编码与架构规则
├── agents/                   # 🤖 项目专属智能体定义
├── assets/                   # 🖼️ 静态资源
├── codeDocs/                 # 📖 代码文档 (本目录)
├── AGENTS.md                 # AI Agent 接入规则
├── CLAUDE.md                 # Claude Code 使用说明
├── HERMES.md                 # Hermes 使用说明
├── README.md                 # 项目主说明文档
├── skills-lock.json          # 技能版本锁定文件
├── 工作流.md                 # 工作流说明
├── AI开发教程.md             # AI开发教程
├── lark-cli.md               # 飞书CLI说明
├── image.png                 # 项目截图
└── LICENSE                   # 开源协议
```

---

## 根目录文件详解

### `AGENTS.md`
**AI Agent 接入统一查询 MCP 的强制规则。** 这是项目最重要的入口文件之一。任何接入本项目的 AI Agent（如 Claude Code、Codex CLI）都必须遵循此文件中定义的规则。主要规定：
- 必须先读取 `query://usage-guide` 和 `query://client-profile/codex`
- 在当前 CLI 工作区初始化 `.ai-employee/` 目录结构
- 检查并同步 `query-mcp-workflow` 技能包
- 实现型需求优先调用 `start_project_workflow(...)` 作为固定入口
- 维护本地 requirement 对象和服务端任务树双写
- 清晰度评分机制（1-5分），低于3分需先确认再执行

### `CLAUDE.md`
**Claude Code CLI 的使用说明。** 指导用户如何在 Claude Code 环境中使用本项目，包括安装、配置、常用命令和工作流。

### `HERMES.md`
**Hermes AI 助手的使用说明。** 指导用户如何在 Hermes 环境中接入本项目的 MCP 能力。

### `README.md`
**项目主说明文档。** 介绍 AI 员工工厂的核心概念、功能特性、架构设计和快速开始指南。包括 AI 员工管理、项目管理、统一查询 MCP、技能/规则/记忆/人设体系等功能说明。

### `skills-lock.json`
**技能版本锁定文件。** 锁定当前项目中所有飞书技能包（22个 lark-* 技能）的版本，确保团队使用一致的技能版本。

### `工作流.md`
**工作流说明文档。** 描述项目的标准工作流程，包括需求分析、任务规划、执行和交付等阶段。

### `AI开发教程.md`
**AI 开发教程。** 面向开发者的教程文档，指导如何基于本项目进行 AI-Native 开发。

### `lark-cli.md`
**飞书 CLI 说明。** 介绍 `lark-cli` 命令行工具的使用方法，包括技能调用、命令语法和常见场景。

### `LICENSE`
**开源许可证文件。**

### `image.png`
**项目架构截图或示意图。**

---

## 一级子目录详解

### `web-admin/` — 管理台

> 详细文档见 [web-admin.md](./web-admin.md)

```
web-admin/
├── api/                      # FastAPI 后端
│   ├── server.py             # 入口文件
│   ├── pyproject.toml        # Python 项目配置
│   ├── uv.lock               # uv 依赖锁定
│   ├── .env / .env.example   # 环境变量配置
│   ├── init_admin.py         # 初始化管理员脚本
│   ├── system-policy.md      # 系统策略文档
│   ├── core/                 # 核心模块
│   ├── routers/              # API 路由 (28个模块)
│   ├── services/             # 业务服务层
│   ├── models/               # Pydantic 数据模型
│   ├── schemas/              # 数据库 Schema
│   ├── ws/                   # WebSocket 支持
│   ├── tasks/                # 后台任务
│   ├── db_utils/             # 数据库工具
│   ├── utils/                # 通用工具
│   ├── tests/                # 测试用例
│   ├── mcp/                  # 内置 MCP 端点
│   └── migrations/           # 数据库迁移
├── frontend/                 # Vue3 前端
│   ├── package.json          # npm 配置
│   ├── vite.config.ts        # Vite 构建配置
│   ├── index.html            # 入口 HTML
│   ├── nginx.conf            # Nginx 配置
│   ├── src/
│   │   ├── main.ts           # 前端入口
│   │   ├── App.vue           # 根组件
│   │   ├── router/           # 路由配置
│   │   ├── stores/           # Pinia 状态管理
│   │   ├── api/              # API 请求层
│   │   ├── views/            # 页面视图
│   │   ├── components/       # 公共组件
│   │   ├── layouts/          # 布局组件
│   │   └── utils/            # 工具函数
│   └── public/               # 静态资源
├── docker-compose.yml        # 开发环境编排
├── docker-compose.test.yml   # 测试环境编排
├── docker-compose.prod.yml   # 生产环境编排
└── docker-compose.base.yml   # 基础服务编排
```

### `mcp-skills/` — 技能管理 MCP 服务

> 详细文档见 [mcp-services.md](./mcp-services.md)

```
mcp-skills/
├── server.py                 # MCP 服务入口 (FastMCP)
├── pyproject.toml            # Python 项目配置
├── .env.example              # 环境变量模板
└── knowledge/
    ├── skills/               # 技能定义 (JSON)
    │   ├── query-mcp-workflow.json  # 统一查询工作流技能定义
    │   └── ...
    └── skill-packages/       # 技能包目录
        └── query-mcp-workflow/
            ├── SKILL.md      # 技能主文档
            ├── manifest.json # 技能清单
            ├── prompts/      # 提示词模板
            └── references/   # 参考文档
```

**职责：** 管理所有可用技能的注册、发现、查询和下发。外部 Agent 通过此 MCP 服务获取可用的技能定义和提示词模板。

### `mcp-rules/` — 规则管理 MCP 服务

```
mcp-rules/
├── server.py                 # MCP 服务入口
├── pyproject.toml            # Python 项目配置
├── .env.example              # 环境变量模板
└── knowledge/
    └── rules/                # 规则定义 (JSON)
        ├── coding-standards.json   # 编码规范
        ├── architecture.json       # 架构约束
        └── ...
```

**职责：** 管理项目规则、编码规范和架构约束。提供规则的 CRUD、检索和应用能力，确保 AI 员工行为符合项目约定。

### `mcp-memory/` — 记忆管理 MCP 服务

```
mcp-memory/
├── server.py                 # MCP 服务入口
├── pyproject.toml            # Python 项目配置
├── __init__.py               # 包初始化
├── knowledge.db              # 知识库 (SQLite)
└── memory_store.db           # 记忆存储 (SQLite)
```

**职责：** 管理 AI 员工和项目的长期记忆。支持记忆的持久化存储、检索和上下文注入，让 AI 员工可以跨会话保持知识连续性。

### `mcp-persona/` — 人设管理 MCP 服务

```
mcp-persona/
├── server.py                 # MCP 服务入口
└── pyproject.toml            # Python 项目配置
```

**职责：** 管理 AI 员工的人设定义。包括角色性格、沟通风格、专业领域等配置，让每个 AI 员工具有独特的行为特征。

### `mcp-evolution/` — 进化引擎 MCP 服务

```
mcp-evolution/
├── server.py                 # MCP 服务入口
├── pyproject.toml            # Python 项目配置
└── __init__.py               # 包初始化
```

**职责：** 驱动 AI 员工的持续进化。根据使用反馈、任务表现和经验积累，自动调整和优化员工的能力配置、规则优先级和行为策略。

### `mcp-sync/` — 同步 MCP 服务

```
mcp-sync/
├── server.py                 # MCP 服务入口
└── pyproject.toml            # Python 项目配置
```

**职责：** 负责跨服务间的数据同步。确保技能、规则、记忆、人设等模块的状态一致性，支持多服务协同工作。

---

### `docker/` — Docker 部署配置

```
docker/
├── docker-compose.yml        # 开发环境 Docker Compose
├── docker-compose.test.yml   # 测试环境 Docker Compose
├── docker-compose.prod.yml   # 生产环境 Docker Compose
├── docker-compose.base.yml   # 基础服务 (DB/Redis) 编排
├── .env.example              # 环境变量模板
├── nginx/                    # Nginx 配置
├── postgres/                 # PostgreSQL 初始化脚本
├── redis/                    # Redis 配置
├── scripts/                  # 辅助脚本
└── README*.md                # 部署说明文档
```

> 详细文档见 [deploy-and-config.md](./deploy-and-config.md)

### `remote-docker-deploy/` — 远程部署工具

```
remote-docker-deploy/
├── deploy.sh                 # 部署脚本
├── Dockerfile                # 应用镜像定义
├── docker-compose.yml        # 远程部署编排
├── .env.example              # 环境变量模板
└── *.py                      # 部署辅助脚本
```

**职责：** 将项目部署到远程 Docker 主机的工具集。包含镜像构建、服务启动、健康检查和回滚机制。

### `docs/` — 项目文档

```
docs/
├── architecture/             # 架构设计文档
├── prd/                      # 产品需求文档
├── design/                   # 设计方案
├── guides/                   # 使用指南
├── api/                      # API 文档
└── images/                   # 文档图片
```

**职责：** 汇集项目的架构设计、产品需求、技术方案和使用指南文档。

### `rules/` — AI 编码规则

```
rules/
├── coding-standards.md       # 编码规范
├── architecture-rules.md     # 架构约束
├── api-design.md             # API 设计规范
├── testing.md                # 测试规范
└── git-workflow.md           # Git 工作流规范
```

**职责：** 定义 AI Agent 在开发和维护项目时必须遵循的规则。这些规则可被 MCP 规则服务读取并注入到 AI 上下文中。

### `agents/` — 智能体定义

```
agents/
├── developer.md              # 开发者智能体
├── reviewer.md               # 代码审查智能体
├── tester.md                 # 测试智能体
└── architect.md              # 架构师智能体
```

**职责：** 定义项目中各类 AI 智能体的角色、职责、技能组合和行为规则。

---

## 架构关系图

```
                   ┌──────────────────┐
                   │  外部 AI/IDE/CLI  │
                   └────────┬─────────┘
                            │ MCP 协议
              ┌─────────────┼─────────────┐
              │             │             │
    ┌─────────▼──┐  ┌──────▼──────┐  ┌──▼──────────┐
    │  统一查询   │  │  员工 MCP   │  │  项目 MCP   │
    │  /mcp/query │  │ /mcp/emp/*  │  │ /mcp/proj/* │
    └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
           │                │                │
    ┌──────▼────────────────▼────────────────▼──────┐
    │              Web-Admin API 网关                │
    │         (FastAPI + 28 个路由模块)              │
    └──────┬──────────┬──────────┬──────────────────┘
           │          │          │
    ┌──────▼──┐ ┌─────▼───┐ ┌───▼──────────┐
    │ Skills  │ │  Rules  │ │ Memory/Persona│
    │  MCP    │ │  MCP    │ │  MCP          │
    └────┬────┘ └────┬────┘ └──────┬────────┘
         │           │             │
    ┌────▼───────────▼─────────────▼────┐
    │     PostgreSQL 17 + Redis 7       │
    │        (数据持久化层)              │
    └───────────────────────────────────┘
```
