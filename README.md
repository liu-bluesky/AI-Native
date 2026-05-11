# AI 员工工厂

AI 员工工厂是一个基于 MCP（Model Context Protocol）的 AI-Native 开发与管理平台。它把项目上下文、员工能力、技能、规则、记忆、人设、任务树和工作轨迹沉淀为可被外部 AI、IDE、CLI、后台系统稳定调用的 MCP 能力，帮助用户创建、管理和持续进化多个 AI 员工。

项目默认采用 `MCP-first` 的产品与架构定位：平台核心能力优先通过项目 MCP、统一查询 MCP、员工 MCP、技能 MCP、规则 MCP 等入口暴露；`web-admin` 管理台主要承担配置、运营、观测、人工验证和可视化管理。

## 核心功能

### 1. AI 员工管理

- 创建、编辑、查看和管理 AI 员工。
- 为员工组合 Skills、Rules、Memory、Persona 等能力模块。
- 支持员工使用情况统计、项目协作和任务执行链路追踪。
- 通过员工 MCP 对外暴露员工级能力，供宿主 Agent 或外部系统调用。

### 2. 项目管理与项目 MCP

- 管理项目、项目成员、项目规则、项目经验和项目素材。
- 支持项目级上下文读取、规则检索、技能调用和项目协作编排。
- 通过 `/mcp/projects/{project_id}` 暴露项目 MCP，让外部 Agent 可以围绕指定项目开展查询、实现、排查和交付。
- 支持项目工作会话、任务树推进、需求记录和执行轨迹沉淀。

### 3. 统一查询 MCP

统一查询 MCP 是宿主只接入一个聚合入口时的推荐入口，挂载在 `/mcp/query`。

它主要负责：

- 定位项目、员工、规则和相关上下文。
- 读取项目手册、员工手册和规则正文。
- 聚合相关能力、经验规则和可用代理工具。
- 分析任务、生成执行步骤、绑定任务树并推进节点状态。
- 维护工作会话、需求记录、工作事实、检查点和交付报告。

一句话总结：统一查询 MCP 的核心是“显式绑定、本地优先、任务树闭环、验证收尾”。

### 4. 技能、规则、记忆与人设

平台内置多类能力服务：

- `mcp-skills`：技能管理，支持技能查询、安装、卸载和资源管理。
- `mcp-rules`：规则管理，支持规则查询、提交、演化和反馈记录。
- `mcp-memory`：记忆管理，支持保存、召回、遗忘和压缩记忆。
- `mcp-persona`：人设管理，支持语气设置、语料训练和快照。
- `mcp-evolution`：进化引擎，基于使用情况和反馈提出规则或能力升级建议。
- `mcp-sync`：同步服务，用于推送更新、同步状态和通知 Agent。

### 5. web-admin 管理台

`web-admin` 提供 Vue 3 + Element Plus 管理界面，主要用于平台配置、运营、调试和观测。

当前前端功能覆盖：

- 初始化、登录、注册和用户权限管理。
- 员工管理、员工详情和员工使用统计。
- 项目列表、项目详情、项目对话、创作工作台、素材库、声音库、短片工作室和作品画廊。
- 技能管理、技能资源管理、规则管理、记忆管理、人设管理。
- 模型供应商配置、系统配置、字典管理、更新日志、机器人连接器。
- MCP 监控、在线用户、统计看板、工作会话管理和任务管理。
- 反馈工单、批量分析、候选规则评审和进化报告。
- 公开介绍页、市场页和更新日志页。

### 6. 任务树与工作轨迹

平台将需求执行过程结构化为任务树和工作会话：

- 每个需求可以绑定独立的 `chat_session_id` 和 `session_id`。
- 任务树节点用于描述分析、实现、验证等面向用户目标的步骤。
- 工作事实、会话事件和检查点用于支持中断恢复、过程审计和结果追溯。
- 交付前要求补齐验证结果，避免只用自然语言声明“已完成”。

## 使用主次定位

当前项目默认按 `MCP-first` 理解和设计：

- 主入口是 `项目 MCP` 与 `统一查询 MCP`，优先服务宿主 AI、IDE、CLI 或其他外部 Agent 的接入与调用。
- `web-admin` 里的 AI 对话框属于次要入口，主要承担演示、运营配置、人工验证、问题排查和任务可视化，不应反向定义平台主能力边界。
- 新功能设计时，默认先回答“是否能通过 MCP tools/resources/prompts/任务树上下文稳定暴露”，再决定是否补充聊天页面或后台界面。
- 若某项能力只能在聊天框里使用、却无法沉淀为 MCP 能力或项目级可追溯数据，默认不应视为平台核心能力完成。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + Composition API + Element Plus + Vite |
| 后端 API | Python FastAPI + Pydantic |
| MCP 服务 | FastMCP |
| 存储 | PostgreSQL / JSON / SQLite（按模块切换） |
| 认证 | JWT HS256 |
| 包管理 | 前端 npm / 后端 pyproject.toml |
| 部署 | Docker Compose / 本地直跑 |

## 后端数据库配置

后端数据库配置分成两个入口：

- 本地直跑后端：`web-admin/api/.env`
- Docker 编排：`docker/.env`

推荐规则：

- 应用内部优先使用 `DATABASE_URL`。
- `DB_HOST`、`DB_PORT`、`DB_USER`、`DB_PASSWORD`、`DB_NAME` 只作为兼容回退。
- 真实环境变量优先级高于 `.env` 文件。
- 本地 API 会自动读取 `web-admin/api/.env` 和 `web-admin/api/.env.local`。

### 本地直跑后端

准备配置文件：

```bash
cp web-admin/api/.env.example web-admin/api/.env
```

默认示例使用本机 PostgreSQL：

```env
DATABASE_URL=postgresql://admin:changeme@127.0.0.1:5432/ai_employee
CORE_STORE_BACKEND=postgres
USAGE_STORE_BACKEND=postgres
```

初始化并启动：

```bash
cd web-admin/api
pip install -e .
python init_admin.py
python server.py
```

### Docker 启动整套服务

准备 Docker 配置：

```bash
cp docker/.env.example docker/.env
```

`docker/.env` 负责 Compose 级别的数据库参数和存储后端，例如：

```env
DB_USER=admin
DB_PASSWORD=changeme
DB_NAME=ai_employee
DB_PORT=5432
CORE_STORE_BACKEND=postgres
USAGE_STORE_BACKEND=postgres
```

启动：

```bash
cd docker
docker compose up -d --build
```

访问地址：

- 前端：`http://localhost:3000`
- API：`http://localhost:8000`

## 常用启动方式

### 前端开发

```bash
cd web-admin/frontend
npm install
npm run dev
```

前端开发服务器默认走代理，接口指向后端 `8000`。

### 后端开发

```bash
cd web-admin/api
pip install -e .
python init_admin.py
python server.py
```

### 生产方式启动 API

```bash
cd web-admin/api
uvicorn server:app --host 0.0.0.0 --port 8000
```

### 独立运行 MCP 服务示例

```bash
cd mcp-skills
pip install -e .
python server.py
```

## API 与 MCP 入口

后端 FastAPI 应用会挂载多个 MCP 代理入口：

- `/mcp/query`：统一查询 MCP。
- `/mcp/projects/{project_id}`：项目 MCP。
- `/mcp/employees/{employee_id}`：员工 MCP。
- `/mcp/skills/{skill_id}`：技能 MCP。
- `/mcp/rules/{rule_id}`：规则 MCP。

常规业务 API 由 `web-admin/api/core/routers/` 下的路由模块提供，包括项目、员工、技能、规则、记忆、人设、进化、同步、统计、MCP 监控、工作会话、用户权限等模块。

## 项目结构

```text
ai-employee/
├── docs/                         # 项目文档、架构设计、专项方案和 PRD
├── rules/                        # AI 可消费的编码与架构规则
├── agents/                       # 项目专属智能体定义
├── mcp-skills/                   # 技能管理 MCP 服务
├── mcp-rules/                    # 规则管理 MCP 服务
├── mcp-memory/                   # 记忆管理 MCP 服务
├── mcp-persona/                  # 人设管理 MCP 服务
├── mcp-evolution/                # 进化引擎 MCP 服务
├── mcp-sync/                     # 同步 MCP 服务
├── mcp-common/                   # MCP 通用能力与共享代码
├── mcp-server/                   # MCP 服务相关入口与配置
├── docker/                       # Docker Compose 部署配置
├── remote-docker-deploy/         # 远程 Docker 发布工具
└── web-admin/
    ├── api/                      # FastAPI 后端与 MCP 代理入口
    └── frontend/                 # Vue 3 管理台
```

## 关键开发约定

- 新能力默认优先设计为 MCP tool/resource/prompt 或项目级 API，再考虑是否补充后台页面。
- 涉及需求执行、项目协作、任务恢复和交付时，应维护任务树、工作会话和验证结果。
- 修改前端代码前优先阅读 `rules/frontend.md`。
- 修改后端代码前优先阅读 `rules/backend.md`。
- 修改 MCP 服务前优先阅读 `rules/mcp-service.md`。
- 涉及跨层架构、权限边界或数据流时优先阅读 `rules/architecture.md`。

## 文档

- [项目总览](docs/00-项目总览/PROJECT.md)
- [Docker 使用说明](docker/README.md)
- [远程 Docker 发布工具](remote-docker-deploy/README.md)
- [编码规范](rules/)

## License

MIT
