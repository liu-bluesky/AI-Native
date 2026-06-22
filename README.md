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

## 当前智能体工作流模块

当前智能体工作流由“入口识别、能力路由、统一查询、任务树、运行时执行、权限验证、轨迹恢复”几类模块组成。它们共同保证外部 Agent、IDE、CLI 或后台对话入口收到需求后，能够先理解任务，再选择能力，最后完成可追踪、可恢复、可验证的交付。

### 术语约定：本地智能体与后端系统智能体

为避免在项目对话、机器人接入和桌面端运行链路里混用“智能体”一词，后续默认按下面两个术语区分：

- **桌面本地智能体**：指运行在用户电脑桌面端的本地 runtime，入口在前端 Tauri / native bridge。它负责在本机工作区内执行本地工具，例如读取文件、运行命令、处理本机授权和维护本地 requirement 记录；模型调用也由本机 runtime 发起，使用系统里配置的 OpenAI-compatible 模型接口。后端只提供配置读取、记录同步和审计存储，不直接执行本机工具。
- **后端系统智能体**：指运行在后端 API / Agent Runtime / 项目聊天系统对话链路里的旧智能体。它由后端解析项目上下文、模型供应商、任务树、工具和权限策略，使用后端可访问的模型供应商配置发起模型调用。该链路已进入淘汰方向，后续新开发禁止继续扩展或新增依赖，存量代码只允许做迁移、兼容清理和删除准备。

简写约定：用户说“本地智能体”“电脑本地智能体”时，默认指桌面本地智能体；用户说“机器人模块”“平台机器人”时，也默认要求接入桌面本地智能体，除非明确说明是在排查旧后端系统智能体存量代码；用户说“后端智能体”时，默认指待删除的旧链路。

机器人配置约束：飞书、QQ、微信等第三方机器人接入不应再把大模型对话接到后端系统智能体。机器人配置里的大模型选择只用于声明桌面本地智能体运行时要使用的模型目标；平台消息应进入“后端记录/排队 -> 桌面端本地智能体领取执行 -> 回写结果”的链路。若桌面端接管队列尚未接通，必须显式标记为迁移缺口，不允许静默回退到后端系统对话。

### 1. 工作流状态识别

核心位置：`web-admin/api/services/assistant/assistant_workflow_state_service.py`、`web-admin/api/services/assistant/assistant_workflow_policy_service.py`。

该模块负责从用户消息中识别任务类型，例如查询、文档、开发、自动化、日程、提醒、缺陷修复等；再生成 `assistant_workflow` 状态，决定当前任务是直接回答、工具增强、收集后确认，还是进入真实 Agent 执行。它也负责一次性确认策略，避免已经确认过的写入类任务反复询问。

### 2. 能力路由

核心位置：`web-admin/api/services/assistant/assistant_capability_router_service.py`、`web-admin/api/services/runtime/tool_registry.py`。

该模块负责根据任务类型和现有工具清单选择优先使用的能力来源。比如代码任务优先本地连接器和命令工具，日程与文档任务优先项目技能、外部 MCP 或系统 MCP，查询任务优先项目工具和项目技能。它的目标是复用已有工具、技能和 MCP 能力，而不是把每个新需求都误判为“需要新增技能”。

### 3. 统一查询 MCP 工作流

核心位置：`web-admin/api/services/mcp/dynamic_mcp_apps_query.py`、`.ai-employee/skills/query-mcp-workflow/`。

统一查询 MCP 是项目级任务的聚合入口，负责绑定 `project_id`、`chat_session_id` 和本地工作区，读取项目手册，分析任务，聚合相关上下文，生成执行计划，并维护本地 requirement 对象。它强调显式绑定、本地优先和任务树闭环，避免仅依赖自然语言描述来表示任务进度。

### 4. 项目上下文与规则模块

核心位置：项目 MCP、员工 MCP、规则 MCP、技能 MCP，以及 `get_manual_content`、`resolve_relevant_context`、`resolve_project_experience_rules` 等查询工具。

该模块负责把项目手册、员工手册、项目规则、员工规则、经验规则、技能代理工具和历史记忆聚合给 Agent。执行任务前，Agent 应优先使用项目绑定的员工、规则和技能；只有项目现有能力不足时，才使用通用能力补足。

### 5. 任务树闭环

核心位置：`get_current_task_tree`、`update_task_node_status`、`complete_task_node_with_verification`，以及项目任务树服务。

任务树把一次需求拆成面向用户目标的节点，例如分析现状、实现改动、验证结果。开始节点前需要标记 `in_progress`，完成节点时必须写入验证结果。整棵树全部完成后归档到项目历史，后续可以通过项目、聊天会话和工作会话追溯。

### 6. Agent Runtime

核心位置：`web-admin/api/services/agent_runtime/`。

这是后台真实执行型任务的运行时外壳。它创建 `TaskRun`，记录运行事件和对话转录，构建可恢复上下文，并根据 `assistant_workflow` 选择 `query_engine` 或 legacy orchestrator。运行时按 `core / v2 / shared / integrations` 分层，主要子模块包括：

- `v2/runtime.py`：组织一次 Agent 运行，建立运行上下文并流式输出结果。
- `core/task_run.py` / `core/state_store.py`：保存任务运行对象和状态。
- `v2/query_engine.py`：驱动模型、工具调用和多轮观察。
- `v2/dynamic_tool_pool.py` / `shared/tool_registry.py`：整理运行时可用工具和插件。
- `shared/tool_execution_runner.py` / `shared/tool_results.py`：执行工具并标准化工具观察结果。
- `core/event_log.py` / `core/transcript_store.py` / `v2/run_inspector.py`：记录事件、转录和运行快照，便于审计与排查。
- `integrations/external_executor.py` / `integrations/gateway.py`：对接外部执行器和网关。

### 7. 权限、信任与验证

核心位置：`agent_runtime/v2/permission_policy.py`、`agent_runtime/v2/permission_store.py`、`agent_runtime/shared/trust_policy.py`、`agent_runtime/shared/verification_policy.py`、`agent_runtime/shared/completion_policy.py`。

该模块负责判断工具调用是否需要用户授权、当前工作区是否可信、开发型任务是否必须提供验证证据，以及一次任务能否完成。完成策略会检查模型回复、后台操作、用户待办、工具错误、验证状态和任务树验证结果，避免在缺少证据时提前收口。

### 8. 中断恢复与后台操作续跑

核心位置：`agent_runtime/v2/resume_service.py`、`agent_runtime/v2/operation_resume.py`、`web-admin/api/services/mcp/query_mcp_project_state.py`。

该模块负责在权限等待、后台操作、CLI 中断或页面刷新后恢复同一个任务。统一查询 MCP 会把 `chat_session_id`、`session_id`、requirement、任务树和本地 query-mcp 状态写到 `.ai-employee/` 下的 canonical 路径；Agent Runtime 则通过运行快照、事件日志和恢复上下文继续原来的工具调用或后台操作。

### 9. 可视化与观测入口

核心位置：`web-admin` 管理台、MCP 监控、任务树视图、工作会话管理、Agent Runtime inspector。

该模块面向运营、调试和人工验证。它展示当前任务树、工作会话、运行事件、工具调用、权限状态和执行结果，帮助判断任务是正在执行、等待确认、已失败，还是已验证完成。

整体链路可以概括为：

```text
用户需求
  -> 工作流状态识别
  -> 能力路由
  -> 统一查询 MCP / 项目 MCP 聚合上下文
  -> 任务树与本地 requirement 绑定
  -> Agent Runtime 或现有项目工具执行
  -> 权限、信任、验证与完成策略检查
  -> 工作事实、事件日志、任务树归档和交付报告
```

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

如果你启用“网页在线安装 CLI 插件”的 Docker 方案 B，当前默认会把 CLI 工具根目录持久化到 API 容器内 `/app/.ai-employee/cli-toolchain`，用于保存：

- 公共 CLI 本体与二进制
- npm 全局 prefix
- CLI 安装检测用的运行时工具链信息

启动：

```bash
cd docker
docker compose up -d --build
```

这套 compose 默认还会额外挂载一份 CLI toolchain 持久化目录：

- 本地 compose：`${HOME}/.ai-employee/cli-toolchain -> /app/.ai-employee/cli-toolchain`
- 生产 compose：Docker volume `ai_employee_cli_toolchain_prod -> /app/.ai-employee/cli-toolchain`

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
前端本地环境变量放在 `web-admin/frontend/.env`。例如：

```env
VITE_API_PROXY_TARGET=http://127.0.0.1:8000
VITE_SHOW_LOCAL_RUNTIME_SETTINGS=true
```

如果你本地也想隐藏 AI 对话设置里的本机控制项，把它改成：

```env
VITE_SHOW_LOCAL_RUNTIME_SETTINGS=false
```

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

常规业务 API 由 `web-admin/api/routers/` 下的路由模块提供，包括项目、员工、技能、规则、记忆、人设、进化、同步、统计、MCP 监控、工作会话、用户权限等模块。

## 项目结构

```text
ai-employee/
├── docs/                         # 项目文档、架构设计、专项方案和 PRD
├── rules/                        # AI 可消费的编码与架构规则
├── agents/                       # 项目专属智能体定义
├── skills/                       # 可复用技能包与脚本
├── assets/                       # 静态素材与资源
├── mcp-skills/                   # 技能管理 MCP 服务
├── mcp-rules/                    # 规则管理 MCP 服务
├── mcp-memory/                   # 记忆管理 MCP 服务
├── mcp-persona/                  # 人设管理 MCP 服务
├── mcp-evolution/                # 进化引擎 MCP 服务
├── mcp-sync/                     # 同步 MCP 服务
├── docker/                       # Docker Compose 部署配置
├── remote-docker-deploy/         # 远程 Docker 发布工具
├── feishu-archive-upload/        # 飞书归档上传工具
└── web-admin/
    ├── api/                      # FastAPI 后端与 MCP 代理入口
    └── frontend/                 # Vue 3 管理台（含 src-tauri 桌面端）
```

## 关键开发约定

- 新能力默认优先设计为 MCP tool/resource/prompt 或项目级 API，再考虑是否补充后台页面。
- 涉及需求执行、项目协作、任务恢复和交付时，应维护任务树、工作会话和验证结果。
- 修改前端代码前优先阅读 `rules/frontend.md`。
- 修改后端代码前优先阅读 `rules/backend.md`。
- 修改 MCP 服务前优先阅读 `rules/mcp-service.md`。
- 涉及跨层架构、权限边界或数据流时优先阅读 `rules/architecture.md`。

## 文档

- [AI 项目执行系统目标定义](docs/00-项目总览/AI项目执行系统目标定义.md)
- [Docker 使用说明](docker/README.md)
- [远程 Docker 发布工具](remote-docker-deploy/README.md)
- [编码规范](rules/)

## License

MIT
