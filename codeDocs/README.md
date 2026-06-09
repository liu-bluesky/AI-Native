# AI 员工工厂 - 代码文档

> 更新日期：2026-06-04
> 范围：按当前仓库现状更新 `codeDocs/` 下既有文档结构，不新增文档层级。

## 文档索引

| 文档 | 说明 |
|---|---|
| [directory-structure.md](./directory-structure.md) | 当前仓库目录、关键文件和模块边界 |
| [web-admin.md](./web-admin.md) | `web-admin` 后端 API、前端路由、运行时与数据层 |
| [mcp-services.md](./mcp-services.md) | 根目录 6 个独立 MCP 服务与 Web-Admin 动态 MCP |
| [deploy-and-config.md](./deploy-and-config.md) | Docker、本地配置、远程发布和规则/技能体系 |

## 项目定位

AI 员工工厂是一个 MCP-first 的 AI-Native 开发与管理平台。核心能力通过项目 MCP、统一查询 MCP、员工 MCP、技能 MCP、规则 MCP 等入口暴露给外部 Agent、IDE、CLI 和后台任务；`web-admin` 管理台负责配置、运营、观测、人工确认和可视化。

当前平台围绕以下对象组织能力：

- 项目：项目上下文、成员、规则、经验、素材、任务树和工作会话。
- 员工：AI 员工的人设、技能、规则、记忆、使用统计和协作能力。
- 技能：系统技能包、项目技能、员工技能和外部技能资源。
- 规则：项目规则、员工规则、反馈驱动规则升级和经验规则。
- 记忆：项目记忆、员工记忆、工作事实、会话事件和可恢复检查点。
- 运行时：统一查询 MCP、项目/员工动态 MCP、Agent Runtime v2、任务树和权限验证。

## 架构分层

```text
外部消费者
  Codex CLI / Claude Code / IDE / 飞书 / 其他 Agent
        |
        v
MCP 接入层
  /mcp/query
  /mcp/projects/{project_id}
  /mcp/employees/{employee_id}
  /mcp/skills/{skill_id}
  /mcp/rules/{rule_id}
        |
        v
Web-Admin API
  FastAPI 路由、业务服务、动态 MCP、任务树、Agent Runtime v2
        |
        v
数据与状态
  PostgreSQL / JSON store / SQLite MCP 知识库 / Redis / .ai-employee 本地状态
        |
        v
独立 MCP 服务与技能包
  mcp-skills / mcp-rules / mcp-memory / mcp-persona / mcp-evolution / mcp-sync
```

## 技术栈

| 层 | 当前技术 |
|---|---|
| 前端 | Vue 3、Vue Router 4、Element Plus、Vite 5、Axios、ECharts、Marked、xlsx |
| 后端 API | Python 3.10+、FastAPI、Pydantic、Uvicorn、PyJWT、psycopg、Redis、structlog |
| MCP 服务 | FastMCP，根目录独立服务使用 `mcp.server.fastmcp`，Web-Admin 内部使用动态 MCP proxy |
| 数据 | PostgreSQL 为主，JSON store 兼容，独立 MCP 服务保留 SQLite/文件知识库 |
| 部署 | `docker/` 下 Compose、API/Frontend Dockerfile、Nginx、远程离线/远程构建发布脚本 |
| 本地工作流状态 | `.ai-employee/query-mcp/` 与 `.ai-employee/requirements/<project_id>/` |

## 核心入口

### Web 管理台

- 后端入口：`web-admin/api/server.py`，实际创建逻辑在 `web-admin/api/core/server.py`。
- 前端入口：`web-admin/frontend/src/main.js`。
- 路由入口：`web-admin/frontend/src/router/index.js`。
- 本地后端启动脚本：`web-admin/api/scripts/start_api_with_runner.sh`。
- Docker 编排：`docker/docker-compose.yml`、`docker/compose.prod.yml`。

### MCP 入口

Web-Admin API 挂载的动态 MCP：

- `/mcp/query`
- `/mcp/projects/{project_id}`
- `/mcp/employees/{employee_id}`
- `/mcp/skills/{skill_id}`
- `/mcp/rules/{rule_id}`

根目录独立 MCP 服务：

- `mcp-skills`
- `mcp-rules`
- `mcp-memory`
- `mcp-persona`
- `mcp-evolution`
- `mcp-sync`

## 当前代码文档维护原则

- `codeDocs/` 描述当前代码库事实，不替代 `docs/` 下的产品/架构方案文档。
- 路径、文件名和命令以仓库当前文件为准。
- 对旧结构只在必要时说明历史背景，不把不存在的目录写成当前事实。
- 任务树、统一查询 MCP、Agent Runtime v2、远程部署等高频变动模块应优先从源码入口核对后再更新。
