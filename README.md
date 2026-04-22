# AI 员工工厂

基于 MCP（Model Context Protocol）的 AI-Native 开发平台。用户可自由组合 Skills、Rules、Memory、Persona 创建多个 AI 员工，并通过进化引擎持续优化能力。
/Users/liulantian/.vett/skills/github/awesome-copilot/refactor

## 使用主次定位

当前项目默认按 `MCP-first` 理解和设计：

- 主入口是 `项目 MCP` 与 `统一查询 MCP`，优先服务宿主 AI、IDE、CLI 或其他外部 Agent 的接入与调用。
- `web-admin` 里的 AI 对话框属于次要入口，主要承担演示、运营配置、人工验证、问题排查和任务可视化，不应反向定义平台主能力边界。
- 新功能设计时，默认先回答“是否能通过 MCP tools/resources/prompts/任务树上下文稳定暴露”，再决定是否补充聊天页面或后台界面。
- 若某项能力只能在聊天框里使用、却无法沉淀为 MCP 能力或项目级可追溯数据，默认不应视为平台核心能力完成。

## 统一查询 MCP 当前工作流

当前项目里，统一查询 MCP 的推荐链路可以简单理解成 7 步：

1. 初始化
   先读取 `query://usage-guide`；在 Codex 这类代码 CLI 中，再读取 `query://client-profile/codex`。同时确保当前工作区存在本地工作流技能 `query-mcp-workflow`，以及 `.ai-employee/query-mcp/`、`.ai-employee/requirements/` 等目录。
2. 显式绑定项目与会话
   不能只依赖“当前项目”文字推断，必须显式传 `project_id`，并在需要任务树连续性时显式传 `chat_session_id` 或调用 `bind_project_context(...)`。如果发现当前 `chat_session_id` 绑定的是旧任务树，应立刻切换到新的会话标识。
3. 读取项目上下文
   已明确项目时，优先读取项目手册 `get_manual_content(project_id=...)`。只有在缺少明确 `project_id`、`employee_id`、`rule_id` 或需要跨项目检索时，才额外调用 `search_ids(...)`。
4. 进入任务处理
   实现型需求优先走 `start_project_workflow(...)`。如果宿主暂时不能走固定入口，至少补齐 `analyze_task -> resolve_relevant_context -> generate_execution_plan`，再进入执行。
5. 本地优先推进
   先在当前仓库完成分析、改动、验证和 requirement 更新，再回写 MCP。canonical 状态文件统一落在：
   - `.ai-employee/query-mcp/active-sessions/<chat_session_id>.json`
   - `.ai-employee/query-mcp/active/<project_id>.json`
   - `.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json`
   - `.ai-employee/requirements/<project_id>/<chat_session_id>.json`
6. 任务树闭环
   开始节点前先 `get_current_task_tree`，执行中用 `update_task_node_status(...)`，完成时必须 `complete_task_node_with_verification(...)`。不能只在自然语言里口头说明“已完成”。
7. 长任务恢复与收尾
   长任务优先 `start_work_session`，随后复用同一组 `chat_session_id/session_id`，并用 `save_work_facts`、`append_session_event` 维护轨迹。中断恢复顺序固定为 `bind_project_context(...) -> resume_work_session(...) -> summarize_checkpoint(...)`，收尾时再按需补 `save_project_memory` 或 `build_delivery_report`。

一句话总结：统一查询 MCP 的核心是“显式绑定、本地优先、任务树闭环、验证收尾”。

## 技术栈

- 前端：Vue 3 + Element Plus + Vite
- 后端：FastAPI + FastMCP
- 存储：PostgreSQL / JSON / SQLite（按模块切换）
- 认证：JWT HS256

## 后端数据库配置

后端数据库配置现在分成两个清晰入口：

- 本地直跑后端：`web-admin/api/.env`
- Docker 编排：`docker/.env`

推荐规则：

- 应用内部优先使用 `DATABASE_URL`
- `DB_HOST`、`DB_PORT`、`DB_USER`、`DB_PASSWORD`、`DB_NAME` 只作为兼容回退
- 真实环境变量优先级高于 `.env` 文件
- 本地 API 会自动读取 `web-admin/api/.env` 和 `web-admin/api/.env.local`

### 1. 本地直跑后端

先准备配置文件：

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

当前版本统一使用平台模型与平台内工具能力，不再提供本地连接器或外部 Agent 运行链路。

### 2. Docker 启动整套服务

先准备 Docker 配置：

```bash
cp docker/.env.example docker/.env
```

`docker/.env` 只负责 Compose 级别的数据库参数和存储后端，例如：

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

### 本地开发

```bash
cd web-admin/frontend
npm install
npm run dev
```

前端开发服务器默认走代理，接口指向后端 `8000`。

### 生产方式启动 API

```bash
cd web-admin/api
uvicorn server:app --host 0.0.0.0 --port 8000
```

## 项目结构

```text
ai设计规范/
├── docs/
├── rules/
├── agents/
├── mcp-skills/
├── mcp-rules/
├── mcp-memory/
├── mcp-persona/
├── mcp-evolution/
├── mcp-sync/
├── docker/
└── web-admin/
    ├── api/
    └── frontend/
```

## 文档

- [项目总览](docs/00-项目总览/PROJECT.md)
- [Docker 使用说明](docker/README.md)
- [远程 Docker 发布工具](remote-docker-deploy/README.md)
- [编码规范](rules/)

## License

MIT
